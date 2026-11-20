from pathlib import Path
import json
import tempfile
import unittest

from loopsieve.hook import run_hook


class HookIntegrationTests(unittest.TestCase):
    def test_hook_emits_full_then_deduplicated_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "demo.py"
            source.write_text("x = 1\n", encoding="utf-8")
            config = {
                "version": 1,
                "state_dir": str(root / "state"),
                "checks": [
                    {
                        "name": "fixture failure",
                        "command": [
                            "{python}",
                            "-c",
                            "import sys; print('demo.py:12:3: error: boom'); sys.exit(1)"
                        ],
                        "kinds": ["python"]
                    }
                ]
            }
            (root / ".loopsieve.json").write_text(json.dumps(config), encoding="utf-8")
            payload = {
                "cwd": str(root),
                "hook_event_name": "PostToolBatch",
                "tool_calls": [
                    {
                        "tool_name": "Edit",
                        "tool_input": {"file_path": str(source)},
                        "tool_use_id": "test",
                        "tool_response": "ok"
                    }
                ]
            }
            first = run_hook(payload)["hookSpecificOutput"]["additionalContext"]
            self.assertIn("error: boom", first)

            source.write_text("x = 2\n", encoding="utf-8")
            second = run_hook(payload)["hookSpecificOutput"]["additionalContext"]
            self.assertIn("unchanged", second)
            self.assertNotIn("demo.py:12:3", second)


if __name__ == "__main__":
    unittest.main()
