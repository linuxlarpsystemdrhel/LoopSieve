import os
import sys
import tempfile
import unittest
from pathlib import Path

from loopsieve.diagnostics import diagnostic_identity
from loopsieve.models import CheckSpec
from loopsieve.runner import run_check


class RunnerLifecycleTests(unittest.TestCase):
    def test_missing_program_is_an_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            spec = CheckSpec("missing", (str(root / "missing-tool"),))
            self.assertEqual(run_check(spec, root, []).status, "ERROR")

    def test_timeout_drains_and_terminates(self):
        spec = CheckSpec(
            "timeout",
            (
                sys.executable,
                "-c",
                "import time; print('ready', flush=True); time.sleep(10)",
            ),
            timeout_seconds=1,
        )
        result = run_check(spec, Path.cwd(), [])
        self.assertTrue(result.timed_out)
        self.assertEqual(result.returncode, 124)
        self.assertIn("ready", result.output)
        self.assertLess(result.duration_seconds, 8)


@unittest.skipUnless(os.name == "posix", "POSIX child-process behavior")
class PosixLifecycleTests(unittest.TestCase):
    def test_return_when_a_descendant_holds_stdout(self):
        spec = CheckSpec(
            "child",
            (
                sys.executable,
                "-c",
                "import subprocess,sys; subprocess.Popen([sys.executable,'-c','import time; time.sleep(8)']); print('done')",
            ),
            timeout_seconds=4,
        )
        result = run_check(spec, Path.cwd(), [])
        self.assertEqual(result.returncode, 0)
        self.assertFalse(result.timed_out)
        self.assertIn("done", result.output)
        self.assertLess(result.duration_seconds, 3)

    def test_unexpected_exit_is_not_success(self):
        spec = CheckSpec(
            "abort",
            (
                sys.executable,
                "-c",
                "import os, signal; os.kill(os.getpid(), signal.SIGTERM)",
            ),
        )
        self.assertEqual(run_check(spec, Path.cwd(), []).returncode, -15)

    def test_diagnostics_use_exact_location_for_outside_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            root = parent / "repo"
            root.mkdir()
            outside = parent / "private.py"
            outside.write_text("secret = 1\n", encoding="utf-8")
            (root / "linked.py").symlink_to(outside)
            _, records = diagnostic_identity(
                "linked.py:1: error: fixture", root, "test", "1"
            )
            self.assertEqual(records[0]["match_level"], "exact-location")
            self.assertEqual(records[0]["location"]["line"], 1)


@unittest.skipUnless(sys.platform == "linux", "Linux address-space limits")
class MemoryFailureTests(unittest.TestCase):
    def test_memory_allocation_failure_remains_failed(self):
        spec = CheckSpec(
            "memory",
            (
                sys.executable,
                "-c",
                "import resource; limit=96*1024**2; resource.setrlimit(resource.RLIMIT_AS,(limit,limit)); bytearray(128*1024**2)",
            ),
        )
        result = run_check(spec, Path.cwd(), [])
        self.assertEqual(result.returncode, 1)
        self.assertIn("MemoryError", result.output)
