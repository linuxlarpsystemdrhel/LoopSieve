"""Terminal workbench command router shared by the interactive TUI and tests.

The router deliberately keeps permissions explicit. It never starts a model on
construction and never executes project check commands unless allow_checks is on.
"""
from __future__ import annotations

import json
import os
import shlex
from pathlib import Path
from typing import Any

from .agent_runtime import AgentRuntime, Journal
from .agents import list_agents, select_agents
from .budget import AdaptiveSwarmBudget
from .capability import CapabilityRegistry
from .huggingface import HuggingFaceClient, search_compatible
from .checkpoint import CheckpointTimeMachine
from .config import load_config
from .engine import verify
from .handoff import VerifiedTaskHandoff
from .hardware import detect_hardware, hardware_summary
from .model_manager import ModelManager, load_catalog
from .model_team import ModelTeam, TeamStore, team_capacity
from .orchestrator import Orchestrator, WorkItem, load_work_items
from .permissions import PermissionEngine
from .provider_catalog import ProviderCatalog
from .quantization import method_catalog, recommend_profiles
from .provider_health import FallbackController, FallbackProvider, ProviderHealthMonitor, ProviderSlot
from .providers import CLIProvider, CompatibleProvider, OllamaProvider, ProviderError
from .reliability import rank_agents
from .routing import route_tools
from .state import default_state_base
from .toolkit import tool_catalog


def build_provider(provider: str = 'ollama', model: str = 'llama3.2:3b',
                   endpoint: str | None = None, timeout: int = 90):
    provider = (provider or 'ollama').lower()
    if provider == 'ollama':
        return OllamaProvider(model=model, endpoint=endpoint or 'http://127.0.0.1:11434/api/chat', timeout=timeout)
    if provider == 'compatible':
        if not endpoint:
            raise ValueError('compatible provider requires --endpoint')
        return CompatibleProvider(model=model, endpoint=endpoint, timeout=timeout)
    if provider in ('claude', 'codex'):
        return CLIProvider(provider, timeout=timeout)
    raise ValueError(f'unknown provider: {provider}')


def build_fallback_chain(primary: Any, fallback: Any | None = None,
                         state_path: Path | None = None) -> FallbackProvider:
    slots = [ProviderSlot(primary, label='primary')]
    if fallback is not None:
        slots.append(ProviderSlot(fallback, label='fallback'))
    return FallbackProvider(slots, state_path=state_path)


def _split_args(text: str) -> list[str]:
    # On Windows, POSIX shlex would consume backslashes in absolute paths.
    return shlex.split(text, posix=os.name != 'nt')


def _text(value: Any, limit: int = 9000) -> str:
    if isinstance(value, str):
        return value[:limit]
    return json.dumps(value, ensure_ascii=False, default=str, indent=2)[:limit]


class TerminalWorkbench:
    def __init__(self, root: Path, *, provider: Any | None = None, provider_name: str = 'ollama',
                 model: str = 'llama3.2:3b', endpoint: str | None = None,
                 allow_writes: bool = False, allow_checks: bool = False,
                 agent_id: str | None = None):
        self.root = Path(root).resolve()
        self.provider_name = provider_name
        self.model = model
        self.endpoint = endpoint
        self.allow_writes = bool(allow_writes)
        self.allow_checks = bool(allow_checks)
        self.agent_id = agent_id
        self.journal = Journal(self.root)
        self.monitor = ProviderHealthMonitor(self.journal.path.parent / 'health.json')
        self.permissions = PermissionEngine()
        self.manager = ModelManager()
        self.capabilities = CapabilityRegistry()
        self.provider_catalog = ProviderCatalog()
        self.hf = HuggingFaceClient()
        self.fallback: FallbackProvider | None = None
        if provider is None:
            try:
                provider = build_provider(provider_name, model, endpoint)
            except ValueError:
                provider = None
        if provider is not None:
            try:
                self.fallback = build_fallback_chain(provider, state_path=self.journal.path.parent / 'fallback.json')
            except Exception:
                self.fallback = None
        self.provider = self.fallback or provider
        self.runtime = AgentRuntime(self.root, self.provider, self.journal,
                                    health_monitor=self.monitor,
                                    permission_engine=self.permissions)
        self.model_team = ModelTeam(self.root, store=TeamStore(self.journal.path.parent / 'team.db'),
                              journal=self.journal, permission_engine=self.permissions)
        if self.provider is not None:
            try:
                self.model_team.add_model(self.model, self.provider, role='primary')
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Command entry point
    # ------------------------------------------------------------------
    def run(self, line: str) -> dict:
        raw = str(line or '').strip()
        if not raw:
            return {'ok': True, 'text': '', 'data': {}}
        if not raw.startswith('/'):
            return self.agent_run(raw)
        parts = raw.split(None, 1)
        command = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ''
        handler = {
            '/help': self.help, '/?': self.help, '/quit': self.quit, '/exit': self.quit,
            '/status': self.status, '/models': self.models, '/model': self.model_command,
            '/provider': self.provider_command, '/fallback': self.fallback_command,
            '/agent': self.agent_command, '/team': self.team, '/verify': self.verify,
            '/sessions': self.sessions, '/checkpoint': self.checkpoint, '/handoff': self.handoff,
            '/risk': self.risk, '/reliability': self.reliability, '/budget': self.budget,
            '/tools': self.tools, '/route': self.route, '/mascot': self.mascot,
            '/hardware': self.hardware, '/recover': self.recover,
            '/hf': self.huggingface, '/providers': self.providers,
            '/quantization': self.quantization, '/permissions': self.permission_command,
            '/capabilities': self.capabilities_command, '/dialogue': self.dialogue,
        }.get(command)
        if handler is None:
            return {'ok': False, 'text': f'Unknown command {command}. Type /help.'}
        try:
            return handler(rest)
        except Exception as exc:
            return {'ok': False, 'text': f'{type(exc).__name__}: {exc}', 'data': {}}

    def help(self, rest: str = '') -> dict:
        text = """LoopSieve terminal workbench
  /status                 session, provider, model and permission summary
  /models                 hardware-aware model catalog
  /model select <id> [q]  select a catalog model/quantization
  /model local [id]       use an installed local Ollama model
  /model auto [task]      choose a fitting model from the catalog
  /model benchmark [id]   real one-call latency check (no coding claim)
  /model memory [id]      memory estimate and fit label
  /provider status        non-invasive provider health probe
  /fallback enable|disable|status|reset
  /agent [id]             show/select an agent role
  /agent run <task>       run a bounded autonomous session
  /team status            multi-model team state and agent counts
  /team add <model>       add the current provider model to the team
  /team run <task>        run a task on the first team model
  /team parallel <task>   run read-only solutions on all team models
  /team dialogue [task]   show the real message bus
  /team export <path>     export team dialogue JSON
  /team <dag.json>        run a dependency-aware task DAG
  /hf search <query>      official HF metadata search with pagination
  /hf info <model>        HF model metadata
  /providers [query]      provider catalog (metadata only)
  /quantization [model]   quantization methods and recommended profiles
  /permissions            active permission policy and grant summary
  /capabilities [query]   unified capability registry and router
  /dialogue [task]        alias for /team dialogue
  /verify <file...>       run configured local checks
  /sessions               list saved sessions
  /checkpoint <session>   list file checkpoints
  /handoff <session> <out> create a verified handoff manifest
  /risk <file...>         heuristic build-risk prediction
  /reliability            local agent outcome ranking
  /budget                 adaptive swarm budget
  /tools                  read-only tool catalog
  /route <agent> <task>   deterministic tool routing
  /hardware               detected CPU/RAM/VRAM
  /recover                recover interrupted sessions
  /mascot                 pixel-art Pip
  /quit                   exit; sessions stay on disk
Writes and project checks remain OFF unless explicitly enabled at launch."""
        return {'ok': True, 'text': text, 'data': {'commands': text.splitlines()}}

    def quit(self, rest: str = '') -> dict:
        return {'ok': True, 'text': 'Goodbye. Sessions and evidence remain on disk.', 'data': {'quit': True}}

    def status(self, rest: str = '') -> dict:
        sessions = self.journal.list()
        active = sessions[0] if sessions else None
        health = self.monitor.status()
        value = {'workspace': str(self.root), 'provider': self.provider_name,
                 'model': self.model, 'agent_id': self.agent_id,
                 'allow_writes': self.allow_writes, 'allow_checks': self.allow_checks,
                 'sessions': len(sessions), 'active_session': active,
                 'provider_health': health,
                 'fallback': self.fallback.status() if self.fallback else None,
                 'hardware': hardware_summary()['summary'],
                 'team': self.model_team.status(), 'permissions': self.permissions.snapshot()}
        lines = [f"Workspace  {self.root}", f"Provider   {self.provider_name}",
                 f"Model      {self.model}", f"Agent      {self.agent_id or 'auto'}",
                 f"Writes     {'ON' if self.allow_writes else 'OFF'}",
                 f"Checks     {'ON' if self.allow_checks else 'OFF'}",
                 f"Sessions   {len(sessions)}",
                 f"Team       {self.model_team.status()['models']} models / {self.model_team.status()['registered_agents']} agents"]
        return {'ok': True, 'text': '\n'.join(lines), 'data': value}

    def models(self, rest: str = '') -> dict:
        installed = self._installed_models()
        value = self.manager.status(installed=installed)
        lines = [f"Hardware: {value['hardware']['os_name']} {value['hardware']['architecture']}  "
                 f"RAM {value['hardware']['ram_total_mb']} MiB  VRAM {value['hardware']['total_vram_mb']} MiB"]
        for row in value['models']:
            lines.append(f"  {row['status']:<20} {row['model']:<28} {row.get('quantization',''):<7} "
                         f"{row.get('estimate',{}).get('total_mb','?')} MiB  {row['license']}")
        lines.append('No model was downloaded or started.')
        return {'ok': True, 'text': '\n'.join(lines), 'data': value}

    def model_command(self, rest: str) -> dict:
        parts = _split_args(rest)
        if not parts:
            return self.models()
        action = parts[0].lower()
        if action == 'select':
            if len(parts) < 2:
                return {'ok': False, 'text': 'usage: /model select <id> [quantization]'}
            model_id = parts[1]
            quant = parts[2] if len(parts) > 2 else None
            installed = model_id in self._installed_models()
            plan = self.manager.select(model_id, quant, provider=self.provider_name, installed=installed)
            self.model = model_id
            if self.provider is not None and hasattr(self.provider, 'model'):
                try:
                    self.provider.model = model_id
                except Exception:
                    pass
            return {'ok': True, 'text': _text(plan), 'data': plan}
        if action == 'local':
            installed = self._installed_models()
            if len(parts) > 1:
                model_id = parts[1]
                if model_id not in installed and not any(x.split(':')[0] == model_id for x in installed):
                    return {'ok': False, 'text': f'{model_id} is not reported as installed by the local provider',
                            'data': {'installed': installed}}
            else:
                model_id = installed[0] if installed else None
            if not model_id:
                return {'ok': False, 'text': 'no installed local model detected; use /provider status or install one',
                        'data': {'installed': installed}}
            plan = self.manager.select(model_id, provider=self.provider_name, installed=True)
            self.model = model_id
            return {'ok': True, 'text': _text(plan), 'data': plan}
        if action == 'auto':
            task = ' '.join(parts[1:]) or 'coding task'
            plan = self.manager.auto(task, installed=self._installed_models())
            if plan.get('selected'):
                self.model = plan['selected']
            return {'ok': True, 'text': _text(plan), 'data': plan}
        if action == 'benchmark':
            model_id = parts[1] if len(parts) > 1 else self.model
            result = self.manager.benchmark(model_id, self.provider)
            return {'ok': result.get('status') != 'FAILED', 'text': _text(result), 'data': result}
        if action == 'memory':
            model_id = parts[1] if len(parts) > 1 else self.model
            result = self.manager.memory(model_id)
            return {'ok': True, 'text': _text(result), 'data': result}
        return {'ok': False, 'text': 'usage: /model [select|local|auto|benchmark|memory] ...'}

    def _installed_models(self) -> list[str]:
        if self.provider is None:
            return []
        try:
            if hasattr(self.provider, 'probe'):
                health = self.provider.probe()
                return list(health.get('installed_models', []) or [])
        except Exception:
            return []
        return []

    def provider_command(self, rest: str) -> dict:
        action = (rest or 'status').split()[0].lower()
        if action == 'status':
            if self.provider is None:
                return {'ok': False, 'text': 'No provider configured. Use --provider ollama|compatible|claude|codex.',
                        'data': {'state': 'UNCONFIGURED'}}
            value = self.monitor.probe(self.provider)
            if self.fallback:
                value['fallback'] = self.fallback.status()
            return {'ok': value.get('state') in ('READY', 'UNVERIFIED'), 'text': _text(value), 'data': value}
        return {'ok': False, 'text': 'usage: /provider status'}

    def fallback_command(self, rest: str) -> dict:
        if not self.fallback:
            return {'ok': False, 'text': 'fallback is not configured', 'data': {}}
        action = (rest or 'status').split()[0].lower()
        controller = FallbackController(self.fallback)
        if action == 'enable':
            value = controller.enable()
        elif action == 'disable':
            value = controller.disable()
        elif action == 'reset':
            value = controller.reset()
        elif action == 'status':
            value = controller.status()
        else:
            return {'ok': False, 'text': 'usage: /fallback enable|disable|status|reset'}
        return {'ok': True, 'text': _text(value), 'data': value}

    def agent_command(self, rest: str) -> dict:
        parts = _split_args(rest)
        if not parts:
            rows = [{'id': a['id'], 'name': a['name'], 'area': a['specialization']} for a in list_agents()]
            return {'ok': True, 'text': _text(rows), 'data': {'agents': rows}}
        action = parts[0].lower()
        if action == 'run':
            return self.agent_run(' '.join(parts[1:]))
        self.agent_id = parts[0]
        try:
            from .catalog import load
            agent = load('agents', self.agent_id)
        except KeyError as exc:
            return {'ok': False, 'text': str(exc)}
        return {'ok': True, 'text': f"Selected {agent['name']} ({agent['id']})", 'data': {'agent': agent}}

    def agent_run(self, task: str) -> dict:
        if not task.strip():
            return {'ok': False, 'text': 'usage: /agent run <task>'}
        if self.provider is None:
            return {'ok': False, 'text': 'No provider configured; agent run cannot start.'}
        session = self.runtime.create(task, self.agent_id, allow_writes=self.allow_writes,
                                      allow_checks=self.allow_checks)
        result = self.runtime.run(session['id'])
        value = {'id': result['id'], 'status': result['status'], 'agent_id': result['agent_id'],
                 'step': result['step'], 'changed': result['changed'], 'evidence': result['evidence'],
                 'last_message': result['messages'][-1] if result.get('messages') else None}
        return {'ok': result['status'] == 'COMPLETED', 'text': _text(value), 'data': value}

    def team(self, rest: str) -> dict:
        parts = _split_args(rest)
        if not parts:
            return {'ok': True, 'text': _text(self.model_team.status()), 'data': self.model_team.status()}
        action = parts[0].lower()
        if action == 'status':
            return {'ok': True, 'text': _text(self.model_team.status()), 'data': self.model_team.status()}
        if action == 'add':
            if len(parts) < 2:
                return {'ok': False, 'text': 'usage: /team add <model-id>'}
            if self.provider is None:
                return {'ok': False, 'text': 'No provider configured; cannot add a model.'}
            value = self.model_team.add_model(parts[1], self.provider)
            return {'ok': True, 'text': _text(value), 'data': value}
        if action == 'remove':
            if len(parts) < 2:
                return {'ok': False, 'text': 'usage: /team remove <model-id>'}
            value = self.model_team.remove_model(parts[1])
            return {'ok': True, 'text': _text(value), 'data': value}
        if action == 'run':
            task = ' '.join(parts[1:])
            if not task:
                return {'ok': False, 'text': 'usage: /team run <task>'}
            value = self.model_team.run(task, allow_writes=self.allow_writes, allow_checks=self.allow_checks)
            return {'ok': value['state'] == 'COMPLETED', 'text': _text(value), 'data': value}
        if action == 'parallel':
            task = ' '.join(parts[1:])
            if not task:
                return {'ok': False, 'text': 'usage: /team parallel <task>'}
            value = self.model_team.run_parallel_solutions(task)
            return {'ok': value['pass_count'] > 0, 'text': _text(value), 'data': value}
        if action == 'dialogue':
            task_id = parts[1] if len(parts) > 1 else None
            value = self.model_team.dialogue(task_id)
            return {'ok': True, 'text': _text(value), 'data': value}
        if action == 'export':
            if len(parts) < 2:
                return {'ok': False, 'text': 'usage: /team export <path> [task-id]'}
            value = self.model_team.export_dialogue(Path(parts[1]), parts[2] if len(parts) > 2 else None)
            return {'ok': True, 'text': _text(value), 'data': value}
        path = Path(rest).expanduser()
        if not path.is_file():
            return {'ok': False, 'text': 'usage: /team <task-dag.json> or /team status|add|run|parallel|dialogue|export'}
        if self.provider is None:
            return {'ok': False, 'text': 'No provider configured; team run cannot start.'}
        items = load_work_items(path)
        outcome = Orchestrator(self.runtime, max_workers=min(4, len(items))).run(
            items, allow_writes=self.allow_writes, allow_checks=self.allow_checks)
        return {'ok': outcome['status'] == 'COMPLETED', 'text': _text(outcome), 'data': outcome}

    def dialogue(self, rest: str = '') -> dict:
        parts = _split_args(rest)
        value = self.model_team.dialogue(parts[0] if parts else None)
        return {'ok': True, 'text': _text(value), 'data': value}

    def huggingface(self, rest: str) -> dict:
        parts = _split_args(rest)
        if not parts:
            return {'ok': False, 'text': 'usage: /hf search <query> | /hf info <model>'}
        action = parts[0].lower()
        if action == 'search':
            if len(parts) < 2:
                return {'ok': False, 'text': 'usage: /hf search <query>'}
            value = self.hf.search(' '.join(parts[1:]), limit=10)
            return {'ok': True, 'text': _text(value), 'data': value}
        if action == 'info':
            if len(parts) < 2:
                return {'ok': False, 'text': 'usage: /hf info <model-id>'}
            value = self.hf.model_info(parts[1])
            return {'ok': True, 'text': _text(value), 'data': value}
        if action == 'files':
            if len(parts) < 2:
                return {'ok': False, 'text': 'usage: /hf files <model-id>'}
            value = self.hf.files(parts[1])
            return {'ok': True, 'text': _text(value), 'data': {'files': value}}
        return {'ok': False, 'text': 'usage: /hf search|info|files ...'}

    def providers(self, rest: str = '') -> dict:
        value = {'profiles': [x.as_dict() for x in self.provider_catalog.search(rest or '', limit=50)],
                 'status': self.provider_catalog.status()}
        return {'ok': True, 'text': _text(value), 'data': value}

    def quantization(self, rest: str = '') -> dict:
        model_id = _split_args(rest)[0] if _split_args(rest) else self.model
        model = self.manager.find(model_id)
        budget = (self.manager.hardware.free_vram_mb or self.manager.hardware.ram_free_mb or 0)
        value = {'model': model.id, 'methods': method_catalog(),
                 'profiles': recommend_profiles(model.params_b, budget, context_tokens=model.context_tokens,
                                                layers=model.layers, kv_heads=model.kv_heads,
                                                head_dim=model.head_dim) if budget else None,
                 'budget_mb': budget}
        return {'ok': True, 'text': _text(value), 'data': value}

    def permission_command(self, rest: str = '') -> dict:
        value = self.permissions.snapshot()
        return {'ok': True, 'text': _text(value), 'data': value}

    def capabilities_command(self, rest: str = '') -> dict:
        if rest:
            value = {'query': rest, 'results': [x.compact() for x in self.capabilities.search(rest, limit=20)],
                     'route': self.capabilities.route(rest, permission_engine=self.permissions)}
        else:
            value = {'kinds': {kind: len(self.capabilities.list(kind)) for kind in
                               ('tool', 'agent', 'skill', 'plugin', 'technology', 'model', 'provider', 'quantization')},
                     'total': len(self.capabilities.list())}
        return {'ok': True, 'text': _text(value), 'data': value}

    def verify(self, rest: str) -> dict:
        files = [x for x in _split_args(rest) if x]
        if not files:
            return {'ok': False, 'text': 'usage: /verify <file...>'}
        result = verify(self.root, [Path(x) for x in files], load_config(self.root))
        value = {'passed': result.passed, 'context': result.context,
                 'failed': [r.spec.name for r in result.failed_results]}
        return {'ok': result.passed, 'text': _text(value), 'data': value}

    def sessions(self, rest: str = '') -> dict:
        rows = self.journal.list()
        lines = [f"{x['id'][:8]}  {x['status']:<12} {x['agent_id']:<28} {x['task'][:55]}" for x in rows[:40]]
        return {'ok': True, 'text': '\n'.join(lines) or 'No sessions.', 'data': {'sessions': rows}}

    def checkpoint(self, rest: str) -> dict:
        sid = rest.split()[0] if rest else ''
        if not sid:
            return {'ok': False, 'text': 'usage: /checkpoint <session-id>'}
        value = CheckpointTimeMachine(self.journal).summary(sid)
        return {'ok': True, 'text': _text(value), 'data': value}

    def handoff(self, rest: str) -> dict:
        parts = _split_args(rest)
        if len(parts) < 2:
            return {'ok': False, 'text': 'usage: /handoff <session-id> <output.json>'}
        value = VerifiedTaskHandoff(self.journal).handoff(parts[0], Path(parts[1]))
        return {'ok': True, 'text': _text(value), 'data': value}

    def risk(self, rest: str) -> dict:
        from .failure import predict_failure
        files = _split_args(rest)
        if not files:
            return {'ok': False, 'text': 'usage: /risk <file...>'}
        value = predict_failure(self.root, files)
        return {'ok': True, 'text': _text(value), 'data': value}

    def reliability(self, rest: str = '') -> dict:
        value = rank_agents(self.journal)
        lines = [f"{r['agent_id']:<30} score={r['score']:<7} total={r['total']} verified={r['verified']}" for r in value[:20]]
        return {'ok': True, 'text': '\n'.join(lines) or 'No session evidence yet.', 'data': {'ranked': value}}

    def budget(self, rest: str = '') -> dict:
        value = AdaptiveSwarmBudget(detect_hardware()).recommend()
        return {'ok': True, 'text': _text(value), 'data': value}

    def tools(self, rest: str = '') -> dict:
        value = tool_catalog()
        return {'ok': True, 'text': '\n'.join(f"{x['id']:<28} {x['description']}" for x in value), 'data': {'tools': value}}

    def route(self, rest: str) -> dict:
        parts = _split_args(rest)
        if len(parts) < 2:
            return {'ok': False, 'text': 'usage: /route <agent-id> <task>'}
        from .catalog import load
        value = route_tools(load('agents', parts[0]), ' '.join(parts[1:]))
        return {'ok': True, 'text': _text(value), 'data': value}

    def hardware(self, rest: str = '') -> dict:
        value = hardware_summary()
        return {'ok': True, 'text': _text(value), 'data': value}

    def recover(self, rest: str = '') -> dict:
        value = self.runtime.recover()
        return {'ok': True, 'text': _text(value), 'data': {'recovered': value}}

    def mascot(self, rest: str = '') -> dict:
        from .mascot import pixel_mascot
        art = pixel_mascot()
        return {'ok': True, 'text': '\n'.join(art), 'data': {'art': art}}
