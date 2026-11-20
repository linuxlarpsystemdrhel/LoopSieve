from pathlib import Path
import sys
import tempfile
import unittest

from loopsieve.config import Config
from loopsieve.engine import verify
from loopsieve.models import CheckSpec


class EngineTests(unittest.TestCase):
    def test_repeated_failure_is_suppressed_after_new_edit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            changed = root / "demo.py"
            changed.write_text("x = 1\n", encoding="utf-8")
            check = CheckSpec(
                name="always fails",
                command=("{python}", "-c", "import sys; print('demo.py:12:3: error: boom'); sys.exit(1)"),
                kinds=("python",),
            )
            config = Config(checks=(check,), state_dir=str(root / "state"))
            first = verify(root, [changed], config)
            self.assertFalse(first.repeated)
            self.assertIn("error: boom", first.context)

            changed.write_text("x = 2\n", encoding="utf-8")
            second = verify(root, [changed], config)
            self.assertTrue(second.repeated)
            self.assertIn("unchanged", second.context)
            self.assertNotIn("demo.py:12:3", second.context)

    def test_success_context_is_short(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            changed = root / "demo.py"
            changed.write_text("x = 1\n", encoding="utf-8")
            check = CheckSpec(name="pass", command=("{python}", "-c", "print('ok')"), kinds=("python",))
            config = Config(checks=(check,), state_dir=str(root / "state"))
            result = verify(root, [changed], config)
            self.assertTrue(result.passed)
            self.assertIn("passed 1 check", result.context)


if __name__ == "__main__":
    unittest.main()
