"""Small failing checks used to measure diagnostic explanations."""

import argparse
import importlib
import json
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=("division", "json", "import", "syntax"))
    parser.add_argument("--padding", type=int, default=0)
    args = parser.parse_args()
    for index in range(args.padding):
        print(f"build step {index:03d} scanned package targets")
    sys.stdout.flush()
    if args.case == "division":
        total, count = 8, 0
        print(total / count)
    elif args.case == "json":
        json.loads("{debug: true}")
    elif args.case == "import":
        importlib.import_module("loopsieve_example_dependency")
    else:
        compile("if True\n    print('hello')", "example.py", "exec")


if __name__ == "__main__":
    main()
