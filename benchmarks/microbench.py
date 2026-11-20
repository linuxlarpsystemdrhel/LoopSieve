"""Reproducible local cold-start and memory inspection, no LLM calls."""
from __future__ import annotations
import json
import os
import statistics
import subprocess
import sys
import time
import tracemalloc
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ENV={**os.environ,'PYTHONPATH':str(ROOT/'src')}


def benchmark():
    latencies=[]
    for _ in range(3):
        start=time.perf_counter()
        p=subprocess.run([sys.executable,'-m','loopsieve','doctor'],cwd=ROOT,env=ENV,capture_output=True,text=True,timeout=30)
        if p.returncode:raise RuntimeError(p.stderr)
        latencies.append(round((time.perf_counter()-start)*1000,2))
    tracemalloc.start()
    start_cpu=time.process_time()
    start=time.perf_counter()
    from loopsieve.catalog import validate_catalog
    from loopsieve.toolkit import tool_catalog
    counts=validate_catalog()
    tools=tool_catalog()
    peak=tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    import resource
    process_peak_rss_mib = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 2) if sys.platform.startswith('linux') else 'NOT_MEASURED'
    return {
        'runner':'local Linux execution (not a cross-platform performance claim)',
        'python':sys.version.split()[0],
        'doctor_cold_start_ms_samples':latencies,
        'doctor_cold_start_ms_median':round(statistics.median(latencies),2),
        'catalog_validation_wall_ms':round((time.perf_counter()-start)*1000,2),
        'catalog_validation_cpu_ms':round((time.process_time()-start_cpu)*1000,2),
        'catalog_validation_tracemalloc_peak_mib':round(peak/1048576,3),
        'process_peak_rss_mib':process_peak_rss_mib,
        'catalogs':counts,'tools':len(tools),
        'gpu_memory_mib':'NOT_MEASURED; no GPU model is loaded by LoopSieve',
        'note':'CPU and Python tracemalloc metrics describe local operations, not entire agent usage'
    }

if __name__=='__main__':print(json.dumps(benchmark(),indent=2))
