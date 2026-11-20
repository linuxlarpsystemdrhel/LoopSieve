"""Lazy agent definitions and a bounded, explicit local task scheduler.

This module does not secretly instantiate 100 models. It executes only
explicitly requested read-only local tool operations under role permissions.
"""
from __future__ import annotations

import hashlib
import contextlib
import json
import os
import tempfile
import time
from pathlib import Path

from .catalog import list_entries, load
from .state import default_state_base
from .toolkit import run_tool


def list_agents(keyword: str='') -> list[dict]:
    agents=list_entries('agents')
    if keyword:
        k=keyword.lower()
        agents=[a for a in agents if k in (a['name']+' '+' '.join(a['keywords'])+' '+a['specialization']).lower()]
    return agents


def select_agents(task: str, max_agents: int=1) -> list[dict]:
    if not task.strip(): return []
    import re
    words=set(re.findall(r'[a-z0-9+]+',task.lower()))
    values=[]
    for a in list_agents():
        keys=set(a['keywords'])
        name=set(re.findall(r'[a-z0-9+]+',a['name'].lower()))
        score=3*len(words & keys)+2*len(words & name)
        if score:values.append((score,a))
    values.sort(key=lambda x:(-x[0],x[1]['id']))
    if not values:
        return [load('agents','001-chief-architect')]
    return [x[1] for x in values[:max(1,min(max_agents,4))]]


class TaskStore:
    """Small persistent task queue; no daemon, network, or background agents."""
    def __init__(self, root: Path, state_dir: Path | None=None):
        self.root=root.resolve()
        self.path=(state_dir or default_state_base())/'task-queues'/hashlib.sha256(str(self.root).encode()).hexdigest()[:16]/'tasks.json'

    @contextlib.contextmanager
    def _exclusive(self):
        """Short cross-process file lock. No external lock dependency."""
        lock=self.path.with_suffix('.lock')
        lock.parent.mkdir(parents=True,exist_ok=True)
        started=time.monotonic()
        while True:
            try:
                fd=os.open(lock,os.O_CREAT | os.O_EXCL | os.O_WRONLY,0o600)
                os.close(fd)
                break
            except (FileExistsError, PermissionError):
                if time.monotonic()-started>5:
                    raise TimeoutError('task state is locked by another process')
                try:
                    if time.time()-lock.stat().st_mtime>60:
                        lock.unlink(missing_ok=True)
                except OSError:pass
                time.sleep(0.02)
        try:yield
        finally:
            lock.unlink(missing_ok=True)

    def all(self) -> list[dict]:
        try:
            data=json.loads(self.path.read_text(encoding='utf-8'))
            return data if isinstance(data,list) else []
        except (OSError,ValueError): return []

    def _save(self, tasks: list[dict]):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        fd,tmp=tempfile.mkstemp(dir=self.path.parent, prefix='task-',suffix='.json')
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as f: json.dump(tasks,f,indent=2)
            os.replace(tmp,self.path)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)

    def create(self, task: str, tool_name: str | None =None, args: dict | None=None, agent_id: str | None=None) -> dict:
        if not task.strip(): raise ValueError('task cannot be blank')
        agent=load('agents',agent_id) if agent_id else select_agents(task)[0]
        if tool_name and tool_name not in agent['allowed_tools']:
            raise PermissionError(f'{agent["name"]} cannot use {tool_name}')
        canonical=json.dumps({'task':task,'tool':tool_name,'args':args or {},'agent':agent['id']},sort_keys=True)
        digest=hashlib.sha256(canonical.encode()).hexdigest()[:12]
        with self._exclusive():
            tasks=self.all()
            for item in tasks:
                if item.get('dedup_key')==digest and item.get('status') in {'QUEUED','RUNNING'}:
                    return item
            item={'task_id':f'task-{time.time_ns()}-{digest[:6]}','dedup_key':digest,'task':task,
              'agent_id':agent['id'],'tool':tool_name,'args':args or {},'status':'QUEUED',
              'created_at':int(time.time()),'result':None}
            tasks.append(item);self._save(tasks[-500:]);return item

    def cancel(self,task_id: str):
        with self._exclusive():
            tasks=self.all()
            for t in tasks:
                if t['task_id']==task_id and t['status']=='QUEUED':
                    t['status']='CANCELLED';self._save(tasks);return t
        raise ValueError('task not queued or not found')

    def run(self,task_id: str):
        with self._exclusive():
            tasks=self.all()
            for t in tasks:
                if t.get('status')=='RUNNING' and time.time()-t.get('started_at',0)>90:
                    t['status']='ERROR'; t['result']={'error':'stale running task recovered after timeout'}
            entry=next((t for t in tasks if t['task_id']==task_id),None)
            if entry is None:raise KeyError(task_id)
            if entry['status']!='QUEUED':raise ValueError('task already started, completed or cancelled')
            if sum(t['status']=='RUNNING' for t in tasks)>=4:
                raise RuntimeError('maximum local task concurrency of 4 reached')
            entry['status']='RUNNING'; entry['started_at']=int(time.time())
            self._save(tasks)
        outcome={}
        if not entry['tool']:
            status='BLOCKED';outcome={'reason':'role definition alone does not provide an LLM; specify an allowed local tool'}
        else:
            role=load('agents',entry['agent_id'])
            if entry['tool'] not in role['allowed_tools']:
                status='BLOCKED';outcome={'error':'agent tool permission revoked'}
            else:
                try:
                    output=run_tool(entry['tool'],self.root,entry['args'])
                    status='COMPLETED';outcome={'tool':entry['tool'],'data':output}
                except Exception as exc:
                    status='ERROR';outcome={'error':f'{type(exc).__name__}: {exc}'}
        with self._exclusive():
            tasks=self.all()
            current=next(t for t in tasks if t['task_id']==task_id)
            current['status']=status;current['result']=outcome
            current['completed_at']=int(time.time())
            self._save(tasks)
            return current
