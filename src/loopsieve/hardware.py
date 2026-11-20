"""Cross-platform hardware discovery for local model selection.

No GPU library is required. The detector uses standard library facilities and
optional vendor tools (nvidia-smi) only. Unsupported values are reported as
None instead of being invented.
"""
from __future__ import annotations

import ctypes
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class GpuInfo:
    name: str
    vram_total_mb: int | None = None
    vram_free_mb: int | None = None
    driver: str | None = None
    source: str = 'unknown'

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class HardwareProfile:
    os_name: str
    architecture: str
    cpu: str | None
    cpu_count: int | None
    ram_total_mb: int | None
    ram_free_mb: int | None
    gpus: tuple[GpuInfo, ...] = ()
    detected_at: float | None = None
    source: str = 'standard-library'
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        value = asdict(self)
        value['gpus'] = [g.as_dict() if isinstance(g, GpuInfo) else g for g in self.gpus]
        value['total_vram_mb'] = self.total_vram_mb
        value['free_vram_mb'] = self.free_vram_mb
        return value

    @property
    def total_vram_mb(self) -> int | None:
        values = [g.vram_total_mb for g in self.gpus if g.vram_total_mb]
        return sum(values) if values else None

    @property
    def free_vram_mb(self) -> int | None:
        values = [g.vram_free_mb for g in self.gpus if g.vram_free_mb is not None]
        return sum(values) if values else None


def _run(argv: list[str], timeout: int = 6) -> str | None:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
        if proc.returncode == 0:
            return proc.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return None
    return None


def _ram_windows() -> tuple[int | None, int | None]:
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ('dwLength', ctypes.c_ulong),
            ('dwMemoryLoad', ctypes.c_ulong),
            ('ullTotalPhys', ctypes.c_ulonglong),
            ('ullAvailPhys', ctypes.c_ulonglong),
            ('ullTotalPageFile', ctypes.c_ulonglong),
            ('ullAvailPageFile', ctypes.c_ulonglong),
            ('ullTotalVirtual', ctypes.c_ulonglong),
            ('ullAvailVirtual', ctypes.c_ulonglong),
            ('ullAvailExtendedVirtual', ctypes.c_ulonglong),
        ]
    try:
        status = MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return (int(status.ullTotalPhys // (1024 * 1024)),
                    int(status.ullAvailPhys // (1024 * 1024)))
    except Exception:
        pass
    return None, None


def _ram_linux() -> tuple[int | None, int | None]:
    try:
        values: dict[str, int] = {}
        for line in Path('/proc/meminfo').read_text(encoding='utf-8').splitlines():
            key, _, rest = line.partition(':')
            if key in {'MemTotal', 'MemAvailable'}:
                values[key] = int(rest.strip().split()[0])
        return (values.get('MemTotal', 0) // 1024 or None,
                values.get('MemAvailable', 0) // 1024 or None)
    except (OSError, ValueError, IndexError):
        return None, None


def _ram_macos() -> tuple[int | None, int | None]:
    total = _run(['sysctl', '-n', 'hw.memsize'])
    free = _run(['vm_stat'])
    try:
        total_mb = int(total) // (1024 * 1024) if total else None
    except ValueError:
        total_mb = None
    free_mb = None
    if free:
        pages = 0
        page_size = 4096
        for line in free.splitlines():
            if 'page size of' in line:
                try:
                    page_size = int(line.split('page size of')[1].split()[0])
                except (ValueError, IndexError):
                    pass
            if line.startswith('Pages free:'):
                try:
                    pages = int(line.split(':')[1].strip().rstrip('.'))
                except (ValueError, IndexError):
                    pages = 0
        if pages:
            free_mb = (pages * page_size) // (1024 * 1024)
    return total_mb, free_mb


def _ram() -> tuple[int | None, int | None, str]:
    try:
        import psutil  # type: ignore
        mem = psutil.virtual_memory()
        return int(mem.total // (1024 * 1024)), int(mem.available // (1024 * 1024)), 'psutil'
    except Exception:
        pass
    if os.name == 'nt':
        total, free = _ram_windows()
        return total, free, 'GlobalMemoryStatusEx'
    if sys.platform == 'darwin':
        total, free = _ram_macos()
        return total, free, 'sysctl'
    total, free = _ram_linux()
    return total, free, '/proc/meminfo'


def _nvidia_gpus() -> tuple[list[GpuInfo], str | None]:
    exe = shutil.which('nvidia-smi')
    if not exe:
        return [], None
    text = _run([exe, '--query-gpu=name,memory.total,memory.free,driver_version',
                 '--format=csv,noheader,nounits'])
    if not text:
        return [], 'nvidia-smi returned no data'
    gpus: list[GpuInfo] = []
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(',')]
        if len(parts) < 4:
            continue
        try:
            total = int(float(parts[1]))
            free = int(float(parts[2]))
        except ValueError:
            total = free = None
        gpus.append(GpuInfo(name=parts[0], vram_total_mb=total, vram_free_mb=free,
                            driver=parts[3], source='nvidia-smi'))
    return gpus, None


def _rocm_gpus() -> list[GpuInfo]:
    exe = shutil.which('rocm-smi')
    if not exe:
        return []
    text = _run([exe, '--showproductname', '--showmeminfo', 'vram'])
    if not text:
        return []
    # rocm-smi output differs across releases; only parse values that are explicit.
    total = free = None
    for line in text.splitlines():
        lowered = line.lower()
        if 'vram total' in lowered and ':' in line:
            try:
                total = int(float(line.split(':')[1].strip().split()[0]))
            except (ValueError, IndexError):
                pass
        if 'vram used' in lowered and ':' in line:
            try:
                used = int(float(line.split(':')[1].strip().split()[0]))
                if total is not None:
                    free = max(total - used, 0)
            except (ValueError, IndexError):
                pass
    return [GpuInfo(name='AMD GPU', vram_total_mb=total, vram_free_mb=free, source='rocm-smi')] if total else []


def detect_hardware() -> HardwareProfile:
    """Return the best available profile, with explicit unknowns and warnings."""
    warnings: list[str] = []
    total, free, source = _ram()
    if total is None:
        warnings.append('RAM total unavailable')
    if free is None:
        warnings.append('free RAM unavailable')
    gpus, nvidia_warning = _nvidia_gpus()
    if nvidia_warning:
        warnings.append(nvidia_warning)
    if not gpus:
        gpus = _rocm_gpus()
    try:
        cpu = platform.processor() or None
    except Exception:
        cpu = None
    return HardwareProfile(
        os_name=platform.system() or os.name,
        architecture=platform.machine() or 'unknown',
        cpu=cpu,
        cpu_count=os.cpu_count(),
        ram_total_mb=total,
        ram_free_mb=free,
        gpus=tuple(gpus),
        source=source,
        warnings=tuple(warnings),
    )


def hardware_summary(profile: HardwareProfile | None = None) -> dict:
    profile = profile or detect_hardware()
    return {
        'hardware': profile.as_dict(),
        'summary': {
            'cpu': profile.cpu or 'unknown',
            'cpu_count': profile.cpu_count,
            'ram_total_mb': profile.ram_total_mb,
            'ram_free_mb': profile.ram_free_mb,
            'total_vram_mb': profile.total_vram_mb,
            'free_vram_mb': profile.free_vram_mb,
            'gpu': profile.gpus[0].name if profile.gpus else 'none detected',
        },
        'limits': 'Values are reported by the operating system or vendor tool; unknown is not zero.',
    }
