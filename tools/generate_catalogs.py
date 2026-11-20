"""Deterministic source-data generation. Run from the repository root."""
import json
import re
from pathlib import Path

BASE=Path('src/loopsieve/data')
for folder in ('agents','skills','plugins','technologies'):
    (BASE/folder).mkdir(parents=True,exist_ok=True)

# name | discoverable keywords | precise expected artifact | quality gate
ROLE_ROWS = '''
Chief Architect|architecture design decomposition|module boundary map|No cyclic dependencies in public interfaces
Python Engineer|python py pytest|typed Python implementation plan|AST parses and tests cover edge conditions
TypeScript Engineer|typescript ts typecheck|strict TypeScript implementation plan|No any-typed public surfaces
JavaScript Engineer|javascript js runtime|JavaScript compatibility analysis|Node/browser assumptions documented
Rust Engineer|rust cargo lifetimes|borrow-safe Rust module design|cargo check acceptance criterion
C++ Engineer|cpp cxx cmake|C++ ownership and ABI review|RAII used for resource ownership
Go Engineer|golang go modules|idiomatic Go concurrency plan|go test plus race mode when available
Java Engineer|java jvm maven|Java implementation guidance|No unchecked exception masking
Kotlin Engineer|kotlin android coroutine|coroutine and null-safety review|Cancellation behavior checked
CSharp Engineer|csharp dotnet aspnet|C# service design|Async disposal reviewed
Swift Engineer|swift ios macos|Swift concurrency review|MainActor constraints documented
Frontend Engineer|frontend react vue html|component implementation outline|Responsive states enumerated
Backend Engineer|backend server services|service contract and error flow|Failure states are specified
API Engineer|api rest openapi endpoints|HTTP endpoint contract|Status codes and pagination tested
Database Architect|database schema migrations|transactional schema design|Rollback and locking considered
SQL Optimizer|sql query index|query plan recommendation|Explain plan required for performance claims
GraphQL Engineer|graphql resolver schema|query complexity review|N+1 potential assessed
Microservices Engineer|microservices integration tracing|service boundary proposal|Retry and idempotency considered
Concurrency Engineer|threads locks async|race-safety proof obligations|Lock ordering described
Distributed Systems Engineer|distributed consensus messaging|consistency model statement|Partial failure scenarios included
Migration Engineer|migration upgrade schema|reversible migration checklist|Backward compatibility tested
Legacy Maintenance Engineer|legacy compatibility refactor|minimal-impact change plan|Behavior preserved under regression suite
Build Systems Engineer|build cmake ninja make|reproducible build plan|Outputs deterministic under pinned inputs
Package Maintainer|package pip npm publishing|package release manifest|Dependencies and license checked
Code Reviewer|review diff quality|actionable review findings|Each finding links to evidence
ML Systems Scientist|machine learning training ml|experiment protocol|Baselines and seeds recorded
Transformer Engineer|transformer attention qkv|attention implementation review|Shape and masking validated
Inference Engineer|inference runtime latency|inference serving design|Latency and memory measured
Quantization Engineer|quantization gguf compression|quantization benchmark proposal|PPL assessed against same reference data
Fine-Tuning Engineer|finetune lora adapters|training adjustment plan|Train and evaluation leakage checked
Model Evaluation Engineer|benchmark evaluation model|evaluation dataset card|Statistical variance reported
Retrieval Engineer|retrieval rag search|retrieval relevance experiment|Recall and precision measured
Vector Database Engineer|vector embedding ann|index configuration plan|Recall-latency tradeoff measured
Prompt Systems Engineer|prompt template system|controlled prompting experiment|Prompt injection tests included
Agent Orchestrator|agent scheduler routing|bounded task delegation plan|No unnecessary parallel calls
Multimodal Engineer|multimodal vision text|cross-modal interface contract|Input modality assumptions declared
Computer Vision Engineer|vision images detection|image model pipeline proposal|Dataset shifts evaluated
Speech Systems Engineer|speech asr tts|speech inference workflow|Real-time latency accounted for
Dataset Curator|dataset metadata cleaning|dataset provenance checklist|Licensing and dedup verified
Model Security Engineer|model safety poisoning|model threat assessment|Unsafe artifacts are isolated
DevOps Engineer|devops infrastructure deployment|deployment runbook|Rollback procedure ready
CI CD Engineer|ci github actions pipelines|deterministic CI workflow|Tests actually execute on supported platforms
Docker Engineer|docker container images|container hardening checklist|Least privilege demonstrated
Kubernetes Engineer|k8s kubernetes helm|cluster manifest review|Resource limits and probes present
Linux Engineer|linux shell procfs|Linux diagnostics guide|OS-specific assumptions noted
Windows Engineer|windows powershell win32|Windows compatibility plan|Paths and subprocess behavior checked
MacOS Engineer|macos darwin launchd|macOS integration review|Code signing requirements stated
Network Engineer|tcp http dns network|network fault isolation plan|Timeout and retry limits defined
Observability Engineer|logs traces metrics|instrumentation map|Cardinality and redaction reviewed
Performance Profiler|profiling cpu memory|profiling experiment|Measured bottleneck not guessed
Cloud Architect|cloud aws azure gcp|cloud isolation and cost review|Minimal credentials and costs documented
Storage Engineer|storage filesystem cache|storage reliability analysis|Corruption recovery considered
Reliability Engineer|sre availability|failure mode analysis|SLO and recovery paths described
Incident Responder|incident outage triage|incident timeline|Facts separated from hypotheses
Release Engineer|release changelog tags|release validation checklist|Rollback verified before publication
AppSec Auditor|appsec code security|exploitability assessment|Findings have reproducible cases
Supply Chain Auditor|supplychain sbom provenance|dependency provenance report|Pinned hashes and license reviewed
Secrets Auditor|secret key leakage|redacted credential audit|No sensitive values printed
Authentication Engineer|authentication oauth login|authentication flow threat model|Session expiry and revocation covered
Authorization Engineer|authorization permissions rbac|permission matrix|Privilege escalation probes enumerated
Threat Modeler|threat model trust boundaries|attack surface inventory|Trust assumptions explicit
Web Security Engineer|xss csrf web|web attack checklist|Untrusted inputs treated as data
API Security Engineer|api security rate limiting|API abuse test cases|Authorization checked per resource
Cryptography Integrator|cryptography signature encryption|crypto API integration review|No custom unreviewed primitives
Sandbox Engineer|sandbox isolation process|process isolation specification|Escape paths considered
Prompt Injection Auditor|prompt injection untrusted|agent instruction boundary checks|Untrusted content cannot grant privileges
Dependency Auditor|cve vulnerability packages|package risk report|CVE claims sourced
Privacy Engineer|privacy logging pII|data minimization review|Retention limits and redaction verified
License Compliance Engineer|license spdx attribution|license inventory|Redistribution terms checked
Unit Test Engineer|unit test fixtures|isolated unit test matrix|Deterministic assertions
Integration Test Engineer|integration services adapters|integration contract tests|Unavailable dependencies reported distinctly
End to End Test Engineer|e2e user workflow|complete user journey test|Exit conditions verified
Regression Test Engineer|regression historical failures|permanent regression cases|Prior failure reproduced before fix
Test Impact Analyst|test impact changed files|test selection hypothesis|Unknown dependencies trigger conservative tests
Fuzz Testing Engineer|fuzz parser malformed|fuzz corpus and oracles|Crash minimization included
Property Testing Engineer|property invariants|generative invariants|Counterexamples retained
Coverage Engineer|coverage code paths|coverage gap analysis|Branch coverage considered
Debugger|debug traceback failure|root cause narrative|Hypothesis tested with reproduction
Flaky Test Investigator|flaky nondeterminism test|flaky isolation plan|Retries not mistaken for fixes
Static Analysis Engineer|lint static types|static rule findings|False positives evaluated
Benchmark Engineer|benchmark timing comparison|reproducible benchmark report|Warm-up and measurement variance reported
UI UX Designer|ui ux information architecture|screen interaction spec|Critical paths keyboard accessible
Design Systems Engineer|design tokens components|component token contract|Tokens reused consistently
Accessibility Engineer|accessibility wcag screenreader|WCAG audit plan|Contrast and keyboard behavior checked
Responsive Design Engineer|responsive mobile layout|breakpoint behavior specification|Small viewport tested
Visual Regression Engineer|visual screenshot diff|visual regression protocol|Baseline images versioned
Typography Engineer|typography fonts hierarchy|typographic scale proposal|Readability across sizes checked
Product Interface Engineer|dashboard information design|dashboard information hierarchy|No decorative fake metrics
Motion UX Engineer|animation interaction motion|motion behavior spec|Reduced-motion support included
CLI UX Engineer|cli tui terminal commands|terminal usability checklist|Help output and failure codes tested
Graphics Engineer|graphics shaders rendering|rendering pipeline plan|Frame-time and memory profiled
Unreal Engine Engineer|unreal blueprint ue5|Unreal plugin integration plan|Editor/runtime compatibility declared
Blender Engineer|blender bpy mesh|Blender procedural workflow|Non-destructive output preferred
3D Assets Engineer|3d mesh lod uv|3D asset validation plan|Topology and LOD reviewed
Audio Engineer|audio dsp signal|audio processing pipeline plan|Sample-rate changes tested
Scientific Computing Engineer|scientific numeric vector|numerical validation study|Reference precision and error bounds defined
Technical Writer|documentation readme tutorials|task-focused documentation update|Commands reproducible as written
Product Strategist|product adoption roadmap|user problem hypothesis|Evidence linked to user pain
Developer Relations Engineer|community issues contributors|contribution onboarding plan|First contribution can be tested
Project Manager|project planning milestones|dependency-aware delivery milestones|Risks and blockers tracked
'''
rows=[]
for line in ROLE_ROWS.strip().splitlines():
    fields=line.strip().split('|')
    if len(fields)!=4: raise ValueError(line)
    rows.append(fields)
assert len(rows)==100,len(rows)

for i,(name,keywords,artifact,gate) in enumerate(rows,1):
    slug=re.sub('[^a-z0-9]+','-',name.lower()).strip('-')
    category = ('software' if i<=25 else 'ai' if i<=40 else 'infrastructure' if i<=55 else 'security' if i<=69 else 'quality' if i<=81 else 'design' if i<=90 else 'advanced' if i<=96 else 'product')
    base_tools={'software':['workspace_tree','file_read','python_ast_symbols','git_diff_stat'],
        'ai':['project_digest','python_imports','pyproject_meta','python_complexity'],
        'infrastructure':['env_runtime','environment_paths','config_files','release_readiness'],
        'security':['secret_pattern_scan','workspace_symlinks','package_deps','git_status'],
        'quality':['unit_discovery','search_text','verification_report','python_syntax'],
        'design':['markdown_headings','file_read','file_search_name','extension_inventory'],
        'advanced':['file_search_name','file_stat','project_digest','environment_paths'],
        'product':['release_readiness','markdown_links','git_log','task_comments']}[category]
    data={
        'schema_version':1, 'id':f'{i:03d}-{slug}','name':name,'description':f'Specialized {name.lower()} for tasks involving {keywords.replace(" ", ", ")}.',
        'role':'advisory local-first engineering specialist','specialization':category,
        'keywords':keywords.split(), 'responsibilities':[f'Investigate {keywords} without assuming absent evidence',f'Produce {artifact}',f'Flag unsupported conclusions before delivery'],
        'goals':[artifact,gate],
        'instructions':f'Inspect the smallest relevant files first. For {name.lower()} work, prioritize {artifact}. State what was tested, what is inferred, and what remains unverified. Do not claim tools or external systems ran unless their results were collected.',
        'policy':{'external_llm_calls':'none_by_default','auto_execute':False,'requires_explicit_dispatch':True},
        'safety_rules':['Never reveal secrets','Do not execute untrusted shell text','Never bypass provider authentication or subscription limits'],
        'permission_scope':['workspace:read'], 'allowed_tools':base_tools,
        'allowed_skills':[], 'allowed_plugins':[],
        'input_schema':{'type':'object','required':['task'],'properties':{'task':{'type':'string'},'files':{'type':'array','items':{'type':'string'}}}},
        'output_schema':{'type':'object','required':['summary','evidence','status']},
        'acceptance_criteria':[gate, 'All factual claims point to reproducible evidence'],
        'quality_gates':[gate,'No hidden writes, network calls or unapproved tool use'],
        'escalation_rules':['On ambiguous dependencies return BLOCKED','Escalate security-critical uncertainty to human reviewer'],
        'communication_protocol':'JSON task_id + source references + check results, not free-form agent chat',
        'context_policy':{'load':'on_demand','max_chars':6000,'include_only_relevant_files':True},
        'resource_limits':{'max_parallel_tasks':1,'max_llm_calls':0,'max_runtime_seconds':60,'vram_mb':0},
        'memory_policy':'No persistent model state; task outcomes stored as local references only',
        'retry_policy':{'max_retries':1,'backoff_seconds':1},
        'logging_policy':{'audit':True,'secrets':'redacted'},
        'termination_conditions':['deliverable complete','timeout reached','cancelled','permission denied'],
        'test_requirements':[gate],
        'example_tasks':[f'Inspect a repository for {keywords} and write a concise {artifact}.']}
    (BASE/'agents'/f'{i:03d}-{slug}.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')

SKILLS='''
Inspect failing Python tests|unit_discovery,search_text,python_syntax
Review changed Python code|git_diff_stat,python_ast_symbols,python_complexity
Audit package metadata|pyproject_meta,requirements_read,release_readiness
Inspect npm scripts|package_scripts,package_deps,lock_files
Assess release readiness|release_readiness,git_status,git_tags
Find TODO backlog|task_comments,workspace_tree
Inspect dependency drift|lock_files,config_files,project_digest
Review Python type surface|python_functions,python_docstrings,python_imports
Analyze module imports|python_imports,python_ast_symbols,file_head
Inspect AST complexity|python_complexity,python_functions,file_lines
Locate oversized sources|list_large_files,extension_inventory
Discover duplicate files|duplicate_hashes,file_sha256
Inspect repository tree|workspace_tree,file_count,extension_inventory
Audit suspicious secrets|secret_pattern_scan,workspace_symlinks
Verify documentation links|markdown_links,markdown_headings
Check package JSON|json_validate,json_keys,package_scripts
Validate TOML configuration|toml_validate,pyproject_meta
Validate YAML configuration|yaml_validate,file_head
Validate XML configuration|xml_validate,file_stat
Validate INI configuration|ini_sections,file_head
Inspect CSV schema|csv_columns,file_stat
Compare documentation files|file_diff,markdown_headings
Review git repository status|git_status,git_diff_stat,git_files
Inspect git branch history|git_branches,git_log,git_tags
Check remote setup|git_remotes,git_commit_info
Audit ignored files|git_ignored,workspace_symlinks
Inspect process environment|env_runtime,environment_paths,process_memory
Review local verification|verification_report,release_readiness
Inspect test inventory|unit_discovery,file_search_name
Review cross-platform tooling|environment_paths,config_files
Trace Python classes|python_classes,python_docstrings
Trace Python functions|python_functions,python_ast_symbols
Inspect Python syntax|python_syntax,python_line_count
Inspect inline TODOs|python_todo,file_lines
Check source integrity|file_sha256,file_size,project_digest
Review source headers|file_head,file_stat
Review source tails|file_tail,file_lines
Audit file naming|file_search_name,extension_inventory
Find source references|search_text,file_lines
Find structural patterns|search_regex,python_ast_symbols
Inspect ZIP release payload|archive_zip_list,file_stat
Review Go metadata|go_modules,config_files
Review Rust metadata|cargo_packages,lock_files
Review TypeScript files|file_search_name,package_scripts
Review asset inventory|extension_inventory,list_large_files
Inspect CI artifacts|file_search_name,release_readiness
Analyze basic API docs|markdown_links,search_text
Review CONTRIBUTING guide|markdown_headings,file_read
Review security policy|markdown_headings,secret_pattern_scan
Prepare issue triage|task_comments,git_log
'''
skills=[]
for i,line in enumerate(SKILLS.strip().splitlines(),1):
    title,tool_ids=line.split('|'); ts=tool_ids.split(',')
    slug=re.sub('[^a-z0-9]+','-',title.lower()).strip('-')
    obj={'schema_version':1,'id':f'skill-{i:03d}-{slug}','name':title,
      'purpose':f'Perform a repeatable local investigation: {title.lower()}.',
      'requirements':['Open an existing workspace','Review files and arguments before running tools'],
      'project_types':['any'], 'inputs':{'root':'local workspace','paths':'optional file overrides'},
      'workflow':[{'step':j+1,'tool':t,'reason':f'Collect {t.replace("_", " ")} evidence before the next stage'} for j,t in enumerate(ts)],
      'tools':ts,'permissions':['workspace:read'],'quality_gates':['No unchecked success claims','All selected tools complete or report a concrete error'],
      'outputs':['structured observations','failure details','recommended next checks'],
      'failure_handling':'Stop and expose tool error; do not substitute fabricated evidence',
      'example_usage':f'loopsieve skills run skill-{i:03d}-{slug}'}
    (BASE/'skills'/(obj['id']+'.json')).write_text(json.dumps(obj,indent=2)+'\n')
    skills.append(obj)
assert len(skills)==50,len(skills)

PLUGINS='''
python|python|--version|Python interpreter
python3|python3|--version|Python interpreter alternative
pip|pip|--version|Python package manager
pip3|pip3|--version|Python package manager alternative
git|git|--version|Version control
gh|gh|--version|GitHub CLI
node|node|--version|Node.js runtime
npm|npm|--version|Node.js package manager
npx|npx|--version|Node command launcher
pnpm|pnpm|--version|Node.js package manager
yarn|yarn|--version|Node package manager
bun|bun|--version|JavaScript runtime
deno|deno|--version|JavaScript runtime
go|go|version|Go toolchain
cargo|cargo|--version|Rust build tool
rustc|rustc|--version|Rust compiler
rustfmt|rustfmt|--version|Rust formatter
clang|clang|--version|LLVM C compiler
clangxx|clang++|--version|LLVM C++ compiler
gcc|gcc|--version|GNU C compiler
gxx|g++|--version|GNU C++ compiler
cmake|cmake|--version|C/C++ build system
ninja|ninja|--version|Fast build runner
make|make|--version|Make build runner
docker|docker|--version|Container engine
podman|podman|--version|Container engine
kubectl|kubectl|version --client|Kubernetes client
helm|helm|version --short|Kubernetes chart manager
terraform|terraform|version|Infrastructure as code
ansible|ansible|--version|Automation
poetry|poetry|--version|Python dependency manager
uv|uv|--version|Python package runner
ruff|ruff|--version|Python linter
mypy|mypy|--version|Python type checker
pytest|pytest|--version|Python test runner
black|black|--version|Python formatter
pylint|pylint|--version|Python lint tool
eslint|eslint|--version|JavaScript linter
prettier|prettier|--version|Formatter
tsc|tsc|--version|TypeScript compiler
java|java|--version|Java runtime
javac|javac|--version|Java compiler
gradle|gradle|--version|Gradle builder
mvn|mvn|--version|Maven builder
dotnet|dotnet|--version|.NET SDK
swift|swift|--version|Swift compiler
sqlite3|sqlite3|--version|SQLite shell
jq|jq|--version|JSON processor
rg|rg|--version|Ripgrep file search
ffmpeg|ffmpeg|--version|Audio/video utility
'''
for i,line in enumerate(PLUGINS.strip().splitlines(),1):
    pid,exe,opts,desc=line.split('|')
    spec={'schema_version':1,'id':f'plugin-{pid}','name':desc,'kind':'external-cli-adapter','executable':exe,
        'probe_args':opts.split(),'operation':'version-health-check',
        'capabilities':['executable-discovery','version-health-check'],
        'permissions':['process:launch:fixed-argv'],'installation':'user-managed; no automatic install',
        'status_without_executable':'REQUIRES_DEPENDENCY','version':'1.0','max_probe_seconds':4}
    (BASE/'plugins'/f'{i:03d}-{pid}.json').write_text(json.dumps(spec,indent=2)+'\n')
assert len(PLUGINS.strip().splitlines())==50

# Technology features are grounded in a callable tool or in a named engine
# implementation. Reusing a tool does not imply an independently proven new
# algorithm. The registry keeps provenance and maturity explicit.
TECH=[
 ('dependency-aware verification','verification_state.snapshot'),
 ('content-addressed cache','verification_state.snapshot'),
 ('conservative unknown-dependency handling','verification_state.snapshot'),
 ('structured verification status','engine.verify'),
 ('incremental verification selection','planner.select_checks'),
 ('failure fingerprinting','diagnostics.diagnostic_identity'),
 ('AST source anchors','diagnostics._source_anchor'),
 ('diagnostic severity identity','diagnostics.diagnostic_identity'),
 ('duplicate failure filtering','engine.verify'),
 ('bounded streaming subprocess output','runner.BoundedStream'),
 ('subprocess timeout enforcement','runner.run_check'),
 ('Claude PostToolBatch integration','hook.run_hook'),
 ('safe hook settings merge','install.install_hook'),
 ('atomic local state persistence','state.save_state'),
 ('project root detection','project.find_project_root'),
 ('changed-file language classification','project.classify_file'),
 ('local benchmark runner','benchmark.run_fixture'),
 ('workspace traversal boundaries','toolkit.safe_path'),
 ('lazy agent registry','agents.list_agents'),
 ('deterministic agent selection','agents.select_agents'),
 ('persistent task queue','agents.TaskStore'),
 ('tool permission enforcement','toolkit.run_tool'),
 ('plugin binary discovery','plugins.probe_plugin'),
 ('skill pipeline orchestration','skills.run_skill'),
 ('terminal dashboard','tui.launch'),
 ('local-only web dashboard','webui.serve'),
]
# Add distinct tested data-processing mechanisms backed by real tools.
from ast import parse
ns={}
for idx,func in enumerate('file_sha256 file_diff duplicate_hashes search_regex python_ast_symbols python_imports python_docstrings python_complexity json_validate toml_validate xml_validate csv_columns markdown_links package_deps git_diff_stat git_commit_info release_readiness secret_pattern_scan workspace_symlinks project_digest git_status lock_files config_files requirements_read'.split(),1):
    TECH.append((f'{func.replace("_"," ")} inspection','toolkit.'+func))
assert len(TECH)==50,len(TECH)
for i,(name,implementation) in enumerate(TECH,1):
    spec={'id':f'technology-{i:03d}','name':name,'implementation':implementation,
      'status':'IMPLEMENTED_PENDING_TEST' if i<=26 else 'IMPLEMENTED',
      'evidence':'Source implementation available; individual behavior must be confirmed by tests',
      'scope':'local deterministic mechanism','dependencies':[]}
    (BASE/'technologies'/f'{i:03d}.json').write_text(json.dumps(spec,indent=2)+'\n')
print('Generated',len(rows),'agents',len(skills),'skills',len(PLUGINS.strip().splitlines()),'plugin adapters',len(TECH),'technology records')
