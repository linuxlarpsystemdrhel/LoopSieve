"""Compare the Python and release Rust CLIs using fresh processes on Linux."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "benchmarks/fixtures/stable-repeat.json"


# A small native parent avoids carrying Python's pre-exec RSS watermark into
# short Rust samples. Linux wait4 reports KiB for the measured child.
MEASUREMENT_HELPER = r"""
#define _DEFAULT_SOURCE
#include <stdio.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

int main(int argc, char **argv) {
    if (argc < 2) return 2;
    struct timespec start, end;
    struct rusage usage;
    int status;
    if (clock_gettime(CLOCK_MONOTONIC, &start) != 0) return 2;
    pid_t child = fork();
    if (child < 0) return 2;
    if (child == 0) {
        FILE *sink = freopen("/dev/null", "w", stdout);
        if (!sink) _exit(2);
        execvp(argv[1], argv + 1);
        _exit(127);
    }
    if (wait4(child, &status, 0, &usage) != child) return 2;
    if (clock_gettime(CLOCK_MONOTONIC, &end) != 0) return 2;
    if (!WIFEXITED(status) || WEXITSTATUS(status)) return 2;
    double ms = (end.tv_sec - start.tv_sec) * 1e3 + (end.tv_nsec - start.tv_nsec) / 1e6;
    printf("%.6f %ld\n", ms, usage.ru_maxrss);
    return 0;
}
"""


def sample(helper: Path, command: list[str], environment: dict[str, str]) -> dict:
    fields = subprocess.check_output(
        [str(helper), *command],
        cwd=ROOT,
        env=environment,
        stdin=subprocess.DEVNULL,
        text=True,
        timeout=30,
    ).split()
    return {"elapsed_ms": float(fields[0]), "peak_rss_kib": int(fields[1])}


def compare(binary: Path, runs: int) -> dict:
    executables = {"python": [sys.executable, "-m", "loopsieve"], "rust": [str(binary)]}
    environment = os.environ | {
        "PYTHONPATH": str(ROOT / "src"),
        "CLAUDE_PLUGIN_DATA": "",
    }
    samples = {}
    with tempfile.TemporaryDirectory(prefix="loopsieve-runtime-bench-") as scratch:
        project = Path(scratch)
        helper = project / "measure"
        subprocess.run(
            ["cc", "-O2", "-std=c11", "-x", "c", "-", "-o", str(helper)],
            input=MEASUREMENT_HELPER,
            text=True,
            check=True,
        )
        (project / "source.rs").touch()
        program = shutil.which("true")
        if not program:
            raise RuntimeError("could not find the true executable")
        (project / ".loopsieve.json").write_text(
            json.dumps(
                {
                    "checks": [
                        {"name": "fixture", "command": [program], "kinds": ["rust"]}
                    ]
                }
            ),
            encoding="utf-8",
        )
        workloads = {
            "help": ["--help"],
            "fixture": ["benchmark", str(FIXTURE), "--json"],
            "check": ["check", "--root", scratch, "source.rs"],
        }
        for workload, arguments in workloads.items():
            rows = {name: [] for name in executables}
            for index in range(runs + 2):
                order = list(executables)
                if index % 2:
                    order.reverse()
                for implementation in order:
                    state = str(project / f"{workload}-{implementation}-{index}")
                    env = environment | {
                        "LOOPSIEVE_STATE_DIR": state,
                        "LOOPSIEVE_RUST_STATE_DIR": state,
                    }
                    row = sample(helper, executables[implementation] + arguments, env)
                    if index >= 2:
                        rows[implementation].append(row)
            samples[workload] = {
                implementation: {
                    "median_elapsed_ms": statistics.median(
                        row["elapsed_ms"] for row in values
                    ),
                    "median_peak_rss_kib": statistics.median(
                        row["peak_rss_kib"] for row in values
                    ),
                    "samples": values,
                }
                for implementation, values in rows.items()
            }
    cpu = next(
        (
            line.split(":", 1)[1].strip()
            for line in Path("/proc/cpuinfo").read_text().splitlines()
            if line.startswith("model name")
        ),
        platform.machine(),
    )
    return {
        "recorded_utc": datetime.now(UTC).isoformat(),
        "host": {
            "cpu": cpu,
            "kernel": platform.release(),
            "architecture": platform.machine(),
        },
        "software": {
            "python": platform.python_version(),
            "rustc": subprocess.check_output(["rustc", "--version"], text=True).strip(),
        },
        "method": {
            "samples_per_implementation": runs,
            "discarded_warmups_per_implementation": 2,
            "startup": "fresh subprocess per sample; filesystem caches not flushed",
            "ram": "per-process peak RSS in KiB via Linux wait4 from a small native parent",
            "check": "fresh local state and one successful true subprocess",
        },
        "workloads": samples,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rust", type=Path, default=ROOT / "target/release/loopsieve-rs"
    )
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != "linux" or args.runs < 2:
        parser.error("requires Linux and at least two measured runs")
    baseline = compare(args.rust.resolve(strict=True), args.runs)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(
            baseline,
            stream,
            indent=2,
            allow_nan=False,
        )
        stream.write("\n")


if __name__ == "__main__":
    main()
