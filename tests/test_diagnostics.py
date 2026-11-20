from pathlib import Path
import unittest

from loopsieve.diagnostics import normalize_for_fingerprint, summarize_failure
from loopsieve.models import CheckResult, CheckSpec


class DiagnosticsTests(unittest.TestCase):
    def test_normalization_retains_distinct_locations(self):
        root = Path("/tmp/example")
        a = "/tmp/example/src/app.py:12:4: error: bad value in 0xabc after 1.23s"
        b = "/tmp/example/src/app.py:99:8: error: bad value in 0xdef after 9.99s"
        self.assertNotEqual(normalize_for_fingerprint(a, root), normalize_for_fingerprint(b, root))

    def test_summary_keeps_error_neighborhood(self):
        spec = CheckSpec(name="x", command=("x",))
        result = CheckResult(spec=spec, returncode=1, duration_seconds=0.1, output="noise\ncontext\nERROR broken\nmore\ntail", command=["x"])
        summary = summarize_failure(result, 4)
        self.assertIn("ERROR broken", summary)
        self.assertIn("context", summary)


if __name__ == "__main__":
    unittest.main()
