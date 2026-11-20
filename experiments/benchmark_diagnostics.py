"""Profile fingerprint function on repeated diagnostic locations in one source file."""

import argparse
import cProfile
import json
import statistics
import tempfile
import time
from pathlib import Path

from loopsieve.diagnostics import diagnostic_identity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = "".join(f"def step_{i}():\n    return {i}\n\n" for i in range(300))
        (root / "fixture.py").write_text(source, encoding="utf-8")
        diagnostics = "\n".join(
            f"fixture.py:{i * 3 + 2}:5: error: unexpected value" for i in range(100)
        )
        times = []
        diagnostic_identity(diagnostics, root, "fixture", "1")
        for _ in range(11):
            before = time.perf_counter()
            digest, records = diagnostic_identity(diagnostics, root, "fixture", "1")
            times.append((time.perf_counter() - before) * 1000)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(
                {
                    "digest": digest,
                    "records": len(records),
                    "samples_ms": times,
                    "median_ms": statistics.median(times),
                },
                stream,
                indent=2,
            )
            stream.write("\n")
        if args.profile:
            profiler = cProfile.Profile()
            profiler.runcall(diagnostic_identity, diagnostics, root, "fixture", "1")
            with args.profile.open("x", encoding="utf-8") as stream:
                import pstats

                pstats.Stats(profiler, stream=stream).strip_dirs().sort_stats(
                    "cumtime"
                ).print_stats(18)


if __name__ == "__main__":
    main()
