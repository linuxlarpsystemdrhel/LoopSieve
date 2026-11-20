"""Evidence-first local code intelligence and task risk analysis."""
from __future__ import annotations

import ast
import hashlib
import json
import re
from collections import defaultdict, deque
from pathlib import Path

from .toolkit import files, safe_path


def python_impact(root: Path, changed: list[str]) -> dict:
    """Reverse import graph for root-level and package modules. Incomplete, never a verification proof."""
    root = Path(root).resolve()
    paths = [p for p in files(root, {'limit': 1500}) if p.suffix == '.py' and p.stat().st_size < 300000]
    module_by_path = {}
    for p in paths:
        rel = p.relative_to(root)
        if rel.name == '__init__.py':
            module = '.'.join(rel.parent.parts)
        else:
            module = '.'.join(rel.with_suffix('').parts)
        if module: module_by_path[module] = rel.as_posix()
    reverse: dict[str,set[str]] = defaultdict(set)
    for p in paths:
        rel = p.relative_to(root).as_posix()
        try: tree = ast.parse(p.read_text(encoding='utf-8'))
        except (SyntaxError,UnicodeError,OSError): continue
        imports = set()
        for n in ast.walk(tree):
            if isinstance(n,ast.Import):
                imports.update(x.name for x in n.names)
            elif isinstance(n,ast.ImportFrom):
                if n.level:
                    pkg = p.relative_to(root).parent.parts[:max(0, len(p.relative_to(root).parent.parts)-(n.level-1))]
                    base = '.'.join((*pkg,*(n.module.split('.') if n.module else [])))
                else: base = n.module or ''
                imports.add(base)
                imports.update(base+'.'+a.name for a in n.names)
        for candidate in imports:
            parts=candidate.split('.')
            for i in range(len(parts),0,-1):
                match=module_by_path.get('.'.join(parts[:i]))
                if match and match!=rel:
                    reverse[match].add(rel)
                    break
    origins=[]
    for x in changed:
        checked=safe_path(root,x)
        origins.append(checked.relative_to(root).as_posix())
    queue=deque((x,0) for x in origins)
    affected={}; reasons={}
    while queue:
        node, depth=queue.popleft()
        for importer in sorted(reverse.get(node, [])):
            if importer in origins or importer in affected:continue
            affected[importer]=depth+1
            reasons[importer]=f'import depends on {node}'
            queue.append((importer,depth+1))
    return {'changed': origins,'potentially_affected': [{'file': f, 'distance':d,'reason':reasons[f]}
                for f,d in sorted(affected.items(),key=lambda x:(x[1],x[0]))],
            'confidence':'partial: Python static imports only; dynamic imports, side effects and external dependencies are not resolved',
            'verified': False}


def compile_context(root: Path, query: str, budget: int = 6000) -> dict:
    """Line-based ranked excerpts with source hashes and bounded context."""
    if not 300<=budget<=20000: raise ValueError('context budget must be 300..20000')
    terms=[x for x in re.findall(r'[\w]{3,}',query.lower()) if x not in {'with','from','that','this','file','code','the'}]
    if not terms:raise ValueError('query needs meaningful terms')
    root=Path(root).resolve();matches=[]
    for p in files(root, {'limit':800}):
        if p.suffix.lower() not in {'.py','.rs','.js','.ts','.tsx','.go','.cpp','.hpp','.md','.toml'}:continue
        if p.stat().st_size>150000:continue
        try: content=p.read_text(encoding='utf-8')
        except (UnicodeError,OSError):continue
        h=hashlib.sha256(content.encode()).hexdigest()
        rel=p.relative_to(root).as_posix()
        for i,line in enumerate(content.splitlines(),1):
            if len(line)>500:continue
            score=sum(4 if t in rel.lower() else 1 for t in set(terms) if t in line.lower())
            if score:
                matches.append((score,rel,i,line[:220],h))
    matches.sort(key=lambda x:(-x[0],x[1],x[2]))
    excerpts=[];used=0
    for score,rel,lineno,line,h in matches:
        item={'path':rel,'line':lineno,'score':score,'text':line,'source_sha256':h}
        size=len(json.dumps(item,ensure_ascii=False))
        if used+size>budget:continue
        excerpts.append(item); used+=size
    return {'query':query,'budget_chars':budget,'approx_chars':used,'excerpts':excerpts,
            'files_considered':len({x[1] for x in matches}), 'policy':'source-backed snippets only; no proof of semantic completeness'}


def check_contract(task: str, acceptance: list[str], *, max_items: int = 24) -> dict:
    """Validate explicit, non-placeholder acceptance criteria without pretending to generate tests."""
    if not isinstance(task,str) or len(task.strip())<10:raise ValueError('task description too short')
    if not isinstance(acceptance,list) or not 1<=len(acceptance)<=max_items:
        raise ValueError('acceptance criteria must contain 1..24 items')
    criteria=[]
    for i,text in enumerate(acceptance,1):
        if not isinstance(text,str) or len(text.strip())<12 or len(text)>400:
            raise ValueError(f'criterion {i} needs 12..400 characters')
        if re.fullmatch(r'(?:todo|tbd|test|works|pass|ok)[.! ]*',text.strip(),re.I):
            raise ValueError(f'criterion {i} is not testable')
        criteria.append({'id':f'AC-{i:03d}','description':text.strip(),'status':'UNVERIFIED'})
    return {'task':task,'criteria':criteria,'gate':'BLOCKED_UNTIL_EVIDENCE'}


def detect_doc_conflicts(root: Path) -> list[dict]:
    """Find conflicting Python dependency pins between common requirements sources."""
    root=Path(root).resolve();versions=defaultdict(list)
    for p in (root/'requirements.txt',root/'requirements-dev.txt'):
        if not p.is_file():continue
        for i,line in enumerate(p.read_text(errors='replace').splitlines(),1):
            m=re.match(r'^([A-Za-z0-9_.-]+)==([^\s;#]+)',line.strip())
            if m:versions[m.group(1).lower().replace('_','-')].append((m.group(2),p.name,i))
    return [{'package':name,'pins':[{'version':v,'file':f,'line':n} for v,f,n in entries]}
            for name,entries in sorted(versions.items()) if len(set(e[0] for e in entries))>1]
