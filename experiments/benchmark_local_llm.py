"""Measure the user-supplied diagnostic model with real, repeatable failed checks."""

import argparse
import cProfile
import json
import os
import platform
import pstats
import random
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from collections import defaultdict, deque
from contextlib import nullcontext
from dataclasses import asdict, replace
from pathlib import Path

from loopsieve.config import Config
from loopsieve.engine import verify
from loopsieve.local_llm import (
    LocalInferenceError,
    diagnostic_evidence,
    explain,
    load_local_config,
)
from loopsieve.models import CheckSpec
from tools.run_local_model import (
    ROOT,
    checked_weights,
    find_device,
    health,
    running_server,
    server_command,
)

FIXTURE = Path("experiments/fixtures/diagnostic_check.py")
CASES = {
    "division": (
        r"zerodivisionerror|(divid\w*|division)\b.*(zero|\b0\b)",
        r"check|guard|nonzero|zero|denominator",
    ),
    "json": (
        r"(double.quote|unquoted|enclosed in quotes|quotes? around).*(key|name|debug)|"
        r"(key|name|debug).*(double.quote|unquoted|enclosed in quotes|quotes?)",
        r"quot",
    ),
    "import": (
        r"(missing|not found|no module|failed to import|cannot (find|import)).*loopsieve_example_dependency|"
        r"loopsieve_example_dependency.*(missing|not (installed|found))",
        r"install|environment|path",
    ),
    "syntax": (r"syntax error|syntaxerror|missing colon", r"colon|\x27:\x27|\x60:\x60"),
}
PADDING = {"short": 0, "medium": 60, "long": 150}
MODES = ("A", "B", "C")


def cpu_time(pid):
    stat = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    return (int(stat[11]) + int(stat[12])) / os.sysconf("SC_CLK_TCK")


def rss_kib(pid):
    status = Path(f"/proc/{pid}/status").read_text()
    return int(re.search(r"^VmRSS:\s+(\d+)", status, re.MULTILINE)[1])


class Sampler:
    def __init__(self, server_pid):
        self.server_pid = server_pid
        self.stop = threading.Event()
        self.peak_server_kib = None
        self.peak_client_kib = None

    def sample(self):
        try:
            self.peak_server_kib = max(
                self.peak_server_kib or 0, rss_kib(self.server_pid)
            )
            self.peak_client_kib = max(self.peak_client_kib or 0, rss_kib(os.getpid()))
        except (OSError, TypeError):
            pass

    def monitor(self):
        while not self.stop.wait(0.05):
            self.sample()

    def __enter__(self):
        self.sample()
        self.thread = threading.Thread(target=self.monitor)
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stop.set()
        self.thread.join()
        self.sample()


class GpuTelemetry:
    """Sample device-wide occupancy and utilization with the NVIDIA driver."""

    interval_ms = 50

    def __init__(self, index):
        self.command = ["nvidia-smi", "-i", str(index), "--format=csv,noheader,nounits"]
        self.samples = deque(maxlen=4096)
        self.lock = threading.Lock()
        self.started = threading.Event()
        self.metadata = {}

    def monitor(self):
        for raw in self.process.stdout:
            try:
                memory, utilization = map(int, raw.split(","))
            except ValueError:
                continue
            with self.lock:
                self.samples.append((time.perf_counter(), memory, utilization))
            self.started.set()

    def __enter__(self):
        static = subprocess.check_output(
            self.command + ["--query-gpu=name,driver_version,memory.total,memory.used"],
            text=True,
            timeout=5,
        )
        name, driver, total, used = (value.strip() for value in static.split(","))
        self.metadata = {
            "name": name,
            "driver": driver,
            "total_vram_mib": int(total),
            "device_vram_before_server_mib": int(used),
            "sampling_interval_ms": self.interval_ms,
        }
        self.process = subprocess.Popen(
            self.command
            + [
                "--query-gpu=memory.used,utilization.gpu",
                f"--loop-ms={self.interval_ms}",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        self.thread = threading.Thread(target=self.monitor)
        self.thread.start()
        if not self.started.wait(5):
            self.__exit__()
            raise RuntimeError("nvidia-smi returned no GPU samples")
        return self

    def __exit__(self, *_):
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.thread.join()
        self.process.stdout.close()

    def utilization(self, start, end):
        with self.lock:
            observations = [
                (memory, util)
                for timestamp, memory, util in self.samples
                if start <= timestamp <= end
            ]
        return {
            "gpu_samples": len(observations),
            "gpu_vram_mib": max((memory for memory, _ in observations), default=None),
            "gpu_utilization_pct": statistics.median(util for _, util in observations)
            if observations
            else None,
        }

    def server_vram(self, pid):
        data = subprocess.check_output(
            self.command + ["--query-compute-apps=pid,used_memory"],
            text=True,
            timeout=5,
        )
        for line in data.splitlines():
            process, memory = (part.strip() for part in line.split(","))
            if process == str(pid) and memory.isdigit():
                return int(memory)
        return None


def collect_checks(state, root):
    checks = {}
    for name in CASES:
        for length, padding in PADDING.items():
            spec = CheckSpec(
                name=name,
                command=(sys.executable, str(FIXTURE), name, "--padding", str(padding)),
                max_output_chars=12000,
            )
            config = Config((spec,), state_dir=str(state))
            run = verify(root, [FIXTURE], config)
            if len(run.failed_results) != 1 or run.failed_results[0].returncode != 1:
                raise RuntimeError(f"unexpected fixture result for {name}/{length}")
            checks[name, length] = run
    return checks


def score(text, case):
    cause, separator, next_step = text.lower().partition("next:")
    return {
        "cause": bool(re.search(CASES[case][0], cause)),
        "next": bool(separator and re.search(CASES[case][1], next_step)),
        "format": cause.startswith("cause:") and bool(separator),
    }


def sample(mode, case, length, run, config, pid, phase, gpu=None):
    cpu_before = cpu_time(pid)
    with Sampler(pid) as resources:
        started = time.perf_counter()
        if mode == "A":
            evidence = run.failed_results[0].output
        else:
            evidence = diagnostic_evidence(run, 36)
        prepared = time.perf_counter()
        row = {
            "mode": mode,
            "case": case,
            "length": length,
            "phase": phase,
            "evidence_bytes": len(evidence.encode()),
            "verify_ms": run.failed_results[0].duration_seconds * 1000,
            "prepare_ms": (prepared - started) * 1000,
            "gpu_utilization_pct": None,
            "gpu_vram_mib": None,
        }
        try:
            result = explain(evidence, config, cache_prompt=mode == "C")
            row.update(asdict(result), quality=score(result.text, case), status="ok")
            row["text"] = result.text.replace(str(ROOT) + "/", "./")
        except LocalInferenceError as exc:
            row.update(status="error", error=str(exc))
        ended = time.perf_counter()
    elapsed = ended - started
    if gpu:
        row.update(gpu.utilization(started, ended))
    row.update(
        pipeline_ms=elapsed * 1000,
        server_cpu_pct_one_core=(cpu_time(pid) - cpu_before) / elapsed * 100,
        server_peak_rss_mib=resources.peak_server_kib / 1024
        if resources.peak_server_kib
        else None,
        client_peak_rss_mib=resources.peak_client_kib / 1024
        if resources.peak_client_kib
        else None,
    )
    return row


def summarize(rows):
    groups = defaultdict(list)
    for row in rows:
        if row["phase"] == "measurement":
            groups[row["mode"], row["length"]].append(row)
    summary = []
    for (mode, length), group in sorted(groups.items()):
        good = [row for row in group if row["status"] == "ok"]
        entry = {
            "mode": mode,
            "length": length,
            "requests": len(group),
            "errors": len(group) - len(good),
        }
        if good:
            for metric in (
                "pipeline_ms",
                "latency_ms",
                "first_token_ms",
                "prompt_tokens",
                "cached_tokens",
                "prompt_ms",
                "decode_tokens_per_second",
                "server_cpu_pct_one_core",
                "server_peak_rss_mib",
                "client_peak_rss_mib",
                "prepare_ms",
                "gpu_utilization_pct",
                "gpu_vram_mib",
            ):
                values = [row[metric] for row in good if row[metric] is not None]
                entry["median_" + metric] = (
                    round(statistics.median(values), 3) if values else None
                )
            entry["max_server_rss_mib"] = round(
                max(row["server_peak_rss_mib"] for row in good), 3
            )
            entry["serial_requests_per_second"] = round(
                1000 * len(group) / sum(r["pipeline_ms"] for r in group), 3
            )
            entry["quality_pass"] = sum(all(r["quality"].values()) for r in good)
        summary.append(entry)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--sha256", help="optional publisher SHA-256")
    parser.add_argument("--llm-config", type=Path, required=True)
    parser.add_argument("--context-tokens", type=int, default=8192)
    parser.add_argument("--server", default="llama-server")
    parser.add_argument("--port", type=int, default=18080)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument(
        "--nvidia-index",
        type=int,
        default=0,
        help="nvidia-smi index for the CUDA device used by llama-server",
    )
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument(
        "--profile",
        type=Path,
        help="write cProfile statistics for one diagnostic preparation",
    )
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or not 1 <= args.threads <= 256 or args.repeats < 2:
        parser.error("provide a valid port, 1–256 threads and at least two repeats")
    if sys.platform != "linux" or Path.cwd() != ROOT:
        parser.error("run on Linux from the repository root")
    if args.output.exists() or (args.profile and args.profile.exists()):
        parser.error("output files must be new")
    binary = shutil.which(args.server)
    if not binary or health(args.port):
        parser.error("an installed llama-server and a free loopback port are required")
    try:
        weights = checked_weights(args.weights, args.sha256)
        config = replace(
            load_local_config(args.llm_config), endpoint=f"http://127.0.0.1:{args.port}"
        )
        if args.context_tokens <= 0:
            raise ValueError("--context-tokens must be positive")
        device = find_device(binary, args.device)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        parser.error(str(exc))
    metadata = {
        "alias": config.model,
        "filename": weights.name,
        "size_bytes": weights.stat().st_size,
        "publisher_sha256": args.sha256,
    }
    command = server_command(
        binary,
        weights,
        config.model,
        args.context_tokens,
        args.port,
        args.threads,
        device,
    )
    telemetry = (
        GpuTelemetry(args.nvidia_index) if args.device == "cuda" else nullcontext()
    )
    version = subprocess.check_output(
        [binary, "--version"], text=True, stderr=subprocess.STDOUT
    ).strip()
    rows = []
    rng = random.Random(42)
    with tempfile.TemporaryDirectory(prefix="loopsieve-benchmark-") as state:
        checks = collect_checks(state, ROOT)
        with (
            telemetry as gpu,
            tempfile.TemporaryFile() as server_log,
            running_server(command, args.port, stderr=server_log) as server,
        ):
            if gpu:
                gpu.metadata["server_resident_vram_after_startup_mib"] = (
                    gpu.server_vram(server.pid)
                )
            for (case, length), run in checks.items():
                block_order = list(MODES)
                rng.shuffle(block_order)
                for mode in block_order:
                    rows.append(
                        sample(
                            mode, case, length, run, config, server.pid, "warmup", gpu
                        )
                    )
                    for _ in range(args.repeats):
                        rows.append(
                            sample(
                                mode,
                                case,
                                length,
                                run,
                                config,
                                server.pid,
                                "measurement",
                                gpu,
                            )
                        )
                print(f"Measured {case}/{length}", flush=True)
            if gpu:
                gpu.metadata["server_resident_vram_after_measurement_mib"] = (
                    gpu.server_vram(server.pid)
                )
    result = {
        "model": metadata,
        "software": {
            "llama_server": version,
            "python": platform.python_version(),
            "os": platform.platform(),
        },
        "hardware": {
            "cpu": re.search(
                r"^model name\s+: (.+)", Path("/proc/cpuinfo").read_text(), re.MULTILINE
            )[1],
            "logical_cpus_available": len(os.sched_getaffinity(0)),
            "host_ram_kib": int(
                re.search(
                    r"^MemTotal:\s+(\d+)",
                    Path("/proc/meminfo").read_text(),
                    re.MULTILINE,
                )[1]
            ),
            "gpu": gpu.metadata if gpu else None,
            "gpu_metrics": "NVIDIA device-wide sampling"
            if gpu
            else "CPU-only invocation",
        },
        "settings": {
            "llama_server_arguments": [
                weights.name if value == str(weights) else value
                for value in command[1:]
            ],
            "checkout_paths_in_report_relative": True,
            "device": device,
            "inference": asdict(config),
            "repeats": args.repeats,
            "padding_lines": PADDING,
            "block_order_seed": 42,
            "concurrency": 1,
            "sample_interval_ms": 50,
            "verification_replayed": False,
            "quality_rubric": CASES,
        },
        "rows": rows,
        "summary": summarize(rows),
    }
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    if args.profile:
        with args.profile.open("x", encoding="utf-8") as stream:
            profiler = cProfile.Profile()
            for _ in range(500):
                profiler.runcall(diagnostic_evidence, checks["json", "long"], 36)
            pstats.Stats(profiler, stream=stream).strip_dirs().sort_stats(
                "cumtime"
            ).print_stats(20)
    if any(r["status"] != "ok" for r in rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
