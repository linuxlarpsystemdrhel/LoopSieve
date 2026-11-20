from pathlib import Path
import unittest

from loopsieve.models import CheckSpec
from loopsieve.planner import select_checks


class PlannerTests(unittest.TestCase):
    def test_selects_only_relevant_checks(self):
        checks = (
            CheckSpec(name="py", command=("x",), kinds=("python",)),
            CheckSpec(name="js", command=("x",), kinds=("javascript",)),
            CheckSpec(name="all", command=("x",), kinds=("any",)),
        )
        selected = select_checks(checks, [Path("src/a.py")])
        self.assertEqual([x.name for x in selected], ["py", "all"])


if __name__ == "__main__":
    unittest.main()
