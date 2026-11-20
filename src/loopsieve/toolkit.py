"""Built-in, read-only local developer tools.

Every registered tool has an actual implementation, explicit inputs, and a
workspace boundary. Tools never evaluate shell strings or fetch network data.
"""
from __future__ import annotations

import ast
import configparser
import csv
import difflib
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tomllib
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path
from typing import Callable
from zipfile import ZipFile

REGISTRY: dict[str, tuple[str, Callable]] = {}
EXCLUDE = {'.git', '.venv', 'venv', 'node_modules', '.mypy_cache', '__pycache__', '.pytest_cache', 'build', 'dist'}
SENSITIVE = re.compile(r'(^|/)(?:\.env(?:\..*)?|id_rsa|id_ed25519|credentials(?:\.json)?|secrets?(?:\..*)?|\.npmrc|\.pypirc|\.ssh|\.git|\.claude|\.loopsieve|[^/]*\.(?:pem|key))(?:$|/)', re.I)


def tool(description: str):
    def decorator(fn: Callable):
        REGISTRY[fn.__name__] = (description, fn)
        return fn
    return decorator


def safe_path(root: Path, name: str) -> Path:
    root = root.resolve()
    p = (root / name).resolve()
    if not p.is_relative_to(root):
        raise PermissionError('path escapes workspace')
    rel = p.relative_to(root).as_posix()
    if SENSITIVE.search(rel):
        raise PermissionError('sensitive file is blocked')
    return p


def file_arg(root: Path, args: dict) -> Path:
    return safe_path(root, str(args.get('path', 'README.md')))


def read_file(root: Path, args: dict) -> str:
    p = file_arg(root, args)
    if p.stat().st_size > 1024 * 1024:
        raise ValueError('file exceeds 1 MiB read limit')
    return p.read_text(encoding='utf-8', errors='replace')


def files(root: Path, args: dict):
    limit = min(max(int(args.get('limit', 500)), 1), 3000)
    result = []
    for base, dirs, names in os.walk(root):
        dirs[:] = [d for d in sorted(dirs) if d not in EXCLUDE and not (Path(base)/d).is_symlink()]
        for name in sorted(names):
            p = Path(base)/name
            if p.is_symlink(): continue
            relative = p.relative_to(root).as_posix()
            if not SENSITIVE.search(relative): result.append(p)
            if len(result) >= limit: return result
    return result


def simple_git(root: Path, command: list[str]):
    if not shutil.which('git'): return {'status':'REQUIRES_DEPENDENCY','dependency':'git'}
    p = subprocess.run(['git', '-C', str(root), *command], capture_output=True, text=True, timeout=10)
    return {'exit_code':p.returncode, 'output':p.stdout[:15000], 'error':p.stderr[:1000]}


@tool('List tracked project source files with safe traversal')
def workspace_tree(root, args): return [p.relative_to(root).as_posix() for p in files(root, args)]

@tool('Read a bounded UTF-8 workspace file')
def file_read(root, args): return read_file(root, args)[:min(int(args.get('max_chars', 8000)), 16000)]

@tool('Read numbered lines from a file')
def file_lines(root, args):
    start = max(1, int(args.get('start', 1))); count = min(100, max(1, int(args.get('count', 20))))
    return [{'number':i+1, 'text':v} for i,v in enumerate(read_file(root,args).splitlines()) if start-1<=i<start-1+count]

@tool('Read beginning of a text file')
def file_head(root,args): return read_file(root,args).splitlines()[:min(100,int(args.get('lines',10)))]

@tool('Read end of a text file')
def file_tail(root,args): return read_file(root,args).splitlines()[-min(100,int(args.get('lines',10))):]

@tool('Retrieve metadata without following out-of-workspace symlinks')
def file_stat(root,args):
    p=file_arg(root,args); st=p.stat(); return {'bytes':st.st_size,'mtime_ns':st.st_mtime_ns,'is_file':p.is_file()}

@tool('Calculate a source file SHA-256')
def file_sha256(root,args): return hashlib.sha256(file_arg(root,args).read_bytes()).hexdigest()

@tool('Return file size in bytes')
def file_size(root,args): return file_arg(root,args).stat().st_size

@tool('Return a file extension')
def file_extension(root,args): return file_arg(root,args).suffix.lower()

@tool('Count safely discoverable files')
def file_count(root,args): return len(files(root,args))

@tool('Find filenames matching a case-insensitive substring')
def file_search_name(root,args): return [p.relative_to(root).as_posix() for p in files(root,args) if str(args.get('query','README')).lower() in p.name.lower()]

@tool('Search source file content for literal text')
def search_text(root,args):
    query=str(args.get('query','def ')); result=[]
    for p in files(root,args):
        if p.stat().st_size>200000: continue
        for i,line in enumerate(p.read_text(errors='replace').splitlines(),1):
            if query in line: result.append({'file':p.relative_to(root).as_posix(),'line':i,'snippet':line[:200]})
            if len(result)>=60: return result
    return result

@tool('Search source code using a bounded regular expression')
def search_regex(root,args):
    pattern=str(args.get('pattern',r'\bclass\s+'))
    if len(pattern)>120: raise ValueError('pattern too long')
    regex=re.compile(pattern); result=[]
    for p in files(root,args):
        if p.stat().st_size>200000: continue
        for i,line in enumerate(p.read_text(errors='replace').splitlines(),1):
            if len(line)<5000 and regex.search(line): result.append([p.relative_to(root).as_posix(),i,line[:200]])
            if len(result)>=60: return result
    return result

@tool('Find files with duplicate SHA-256 digests')
def duplicate_hashes(root,args):
    groups=defaultdict(list)
    for p in files(root,args):
        if p.stat().st_size<=1048576: groups[hashlib.sha256(p.read_bytes()).hexdigest()].append(p.relative_to(root).as_posix())
    return [v for v in groups.values() if len(v)>1]

@tool('Find largest files within the project')
def list_large_files(root,args): return sorted([{'file':p.relative_to(root).as_posix(),'bytes':p.stat().st_size} for p in files(root,args)],key=lambda x:-x['bytes'])[:20]

@tool('Count project file extensions')
def extension_inventory(root,args): return dict(Counter(p.suffix.lower() or '<none>' for p in files(root,args)))

@tool('Generate a unified diff from two workspace text files')
def file_diff(root,args):
    a=read_file(root,args).splitlines(); b=read_file(root,{'path':args.get('other','CHANGELOG.md')}).splitlines()
    return '\n'.join(list(difflib.unified_diff(a,b,fromfile=args.get('path','README.md'),tofile=args.get('other','CHANGELOG.md')))[:150])

@tool('Inspect entries in a ZIP archive without extraction')
def archive_zip_list(root,args):
    with ZipFile(file_arg(root,args)) as z: return [{'file':x.filename,'size':x.file_size} for x in z.infolist()[:100]]

@tool('Validate JSON and return basic structure')
def json_validate(root,args):
    value=json.loads(read_file(root,args)); return {'valid':True,'type':type(value).__name__}

@tool('Show top-level JSON object keys')
def json_keys(root,args):
    value=json.loads(read_file(root,args)); return sorted(value) if isinstance(value,dict) else []

@tool('Validate YAML with optional PyYAML')
def yaml_validate(root,args):
    try: import yaml
    except ImportError: return {'status':'REQUIRES_DEPENDENCY','dependency':'PyYAML'}
    return {'valid':True,'type':type(yaml.safe_load(read_file(root,args))).__name__}

@tool('Validate TOML syntax')
def toml_validate(root,args): return {'valid': isinstance(tomllib.loads(read_file(root,args)),dict)}

@tool('Validate XML markup')
def xml_validate(root,args): return {'root_tag':ET.fromstring(read_file(root,args)).tag}

@tool('Extract sections from INI config')
def ini_sections(root,args):
    cfg=configparser.ConfigParser(); cfg.read_string(read_file(root,args)); return cfg.sections()

@tool('Inspect CSV column names and row count')
def csv_columns(root,args):
    rows=list(csv.reader(read_file(root,args).splitlines()));return {'columns':rows[0] if rows else [],'rows':max(0,len(rows)-1)}

@tool('Extract Markdown heading hierarchy')
def markdown_headings(root,args): return [x.strip() for x in read_file(root,args).splitlines() if x.startswith('#')]

@tool('Extract Markdown links')
def markdown_links(root,args): return [{'label':x,'url':y} for x,y in re.findall(r'\[([^\]]+)\]\(([^)]+)\)', read_file(root,args))][:100]


def python_tree(root,args): return ast.parse(read_file(root,args),filename=str(file_arg(root,args)))

@tool('Enumerate Python AST top-level definitions')
def python_ast_symbols(root,args): return [{'name':n.name,'line':n.lineno,'type':type(n).__name__} for n in python_tree(root,args).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))]

@tool('List Python module imports')
def python_imports(root,args):
    return sorted({a.name.split('.')[0] for n in ast.walk(python_tree(root,args)) if isinstance(n,ast.Import) for a in n.names} | {n.module or '' for n in ast.walk(python_tree(root,args)) if isinstance(n,ast.ImportFrom)})

@tool('List Python function definitions')
def python_functions(root,args): return [{'name':n.name,'line':n.lineno} for n in ast.walk(python_tree(root,args)) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))]

@tool('List Python class definitions')
def python_classes(root,args): return [n.name for n in ast.walk(python_tree(root,args)) if isinstance(n,ast.ClassDef)]

@tool('Check Python function/class docstring presence')
def python_docstrings(root,args): return [{'name':n.name,'documented':bool(ast.get_docstring(n))} for n in ast.walk(python_tree(root,args)) if isinstance(n,(ast.FunctionDef,ast.ClassDef))]

@tool('Find TODO/FIXME comments in Python source')
def python_todo(root,args): return [(i,x.strip()) for i,x in enumerate(read_file(root,args).splitlines(),1) if re.search(r'\b(?:TODO|FIXME)\b',x)]

@tool('Parse and validate Python source syntax')
def python_syntax(root,args): python_tree(root,args); return {'valid':True}

@tool('Count Python source lines, blanks and comments')
def python_line_count(root,args):
    ls=read_file(root,args).splitlines();return {'total':len(ls),'blank':sum(not l.strip() for l in ls),'comment':sum(l.lstrip().startswith('#') for l in ls)}

@tool('Count major Python AST control-flow structures')
def python_complexity(root,args): return dict(Counter(type(n).__name__ for n in ast.walk(python_tree(root,args)) if isinstance(n,(ast.If,ast.For,ast.While,ast.Try,ast.With,ast.Match))))

@tool('Inspect Python requirements.txt lines')
def requirements_read(root,args): return [l.strip() for l in read_file(root,args).splitlines() if l.strip() and not l.startswith('#')]

@tool('Read PEP 621 project metadata')
def pyproject_meta(root,args): return tomllib.loads(read_file(root,args)).get('project',{})

@tool('List scripts in npm package manifest')
def package_scripts(root,args): return json.loads(read_file(root,args)).get('scripts',{})

@tool('List direct npm package dependencies')
def package_deps(root,args):
    data=json.loads(read_file(root,args));return {'dependencies':data.get('dependencies',{}),'devDependencies':data.get('devDependencies',{})}

@tool('Parse Go module requirements')
def go_modules(root,args): return [line.strip() for line in read_file(root,args).splitlines() if line.lstrip().startswith(('module ','require '))]

@tool('Inspect Cargo package metadata')
def cargo_packages(root,args): return tomllib.loads(read_file(root,args)).get('package',{})

@tool('Run read-only git status')
def git_status(root,args): return simple_git(root,['status','--short'])

@tool('List local git branches')
def git_branches(root,args): return simple_git(root,['branch','--list'])

@tool('Read recent commit subjects')
def git_log(root,args): return simple_git(root,['log','-8','--oneline'])

@tool('Inspect the diff summary')
def git_diff_stat(root,args): return simple_git(root,['diff','--stat'])

@tool('List tracked git files')
def git_files(root,args): return simple_git(root,['ls-files'])

@tool('List git remote names')
def git_remotes(root,args): return simple_git(root,['remote'])

@tool('List recent git tags')
def git_tags(root,args): return simple_git(root,['tag','-l'])

@tool('Get HEAD commit ID')
def git_commit_info(root,args): return simple_git(root,['rev-parse','--verify','HEAD'])

@tool('List ignored paths safely')
def git_ignored(root,args): return simple_git(root,['ls-files','--others','--ignored','--exclude-standard'])

@tool('Discover common project configuration files')
def config_files(root,args): return [p.relative_to(root).as_posix() for p in files(root,args) if p.name in {'pyproject.toml','package.json','Cargo.toml','go.mod','tsconfig.json','.loopsieve.json','pytest.ini','setup.cfg'}]

@tool('Discover package manager lockfiles')
def lock_files(root,args): return [p.relative_to(root).as_posix() for p in files(root,args) if p.name in {'package-lock.json','Cargo.lock','poetry.lock','uv.lock','pnpm-lock.yaml','yarn.lock','go.sum'}]

@tool('Inspect interpreter and OS information')
def env_runtime(root,args): return {'python':sys.version.split()[0],'os':platform.system(),'architecture':platform.machine(),'cwd':str(root)}

@tool('Check whether common developer executables are available')
def environment_paths(root,args): return {x:bool(shutil.which(x)) for x in ('git','python','node','npm','go','cargo','docker','clang','ruff','pytest')}

@tool('Read current process RSS via psutil when installed')
def process_memory(root,args):
    try: import psutil
    except ImportError:return {'status':'REQUIRES_DEPENDENCY','dependency':'psutil'}
    return {'rss_bytes':psutil.Process(os.getpid()).memory_info().rss}

@tool('Discover unittest modules without running them')
def unit_discovery(root,args): return [p.relative_to(root).as_posix() for p in files(root,args) if p.name.startswith('test_') and p.suffix=='.py']

@tool('Hash all discovered files into a workspace content digest')
def project_digest(root,args):
    h=hashlib.sha256()
    for p in files(root,args):
        if p.stat().st_size<1048576:
            h.update(p.relative_to(root).as_posix().encode()); h.update(hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()

@tool('Search for suspicious credential assignments without returning secret values')
def secret_pattern_scan(root,args):
    matches=[]
    regex=re.compile(r'(?i)\b(api[_-]?key|secret[_-]?key|access[_-]?token|password)\b\s*[:=]')
    for p in files(root,args):
        if p.stat().st_size>200000: continue
        for i,line in enumerate(p.read_text(errors='replace').splitlines(),1):
            if regex.search(line): matches.append({'file':p.relative_to(root).as_posix(),'line':i,'kind':'candidate credential assignment'})
            if len(matches)>=50:return matches
    return matches

@tool('List external symlinks and unsafe workspace paths without opening them')
def workspace_symlinks(root,args):
    result=[]
    for base,dirs,names in os.walk(root):
        dirs[:]=[d for d in dirs if d not in EXCLUDE]
        for name in dirs+names:
            p=Path(base)/name
            if p.is_symlink():result.append(p.relative_to(root).as_posix())
            if len(result)>=50:return result
    return result

@tool('Locate TODO/FIXME comments across source files')
def task_comments(root,args):
    result=[]
    for p in files(root,args):
        if p.stat().st_size>200000:continue
        for i,line in enumerate(p.read_text(errors='replace').splitlines(),1):
            if re.search(r'\b(TODO|FIXME)\b',line):result.append({'file':p.relative_to(root).as_posix(),'line':i})
            if len(result)>=80:return result
    return result

@tool('Check basic repository release files')
def release_readiness(root,args):
    names=['README.md','LICENSE','CHANGELOG.md','SECURITY.md','CONTRIBUTING.md','.github/workflows/ci.yml']
    return {n:(root/n).is_file() for n in names}

@tool('Summarize latest LoopSieve local verification results')
def verification_report(root,args):
    from .config import load_config
    from .engine import state_report
    return state_report(root,load_config(root))


def tool_catalog():
    return [{'id':name,'description':description,'permission':'workspace:read','input_schema':{'type':'object'},'output_schema':{'type':'json-compatible'},'timeout_seconds':15} for name,(description,_) in sorted(REGISTRY.items())]


def run_tool(name: str, root: Path, args: dict | None=None):
    if name not in REGISTRY: raise ValueError(f'unknown tool: {name}')
    if not isinstance(args,dict): raise TypeError('tool arguments must be an object')
    return REGISTRY[name][1](root.resolve(),args)
