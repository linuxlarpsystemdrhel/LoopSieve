"""External CLI adapter discovery and optional version contract checks."""
from __future__ import annotations

import shutil
import subprocess

from .catalog import list_entries, load


def list_plugins():
    return [{**p, 'status':'AVAILABLE_NOT_PROBED' if shutil.which(p['executable']) else 'REQUIRES_DEPENDENCY'} for p in list_entries('plugins')]


def probe_plugin(plugin_id: str):
    spec=load('plugins',plugin_id)
    path=shutil.which(spec['executable'])
    if not path:
        return {'id':spec['id'],'status':'REQUIRES_DEPENDENCY','binary':spec['executable']}
    try:
        run=subprocess.run([path,*spec['probe_args']],stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=min(spec['max_probe_seconds'],5),shell=False)
        output=(run.stdout or run.stderr).strip()
        return {'id':spec['id'],'status':'AVAILABLE' if run.returncode==0 else 'PROBE_FAILED','binary':path,'exit_code':run.returncode,'version_output':output[:1000]}
    except (subprocess.TimeoutExpired,OSError) as exc:
        return {'id':spec['id'],'status':'PROBE_FAILED','error':str(exc)[:300]}
