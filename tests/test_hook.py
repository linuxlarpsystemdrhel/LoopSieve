from pathlib import Path
import unittest

from loopsieve.hook import build_hook_response, extract_changed_files


class HookTests(unittest.TestCase):
    def test_extracts_only_edit_paths(self):
        root = Path("/tmp/project")
        payload = {
            "tool_calls": [
                {"tool_name": "Read", "tool_input": {"file_path": "a.py"}},
                {"tool_name": "Edit", "tool_input": {"file_path": "src/a.py"}},
                {"tool_name": "Write", "tool_input": {"file_path": "src/b.py"}},
            ]
        }
        files = extract_changed_files(payload, root)
        self.assertEqual(files, [root / "src/a.py", root / "src/b.py"])

    def test_builds_post_tool_batch_output(self):
        value = build_hook_response("hello")
        self.assertEqual(value["hookSpecificOutput"]["hookEventName"], "PostToolBatch")
        self.assertEqual(value["hookSpecificOutput"]["additionalContext"], "hello")


if __name__ == "__main__":
    unittest.main()
