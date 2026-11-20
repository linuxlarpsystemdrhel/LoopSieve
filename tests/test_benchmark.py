from pathlib import Path
import tempfile
import json
import unittest

from loopsieve.benchmark import run_fixture


class BenchmarkTests(unittest.TestCase):
    def test_fixture_suppresses_repeated_normalized_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "fixture.json"
            fixture.write_text(json.dumps({"outputs": [
                "src/a.py:10:2: error: failed after 1.0s\n" + "detail\n" * 200,
                "src/a.py:99:7: error: failed after 9.0s\n" + "detail\n" * 200,
            ]}), encoding="utf-8")
            result = run_fixture(fixture)
            self.assertEqual(result.repeated_failures, 0)  # distinct lines cannot be safely collapsed
            self.assertEqual(result.loopsieve_chars, result.raw_chars)


    def test_stable_repetitions_are_reduced_without_erasing_locations(self):
        fixture = Path(__file__).resolve().parents[1] / 'benchmarks' / 'fixtures' / 'stable-repeat.json'
        result=run_fixture(fixture)
        self.assertEqual(result.repeated_failures,7)
        self.assertGreater(result.reduction_ratio,0.80)

    def test_adversarial_locations_are_all_retained(self):
        fixture = Path(__file__).resolve().parents[1] / 'benchmarks' / 'fixtures' / 'adversarial-identity.json'
        result=run_fixture(fixture)
        self.assertEqual(result.repeated_failures,0)
        self.assertEqual(result.raw_chars,result.loopsieve_chars)


if __name__ == "__main__":
    unittest.main()
