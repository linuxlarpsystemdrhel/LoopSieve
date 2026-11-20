from pathlib import Path
import json
import tempfile
import unittest
from unittest import mock

from loopsieve.install import install_hook, uninstall_hook


class InstallTests(unittest.TestCase):
    def test_install_and_remove_preserves_existing_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / ".claude" / "settings.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"permissions": {"allow": ["Read"]}}), encoding="utf-8")
            with mock.patch("loopsieve.install.shutil.which", return_value="/usr/local/bin/loopsieve"):
                install_hook(root)
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(data["permissions"]["allow"], ["Read"])
                self.assertEqual(len(data["hooks"]["PostToolBatch"]), 1)
                install_hook(root)
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(len(data["hooks"]["PostToolBatch"]), 1)
                uninstall_hook(root)
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertNotIn("PostToolBatch", data.get("hooks", {}))


if __name__ == "__main__":
    unittest.main()
