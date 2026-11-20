import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from loopsieve.huggingface import HuggingFaceClient
from loopsieve.local_llm import (
    LocalInferenceError,
    LocalModelConfig,
    diagnostic_evidence,
    explain,
    load_local_config,
)
from loopsieve.models import CheckResult, CheckSpec, VerificationRun
from loopsieve.providers import CompatibleProvider, OllamaProvider
from loopsieve.tui import data_rows
from tools import run_local_model


class LocalConfigTests(unittest.TestCase):
    def test_explicit_model_and_optional_override(self):
        with self.assertRaisesRegex(ValueError, "--llm-config"):
            load_local_config()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "local.json"
            path.write_text(
                '{"model": "fixture", "endpoint": "http://[::1]:8123", "max_tokens": 24}'
            )
            self.assertEqual(load_local_config(path).model, "fixture")
            self.assertEqual(load_local_config(path).max_tokens, 24)

    def test_reject_invalid_configurations(self):
        invalid = [
            b"",
            b"{",
            b"[]",
            b"\xff",
            b'{"unknown":4}',
            b'{"max_tokens":true}',
            b'{"timeout_seconds":NaN}',
            b'{"seed":-1}',
            b'{"model":" "}',
            b'{"endpoint":"http://localhost:8080"}',
            b'{"endpoint":"http://example.invalid"}',
            b'{"endpoint":"http://x@127.0.0.1"}',
            b'{"endpoint":"http://127.0.0.1/cloud"}',
            b'{"endpoint":"http://127.0.0.1:65536"}',
            b'{"endpoint":"https://127.0.0.1"}',
            b" " * 16385,
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "local.json"
            for contents in invalid:
                with self.subTest(contents=contents[:80]):
                    path.write_bytes(contents)
                    with self.assertRaisesRegex(
                        ValueError, "invalid local model configuration"
                    ):
                        load_local_config(path)
            with self.assertRaises(ValueError):
                load_local_config(path.with_name("missing.json"))

    def test_repeat_preserves_diagnostic_and_omits_argv(self):
        spec = CheckSpec("compile", ("tool", "private-token"))
        result = CheckResult(
            spec,
            1,
            30,
            "IndexError: index out of range",
            list(spec.command),
            status="FAIL",
        )
        first = VerificationRun(Path("."), [], [result])
        again = replace(first, repeated=True, context="unchanged diagnostics")
        evidence = diagnostic_evidence(again, 36)
        self.assertEqual(evidence, diagnostic_evidence(first, 36))
        self.assertIn("IndexError", evidence)
        self.assertNotIn("private-token", evidence)

    def test_empty_inference_input_fails_before_connecting(self):
        with self.assertRaisesRegex(ValueError, "empty"):
            explain(" \t\n", LocalModelConfig(model="fixture"))

    def test_capabilities_panel_resolves_registry(self):
        headers, rows = data_rows("Capabilities", Path.cwd())
        self.assertEqual(headers[:2], ["Kind", "Capability"])
        self.assertTrue(rows)


class LocalModelLauncherTests(unittest.TestCase):
    def test_missing_untrusted_and_matching_weights(self):
        data = b"known fixture, not a model"
        digest = hashlib.sha256(data).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.gguf"
            with self.assertRaisesRegex(ValueError, "existing nonempty"):
                run_local_model.checked_weights(path)
            path.write_bytes(b"A" * len(data))
            with self.assertRaisesRegex(ValueError, "hexadecimal"):
                run_local_model.checked_weights(path, "bad")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                run_local_model.checked_weights(path, digest)
            path.write_bytes(data)
            self.assertEqual(
                run_local_model.checked_weights(path, digest), path.resolve()
            )
            self.assertEqual(run_local_model.checked_weights(path), path.resolve())

    def test_backend_selection_and_missing_launcher(self):
        with patch.object(run_local_model.subprocess, "run") as run:
            self.assertEqual(run_local_model.find_device("llama-server", "cpu"), "none")
            run.assert_not_called()
            run.return_value.stdout = "Available devices:\n  (none)\n"
            run.return_value.stderr = ""
            self.assertEqual(
                run_local_model.find_device("llama-server", "auto"), "none"
            )
            with self.assertRaisesRegex(ValueError, "no CUDA device"):
                run_local_model.find_device("llama-server", "cuda")
            run.return_value.stdout = "Available devices:\n  CUDA0: test device\n"
            self.assertEqual(
                run_local_model.find_device("llama-server", "auto"), "CUDA0"
            )
        with subprocess.Popen(
            [
                sys.executable,
                "-m",
                "tools.run_local_model",
                "--server",
                "./missing-llama-server",
                "--weights",
                "fixture.gguf",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ) as proc:
            _, stderr = proc.communicate(timeout=10)
            self.assertEqual(proc.returncode, 2)
            self.assertIn("llama-server is unavailable", stderr)


def event(data):
    return b"data: " + json.dumps(data).encode() + b"\n\n"


CHUNKS = [
    event({"choices": [{"delta": {"role": "assistant"}}]}),
    event({"choices": [{"delta": {"content": "Cause: division by zero.\n"}}]}),
    event(
        {
            "choices": [
                {
                    "delta": {"content": "Next: guard the denominator."},
                    "finish_reason": "stop",
                }
            ]
        }
    ),
    event(
        {
            "usage": {"prompt_tokens": 47, "completion_tokens": 13},
            "timings": {"cache_n": 46, "prompt_ms": 2, "predicted_per_second": 39.5},
            "choices": [],
        }
    ),
    b"data: [DONE]\n\n",
]


class LocalTransportTests(unittest.TestCase):
    def setUp(self):
        test = self
        self.received = []
        self.status = 200
        self.chunks = CHUNKS
        self.delay = 0

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                test.received.append((self.path, {}))
                self.send_response(test.status)
                self.send_header("Location", "/unexpected-redirect")
                self.end_headers()

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                test.received.append((self.path, body))
                self.send_response(test.status)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Location", "/unexpected-redirect")
                self.end_headers()
                time.sleep(test.delay)
                try:
                    for chunk in test.chunks:
                        self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.05}
        )
        self.thread.start()
        self.addCleanup(self.close_server)
        self.config = replace(
            LocalModelConfig(model="fixture"),
            endpoint=f"http://127.0.0.1:{self.server.server_port}",
        )

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_stream_metrics_repeatability_and_proxy_independence(self):
        with patch.dict(
            os.environ, {"HTTP_PROXY": "http://127.0.0.1:1", "NO_PROXY": ""}
        ):
            first = explain(
                "ZeroDivisionError: division by zero", self.config, cache_prompt=False
            )
            again = explain(
                "ZeroDivisionError: division by zero", self.config, cache_prompt=True
            )
        self.assertEqual(first.text, again.text)
        self.assertLessEqual(first.first_token_ms, first.latency_ms)
        self.assertEqual(first.prompt_tokens, 47)
        self.assertEqual(again.cached_tokens, 46)
        self.assertEqual(first.decode_tokens_per_second, 39.5)
        first_path, first_body = self.received[0]
        self.assertEqual(first_path, "/v1/chat/completions")
        self.assertFalse(first_body["cache_prompt"])
        self.assertEqual(self.received[1][1], first_body | {"cache_prompt": True})

    def test_error_status_and_redirect_do_not_retry(self):
        for code in (302, 404, 503, 507):
            with self.subTest(code=code):
                self.status = code
                calls = len(self.received)
                with self.assertRaisesRegex(LocalInferenceError, f"HTTP {code}"):
                    explain("diagnostics", self.config)
                self.assertEqual(len(self.received), calls + 1)

    def test_timeout_and_no_loopback_ollama_redirect(self):
        self.delay = 0.2
        with self.assertRaisesRegex(LocalInferenceError, "timed out"):
            explain("diagnostics", replace(self.config, timeout_seconds=0.05))
        self.status = 302
        endpoint = f"{self.config.endpoint}/api/chat"
        with patch.dict(
            os.environ, {"http_proxy": "http://127.0.0.1:1", "no_proxy": ""}
        ):
            result = OllamaProvider("fixture", endpoint).probe()
        self.assertEqual(result["state"], "SERVER_UNAVAILABLE")
        self.assertEqual(self.received[-1], ("/api/tags", {}))
        self.assertNotIn("/unexpected-redirect", [path for path, _ in self.received])

    def test_api_credentials_are_not_copied_to_redirects(self):
        collected = []

        class RedirectHandler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                collected.append((self.path, self.headers.get("Authorization")))
                if self.path in ("/hf-target", "/compatible-target"):
                    self.send_response(200)
                    self.end_headers()
                    body = b"[]" if self.path == "/hf-target" else b'{"data":[]}'
                    self.wfile.write(body)
                else:
                    self.send_response(302)
                    target = (
                        "/hf-target"
                        if self.path.startswith("/api/")
                        else "/compatible-target"
                    )
                    self.send_header("Location", target)
                    self.end_headers()

        with ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler) as server:
            worker = threading.Thread(
                target=server.serve_forever, kwargs={"poll_interval": 0.05}
            )
            worker.start()
            try:
                origin = f"http://127.0.0.1:{server.server_port}"
                HuggingFaceClient(base_url=origin, token="hf-fixture").search()
                provider = CompatibleProvider("fixture", origin, api_key="api-fixture")
                self.assertEqual(provider.probe()["state"], "READY")
            finally:
                server.shutdown()
                worker.join()
        self.assertEqual(
            [key for _, key in collected],
            ["Bearer hf-fixture", None, "Bearer api-fixture", None],
        )

    def test_large_multibyte_input_is_bounded(self):
        explain("症" * 5000, self.config)
        payload = self.received[0][1]["messages"][1]["content"]
        self.assertLessEqual(len(payload.encode()), 6421)
        self.assertIn("omitted", payload)

    def test_malformed_truncated_empty_and_oversized_stream(self):
        for chunks in (
            [b"data: xxx\n"],
            CHUNKS[:2],
            CHUNKS[-1:],
            [b"data: " + b"a" * 65536],
            [event({"error": {"message": "memory allocation failed"}})],
        ):
            with self.subTest(chunk_count=len(chunks)):
                self.chunks = chunks
                with self.assertRaises(LocalInferenceError):
                    explain("diagnostics", self.config)

    def test_terminal_controls_are_removed(self):
        self.chunks = [
            event(
                {
                    "choices": [
                        {"delta": {"content": "Cause: \x1b]0;injected\x07unsafe\u202e"}}
                    ]
                }
            ),
            CHUNKS[-1],
        ]
        result = explain("diagnostics", self.config)
        self.assertNotIn("\x1b", result.text)
        self.assertNotIn("\x07", result.text)
        self.assertNotIn("\u202e", result.text)

    def test_cli_integration_preserves_verification_outcome(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "llm.json"
            config.write_text(
                json.dumps(
                    {"model": self.config.model, "endpoint": self.config.endpoint}
                ),
                encoding="utf-8",
            )
            check = root / ".loopsieve.json"
            environment = os.environ | {
                "LOOPSIEVE_STATE_DIR": str(root / "state"),
                "CLAUDE_PLUGIN_DATA": "",
            }
            cli = [
                sys.executable,
                "-m",
                "loopsieve",
                "check",
                "--root",
                directory,
                "--explain",
                "--llm-config",
                str(config),
                "source.py",
            ]
            for exit_code, http_status in ((0, 200), (1, 200), (1, 503)):
                check.write_text(
                    json.dumps(
                        {
                            "checks": [
                                {
                                    "name": "test",
                                    "command": [
                                        "{python}",
                                        "-c",
                                        f"print('ZeroDivisionError: division by zero'); raise SystemExit({exit_code})",
                                    ],
                                }
                            ]
                        }
                    ),
                    encoding="utf-8",
                )
                self.status = http_status
                before = len(self.received)
                result = subprocess.run(
                    cli, capture_output=True, text=True, env=environment, timeout=15
                )
                self.assertEqual(result.returncode, exit_code, result.stderr)
                self.assertEqual(len(self.received) - before, exit_code)
                if exit_code and http_status == 200:
                    self.assertIn("Local model suggestion (unverified)", result.stdout)
                if http_status == 503:
                    self.assertIn("explanation unavailable", result.stderr)
