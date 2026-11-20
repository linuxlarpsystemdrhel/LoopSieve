"""Regression coverage for the CLI's verification and state boundaries."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from loopsieve.config import Config, load_config
from loopsieve.diagnostics import diagnostic_identity, summarize_failure
from loopsieve.engine import state_report, verify
from loopsieve.hook import run_hook
from loopsieve.models import CheckResult, CheckSpec
from loopsieve.runner import BoundedStream, expand_command
from loopsieve.state import project_state_path


class VerificationReliabilityTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.source = self.root / "source.py"
        self.source.write_text("value = 1\n", encoding="utf-8")
        self.spec = CheckSpec("fixture", ("{python}", "-c", "print('fixture ran')"))
        self.config = Config((self.spec,), state_dir=str(self.root / "state"))

    def write_config(self, data):
        (self.root / ".loopsieve.json").write_text(json.dumps(data), encoding="utf-8")

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "loopsieve", *args],
            capture_output=True,
            text=True,
            timeout=20,
        )

    def test_parallel_cli_runs_preserve_all_counters(self):
        workers = 12
        barrier = self.root / "barrier"
        barrier.mkdir()
        command = (
            "import os, time; from pathlib import Path\n"
            "barrier = Path('barrier')\n"
            "(barrier / str(os.getpid())).touch()\n"
            "deadline = time.monotonic() + 10\n"
            f"while len(list(barrier.iterdir())) < {workers}:\n"
            "    if time.monotonic() > deadline: raise SystemExit(3)\n"
            "    time.sleep(0.02)\n"
        )
        self.write_config(
            {
                "state_dir": self.config.state_dir,
                "checks": [
                    {"name": "parallel", "command": ["{python}", "-c", command]}
                ],
            }
        )
        args = ("check", "--root", str(self.root), str(self.source))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(lambda _: self.cli(*args), range(workers)))
        self.assertEqual([proc.returncode for proc in results], [0] * workers)
        self.assertEqual([proc.stderr for proc in results], [""] * workers)
        stats = state_report(self.root, self.config)["stats"]
        self.assertEqual(stats["runs"], workers)
        self.assertEqual(stats["passed_runs"], workers)

    def test_owner_process_exit_releases_state_lock(self):
        path = project_state_path(self.root, self.config.state_dir)
        script = (
            "import os, sys; from pathlib import Path\n"
            "from loopsieve.state import state_write_lock\n"
            "with state_write_lock(Path(sys.argv[1])):\n"
            "    os._exit(0)\n"
        )
        subprocess.run(
            [sys.executable, "-c", script, str(path)], check=True, timeout=10
        )
        result = verify(self.root, [self.source], self.config)
        self.assertTrue(result.passed)
        self.assertIsNone(result.state_warning)

    def test_existing_state_with_invalid_counters_recovers(self):
        path = project_state_path(self.root, self.config.state_dir)
        path.parent.mkdir(parents=True)
        path.write_text(
            '{"stats":{"runs":"7","failed_runs":[],"raw_diagnostic_chars":"x"}}',
            encoding="utf-8",
        )
        self.assertEqual(state_report(self.root, self.config)["stats"], {"runs": 7})
        self.assertTrue(verify(self.root, [self.source], self.config).passed)
        self.assertEqual(state_report(self.root, self.config)["stats"]["runs"], 8)
        path.write_bytes(b"\xff")
        self.assertTrue(verify(self.root, [self.source], self.config).passed)
        self.assertEqual(state_report(self.root, self.config)["stats"]["runs"], 1)

    def test_unwritable_state_preserves_cli_failure_diagnostic(self):
        invalid = self.root / "not-a-directory"
        invalid.touch()
        self.write_config(
            {
                "state_dir": str(invalid),
                "checks": [
                    {
                        "command": [
                            "{python}",
                            "-c",
                            "print('real failure'); raise SystemExit(7)",
                        ]
                    }
                ],
            }
        )
        result = self.cli("check", "--root", str(self.root), str(self.source))
        self.assertEqual(result.returncode, 1)
        self.assertIn("real failure", result.stdout)
        self.assertIn("could not save verification state", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_invalid_config_is_rejected_by_check_and_report(self):
        self.write_config({"checks": [False, self.spec.as_dict()]})
        for args in (
            ("check", "--root", str(self.root), str(self.source)),
            ("report", "--root", str(self.root)),
        ):
            with self.subTest(command=args[0]):
                result = self.cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertIn("checks[0]", result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_check_fields_validate_without_unsafe_coercion(self):
        for field, value in (
            ("enabled", "false"),
            ("inputs", "source.py"),
            ("env_keys", [42]),
            ("max_output_chars", 0),
            ("timeout_seconds", True),
            ("cwd", []),
        ):
            with self.subTest(field=field):
                self.write_config({"checks": [self.spec.as_dict() | {field: value}]})
                with self.assertRaisesRegex(ValueError, field):
                    load_config(self.root)
        self.write_config({"checks": [self.spec.as_dict(), self.spec.as_dict()]})
        with self.assertRaisesRegex(ValueError, "duplicates the check name"):
            load_config(self.root)

    def test_changed_input_during_execution_does_not_create_cache_hit(self):
        flag = self.root / "flag"
        flag.write_text("before", encoding="utf-8")
        spec = CheckSpec(
            "mutating",
            (
                "{python}",
                "-c",
                "from pathlib import Path; Path('flag').write_text('after')",
            ),
            inputs=("flag",),
            complete_inputs=True,
            deterministic=True,
        )
        config = Config((spec,), state_dir=self.config.state_dir)
        self.assertTrue(verify(self.root, [self.source], config).passed)
        decisions = state_report(self.root, config)["verification_decisions"]
        self.assertIn("during execution", decisions[0]["reason"])
        flag.write_text("before", encoding="utf-8")
        result = verify(self.root, [self.source], config)
        self.assertEqual(result.results[0].status, "PASS")
        self.assertEqual(flag.read_text(encoding="utf-8"), "after")

    @unittest.skipUnless(os.name == "posix", "POSIX cwd-relative executable resolution")
    def test_relative_executable_is_fingerprinted_in_check_cwd(self):
        tools = self.root / "bin"
        tools.mkdir()
        program = tools / "fixture"
        program.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        program.chmod(0o700)
        spec = CheckSpec(
            "relative executable",
            ("./fixture",),
            cwd="bin",
            inputs=("source.py",),
            complete_inputs=True,
            deterministic=True,
        )
        config = Config((spec,), state_dir=self.config.state_dir)
        self.assertTrue(verify(self.root, [self.source], config).passed)
        self.assertEqual(
            verify(self.root, [self.source], config).results[0].status,
            "SKIPPED_VALID_CACHE",
        )
        program.write_text("#!/bin/sh\nexit 8\n", encoding="utf-8")
        self.assertEqual(
            verify(self.root, [self.source], config).results[0].returncode, 8
        )

    def test_hook_tolerates_non_string_tool_names(self):
        payload = {
            "cwd": str(self.root),
            "tool_calls": [{"tool_name": []}, {"tool_name": {"kind": "Edit"}}],
        }
        self.assertEqual(run_hook(payload), {})

    def test_location_identity_preserves_column_and_unparsed_path_prefix(self):
        first, _ = diagnostic_identity(
            "source.py:1:2: error: broken", self.root, "tool", "FAIL"
        )
        second, _ = diagnostic_identity(
            "source.py:1:5: error: broken", self.root, "tool", "FAIL"
        )
        self.assertNotEqual(first, second)
        first, _ = diagnostic_identity(
            "left dir/source.py:1:2: error: broken", self.root, "tool", "FAIL"
        )
        second, _ = diagnostic_identity(
            "right dir/source.py:1:2: error: broken", self.root, "tool", "FAIL"
        )
        self.assertNotEqual(first, second)

    def test_summaries_keep_short_traceback_and_long_terminal_failure(self):
        short = "Traceback (most recent call last):\n    total / count\nZeroDivisionError: division by zero"
        result = CheckResult(self.spec, 1, 0, short, [])
        self.assertEqual(summarize_failure(result, 4), short)
        result.output = "\n".join(
            ["warning: early detail"] * 80 + ["RuntimeError: terminal cause"]
        )
        self.assertIn("RuntimeError: terminal cause", summarize_failure(result, 4))

    def test_odd_output_budget_and_filename_starting_with_hyphen(self):
        message = "a" * 198 + "ñ!"
        capture = BoundedStream(201)
        capture.feed(message.encode())
        self.assertEqual(capture.render(), message)
        spec = CheckSpec("filename", ("tool", "{files}"))
        command, _ = expand_command(spec, self.root, [self.root / "-source.py"])
        self.assertEqual(command[1], os.curdir + os.sep + "-source.py")
