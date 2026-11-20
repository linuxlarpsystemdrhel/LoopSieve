"""Run a user-supplied local GGUF on Linux."""

import argparse
import contextlib
import http.client
import re
import shutil
import subprocess
import time
from pathlib import Path

from loopsieve.model_manager import ModelDownloader

ROOT = Path(__file__).resolve().parents[1]


def checked_weights(path: Path, sha256: str | None = None) -> Path:
    path = path.expanduser()
    if path.suffix.lower() != ".gguf" or not path.is_file() or path.stat().st_size == 0:
        raise ValueError("--weights must point to an existing nonempty .gguf file")
    if sha256 is not None:
        if not re.fullmatch(r"[0-9a-fA-F]{64}", sha256):
            raise ValueError("--sha256 must be a 64-character hexadecimal digest")
        if ModelDownloader(path.parent).verify(path, sha256)["status"] != "PASS":
            raise ValueError("Model weights failed SHA-256 verification.")
    return path.resolve()


def find_device(binary: str, mode: str) -> str:
    if mode == "cpu":
        return "none"
    result = subprocess.run(
        [binary, "--list-devices"],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    match = re.search(r"^\s*(CUDA[0-9]+):", result.stdout + result.stderr, re.MULTILINE)
    if match:
        return match[1]
    if mode == "cuda":
        raise ValueError(
            "llama-server found no CUDA device. Select --device cpu or use a CUDA-enabled build."
        )
    return "none"


def server_command(
    binary: str,
    weights: Path,
    model: str,
    context_tokens: int,
    port: int,
    threads: int,
    device: str,
) -> list[str]:
    return [
        binary,
        "--model",
        str(weights),
        "--alias",
        model,
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--ctx-size",
        str(context_tokens),
        "--threads",
        str(threads),
        "--threads-batch",
        str(threads),
        "--parallel",
        "1",
        "--device",
        device,
        "--gpu-layers",
        "0" if device == "none" else "all",
        "--no-webui",
        "--no-context-shift",
        "--cache-ram",
        "0",
    ]


def health(port: int) -> bool:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=0.5)
    try:
        connection.request("GET", "/health")
        with connection.getresponse() as response:
            return response.status == 200
    except (OSError, http.client.HTTPException):
        return False
    finally:
        connection.close()


@contextlib.contextmanager
def running_server(
    command: list[str], port: int, *, startup_timeout: float = 60, stderr=None
):
    with subprocess.Popen(
        command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=stderr
    ) as process:
        try:
            deadline = time.monotonic() + startup_timeout
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(
                        f"llama-server exited during startup (code {process.returncode})"
                    )
                if health(port) and process.poll() is None:
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError(
                    "llama-server did not become ready before the startup deadline"
                )
            yield process
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--server", default="llama-server", help="path or installed llama-server name"
    )
    parser.add_argument(
        "--weights", type=Path, required=True, help="local GGUF that you supply"
    )
    parser.add_argument("--sha256", help="optional publisher SHA-256")
    parser.add_argument(
        "--model", default="local-model", help="alias sent by the client"
    )
    parser.add_argument("--context-tokens", type=int, default=8192)
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or not 1 <= args.threads <= 256:
        parser.error("port must be 1–65535 and threads must be 1–256")
    binary = shutil.which(args.server)
    if binary is None:
        parser.error(
            "llama-server is unavailable. Install a trusted llama.cpp binary or pass --server."
        )
    try:
        weights = checked_weights(args.weights, args.sha256)
        if not args.model.strip() or args.context_tokens <= 0:
            raise ValueError(
                "--model must be nonempty and --context-tokens must be positive"
            )
        device = find_device(binary, args.device)
        if health(args.port):
            raise ValueError("a server is already listening on that port")
        command = server_command(
            binary,
            weights,
            args.model,
            args.context_tokens,
            args.port,
            args.threads,
            device,
        )
        with running_server(command, args.port) as process:
            backend = "CPU" if device == "none" else device
            print(
                f"llama-server ready on 127.0.0.1:{args.port} ({backend})", flush=True
            )
            code = process.wait()
            if code:
                raise RuntimeError(f"llama-server exited (code {code})")
    except KeyboardInterrupt:
        return
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        parser.exit(2, f"Local model startup failed: {exc}\n")


if __name__ == "__main__":
    main()
