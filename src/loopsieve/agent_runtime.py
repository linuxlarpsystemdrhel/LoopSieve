"""Bounded autonomous agent executor with persistent state and independent roles.

No LLM calls happen at import or catalog listing. Sessions are demand-activated.
The model produces a restricted JSON decision, never an executable command.
"""
from __future__ import annotations

import hashlib
import contextlib
import json
import os
import re
import sqlite3
import tempfile
import time
import uuid
from pathlib import Path

from .agents import select_agents
from .catalog import load
from .config import load_config
from .engine import verify
from .state import default_state_base
from .toolkit import safe_path, files, run_tool
from .permissions import PermissionEngine
from .provenance import EvidenceLedger

TERMINAL={'COMPLETED','FAILED','BLOCKED','CANCELLED','TERMINATED'}
STATES={'DORMANT','INITIALIZING','READY','PLANNING','WORKING','WAITING_FOR_TOOL','WAITING_FOR_AGENT',
        'VERIFYING','PAUSED','BLOCKED','FAILED','COMPLETED','TERMINATED','CANCELLED'}

class RuntimeErrorState(RuntimeError): pass


def _clean(s:str,max_len:int=12000)->str:
    # Never serialize raw API keys, tokens or giant provider responses into session history.
    s=s[:max_len]
    return re.sub(r'(?i)((?:api[_-]?key|token|authorization|password|secret)\s*[=:]\s*)\S+',r'\1[REDACTED]',s)


class Journal:
    """Durable SQLite state. One session per role/task, atomic transactions."""
    def __init__(self,root:Path,base:Path|None=None):
        self.root=root.resolve()
        key=hashlib.sha256(str(self.root).encode()).hexdigest()[:20]
        self.path=(base or default_state_base())/'autonomy'/key/'sessions.db'
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self._init()
        self.proof = EvidenceLedger(self.path.parent / 'evidence.db')
    @contextlib.contextmanager
    def _db(self):
        con=sqlite3.connect(self.path,timeout=10)
        con.row_factory=sqlite3.Row
        try:
            with con:
                yield con
        finally:
            con.close()
    def _init(self):
        with self._db() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('''CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY, agent_id TEXT, task TEXT, status TEXT, step INTEGER,
                max_steps INTEGER, allow_writes INTEGER, allow_checks INTEGER,
                messages TEXT, changed TEXT, evidence TEXT, updated REAL)''')
            db.execute('''CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT,
                kind TEXT, details TEXT, created REAL)''')
            db.execute('''CREATE TABLE IF NOT EXISTS checkpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, path TEXT,
                content TEXT NOT NULL, sha256 TEXT NOT NULL, created REAL NOT NULL)''')
    def save(self,s:dict):
        with self._db() as db:
            db.execute('''INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET status=excluded.status,step=excluded.step,
                messages=excluded.messages,changed=excluded.changed,evidence=excluded.evidence,updated=excluded.updated''',
                (s['id'],s['agent_id'],s['task'],s['status'],s['step'],s['max_steps'],
                int(s['allow_writes']),int(s['allow_checks']),json.dumps(s['messages'],ensure_ascii=False),
                json.dumps(s['changed']),json.dumps(s['evidence']),time.time()))
    def claim(self,sid:str):
        """Atomically acquire one agent turn; reject concurrent step requests."""
        with self._db() as db:
            row=db.execute("UPDATE sessions SET status='PLANNING', updated=? WHERE id=? AND status='READY' AND step<max_steps",(time.time(),sid))
            if row.rowcount!=1:raise RuntimeErrorState('agent step already active, paused, terminated or budget exhausted')

    def event(self,sid:str,kind:str,details:dict):
        data=json.dumps(details,ensure_ascii=False,default=str)
        with self._db() as db:
            db.execute('INSERT INTO events (session_id,kind,details,created) VALUES (?,?,?,?)',
                       (sid,kind,_clean(data,6000),time.time()))
        self.proof.append(sid, kind, details)
    def get(self,sid:str)->dict:
        with self._db() as db:
            row=db.execute('SELECT * FROM sessions WHERE id=?',(sid,)).fetchone()
        if row is None:raise KeyError(f'no session {sid}')
        s=dict(row)
        for k in ('messages','changed','evidence'):s[k]=json.loads(s[k])
        for k in ('allow_writes','allow_checks'):s[k]=bool(s[k])
        return s
    def list(self)->list[dict]:
        with self._db() as db:
            rows=db.execute('SELECT id,agent_id,task,status,step,max_steps,updated FROM sessions ORDER BY updated DESC LIMIT 200').fetchall()
        return [dict(x) for x in rows]
    def events(self,sid:str)->list[dict]:
        with self._db() as db:
            rows=db.execute('SELECT kind,details,created FROM events WHERE session_id=? ORDER BY id',(sid,)).fetchall()
        return [{'kind':r['kind'],'details':json.loads(r['details']),'created':r['created']} for r in rows]

    def checkpoint(self,sid:str,path:str,content:str)->dict:
        """Persist a pre-write file snapshot for deterministic rollback."""
        checksum=hashlib.sha256(content.encode('utf-8')).hexdigest()
        with self._db() as db:
            cursor=db.execute('INSERT INTO checkpoints(session_id,path,content,sha256,created) VALUES(?,?,?,?,?)',
                              (sid,path,content,checksum,time.time()))
            return {'id':cursor.lastrowid,'path':path,'sha256':checksum}

    def checkpoints(self,sid:str)->list[dict]:
        with self._db() as db:
            rows=db.execute('SELECT id,path,sha256,created FROM checkpoints WHERE session_id=? ORDER BY id DESC',(sid,)).fetchall()
        return [dict(r) for r in rows]

    def restore_checkpoint(self,sid:str,checkpoint_id:int)->dict:
        with self._db() as db:
            row=db.execute('SELECT * FROM checkpoints WHERE id=? AND session_id=?',(int(checkpoint_id),sid)).fetchone()
        if row is None:raise KeyError(f'no checkpoint {checkpoint_id} for session {sid}')
        target=safe_path(self.root,row['path'])
        current=target.read_text(encoding='utf-8') if target.is_file() else ''
        replaced=None
        if hashlib.sha256(current.encode('utf-8')).hexdigest()!=row['sha256']:
            replaced=hashlib.sha256(current.encode('utf-8')).hexdigest()
        fd,tmp=tempfile.mkstemp(prefix='.loopsieve-restore-',dir=target.parent)
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as out:out.write(row['content'])
            os.replace(tmp,target)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
        return {'restored':row['path'],'checkpoint_id':row['id'],'sha256':row['sha256'],'overwritten_sha256':replaced}


class AgentRuntime:
    """Autonomous finite-state actor, one model decision per step, constrained actions."""
    def __init__(self,root:Path,provider,journal:Journal|None=None,health_monitor=None,
                 permission_engine:PermissionEngine|None=None):
        self.root=root.resolve()
        self.provider=provider
        self.journal=journal or Journal(self.root)
        self.health_monitor=health_monitor
        self.permission_engine=permission_engine

    def create(self,task:str,agent_id:str|None=None,max_steps:int=8,*,allow_writes=False,allow_checks=False)->dict:
        if not isinstance(task,str) or not task.strip() or len(task)>10000:raise ValueError('invalid task')
        agent=load('agents',agent_id) if agent_id else select_agents(task)[0]
        if not (1<=max_steps<=40):raise ValueError('max_steps must be 1..40')
        if max_steps>int(agent.get('resource_limits',{}).get('max_llm_calls',16)):
            raise ValueError('max_steps exceeds per-agent model-call budget')
        s={'id':str(uuid.uuid4()),'agent_id':agent['id'],'task':task,'status':'READY',
           'step':0,'max_steps':max_steps,'allow_writes':allow_writes,'allow_checks':allow_checks,
           'messages':[{'role':'user','content':_clean(task)}],'changed':[], 'evidence':[]}
        self.journal.save(s);self.journal.event(s['id'],'created',{'agent':s['agent_id'],'writes':allow_writes,'checks':allow_checks})
        if self.permission_engine is not None:
            self.permission_engine.bind_agent(s['id'], agent, allow_writes=allow_writes, allow_checks=allow_checks)
        return s

    def _workspace_read(self,path:str):
        p=safe_path(self.root,path)
        if p.stat().st_size>1024*1024:raise ValueError('file over 1 MiB read limit')
        return p.read_text(encoding='utf-8',errors='replace')[:12000]

    def _patch(self,s:dict,action:dict)->dict:
        if not s['allow_writes']:raise PermissionError('writes require explicit --allow-writes')
        path=action.get('path');old=action.get('find');replacement=action.get('replace')
        if not all(isinstance(x,str) for x in (path,old,replacement)) or not path or not old:
            raise ValueError('patch requires path, nonempty find and replace')
        if len(old)>12000 or len(replacement)>12000:raise ValueError('patch too large')
        p=safe_path(self.root,path)
        if any(part in {'.git','.loopsieve','.venv','node_modules','__pycache__'} for part in p.relative_to(self.root).parts):
            raise PermissionError('system and dependency directories cannot be patched')
        if not p.is_file() or p.stat().st_size>1024*1024:raise ValueError('patch target unavailable or too big')
        before=p.read_text(encoding='utf-8')
        if before.count(old)!=1:raise ValueError('patch must uniquely match existing file content')
        checkpoint=self.journal.checkpoint(s['id'],path,before)
        after=before.replace(old,replacement,1)
        if len(after.encode())>1024*1024:raise ValueError('patched file exceeds size limit')
        # Atomic same-directory rename. Reject symlinks so agent cannot redirect writes.
        if p.is_symlink():raise PermissionError('symlink editing forbidden')
        fd,tmp=tempfile.mkstemp(prefix='.loopsieve-patch-',dir=p.parent)
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as out:out.write(after)
            os.chmod(tmp,p.stat().st_mode & 0o777)
            os.replace(tmp,p)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
        digest=hashlib.sha256(after.encode()).hexdigest()[:16]
        if path not in s['changed']:s['changed'].append(path)
        # Verification evidence cannot be reused after edits.
        s['evidence']=[]
        return {'patched':path,'sha256_16':digest,'verify_required':True,
                'checkpoint_id':checkpoint['id'],'checkpoint_sha256':checkpoint['sha256']}

    def _verify(self,s:dict,action:dict)->dict:
        if not s['allow_checks']:raise PermissionError('checks require explicit --allow-checks')
        paths=action.get('files') or s['changed']
        if not isinstance(paths,list) or not paths:raise ValueError('verify needs changed files')
        if len(paths)>50:raise ValueError('too many files')
        clean=[]
        for path in paths:
            if not isinstance(path,str):raise ValueError('invalid file path')
            clean.append(safe_path(self.root,path))
        cfg=load_config(self.root)
        if not cfg.checks:raise RuntimeErrorState('no configured checks; create .loopsieve.json')
        result=verify(self.root,clean,cfg)
        evidence={'status':'PASS' if result.passed else 'FAIL' if result.failed_results else 'UNVERIFIED',
                  'files':[p.relative_to(self.root).as_posix() for p in clean],
                  'output':_clean(result.context or result.skip_reason or '',4000),
                  'changed_files':sorted(s['changed'])}
        if result.passed:s['evidence'].append(evidence)
        return evidence

    def _action(self,s:dict,action:dict)->dict:
        verb=action.get('action')
        agent=load('agents',s['agent_id'])
        if verb not in agent.get('runtime',{}).get('allowed_actions',[]):
            raise PermissionError(f'{agent["name"]} is not permitted to perform {verb}')
        if self.permission_engine is not None:
            level=self.permission_engine.required_for_action(verb,action.get('tool'))
            self.permission_engine.require(s['id'],level,action=verb,details=f'role={agent["id"]}')
        if verb=='tree':return {'files':[p.relative_to(self.root).as_posix() for p in files(self.root,{'limit':70})][:70]}
        if verb=='inspect':return {'path':action.get('path'),'content':self._workspace_read(action.get('path',''))}
        if verb=='patch':return self._patch(s,action)
        if verb=='verify':return self._verify(s,action)
        if verb=='tool':
            name=action.get('tool');args=action.get('args') or {}
            if not isinstance(name,str) or not isinstance(args,dict):
                raise ValueError('tool action requires a string tool and object args')
            if name not in agent.get('allowed_tools',[]):
                raise PermissionError(f'{agent["name"]} is not permitted to use tool {name}')
            return {'tool':name,'result':run_tool(name,self.root,args)}
        if verb=='search':
            query=action.get('query');limit=min(max(int(action.get('limit',20)),1),60)
            if not isinstance(query,str) or not query.strip():raise ValueError('search needs a nonempty query')
            if 'search_text' in agent.get('allowed_tools',[]):name='search_text'
            elif 'search_regex' in agent.get('allowed_tools',[]):name='search_regex'
            else:raise PermissionError(f'{agent["name"]} has no search tool permission')
            return {'query':query,'tool':name,'results':run_tool(name,self.root,{'query':query,'pattern':query,'limit':limit})[:40]}
        if verb=='diff':
            if 'git_diff_stat' not in agent.get('allowed_tools',[]):raise PermissionError(f'{agent["name"]} has no git diff permission')
            return run_tool('git_diff_stat',self.root,{})
        if verb=='restore':
            if not s['allow_writes']:raise PermissionError('restore requires explicit --allow-writes')
            cid=action.get('checkpoint_id')
            if not isinstance(cid,int):raise ValueError('restore requires an integer checkpoint_id')
            return self.journal.restore_checkpoint(s['id'],cid)
        if verb=='finish':
            if s['step']==0 and not s['changed'] and not s['evidence']:
                raise RuntimeErrorState('completion needs an observed tool action or verification evidence')
            # Cannot deliver an edited codebase without real, current positive evidence.
            if s['changed'] and not any(e['status']=='PASS' and sorted(e['changed_files'])==sorted(s['changed']) for e in s['evidence']):
                raise RuntimeErrorState('cannot finish edited task without fresh PASS verification')
            summary=action.get('summary','')
            if not isinstance(summary,str) or not summary.strip():raise ValueError('summary required')
            s['status']='COMPLETED'
            return {'summary':_clean(summary,3000),'verified':bool(s['evidence']),'changed':s['changed']}
        if verb=='blocked':
            s['status']='BLOCKED';return {'reason':_clean(str(action.get('reason','no reason')))}
        raise ValueError(f'unsupported agent action {verb!r}')

    def step(self,session_id:str)->dict:
        s=self.journal.get(session_id)
        if s['status'] in TERMINAL or s['status']=='PAUSED':raise RuntimeErrorState(f'session is {s["status"]}')
        if s['step']>=s['max_steps']:
            s['status']='FAILED';self.journal.save(s)
            self.journal.event(s['id'],'budget_exhausted',{'max_steps':s['max_steps']})
            return s
        agent=load('agents',s['agent_id'])
        self.journal.claim(session_id)
        try:
            decision=self.provider.complete(s['messages'],agent)
            if not isinstance(decision,dict):raise ValueError('provider returned non-JSON-object decision')
            observed=self.journal.get(session_id)
            if observed['status'] in ('PAUSED','CANCELLED','TERMINATED'):
                self.journal.event(session_id,'discarded_late_decision',{'status':observed['status']})
                return observed
            s['status']='WORKING';self.journal.save(s)
            result=self._action(s,decision)
            message={'ok':True,'data':result}
        except Exception as exc:
            # A denied or invalid model proposal is a tool error, not a fallback to unrestricted shell.
            message={'ok':False,'error':f'{type(exc).__name__}: {_clean(str(exc),500)}'}
            if self.health_monitor is not None:
                try:self.health_monitor.record_failure(getattr(self.provider,'provider_id',type(self.provider).__name__),exc)
                except Exception:pass
            if 'ProviderError' == type(exc).__name__:
                s['status']='BLOCKED'
        s['step']+=1
        s['messages'].append({'role':'assistant','content':_clean(json.dumps(decision if 'decision' in locals() else {'error':'provider unavailable'},ensure_ascii=False),2500)})
        s['messages'].append({'role':'tool','content':_clean(json.dumps(message,ensure_ascii=False),5500)})
        if len(s['messages'])>15:s['messages']=[s['messages'][0]]+s['messages'][-14:]
        observed=self.journal.get(session_id)
        if observed['status'] in ('PAUSED','CANCELLED','TERMINATED'):
            self.journal.event(session_id,'discarded_late_result',{'status':observed['status']})
            return observed
        if s['status'] not in TERMINAL:s['status']='READY'
        self.journal.save(s)
        self.journal.event(s['id'],'step',{'number':s['step'],'action':decision.get('action') if 'decision' in locals() else None,'result':message})
        return s

    def run(self,session_id:str)->dict:
        while True:
            s=self.journal.get(session_id)
            if s['status'] in TERMINAL or s['status']=='PAUSED':return s
            if s['step']>=s['max_steps']:
                s['status']='FAILED';self.journal.save(s)
                self.journal.event(s['id'],'budget_exhausted',{'limit':s['max_steps']})
                return s
            self.step(session_id)

    def recover(self,stale_seconds:int=0)->list[dict]:
        """Reset interrupted non-terminal sessions after a crash. Active work is never silently overwritten."""
        recovered=[]
        now=time.time()
        for summary in self.journal.list():
            if summary['status'] not in ('READY','PLANNING','WORKING'):continue
            s=self.journal.get(summary['id'])
            if stale_seconds and now-float(s.get('updated',now))<stale_seconds:continue
            if s['status'] in ('PLANNING','WORKING'):
                s['status']='READY';self.journal.save(s)
                self.journal.event(s['id'],'recovered',{'from':summary['status']})
            recovered.append({'id':s['id'],'agent_id':s['agent_id'],'status':s['status'],'task':s['task']})
        return recovered

    def pause(self,sid:str)->dict:
        s=self.journal.get(sid)
        if s['status'] in TERMINAL:raise RuntimeErrorState('terminal session cannot be paused')
        s['status']='PAUSED';self.journal.save(s);self.journal.event(sid,'paused',{});return s
    def cancel(self,sid:str)->dict:
        s=self.journal.get(sid)
        if s['status'] in TERMINAL:return s
        s['status']='CANCELLED';self.journal.save(s);self.journal.event(sid,'cancelled',{});return s
    def resume(self,sid:str)->dict:
        s=self.journal.get(sid)
        if s['status'] not in ('PAUSED','READY','PLANNING','WORKING'):
            raise RuntimeErrorState('session is not resumable')
        s['status']='READY';self.journal.save(s)
        return self.run(sid)
