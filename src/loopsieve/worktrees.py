"""Explicit, isolated git worktrees for independent agent experiments.

No auto-merge, no auto-delete, no shell, no remote operations.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path


def _git(root: Path,*args: str,timeout: int=15) -> str:
    p=subprocess.run(['git','-C',str(root),*args],text=True,capture_output=True,timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout or 'git operation failed')[:500])
    return p.stdout.strip()


def prepare_experiment(root: Path, experiment: str, target_parent: Path, *, approve: bool=False) -> dict:
    """Create detached worktree from exact HEAD, only with explicit approval."""
    if not approve:raise PermissionError('explicit approval is required to create a worktree')
    if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_-]{0,35}',experiment):
        raise ValueError('experiment name must be a simple safe ID')
    root=Path(root).resolve()
    if Path(_git(root,'rev-parse','--show-toplevel')).resolve()!=root:
        raise ValueError('root must be the Git repository top level')
    if _git(root,'status','--porcelain'):
        raise ValueError('working tree must be clean before creating experiments')
    head=_git(root,'rev-parse','HEAD')
    target_parent=Path(target_parent).resolve()
    target_parent.mkdir(parents=True, exist_ok=True)
    dest=target_parent/('loopsieve-'+experiment)
    if dest.exists():raise FileExistsError('experiment path already exists')
    _git(root,'worktree','add','--detach',str(dest),head)
    return {'path':str(dest),'base_commit':head,'branch':'detached','status':'READY',
            'policy':'No automatic merge or cleanup; worktree is independently reviewable'}


def worktree_status(root: Path) -> list[dict]:
    output=_git(Path(root).resolve(),'worktree','list','--porcelain')
    blocks=output.split('\n\n')
    result=[]
    for block in blocks:
        lines=block.splitlines()
        if not lines:continue
        row={}
        for line in lines:
            key,_,value=line.partition(' ')
            row[key]=value
        result.append({'path':row.get('worktree'),'head':row.get('HEAD'),'branch':row.get('branch','detached')})
    return result
