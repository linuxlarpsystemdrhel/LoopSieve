"""Deterministic skill steps composed from permission-restricted tools."""
from __future__ import annotations

from pathlib import Path

from .catalog import list_entries,load
from .toolkit import run_tool


def list_skills():return list_entries('skills')


def _pick_path(root: Path, tool: str, args: dict):
    if 'path' in args:return args
    patterns={
      'python':'**/*.py','requirements':'requirements.txt','pyproject':'pyproject.toml',
      'package':'package.json','cargo':'Cargo.toml','go_modules':'go.mod',
      'json':'**/*.json','yaml':'**/*.yaml','toml':'**/*.toml',
      'xml':'**/*.xml','ini':'**/*.ini','csv':'**/*.csv','archive':'**/*.zip',
    }
    pattern=next((pat for prefix,pat in patterns.items() if tool.startswith(prefix)),None)
    if pattern:
        p=next((p for p in root.glob(pattern) if p.is_file() and not any(x in p.parts for x in ('.git','.venv','node_modules','__pycache__'))),None)
        if p:return {**args,'path':p.relative_to(root).as_posix()}
    return args


def run_skill(skill_id: str, root: Path, args: dict | None=None):
    spec=load('skills',skill_id)
    original=args or {}; outcomes=[]
    for step in spec['workflow']:
        step_args=_pick_path(root,step['tool'],dict(original))
        try:
            result=run_tool(step['tool'],root,step_args)
            if isinstance(result,dict) and result.get('status') in {'REQUIRES_DEPENDENCY','PROBE_FAILED'}:
                outcomes.append({'step':step['step'],'tool':step['tool'],'status':'BLOCKED','result':result});break
            outcomes.append({'step':step['step'],'tool':step['tool'],'status':'PASS','result':result})
        except Exception as exc:
            outcomes.append({'step':step['step'],'tool':step['tool'],'status':'ERROR','error':f'{type(exc).__name__}: {exc}'});break
    return {'skill':spec['id'],'status':'COMPLETED' if len(outcomes)==len(spec['workflow']) and all(x['status']=='PASS' for x in outcomes) else 'PARTIAL','steps':outcomes}
