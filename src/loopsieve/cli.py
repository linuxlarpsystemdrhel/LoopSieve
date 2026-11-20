from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .benchmark import run_fixture
from .budget import AdaptiveSwarmBudget
from .capability import CapabilityRegistry
from .huggingface import HuggingFaceClient
from .checkpoint import CheckpointTimeMachine
from .claude_code import status as claude_status, install as claude_install, uninstall as claude_uninstall
from .handoff import VerifiedTaskHandoff
from .hardware import hardware_summary
from .model_manager import ModelDownloader, ModelManager, load_catalog
from .model_team import ModelTeam, TeamStore, team_capacity
from .provider_catalog import ProviderCatalog
from .provider_health import FallbackController, FallbackProvider, ProviderHealthMonitor, ProviderSlot
from .quantization import method_catalog, recommend_profiles
from .secure_store import SecretStore
from .permissions import PermissionEngine
from .reliability import reliability_summary
from .routing import route_tools
from .config import load_config, write_default_config
from .engine import state_report, verify
from .hook import main as hook_main
from .install import install_hook, uninstall_hook
from .project import find_project_root


def _root(value: str | None) -> Path:
    return find_project_root(Path(value).expanduser() if value else Path.cwd())


def command_init(args: argparse.Namespace) -> int:
    root = _root(args.root)
    try:
        path = write_default_config(root, overwrite=args.force)
    except FileExistsError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    config = load_config(root)
    print(f"Wrote {path}")
    if config.checks:
        print("Detected checks:")
        for check in config.checks:
            print(f"  - {check.name}: {' '.join(check.command)}")
    else:
        print("No checks were detected. Add checks to .loopsieve.json before enabling the hook.")
    return 0


def command_check(args: argparse.Namespace) -> int:
    files = [Path(item) for item in args.files]
    if not files:
        print("Pass at least one changed file to `loopsieve check`.", file=sys.stderr)
        return 2
    try:
        root = _root(args.root)
        config = load_config(root)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Unable to load verification configuration: {exc}", file=sys.stderr)
        return 2
    model_config = None
    if getattr(args, "explain", False):
        from .local_llm import load_local_config

        try:
            model_config = load_local_config(args.llm_config)
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 2
    elif getattr(args, "llm_config", None) or getattr(args, "prompt_cache", False):
        print("--llm-config and --prompt-cache require --explain.", file=sys.stderr)
        return 2

    result = verify(root, files, config)
    if result.context:
        print(result.context)
    elif result.skip_reason:
        print(f"LoopSieve: skipped ({result.skip_reason}).")
    if result.state_warning:
        print(f"LoopSieve: {result.state_warning}", file=sys.stderr)
    if model_config is not None and result.failed_results:
        from .local_llm import LocalInferenceError, diagnostic_evidence, explain

        try:
            evidence = diagnostic_evidence(result, config.max_diagnostic_lines)
            advice = explain(evidence, model_config, cache_prompt=args.prompt_cache)
            print("\nLocal model suggestion (unverified)\n" + advice.text)
            if advice.finish_reason == "length":
                print("Local explanation reached the configured token limit.", file=sys.stderr)
        except LocalInferenceError as exc:
            print(f"Local explanation unavailable: {exc}", file=sys.stderr)
    return 0 if result.passed else (1 if result.failed_results else 2)


def command_report(args: argparse.Namespace) -> int:
    try:
        root = _root(args.root)
        report = state_report(root, load_config(root))
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Unable to read verification report: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2))
        return 0
    stats = report.get("stats", {})
    print(f"Project: {root}")
    print(f"Runs: {stats.get('runs', 0)}")
    print(f"Passed: {stats.get('passed_runs', 0)}")
    print(f"Failed: {stats.get('failed_runs', 0)}")
    print(f"Repeated failures suppressed: {stats.get('repeated_failures_suppressed', 0)}")
    print(f"Raw failing diagnostic chars: {stats.get('raw_diagnostic_chars', 0)}")
    print(f"Context chars emitted: {stats.get('emitted_context_chars', 0)}")
    print(f"Observed diagnostic-context reduction: {report.get('diagnostic_context_reduction_ratio', 0) * 100:.1f}%")
    return 0


def command_install(args: argparse.Namespace) -> int:
    root = _root(args.root)
    path = install_hook(root, timeout_seconds=args.timeout)
    print(f"Installed LoopSieve PostToolBatch hook in {path}")
    return 0


def command_uninstall(args: argparse.Namespace) -> int:
    root = _root(args.root)
    path = uninstall_hook(root)
    print(f"Removed LoopSieve hook from {path}")
    return 0


def command_benchmark(args: argparse.Namespace) -> int:
    fixture = Path(args.fixture).expanduser().resolve()
    result = run_fixture(fixture)
    payload = result.as_dict()
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Iterations: {payload['iterations']}")
        print(f"Raw diagnostic chars: {payload['raw_chars']}")
        print(f"LoopSieve emitted chars: {payload['loopsieve_chars']}")
        print(f"Repeated failures suppressed: {payload['repeated_failures_suppressed']}")
        print(f"Diagnostic-context reduction: {payload['diagnostic_context_reduction_ratio'] * 100:.1f}%")
        print("This benchmark measures diagnostic text volume only. It is not a claim about Claude plan usage or billed tokens.")
    return 0


def _out(payload):
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    return 0


def _doctor(args):
    from .catalog import validate_catalog
    from .toolkit import tool_catalog, run_tool
    try:
        counts=validate_catalog()
        runtime=run_tool('env_runtime',_root(args.root),{})
        return _out({'status':'PASS','catalogs':counts,'local_tools':len(tool_catalog()),
                     'runtime':runtime,'optional_tui':'Install loopsieve[tui] for interactive Textual app',
                     'external_models':'not started automatically'})
    except Exception as exc:
        _out({'status':'ERROR','error':str(exc)}); return 2


def _catalog_command(kind,args):
    from .catalog import list_entries,load
    from .toolkit import tool_catalog,run_tool
    from .agents import TaskStore,list_agents,select_agents
    from .plugins import list_plugins,probe_plugin
    from .skills import list_skills,run_skill
    root=_root(args.root)
    try:
        values=json.loads(args.args)
        if not isinstance(values,dict): raise ValueError('--args must be a JSON object')
        action=args.action
        if kind=='agents':
            if action=='list': return _out([{'id':x['id'],'name':x['name'],'area':x['specialization']} for x in list_agents(args.value or '')])
            if action=='show': return _out(load('agents',args.value or ''))
            if action=='select':return _out([{'id':x['id'],'name':x['name']} for x in select_agents(args.value or '')])
        if kind=='tools':
            if action=='list':return _out(tool_catalog())
            if action=='run':return _out({'tool':args.value,'result':run_tool(args.value or '',root,values)})
        if kind=='plugins':
            if action=='list':return _out([{'id':x['id'],'name':x['name'],'status':x['status']} for x in list_plugins()])
            if action=='probe':return _out(probe_plugin(args.value or ''))
        if kind=='skills':
            if action=='list':return _out([{'id':x['id'],'name':x['name'],'steps':len(x['workflow'])} for x in list_skills()])
            if action=='show':return _out(load('skills',args.value or ''))
            if action=='run':return _out(run_skill(args.value or '',root,values))
        if kind=='technologies':
            if action=='list':return _out([{'id':x['id'],'name':x['name'],'implementation':x['implementation'],'status':x['status']} for x in list_entries('technologies')])
            if action=='show':return _out(load('technologies',args.value or ''))
        if kind=='tasks':
            store=TaskStore(root)
            if action=='list':return _out(store.all())
            if action=='create':return _out(store.create(args.value or '',args.tool,values,args.agent))
            if action=='run':return _out(store.run(args.value or ''))
            if action=='cancel':return _out(store.cancel(args.value or ''))
        raise ValueError('action not supported')
    except (KeyError,TypeError,ValueError,PermissionError,OSError) as exc:
        print(f'LoopSieve: {type(exc).__name__}: {exc}',file=sys.stderr)
        return 2


def _provider(args):
    from .providers import OllamaProvider, CompatibleProvider, CLIProvider
    if args.provider=='ollama':return OllamaProvider(model=args.model,endpoint=args.endpoint or 'http://127.0.0.1:11434/api/chat')
    if args.provider in ('claude','codex'):return CLIProvider(args.provider)
    if args.provider=='compatible':
        if not args.endpoint:raise ValueError('compatible requires --endpoint')
        return CompatibleProvider(model=args.model,endpoint=args.endpoint)
    raise ValueError('unknown provider')


def command_agent(args):
    from .agent_runtime import AgentRuntime,Journal
    root=_root(args.root)
    store=Journal(root)
    if args.action=='sessions':print(json.dumps(store.list(),indent=2));return 0
    if args.action=='inspect':
        print(json.dumps({'session':store.get(args.value),'events':store.events(args.value)},ensure_ascii=False,indent=2));return 0
    if args.action=='checkpoints':
        print(json.dumps({'session':args.value,'checkpoints':store.checkpoints(args.value)},ensure_ascii=False,indent=2));return 0
    if args.action=='restore':
        if not args.value or not args.checkpoint:raise ValueError('restore requires a session id and --checkpoint')
        print(json.dumps(store.restore_checkpoint(args.value,args.checkpoint),ensure_ascii=False,indent=2));return 0
    if args.action in ('cancel','pause'):
        runtime=AgentRuntime(root,None,store)
        print(json.dumps((runtime.cancel if args.action=='cancel' else runtime.pause)(args.value),ensure_ascii=False,indent=2));return 0
    if args.action=='recover':
        runtime=AgentRuntime(root,None,store)
        print(json.dumps(runtime.recover(),ensure_ascii=False,indent=2));return 0
    if args.action=='run' and not args.value:raise ValueError('run requires task text')
    runtime=AgentRuntime(root,_provider(args),store)
    if args.action=='run':
        session=runtime.create(args.value,args.role,args.steps,allow_writes=args.allow_writes,allow_checks=args.allow_checks)
        result=runtime.run(session['id'])
    elif args.action in ('resume','step'):
        if not args.value:raise ValueError('session id required')
        result=runtime.resume(args.value) if args.action=='resume' else runtime.step(args.value)
    else:raise ValueError('unsupported action')
    print(json.dumps({'id':result['id'],'status':result['status'],'step':result['step'],
                      'agent_id':result['agent_id'],'changed':result['changed'],'evidence':result['evidence'],
                      'last_message':result['messages'][-1]},ensure_ascii=False,indent=2))
    return 0 if result['status']=='COMPLETED' else 2


def command_team(args):
    from .agent_runtime import AgentRuntime
    from .orchestrator import Orchestrator,load_work_items
    if not args.value:raise ValueError('team requires a JSON task DAG')
    root=_root(args.root)
    runtime=AgentRuntime(root,_provider(args))
    outcome=Orchestrator(runtime,max_workers=args.max_workers).run(load_work_items(Path(args.value)),allow_writes=args.allow_writes,
                                       allow_checks=args.allow_checks,max_steps=args.steps,
                                       parallel=args.parallel,max_workers=args.max_workers)
    print(json.dumps(outcome,ensure_ascii=False,indent=2))
    return 0 if outcome['status']=='COMPLETED' else 2


def command_intelligence(args):
    from .intelligence import context_packet,symbol_index,import_graph,permission_preview,reliability_profiles,session_capsule,source_diff
    from .agent_runtime import Journal
    root=_root(args.root)
    if args.action=='context':value=context_packet(root,args.value or '',max_chars=args.max_chars)
    elif args.action=='symbols':value=symbol_index(root)
    elif args.action=='imports':value=import_graph(root)
    elif args.action=='permissions':value=permission_preview(args.value or '001-chief-architect',args.allow_writes,args.allow_checks)
    elif args.action=='reliability':value=reliability_profiles(Journal(root))
    elif args.action=='diff':value=source_diff(root)
    elif args.action=='capsule':
        if not args.value or not args.output:raise ValueError('capsule requires session ID and --output')
        value=session_capsule(Journal(root),args.value,Path(args.output))
    else:raise ValueError('unknown action')
    print(json.dumps(value,ensure_ascii=False,indent=2))
    return 0


def command_mcp(args):
    from .mcp_manager import inspect_mcp
    print(json.dumps(inspect_mcp(_root(args.root)),ensure_ascii=False,indent=2))
    return 0


def command_proof(args):
    from .agent_runtime import Journal
    from .provenance import EvidenceLedger, ArtifactStore, portable_capsule
    from .project_intelligence import python_impact, compile_context, check_contract, detect_doc_conflicts
    from .memory import ProjectMemory
    from .release_quality import evaluate_release_evidence, run_required_checks
    root=_root(args.root)
    journal=Journal(root)
    if args.action=='evidence':
        if args.operation=='audit':return _out(journal.proof.audit())
        if args.operation=='list':return _out(journal.proof.recent())
    if args.action=='impact':
        paths=([args.operation] if args.operation!='list' else [])+args.paths
        if not paths:raise ValueError('impact requires one or more changed file paths')
        return _out(python_impact(root,paths))
    if args.action=='context':return _out(compile_context(root,args.query or '',args.budget))
    if args.action=='conflicts':return _out(detect_doc_conflicts(root))
    if args.action=='contract':
        data=json.loads(Path(args.input).read_text(encoding='utf-8'))
        return _out(check_contract(data['task'],data['acceptance']))
    if args.action=='gate':
        data=json.loads(Path(args.input).read_text(encoding='utf-8'))
        return _out(evaluate_release_evidence(root,data['results'],data['required']))
    if args.action=='check-suite':
        if not args.approve_commands:raise PermissionError('passing --approve-commands is required before executing local checks')
        data=json.loads(Path(args.input).read_text(encoding='utf-8'))
        return _out(run_required_checks(root,data,args.timeout))
    if args.action=='capsule':
        if not args.session or not args.output:raise ValueError('capsule needs --session and --output')
        return _out(portable_capsule(journal.get(args.session),journal.events(args.session),Path(args.output)))
    if args.action=='memory':
        store=ProjectMemory(root,journal.path.parent/'project-memory.db')
        if args.operation=='list':return _out(store.query(args.query))
        if args.operation=='remember':
            if not (args.query and args.value and args.source):raise ValueError('remember requires --query, --value, --source')
            return _out(store.remember(args.query,args.value,args.source))
    if args.action=='worktree':
        from .worktrees import prepare_experiment, worktree_status
        if args.operation=='list': return _out(worktree_status(root))
        if args.operation=='create':
            if not args.value:raise ValueError('worktree create needs --value <name>')
            return _out(prepare_experiment(root,args.value,Path(args.output) if args.output else journal.path.parent/'worktrees',approve=args.approve_worktree))
    if args.action=='artifact':
        store=ArtifactStore(journal.path.parent/'objects')
        if args.operation=='put':
            if not args.source:raise ValueError('artifact put needs --source workspace-relative path')
            from .toolkit import safe_path
            p=safe_path(root,args.source)
            if not p.is_file():raise ValueError('artifact source missing')
            if p.stat().st_size>2_000_000:raise ValueError('artifact too big')
            return _out(store.put(p.read_bytes()))
        if args.operation=='verify':
            return _out({'sha256':__import__('hashlib').sha256(store.get(args.value)).hexdigest(),'status':'PASS'})
    raise ValueError('unsupported proof action')


def command_innovations(args):
    from importlib.resources import files as resource_files
    manifest=resource_files('loopsieve').joinpath('data/innovations.json')
    data=json.loads(manifest.read_text(encoding='utf-8'))
    items=data['items']
    if args.item is not None:
        matches=[x for x in items if str(x['id'])==args.item]
        if not matches:raise ValueError('no such innovation ID')
        return _out(matches[0])
    if args.status:
        items=[x for x in items if x['status']==args.status]
    if args.summary:
        from collections import Counter
        return _out({'total':len(data['items']),'status_counts':dict(Counter(x['status'] for x in data['items']))})
    return _out(items)


def command_models(args):
    root=_root(args.root)
    manager=ModelManager()
    action=args.action
    if action in ('list','status'):
        value=manager.status(installed=[x for x in (args.installed or [])])
    elif action=='show':
        value=manager.find(args.value or '')
    elif action=='memory':
        value=manager.memory(args.value or manager.models[0].id,args.quantization,args.context)
    elif action=='auto':
        value=manager.auto(args.value or 'coding task',installed=[x for x in (args.installed or [])],max_mb=args.max_mb)
    elif action=='select':
        value=manager.select(args.value or manager.models[0].id,args.quantization,installed=bool(args.installed))
    elif action=='benchmark':
        provider=_provider(args) if args.provider else None
        value=manager.benchmark(args.value or manager.models[0].id,provider)
    elif action=='download':
        if not args.value:raise ValueError('download requires a model id')
        model=manager.find(args.value)
        downloader=ModelDownloader(root/'models')
        value=downloader.download(args.url or model.download_url or '',root/'models'/f'{model.id}.gguf',
                                  sha256=args.sha256 or model.sha256,license=args.license or model.license,
                                  accept_license=args.accept_license,approve=args.approve_download,max_bytes=args.max_bytes)
    elif action=='verify':
        if not args.source or not args.sha256:raise ValueError('verify requires --source and --sha256')
        value=ModelDownloader(root).verify(args.source,args.sha256)
    elif action=='quantize':
        from .quantization import validate_quantization_request
        if not args.value:raise ValueError('quantize requires a model id')
        model=manager.find(args.value)
        value=validate_quantization_request(model.params_b,args.quantization or 'q4_k_m',backend=args.backend)
    else:raise ValueError('unknown models action')
    print(json.dumps(value,ensure_ascii=False,indent=2,default=str));return 0


def command_modelteam(args):
    from .agent_runtime import Journal
    root=_root(args.root)
    journal=Journal(root)
    team=ModelTeam(root,store=TeamStore(journal.path.parent/'team.db'),journal=journal,
                   max_models=args.max_models)
    if args.action=='status':
        value=team.status()
    elif args.action in ('run','parallel'):
        models=args.model or ['llama3.2:3b']
        provider=_provider(argparse.Namespace(provider=args.provider,model=models[0],
                                              endpoint=args.endpoint))
        for model_id in models[:args.max_models]:
            try:team.add_model(model_id,provider)
            except ValueError:pass
            team.register_agents(model_id)
        if args.action=='run':
            value=team.run(args.value or 'Review the repository',model_id=models[0],
                           allow_writes=args.allow_writes,allow_checks=args.allow_checks)
        else:
            value=team.run_parallel_solutions(args.value or 'Review the repository',model_ids=models)
    elif args.action=='agents':
        value={'agents':team.agents(limit=args.limit),'status':team.status()}
    elif args.action=='dialogue':
        value=team.dialogue(args.value,args.limit)
    elif args.action=='capacity':
        value=team_capacity(args.max_models,args.agents_per_model)
    else:raise ValueError('unknown modelteam action')
    print(json.dumps(value,ensure_ascii=False,indent=2,default=str));return 0


def command_hf(args):
    client=HuggingFaceClient(timeout=args.timeout)
    if args.action=='search':
        value=client.search(args.query or '',limit=args.limit,pipeline_tag=args.pipeline or 'text-generation')
    elif args.action=='info':
        if not args.query:raise ValueError('hf info requires a model id')
        value=client.model_info(args.query)
    elif args.action=='files':
        if not args.query:raise ValueError('hf files requires a model id')
        value={'files':client.files(args.query)}
    else:raise ValueError('unknown HF action')
    print(json.dumps(value,ensure_ascii=False,indent=2,default=str));return 0


def command_providers(args):
    catalog=ProviderCatalog()
    if args.query:
        value={'profiles':[x.as_dict() for x in catalog.search(args.query,limit=args.limit)],
               'status':catalog.status()}
    else:
        value={'profiles':[x.as_dict() for x in catalog.search(limit=args.limit)],
               'status':catalog.status()}
    print(json.dumps(value,ensure_ascii=False,indent=2,default=str));return 0


def command_capabilities(args):
    registry=CapabilityRegistry()
    if args.query:
        value={'query':args.query,'results':[x.compact() for x in registry.search(args.query,limit=args.limit)],
               'route':registry.route(args.query)}
    else:
        value={'counts':{kind:len(registry.list(kind)) for kind in ('tool','agent','skill','plugin','technology','model','provider','quantization')},
               'total':len(registry.list())}
    print(json.dumps(value,ensure_ascii=False,indent=2,default=str));return 0


def command_permissions(args):
    engine=PermissionEngine()
    print(json.dumps(engine.snapshot(),ensure_ascii=False,indent=2,default=str));return 0


def command_quantization(args):
    manager=ModelManager()
    model=manager.find(args.model)
    budget=(manager.hardware.free_vram_mb or manager.hardware.ram_free_mb or 0)
    value={'model':model.id,'methods':method_catalog(),
           'profiles':recommend_profiles(model.params_b,budget,context_tokens=model.context_tokens,
                                         layers=model.layers,kv_heads=model.kv_heads,
                                         head_dim=model.head_dim) if budget else None,
           'budget_mb':budget,'hardware':manager.hardware.as_dict()}
    print(json.dumps(value,ensure_ascii=False,indent=2,default=str));return 0


def command_secrets(args):
    store=SecretStore()
    if args.action=='list':value=store.status()
    elif args.action=='set':
        if not args.name:raise ValueError('secrets set requires --name')
        import getpass
        secret=args.value or getpass.getpass('Secret: ')
        value=store.set(args.name,secret)
    elif args.action=='get':
        if not args.name:raise ValueError('secrets get requires --name')
        value={'name':args.name,'present':store.get(args.name) is not None}
    elif args.action=='delete':
        if not args.name:raise ValueError('secrets delete requires --name')
        value={'name':args.name,'deleted':store.delete(args.name)}
    else:raise ValueError('unknown secrets action')
    print(json.dumps(value,ensure_ascii=False,indent=2,default=str));return 0


def command_provider(args):
    from .providers import OllamaProvider
    root=_root(args.root)
    monitor=ProviderHealthMonitor()
    if args.action=='status':
        try:provider=_provider(args)
        except Exception as exc:
            value={'state':'UNCONFIGURED','kind':type(exc).__name__,'reason':str(exc)};print(json.dumps(value,indent=2));return 2
        value=monitor.probe(provider)
    elif args.action=='list':
        value=monitor.status()
    else:raise ValueError('unknown provider action')
    print(json.dumps(value,ensure_ascii=False,indent=2,default=str));return 0


def command_fallback(args):
    root=_root(args.root)
    primary=_provider(args)
    secondary=None
    if args.fallback_provider:
        class Namespace:pass
        ns=Namespace(provider=args.fallback_provider,model=args.fallback_model or args.model,
                     endpoint=args.fallback_endpoint or args.endpoint)
        secondary=_provider(ns)
    chain=FallbackProvider([ProviderSlot(primary,label='primary'),*([ProviderSlot(secondary,label='fallback')] if secondary else [])])
    controller=FallbackController(chain)
    if args.action=='enable':value=controller.enable()
    elif args.action=='disable':value=controller.disable()
    elif args.action=='reset':value=controller.reset()
    elif args.action=='status':value=controller.status()
    else:raise ValueError('unknown fallback action')
    print(json.dumps(value,ensure_ascii=False,indent=2,default=str));return 0


def command_hardware(args):
    print(json.dumps(hardware_summary(),ensure_ascii=False,indent=2,default=str));return 0


def command_claude(args):
    root=_root(args.root)
    if args.action=='status':value=claude_status(root)
    elif args.action=='install':value=claude_install(root,args.timeout)
    elif args.action=='uninstall':value=claude_uninstall(root)
    else:raise ValueError('unknown claude action')
    print(json.dumps(value,ensure_ascii=False,indent=2,default=str));return 0


def command_arena(args):
    from .arena import ModelPerformanceArena
    provider=_provider(args)
    value=ModelPerformanceArena(args.steps).run_model(provider,args.model)
    print(json.dumps(value,ensure_ascii=False,indent=2,default=str));return 0 if value['status']=='PASS' else 2


def command_reliability(args):
    from .agent_runtime import Journal
    print(json.dumps(reliability_summary(Journal(_root(args.root))),ensure_ascii=False,indent=2,default=str));return 0


def command_budget(args):
    from .agent_runtime import Journal
    value=AdaptiveSwarmBudget(hardware_summary()['hardware'] if False else __import__('loopsieve.hardware',fromlist=['detect_hardware']).detect_hardware(),
                              max_agents=args.max_agents,max_llm_calls=args.max_calls).recommend(
                                  active=args.active,model_mb=args.model_mb,calls_used=args.calls_used)
    print(json.dumps(value,ensure_ascii=False,indent=2,default=str));return 0


def command_checkpoint(args):
    from .agent_runtime import Journal
    value=CheckpointTimeMachine(Journal(_root(args.root)))
    if args.action=='list':out=value.summary(args.value or '')
    elif args.action=='restore':
        if not args.value or not args.checkpoint:raise ValueError('restore requires --value session and --checkpoint')
        out=value.restore(args.value,args.checkpoint)
    elif args.action=='latest':out=value.latest(args.value or '',args.source)
    else:raise ValueError('unknown checkpoint action')
    print(json.dumps(out,ensure_ascii=False,indent=2,default=str));return 0


def command_handoff(args):
    from .agent_runtime import Journal
    value=VerifiedTaskHandoff(Journal(_root(args.root)))
    if args.action=='verify':out=value.verify(args.value or '')
    elif args.action=='create':
        if not args.value or not args.output:raise ValueError('handoff create needs --value session and --output')
        out=value.handoff(args.value,args.output)
    elif args.action=='accept':
        if not args.value:raise ValueError('handoff accept needs --value manifest path')
        out=value.accept(args.value)
    else:raise ValueError('unknown handoff action')
    print(json.dumps(out,ensure_ascii=False,indent=2,default=str));return 0


def command_risk(args):
    from .failure import predict_failure
    value=predict_failure(_root(args.root),args.paths)
    print(json.dumps(value,ensure_ascii=False,indent=2,default=str));return 0


def command_route(args):
    from .catalog import load
    value=route_tools(load('agents',args.value or '001-chief-architect'),args.task or '')
    print(json.dumps(value,ensure_ascii=False,indent=2,default=str));return 0


def command_tui(args):
    from .tui import launch
    return launch(_root(args.root),args.provider,args.model,args.allow_writes,args.allow_checks,args.role)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="loopsieve", description="Local verification and diagnostic delta filtering for coding agents.")
    sub = parser.add_subparsers(dest="command", required=False)

    init = sub.add_parser("init", help="detect project checks and write .loopsieve.json")
    init.add_argument("--root")
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=command_init)

    check = sub.add_parser("check", help="run relevant checks for changed files")
    check.add_argument("files", nargs="*")
    check.add_argument("--root")
    check.add_argument("--explain", action="store_true", help="explain failures with a local llama-server")
    check.add_argument("--llm-config", type=Path, help="optional local inference settings JSON")
    check.add_argument("--prompt-cache", action="store_true", help="experimentally enable llama-server prompt reuse")
    check.set_defaults(func=command_check)

    report = sub.add_parser("report", help="show local verification statistics")
    report.add_argument("--root")
    report.add_argument("--json", action="store_true")
    report.set_defaults(func=command_report)

    install = sub.add_parser("install-hook", help="install a project-local Claude Code PostToolBatch hook")
    install.add_argument("--root")
    install.add_argument("--timeout", type=int, default=180)
    install.set_defaults(func=command_install)

    uninstall = sub.add_parser("uninstall-hook", help="remove the project-local Claude Code hook")
    uninstall.add_argument("--root")
    uninstall.set_defaults(func=command_uninstall)

    benchmark = sub.add_parser("benchmark", help="measure repeated-diagnostic suppression on a fixture")
    benchmark.add_argument("fixture")
    benchmark.add_argument("--json", action="store_true")
    benchmark.set_defaults(func=command_benchmark)

    # Local-first expansion: all three interfaces share the same core.
    ui = sub.add_parser("ui", help="open optional interactive terminal UI")
    ui.add_argument("--root")
    ui.set_defaults(func=lambda a: __import__('loopsieve.tui', fromlist=['launch']).launch(_root(a.root)))

    web = sub.add_parser("web", help="serve read-only local dashboard at 127.0.0.1")
    web.add_argument("--root")
    web.add_argument("--port", type=int, default=8765)
    web.set_defaults(func=lambda a: __import__('loopsieve.webui', fromlist=['serve']).serve(_root(a.root), a.port))

    intelligence=sub.add_parser('intelligence',help='local context, symbols, imports, permissions, and session capsules')
    intelligence.add_argument('action',choices=['context','symbols','imports','permissions','reliability','diff','capsule'])
    intelligence.add_argument('value',nargs='?')
    intelligence.add_argument('--root')
    intelligence.add_argument('--output')
    intelligence.add_argument('--max-chars',type=int,default=5000)
    intelligence.add_argument('--allow-writes',action='store_true')
    intelligence.add_argument('--allow-checks',action='store_true')
    intelligence.set_defaults(func=command_intelligence)

    mcp=sub.add_parser('mcp',help='inspect local MCP server config without starting servers')
    mcp.add_argument('action',nargs='?',choices=['list'],default='list')
    mcp.add_argument('--root')
    mcp.set_defaults(func=command_mcp)

    chat=sub.add_parser('chat',help='terminal chat with agent step/run/history')
    chat.add_argument('--root')
    chat.add_argument('--provider',choices=['ollama','claude','codex'],default='ollama')
    chat.add_argument('--model',default='llama3.2:3b')
    chat.add_argument('--role')
    chat.add_argument('--allow-writes',action='store_true')
    chat.add_argument('--allow-checks',action='store_true')
    chat.set_defaults(func=lambda a: __import__('loopsieve.terminal_chat',fromlist=['launch']).launch(
        _root(a.root),a.provider,a.model,a.allow_writes,a.allow_checks,a.role))

    studio = sub.add_parser('studio',help='launch opt-in agent Studio with interactive 3D Pip')
    studio.add_argument('--root')
    studio.add_argument('--port',type=int,default=8766)
    studio.set_defaults(func=lambda a: __import__('loopsieve.studio',fromlist=['serve']).serve(_root(a.root),a.port))

    doctor = sub.add_parser("doctor", help="diagnose catalogs, tools and local environment")
    doctor.add_argument("--root")
    doctor.set_defaults(func=_doctor)

    for name,help_text in (
      ('agents','inspect/select 100 local-first agent roles'),
      ('tools','list or execute safe local tools'),
      ('plugins','inspect 50 optional CLI integration adapters'),
      ('skills','inspect or run 50 deterministic workflows'),
      ('technologies','inspect implemented mechanisms and plans'),
      ('tasks','create, list or run explicit local tasks'),
    ):
        group=sub.add_parser(name, help=help_text)
        group.add_argument('action', nargs='?', default='list',
            choices={'agents':['list','show','select'], 'tools':['list','run'],
              'plugins':['list','probe'], 'skills':['list','show','run'],
              'technologies':['list','show'], 'tasks':['list','create','run','cancel']}[name])
        group.add_argument('value', nargs='?')
        group.add_argument('--root')
        group.add_argument('--args', default='{}', help='JSON object with local tool arguments')
        group.add_argument('--tool', help='explicit read-only tool for a queued task')
        group.add_argument('--agent', help='agent ID for task creation')
        group.add_argument('--json', action='store_true')
        group.set_defaults(func=lambda a,kind=name: _catalog_command(kind,a))

    def provider_flags(p):
        p.add_argument('--root')
        p.add_argument('--provider',choices=['ollama','claude','codex','compatible'],default='ollama')
        p.add_argument('--model',default='llama3.2:3b')
        p.add_argument('--endpoint',help='API endpoint; compatible remote APIs require HTTPS')
        p.add_argument('--steps',type=int,default=8)
        p.add_argument('--allow-writes',action='store_true',help='explicit permission to patch existing project files')
        p.add_argument('--allow-checks',action='store_true',help='explicit permission to run project-defined check commands')
    autonomous=sub.add_parser('agent',help='run or manage demand-activated autonomous agents')
    autonomous.add_argument('action',choices=['run','step','resume','pause','cancel','sessions','inspect','recover','checkpoints','restore'])
    autonomous.add_argument('value',nargs='?',help='task text or session ID')
    autonomous.add_argument('--role',help='agent ID, otherwise selected by task')
    autonomous.add_argument('--checkpoint',type=int,help='checkpoint ID for agent restore')
    provider_flags(autonomous)
    autonomous.set_defaults(func=command_agent)
    team=sub.add_parser('team',help='run a bounded, sequential agent task DAG')
    team.add_argument('value',help='path to task-DAG JSON')
    team.add_argument('--parallel',action='store_true',default=True,help='allow safe write-set-scoped parallelism')
    team.add_argument('--no-parallel',dest='parallel',action='store_false')
    team.add_argument('--max-workers',type=int,default=4)
    provider_flags(team)
    team.set_defaults(func=command_team)
    models=sub.add_parser('models',help='hardware-aware model catalog, memory estimates and verified downloads')
    models.add_argument('action',nargs='?',default='status',choices=['status','list','show','memory','auto','select','benchmark','download','verify','quantize'])
    models.add_argument('value',nargs='?',help='model ID or task text')
    models.add_argument('--root')
    models.add_argument('--quantization')
    models.add_argument('--context',type=int)
    models.add_argument('--max-mb',type=int)
    models.add_argument('--installed',action='append',default=[])
    models.add_argument('--provider',choices=['ollama','compatible','claude','codex'])
    models.add_argument('--model',default='llama3.2:3b')
    models.add_argument('--endpoint')
    models.add_argument('--url')
    models.add_argument('--sha256')
    models.add_argument('--license')
    models.add_argument('--accept-license',action='store_true')
    models.add_argument('--approve-download',action='store_true')
    models.add_argument('--max-bytes',type=int,default=20*1024**3)
    models.add_argument('--backend',default='ollama')
    models.add_argument('--steps',type=int,default=8)
    models.add_argument('--allow-writes',action='store_true')
    models.add_argument('--allow-checks',action='store_true')
    models.set_defaults(func=command_models)

    provider_cmd=sub.add_parser('provider',help='provider health monitor and fallback configuration')
    provider_cmd.add_argument('action',nargs='?',default='status',choices=['status','list'])
    provider_cmd.add_argument('--root')
    provider_cmd.add_argument('--provider',choices=['ollama','compatible','claude','codex'],default='ollama')
    provider_cmd.add_argument('--model',default='llama3.2:3b')
    provider_cmd.add_argument('--endpoint')
    provider_cmd.add_argument('--steps',type=int,default=8)
    provider_cmd.add_argument('--allow-writes',action='store_true')
    provider_cmd.add_argument('--allow-checks',action='store_true')
    provider_cmd.set_defaults(func=command_provider)

    fallback=sub.add_parser('fallback',help='enable, disable or inspect safe provider fallback')
    fallback.add_argument('action',nargs='?',default='status',choices=['enable','disable','status','reset'])
    fallback.add_argument('--root')
    fallback.add_argument('--provider',choices=['ollama','compatible','claude','codex'],default='ollama')
    fallback.add_argument('--model',default='llama3.2:3b')
    fallback.add_argument('--endpoint')
    fallback.add_argument('--fallback-provider',choices=['ollama','compatible','claude','codex'])
    fallback.add_argument('--fallback-model')
    fallback.add_argument('--fallback-endpoint')
    fallback.add_argument('--steps',type=int,default=8)
    fallback.add_argument('--allow-writes',action='store_true')
    fallback.add_argument('--allow-checks',action='store_true')
    fallback.set_defaults(func=command_fallback)

    hardware=sub.add_parser('hardware',help='detect CPU, RAM and GPU/VRAM without loading a model')
    hardware.add_argument('--root')
    hardware.set_defaults(func=command_hardware)

    claude=sub.add_parser('claude',help='install or inspect the official Claude Code project hook')
    claude.add_argument('action',nargs='?',default='status',choices=['status','install','uninstall'])
    claude.add_argument('--root')
    claude.add_argument('--timeout',type=int,default=180)
    claude.set_defaults(func=command_claude)

    arena=sub.add_parser('arena',help='run the same real coding fixture against a provider')
    arena.add_argument('--root')
    arena.add_argument('--provider',choices=['ollama','compatible','claude','codex'],default='ollama')
    arena.add_argument('--model',default='llama3.2:3b')
    arena.add_argument('--endpoint')
    arena.add_argument('--steps',type=int,default=8)
    arena.add_argument('--allow-writes',action='store_true')
    arena.add_argument('--allow-checks',action='store_true')
    arena.set_defaults(func=command_arena)

    reliability=sub.add_parser('reliability',help='rank agent roles from local completed/verified outcomes')
    reliability.add_argument('--root')
    reliability.set_defaults(func=command_reliability)

    budget=sub.add_parser('budget',help='adaptive swarm worker budget from local memory and call limits')
    budget.add_argument('--root')
    budget.add_argument('--max-agents',type=int,default=8)
    budget.add_argument('--max-calls',type=int,default=200)
    budget.add_argument('--active',type=int,default=0)
    budget.add_argument('--model-mb',type=int,default=0)
    budget.add_argument('--calls-used',type=int,default=0)
    budget.set_defaults(func=command_budget)

    checkpoint=sub.add_parser('checkpoint',help='inspect and restore pre-write file checkpoints')
    checkpoint.add_argument('action',nargs='?',default='list',choices=['list','restore','latest'])
    checkpoint.add_argument('value',nargs='?')
    checkpoint.add_argument('--root')
    checkpoint.add_argument('--checkpoint',type=int)
    checkpoint.add_argument('--source')
    checkpoint.set_defaults(func=command_checkpoint)

    handoff=sub.add_parser('handoff',help='create or accept a verified task handoff manifest')
    handoff.add_argument('action',nargs='?',default='verify',choices=['verify','create','accept'])
    handoff.add_argument('value',nargs='?')
    handoff.add_argument('--root')
    handoff.add_argument('--output')
    handoff.set_defaults(func=command_handoff)

    risk=sub.add_parser('risk',help='heuristic build-risk prediction for changed files')
    risk.add_argument('paths',nargs='+')
    risk.add_argument('--root')
    risk.set_defaults(func=command_risk)

    route=sub.add_parser('route',help='deterministic tool routing for an agent and task')
    route.add_argument('value',nargs='?',help='agent ID')
    route.add_argument('--task',required=True)
    route.add_argument('--root')
    route.set_defaults(func=command_route)

    tui=sub.add_parser('tui',help='interactive terminal workbench')
    tui.add_argument('--root')
    tui.add_argument('--provider',choices=['ollama','compatible','claude','codex'],default='ollama')
    tui.add_argument('--model',default='llama3.2:3b')
    tui.add_argument('--role')
    tui.add_argument('--allow-writes',action='store_true')
    tui.add_argument('--allow-checks',action='store_true')
    tui.set_defaults(func=command_tui)

    modelteam=sub.add_parser('modelteam',help='native multi-model team with logical agents and real dialogue')
    modelteam.add_argument('action',nargs='?',default='status',choices=['status','run','parallel','agents','dialogue','capacity'])
    modelteam.add_argument('value',nargs='?')
    modelteam.add_argument('--root')
    modelteam.add_argument('--provider',choices=['ollama','compatible','claude','codex'],default='ollama')
    modelteam.add_argument('--model',action='append',default=[])
    modelteam.add_argument('--endpoint')
    modelteam.add_argument('--steps',type=int,default=8)
    modelteam.add_argument('--max-models',type=int,default=15)
    modelteam.add_argument('--agents-per-model',type=int,default=100)
    modelteam.add_argument('--limit',type=int,default=200)
    modelteam.add_argument('--allow-writes',action='store_true')
    modelteam.add_argument('--allow-checks',action='store_true')
    modelteam.set_defaults(func=command_modelteam)

    hf=sub.add_parser('hf',help='official Hugging Face metadata explorer with pagination')
    hf.add_argument('action',nargs='?',default='search',choices=['search','info','files'])
    hf.add_argument('query',nargs='?')
    hf.add_argument('--limit',type=int,default=20)
    hf.add_argument('--pipeline')
    hf.add_argument('--timeout',type=int,default=20)
    hf.set_defaults(func=command_hf)

    providers=sub.add_parser('providers',help='provider catalog metadata and verification state')
    providers.add_argument('query',nargs='?')
    providers.add_argument('--limit',type=int,default=120)
    providers.set_defaults(func=command_providers)

    capabilities=sub.add_parser('capabilities',help='unified capability registry and router')
    capabilities.add_argument('query',nargs='?')
    capabilities.add_argument('--limit',type=int,default=20)
    capabilities.set_defaults(func=command_capabilities)

    permissions=sub.add_parser('permissions',help='inspect the deny-by-default permission policy')
    permissions.set_defaults(func=command_permissions)

    quantization=sub.add_parser('quantization',help='quantization methods and recommended profiles')
    quantization.add_argument('model',nargs='?',default='llama3.2:3b')
    quantization.set_defaults(func=command_quantization)

    secrets=sub.add_parser('secrets',help='store API keys with DPAPI/keyring; never plaintext by default')
    secrets.add_argument('action',choices=['list','set','get','delete'])
    secrets.add_argument('--name')
    secrets.add_argument('--value',help='prefer the hidden prompt; this flag is for automation')
    secrets.set_defaults(func=command_secrets)

    proof=sub.add_parser('proof',help='inspect and verify provenance, impacts, contracts, memories and artifacts')
    proof.add_argument('action',choices=['evidence','impact','context','conflicts','contract','gate','check-suite','capsule','memory','artifact','worktree'])
    proof.add_argument('operation',nargs='?',default='list')
    proof.add_argument('paths',nargs='*')
    proof.add_argument('--root')
    proof.add_argument('--input',help='JSON contract, gate or explicit check-suite configuration')
    proof.add_argument('--query')
    proof.add_argument('--budget',type=int,default=6000)
    proof.add_argument('--session')
    proof.add_argument('--output')
    proof.add_argument('--value')
    proof.add_argument('--source')
    proof.add_argument('--timeout',type=int,default=25)
    proof.add_argument('--approve-commands',action='store_true',help='explicitly approve executing local verification argv')
    proof.add_argument('--approve-worktree',action='store_true',help='explicitly approve creating a detached Git worktree')
    proof.set_defaults(func=command_proof)

    innovation=sub.add_parser('innovations',help='list evidence-backed status of the 100 proposed innovations')
    innovation.add_argument('item',nargs='?')
    innovation.add_argument('--status',choices=['IMPLEMENTED_TESTED','PARTIAL','PLANNED'])
    innovation.add_argument('--summary',action='store_true')
    innovation.set_defaults(func=command_innovations)

    demo=sub.add_parser('demo',help='run an offline scripted scenario with real code edits and verification')
    demo.add_argument('--output',help='optional JSON report path, refuses overwrite')
    demo.set_defaults(func=lambda a: _out(__import__('loopsieve.demo',fromlist=['run_offline_demo']).run_offline_demo(Path(a.output) if a.output else None)))
    hook = sub.add_parser("hook", help=argparse.SUPPRESS)
    hook.set_defaults(func=None)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command is None:
        from .tui import launch
        return launch(Path.cwd())
    if args.command == "hook":
        return hook_main()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
