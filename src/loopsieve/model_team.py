"""Multi-model team runtime with bounded logical agents and a real message bus.

Each model is one provider slot. Up to 100 logical role agents can be registered
per slot, but only active tasks consume inference calls. Agent counts are never
presented as concurrently loaded model processes.
"""
from __future__ import annotations

import contextlib
import json
import sqlite3
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .agent_runtime import AgentRuntime, Journal
from .agents import list_agents, select_agents
from .permissions import PermissionEngine
from .state import default_state_base

TEAM_MESSAGE_KINDS = {'TASK', 'PROPOSAL', 'REVIEW', 'QUESTION', 'ANSWER', 'ARTIFACT',
                      'TOOL_RESULT', 'BLOCKED', 'VERIFIED'}
AGENT_STATES = {'READY', 'QUEUED', 'EXECUTING', 'COMPLETED', 'FAILED', 'BLOCKED', 'DISABLED'}


@dataclass
class LogicalAgent:
    id: str
    model_id: str
    role_id: str
    role_name: str
    state: str = 'READY'
    context_limit: int = 8192
    permissions: tuple[str, ...] = ('READ_ONLY',)
    session_id: str | None = None
    completed: int = 0
    failed: int = 0
    inference_calls: int = 0
    created_at: float = field(default_factory=time.time)
    last_active: float | None = None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class ModelSlot:
    model_id: str
    provider: Any
    role: str = 'worker'
    context_limit: int = 8192
    max_agents: int = 100
    loaded: bool = False
    runtime: AgentRuntime | None = None
    agents: dict[str, LogicalAgent] = field(default_factory=dict)


@dataclass
class TeamTask:
    id: str
    task: str
    model_id: str
    agent_id: str
    state: str = 'QUEUED'
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    session_id: str | None = None
    result: dict | None = None
    error: str | None = None
    allow_writes: bool = False
    allow_checks: bool = False
    max_steps: int = 8

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class TeamMessage:
    id: str
    kind: str
    from_agent: str
    to_agent: str | None
    content: str
    task_id: str | None = None
    model_id: str | None = None
    created_at: float = field(default_factory=time.time)
    refs: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)


class TeamStore:
    """SQLite message/task log; one file per project state."""
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else default_state_base() / 'team' / 'team.db'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    @contextlib.contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init(self):
        with self._connect() as conn:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('''CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY, kind TEXT, from_agent TEXT, to_agent TEXT,
                content TEXT, task_id TEXT, model_id TEXT, created_at REAL, refs TEXT)''')
            conn.execute('''CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY, payload TEXT, updated REAL)''')

    def message(self, message: TeamMessage) -> dict:
        with self._connect() as conn:
            conn.execute('INSERT OR REPLACE INTO messages VALUES (?,?,?,?,?,?,?,?,?)',
                         (message.id, message.kind, message.from_agent, message.to_agent,
                          message.content[:8000], message.task_id, message.model_id,
                          message.created_at, json.dumps(message.refs, default=str)[:4000]))
        return message.as_dict()

    def task(self, task: TeamTask) -> dict:
        with self._connect() as conn:
            conn.execute('INSERT OR REPLACE INTO tasks VALUES (?,?,?)',
                         (task.id, json.dumps(task.as_dict(), default=str), time.time()))
        return task.as_dict()

    def messages(self, task_id: str | None = None, limit: int = 200) -> list[dict]:
        limit = max(1, min(int(limit), 2000))
        with self._connect() as conn:
            if task_id:
                rows = conn.execute('SELECT * FROM messages WHERE task_id=? ORDER BY created_at LIMIT ?',
                                    (task_id, limit)).fetchall()
            else:
                rows = conn.execute('SELECT * FROM messages ORDER BY created_at DESC LIMIT ?', (limit,)).fetchall()
        result = []
        for row in rows:
            value = dict(row)
            value['refs'] = json.loads(value.get('refs') or '{}')
            result.append(value)
        return result

    def tasks(self, limit: int = 200) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute('SELECT payload FROM tasks ORDER BY updated DESC LIMIT ?', (limit,)).fetchall()
        return [json.loads(row['payload']) for row in rows]


class ModelTeam:
    def __init__(self, root: Path, *, max_models: int = 15, max_agents_per_model: int = 100,
                 store: TeamStore | None = None, journal: Journal | None = None,
                 permission_engine: PermissionEngine | None = None):
        if not 1 <= max_models <= 15:
            raise ValueError('max_models must be 1..15')
        if not 1 <= max_agents_per_model <= 100:
            raise ValueError('max_agents_per_model must be 1..100')
        self.root = Path(root).resolve()
        self.max_models = max_models
        self.max_agents_per_model = max_agents_per_model
        self.store = store or TeamStore()
        self.journal = journal or Journal(self.root)
        self.permissions = permission_engine or PermissionEngine()
        self.slots: dict[str, ModelSlot] = {}
        self.tasks: dict[str, TeamTask] = {}
        self._lock = threading.RLock()

    def add_model(self, model_id: str, provider: Any, *, role: str = 'worker',
                  context_limit: int = 8192, max_agents: int | None = None) -> dict:
        model_id = str(model_id or '').strip()
        if not model_id:
            raise ValueError('model_id is required')
        with self._lock:
            if model_id in self.slots:
                raise ValueError(f'model already in team: {model_id}')
            if len(self.slots) >= self.max_models:
                raise ValueError(f'team already has the maximum of {self.max_models} models')
            count = self.max_agents_per_model if max_agents is None else int(max_agents)
            if not 1 <= count <= self.max_agents_per_model:
                raise ValueError(f'max_agents must be 1..{self.max_agents_per_model}')
            slot = ModelSlot(model_id=model_id, provider=provider, role=role,
                             context_limit=context_limit, max_agents=count)
            slot.runtime = AgentRuntime(self.root, provider, self.journal, permission_engine=self.permissions)
            self.slots[model_id] = slot
        return {'model_id': model_id, 'role': role, 'max_agents': count,
                'registered_models': len(self.slots)}

    def remove_model(self, model_id: str) -> dict:
        with self._lock:
            if model_id not in self.slots:
                raise KeyError(model_id)
            del self.slots[model_id]
        return {'removed': model_id, 'registered_models': len(self.slots)}

    def register_agents(self, model_id: str, *, roles: list[dict] | None = None,
                        count: int | None = None) -> list[dict]:
        slot = self._slot(model_id)
        roles = roles or list_agents()
        wanted = slot.max_agents if count is None else int(count)
        if not 1 <= wanted <= slot.max_agents:
            raise ValueError(f'agent count must be 1..{slot.max_agents}')
        if len(roles) < wanted:
            raise ValueError('not enough role definitions to register the requested agents')
        created = []
        for role in roles[:wanted]:
            agent_id = f'{model_id}::{role["id"]}'
            agent = LogicalAgent(id=agent_id, model_id=model_id, role_id=role['id'],
                                 role_name=role.get('name', role['id']), context_limit=slot.context_limit)
            slot.agents[agent_id] = agent
            created.append(agent.as_dict())
        return created

    def _slot(self, model_id: str) -> ModelSlot:
        if model_id not in self.slots:
            raise KeyError(f'model not in team: {model_id}')
        return self.slots[model_id]

    def _ensure_agents(self, slot: ModelSlot) -> None:
        if not slot.agents:
            self.register_agents(slot.model_id)

    def agents(self, model_id: str | None = None, *, state: str | None = None,
               limit: int = 300) -> list[dict]:
        rows = []
        for slot in self.slots.values():
            if model_id and slot.model_id != model_id:
                continue
            for agent in slot.agents.values():
                if state and agent.state != state:
                    continue
                rows.append(agent.as_dict())
        return rows[:max(1, min(int(limit), 2000))]

    def _choose(self, task: str, model_id: str | None, agent_id: str | None) -> tuple[ModelSlot, LogicalAgent]:
        if not self.slots:
            raise RuntimeError('no models in team')
        if agent_id:
            for slot in self.slots.values():
                if agent_id in slot.agents:
                    return slot, slot.agents[agent_id]
            raise KeyError(agent_id)
        if model_id:
            slot = self._slot(model_id)
        else:
            slot = sorted(self.slots.values(), key=lambda x: x.model_id)[0]
        self._ensure_agents(slot)
        wanted = select_agents(task, max_agents=1)[0]['id']
        exact = [a for a in slot.agents.values() if a.role_id == wanted and a.state == 'READY']
        if exact:
            return slot, exact[0]
        ready = [a for a in slot.agents.values() if a.state == 'READY']
        if not ready:
            raise RuntimeError('no READY logical agents in selected model')
        return slot, ready[0]

    def submit(self, task: str, *, model_id: str | None = None, agent_id: str | None = None,
               max_steps: int = 8, allow_writes: bool = False,
               allow_checks: bool = False) -> dict:
        if not isinstance(task, str) or not task.strip():
            raise ValueError('task is required')
        slot, agent = self._choose(task, model_id, agent_id)
        team_task = TeamTask(id='team-' + uuid.uuid4().hex[:16], task=task[:8000],
                             model_id=slot.model_id, agent_id=agent.id,
                             allow_writes=allow_writes, allow_checks=allow_checks,
                             max_steps=max_steps)
        with self._lock:
            agent.state = 'QUEUED'
            self.tasks[team_task.id] = team_task
            self.store.task(team_task)
        self._say('TASK', agent.id, None, task[:2000], team_task.id, slot.model_id,
                  {'max_steps': max_steps, 'allow_writes': allow_writes, 'allow_checks': allow_checks})
        return team_task.as_dict()

    def run_task(self, task_id: str) -> dict:
        with self._lock:
            team_task = self.tasks.get(task_id)
            if team_task is None:
                raise KeyError(task_id)
            slot = self._slot(team_task.model_id)
            agent = slot.agents.get(team_task.agent_id)
            if agent is None:
                raise KeyError(team_task.agent_id)
            if team_task.state != 'QUEUED':
                raise ValueError(f'task is {team_task.state}')
            team_task.state = 'EXECUTING'
            team_task.started_at = time.time()
            agent.state = 'EXECUTING'
            self.store.task(team_task)
        try:
            session = slot.runtime.create(team_task.task, agent.role_id, max_steps=team_task.max_steps,
                                          allow_writes=team_task.allow_writes,
                                          allow_checks=team_task.allow_checks)
            team_task.session_id = session['id']
            result = slot.runtime.run(session['id'])
            agent.inference_calls += result.get('step', 0)
            agent.last_active = time.time()
            team_task.completed_at = time.time()
            team_task.result = {k: result.get(k) for k in ('status', 'step', 'changed', 'evidence')}
            if result['status'] == 'COMPLETED':
                agent.state = 'READY'; agent.completed += 1; team_task.state = 'COMPLETED'
                self._say('VERIFIED', agent.id, None,
                          result.get('messages', [{}])[-1].get('content', 'completed'),
                          team_task.id, slot.model_id,
                          {'session_id': result['id'], 'evidence': result.get('evidence', [])})
            else:
                agent.state = 'BLOCKED'; agent.failed += 1; team_task.state = result['status']
                self._say('BLOCKED', agent.id, None,
                          result.get('messages', [{}])[-1].get('content', result['status']),
                          team_task.id, slot.model_id, {'session_id': result['id']})
            slot.loaded = True
        except Exception as exc:
            team_task.state = 'FAILED'
            team_task.error = f'{type(exc).__name__}: {exc}'
            agent.state = 'FAILED'; agent.failed += 1; agent.last_active = time.time()
            self._say('BLOCKED', agent.id, None, team_task.error, team_task.id, slot.model_id, {})
        with self._lock:
            self.store.task(team_task)
        return team_task.as_dict()

    def run(self, task: str, **kwargs) -> dict:
        submitted = self.submit(task, **kwargs)
        return self.run_task(submitted['id'])

    def run_parallel_solutions(self, task: str, *, model_ids: list[str] | None = None,
                               max_workers: int = 4) -> dict:
        ids = model_ids or list(self.slots)
        if not ids:
            raise ValueError('no models in team')
        for model_id in ids:
            self._slot(model_id)
        submitted = [self.submit(task, model_id=mid) for mid in ids]
        results = []
        thread_safe = all(getattr(self._slot(mid).provider, 'thread_safe', False) for mid in ids)
        if thread_safe and len(submitted) > 1:
            with ThreadPoolExecutor(max_workers=min(max_workers, len(submitted))) as pool:
                results = list(pool.map(lambda x: self.run_task(x['id']), submitted))
        else:
            results = [self.run_task(x['id']) for x in submitted]
        winner = next((x for x in results if x['state'] == 'COMPLETED'), None)
        for result in results:
            self._say('REVIEW', result['agent_id'], None,
                      f"state={result['state']} changed={len((result.get('result') or {}).get('changed', []))}",
                      result['id'], result['model_id'], {'winner': bool(winner and result['id'] == winner['id'])})
        return {'task': task, 'results': results,
                'winner': winner['id'] if winner else None,
                'pass_count': sum(1 for x in results if x['state'] == 'COMPLETED'),
                'total': len(results),
                'policy': 'read-only parallel solutions; no automatic merge'}

    def _say(self, kind: str, from_agent: str, to_agent: str | None, content: str,
             task_id: str | None, model_id: str | None, refs: dict) -> dict:
        if kind not in TEAM_MESSAGE_KINDS:
            raise ValueError(f'invalid team message kind: {kind}')
        message = TeamMessage(id='msg-' + uuid.uuid4().hex[:16], kind=kind, from_agent=from_agent,
                              to_agent=to_agent, content=str(content)[:8000], task_id=task_id,
                              model_id=model_id, refs=refs)
        return self.store.message(message)

    def dialogue(self, task_id: str | None = None, limit: int = 200) -> dict:
        return {'messages': self.store.messages(task_id, limit), 'task_id': task_id,
                'kinds': sorted(TEAM_MESSAGE_KINDS)}

    def export_dialogue(self, path: Path | str, task_id: str | None = None) -> dict:
        target = Path(path)
        if target.exists():
            raise FileExistsError('dialogue export already exists')
        payload = self.dialogue(task_id, 2000)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding='utf-8')
        return {'path': str(target), 'messages': len(payload['messages'])}

    def status(self) -> dict:
        agents = [a for slot in self.slots.values() for a in slot.agents.values()]
        counts: dict[str, int] = {}
        for agent in agents:
            counts[agent.state] = counts.get(agent.state, 0) + 1
        return {'models': len(self.slots), 'max_models': self.max_models,
                'max_agents_per_model': self.max_agents_per_model,
                'registered_agents': len(agents), 'agent_states': counts,
                'model_loaded': sum(1 for slot in self.slots.values() if slot.loaded),
                'inference_calls': sum(a.inference_calls for a in agents),
                'queued_tasks': sum(1 for t in self.tasks.values() if t.state == 'QUEUED'),
                'executing_tasks': sum(1 for t in self.tasks.values() if t.state == 'EXECUTING'),
                'completed_tasks': sum(1 for t in self.tasks.values() if t.state == 'COMPLETED'),
                'failed_tasks': sum(1 for t in self.tasks.values() if t.state in ('FAILED', 'BLOCKED')),
                'note': 'registered agents are logical roles, not loaded model copies'}


def team_capacity(max_models: int = 15, agents_per_model: int = 100) -> dict:
    return {'max_models': max_models, 'agents_per_model': agents_per_model,
            'max_logical_agents': max_models * agents_per_model,
            'note': 'No model weights are duplicated per agent.'}
