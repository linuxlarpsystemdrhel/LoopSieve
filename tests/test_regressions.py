"""Adversarial cases for the two original critical bugs."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

from loopsieve.config import Config
from loopsieve.diagnostics import diagnostic_identity
from loopsieve.engine import verify
from loopsieve.models import CheckSpec
from loopsieve.runner import BoundedStream


class VerificationRegression(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.main = self.root / 'main.py'
        self.flag = self.root / 'dependency.flag'
        self.main.write_text('value = 1\n', encoding='utf-8')
        self.flag.write_text('ok', encoding='utf-8')
        self.check = CheckSpec(
            name='dependency check', kinds=('python',),
            command=('{python}', '-c', "from pathlib import Path; import sys; sys.exit(0 if Path('dependency.flag').read_text()=='ok' else 7)"),
            inputs=('main.py', 'dependency.flag'), complete_inputs=True, deterministic=True)
        self.cfg = Config(checks=(self.check,), state_dir=str(self.root / 'state'))

    def test_changed_dependency_invalidates_previous_success(self):
        self.assertEqual(verify(self.root, [self.main], self.cfg).results[0].status, 'PASS')
        self.assertEqual(verify(self.root, [self.main], self.cfg).results[0].status, 'SKIPPED_VALID_CACHE')
        self.flag.write_text('broken', encoding='utf-8')
        result = verify(self.root, [self.main], self.cfg)
        self.assertEqual(result.results[0].status, 'FAIL')
        self.assertFalse(result.passed)

    def test_changed_main_invalidates_cache(self):
        verify(self.root, [self.main], self.cfg)
        self.main.write_text('value = 2\n', encoding='utf-8')
        self.assertEqual(verify(self.root, [self.main], self.cfg).results[0].status, 'PASS')

    def test_failed_result_is_never_cached_as_pass(self):
        self.flag.write_text('broken', encoding='utf-8')
        self.assertEqual(verify(self.root, [self.main], self.cfg).results[0].status, 'FAIL')
        result = verify(self.root, [self.main], self.cfg)
        self.assertEqual(result.results[0].status, 'FAIL')
        self.assertFalse(result.passed)

    def test_deleted_dependency_disables_cache(self):
        verify(self.root, [self.main], self.cfg)
        self.flag.unlink()
        result = verify(self.root, [self.main], self.cfg)
        self.assertNotEqual(result.results[0].status, 'SKIPPED_VALID_CACHE')

    def test_unknown_dependencies_are_not_cached(self):
        incomplete = CheckSpec('unbounded', ('{python}', '-c', 'print(1)'), kinds=('python',))
        cfg = Config(checks=(incomplete,), state_dir=str(self.root / 'state2'))
        self.assertEqual(verify(self.root, [self.main], cfg).results[0].status, 'PASS')
        self.assertEqual(verify(self.root, [self.main], cfg).results[0].status, 'PASS')

    def test_command_arguments_invalidate_cache(self):
        verify(self.root, [self.main], self.cfg)
        check = CheckSpec(**{**self.check.__dict__, 'command': ('{python}', '-c', "print('now different')")})
        cfg = Config(checks=(check,), state_dir=str(self.root / 'state'))
        self.assertEqual(verify(self.root, [self.main], cfg).results[0].status, 'PASS')

    def test_config_change_invalidates_cache(self):
        (self.root / '.loopsieve.json').write_text('a', encoding='utf-8')
        verify(self.root, [self.main], self.cfg)
        (self.root / '.loopsieve.json').write_text('b', encoding='utf-8')
        self.assertEqual(verify(self.root, [self.main], self.cfg).results[0].status, 'PASS')

    def test_lock_change_invalidates_cache(self):
        lock = self.root / 'package-lock.json'
        lock.write_text('{}', encoding='utf-8')
        verify(self.root, [self.main], self.cfg)
        lock.write_text('{"different":true}', encoding='utf-8')
        self.assertEqual(verify(self.root, [self.main], self.cfg).results[0].status, 'PASS')

    def test_bounded_stream_never_retains_giant_output(self):
        stream = BoundedStream(1000)
        for _ in range(1000): stream.feed(b'x'*10000)
        self.assertLess(len(stream.head)+len(stream.tail), 1100)
        self.assertIn('omitted', stream.render())


class DiagnosticRegression(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'module.py'

    def fp(self, msg):
        return diagnostic_identity(msg, self.root, 'pytest', '1')[0]

    def test_different_line_without_anchor_not_suppressed(self):
        self.assertNotEqual(self.fp('module.py:12:3: error: invalid syntax'), self.fp('module.py:99:3: error: invalid syntax'))

    def test_different_file_not_suppressed(self):
        self.assertNotEqual(self.fp('module.py:5:2: error: invalid syntax'), self.fp('other.py:5:2: error: invalid syntax'))

    def test_same_error_exact_location_suppressed(self):
        self.assertEqual(self.fp('module.py:5:2: error: invalid syntax'), self.fp('module.py:5:2: error: invalid syntax'))

    def test_identical_text_in_different_functions_not_suppressed(self):
        self.source.write_text('def a():\n    raise ValueError(1)\n\ndef b():\n    raise ValueError(1)\n')
        self.assertNotEqual(self.fp('module.py:2:3: error: bad'), self.fp('module.py:5:3: error: bad'))

    def test_line_shift_same_symbol_and_source_remains_same(self):
        self.source.write_text('def a():\n    raise ValueError(1)\n')
        original = self.fp('module.py:2:3: error: bad')
        self.source.write_text('\n\ndef a():\n    raise ValueError(1)\n')
        self.assertEqual(original, self.fp('module.py:4:3: error: bad'))

    def test_source_rewrite_invalidates_identity(self):
        self.source.write_text('def a():\n    raise ValueError(1)\n')
        original = self.fp('module.py:2:3: error: bad')
        self.source.write_text('def a():\n    raise ValueError(2)\n')
        self.assertNotEqual(original, self.fp('module.py:2:3: error: bad'))

    def test_multiple_diagnostics_preserve_multiplicity(self):
        one = 'module.py:2:3: error: bad'
        self.assertNotEqual(self.fp(one), self.fp(one+'\n'+one))

    def test_severity_changes_identity(self):
        self.assertNotEqual(self.fp('module.py:2:3: error: bad'), self.fp('module.py:2:3: warning: bad'))

    def test_unknown_location_conservative(self):
        self.assertNotEqual(self.fp('error in unknown pass #1'), self.fp('error in unknown pass #2'))


if __name__ == '__main__': unittest.main()
