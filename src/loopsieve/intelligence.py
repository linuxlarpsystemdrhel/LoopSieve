"""Deterministic, explainable local context and session analytics.

No embeddings, LLM, third-party service, or indexed private credentials needed.
"""
from __future__ import annotations
import ast
import hashlib
import json
import re
import shutil
import subprocess
import zipfile
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path

from .agents import list_agents
from .agent_runtime import Journal
from .toolkit import files,safe_path


def symbol_index(root:Path)->list[dict]:
    rows=[]
    for p in files(root,{'limit':500}):
        if p.suffix!='.py' or p.stat().st_size>250000:continue
        try:source=p.read_text(encoding='utf-8');tree=ast.parse(source)
        except (UnicodeError,SyntaxError):continue
        for node in ast.walk(tree):
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
                rows.append({'file':p.relative_to(root).as_posix(),'name':node.name,
                             'type':type(node).__name__,'line':node.lineno})
            if len(rows)>=2500:return rows
    return rows


def import_graph(root:Path)->dict[str,list[str]]:
    graph={}
    for p in files(root,{'limit':600}):
        if p.suffix!='.py' or p.stat().st_size>250000:continue
        try:tree=ast.parse(p.read_text(encoding='utf-8'))
        except (UnicodeError,SyntaxError):continue
        names=set()
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):names.update(alias.name.split('.')[0] for alias in node.names)
            elif isinstance(node,ast.ImportFrom) and node.module:names.add(node.module.split('.')[0])
        graph[p.relative_to(root).as_posix()]=sorted(names)
    return graph


def context_packet(root:Path,query:str,max_chars:int=5000)->dict:
    if not 300<=max_chars<=15000:raise ValueError('context budget 300..15000 chars')
    terms=set(re.findall(r'\w+',query.lower()))-{'the','for','and','with','from','this','that'}
    if not terms:raise ValueError('query needs identifying words')
    matches=[]
    for p in files(root,{'limit':600}):
        if p.stat().st_size>150000 or p.suffix not in ('.py','.rs','.go','.ts','.tsx','.js','.json','.toml','.md'):continue
        try:lines=p.read_text(errors='replace').splitlines()
        except OSError:continue
        rank=0;scored=[]
        for n,line in enumerate(lines,1):
            if len(line)>1000:continue
            score=sum(1 for term in terms if term in line.lower())
            if score:scored.append((score,n,line.strip()[:280]));rank+=score
        if rank:matches.append((rank,p.relative_to(root).as_posix(),scored))
    matches.sort(reverse=True)
    result=[];size=0
    for score,path,lines in matches[:40]:
        for weight,n,text in sorted(lines,key=lambda x:-x[0])[:12]:
            obj={'file':path,'line':n,'text':text}
            length=len(json.dumps(obj,ensure_ascii=False))
            if size+length>max_chars:break
            result.append(obj);size+=length
        if size>=max_chars-500:break
    return {'query':query[:300],'matches':result,'packed_chars':size,'budget_chars':max_chars,
            'files_considered':len(matches),'method':'local_literal_relevance_no_embeddings'}


def permission_preview(agent_id:str,allow_writes=False,allow_checks=False)->dict:
    from .catalog import load
    agent=load('agents',agent_id)
    actions=list(agent.get('runtime',{}).get('allowed_actions',[]))
    active=[name for name in actions if not (name=='patch' and not allow_writes) and not (name=='verify' and not allow_checks)]
    return {'agent':agent_id,'available_actions':active,'denied_by_session':sorted(set(actions)-set(active)),
            'shell_execution':False,'network_tool_execution':False,'permission_escalation':False}


def reliability_profiles(journal:Journal)->list[dict]:
    by={}
    for session in journal.list():
        obj=by.setdefault(session['agent_id'],Counter())
        obj[session['status']]+=1
    return [dict(agent_id=agent,completed=counts.get('COMPLETED',0),failed=counts.get('FAILED',0),
                 blocked=counts.get('BLOCKED',0),total=sum(counts.values())) for agent,counts in sorted(by.items())]


def session_capsule(journal:Journal,session_id:str,path:Path)->dict:
    """Export evidence and file hashes, no project file content or provider credentials."""
    s=journal.get(session_id)
    entries=[]
    for name in s['changed']:
        p=safe_path(journal.root,name)
        entries.append({'path':name,'exists':p.is_file(),
                        'sha256':hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None})
    capsule={'version':1,'session_id':session_id,'agent':s['agent_id'],'status':s['status'],
             'steps':s['step'],'files':entries,'evidence':s['evidence'],
             'created_utc':datetime.now(timezone.utc).isoformat(),
             'comment':'No source files, model messages or API credentials are included.'}
    dest=path.resolve()
    if dest.exists():raise FileExistsError('refusing to overwrite existing capsule')
    dest.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(dest,'x',compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('manifest.json',json.dumps(capsule,indent=2))
        z.writestr('REPLAY.md',f'# LoopSieve session {session_id}\n\nInspect the manifest and reproduce checks locally.\n\nOriginal source files are not included.\n')
    return {'path':str(dest),'manifest':capsule}


def source_diff(root:Path,max_chars:int=10000)->dict:
    if not shutil.which('git'):return {'status':'REQUIRES_DEPENDENCY','dependency':'git'}
    proc=subprocess.run(['git','-C',str(root),'diff','--no-ext-diff','--','.' ],
                        stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=8)
    return {'exit_code':proc.returncode,'diff':proc.stdout.decode(errors='replace')[:max_chars],
            'truncated':len(proc.stdout)>max_chars}
