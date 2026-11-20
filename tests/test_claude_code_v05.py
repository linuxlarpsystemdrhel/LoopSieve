import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from loopsieve.claude_code import hook_payload_example, install, status, uninstall
from loopsieve.hook import extract_changed_files


class ClaudeCodeV05Tests(unittest.TestCase):
    def test_install_status_uninstall(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / '.claude').mkdir()
            (root / '.claude' / 'settings.json').write_text(json.dumps({'permissions': {'allow': ['Read']}}))
            with mock.patch('loopsieve.install.shutil.which', return_value='/usr/local/bin/loopsieve'):
                installed = install(root)
                self.assertEqual(installed['status'], 'INSTALLED')
                current = status(root)
                self.assertEqual(current['claude_code']['status'], 'READY')
                self.assertTrue(current['claude_code']['hook_installed'])
                removed = uninstall(root)
                self.assertEqual(removed['status'], 'REMOVED')
                self.assertEqual(status(root)['claude_code']['status'], 'NOT_INSTALLED')

    def test_post_tool_use_payload_is_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = {'hook_event_name': 'PostToolUse', 'tool_name': 'Edit',
                       'tool_input': {'file_path': str(root / 'a.py')}}
            self.assertEqual(extract_changed_files(payload, root), [root / 'a.py'])
            self.assertEqual(hook_payload_example()['hook_event_name'], 'PostToolBatch')


if __name__ == '__main__':
    unittest.main()
