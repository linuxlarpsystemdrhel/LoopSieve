"""Dependency-aware orchestration with safe, write-set-scoped parallelism.

The orchestrator is deliberately conservative: a task with an unknown write set
runs sequentially. Parallel writes are allowed only when each work item declares
a disjoint write set. This makes concurrent edits reviewable instead of hoping
that a race condition never happens.
"""
from __future__ import annotations

import json
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .agent_runtime import AgentRuntime, TERMINAL
from .agents import select_agents


@dataclass
class WorkItem:
    id: str
    task: str
    agent_id: str | None = None
    depends_on: list[str] = field(default_factory=list)
    write_set: list[str] = field(default_factory=list)
    read_only: bool | None = None
    max_steps: int | None = None
    retries: int = 0
    priority: int = 0
    on_failure: str = 'block'
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError('work item needs a nonempty id')
        if not isinstance(self.task, str) or not self.task.strip():
            raise ValueError(f'work item {self.id} needs a task')
        if self.read_only is None:
            self.read_only = not self.write_set
        if not isinstance(self.depends_on, list) or not all(isinstance(x, str) for x in self.depends_on):
            raise ValueError(f'work item {self.id} has invalid dependencies')
        if not isinstance(self.write_set, list) or not all(isinstance(x, str) for x in self.write_set):
            raise ValueError(f'work item {self.id} has invalid write set')
        for path in self.write_set:
            p = Path(path)
            if p.is_absolute() or '..' in p.parts or not path.strip():
                raise ValueError(f'work item {self.id} has unsafe write path {path!r}')
        if self.retries < 0 or self.retries > 5:
            raise ValueError('retries must be 0..5')
        if self.max_steps is not None and not 1 <= self.max_steps <= 40:
            raise ValueError('max_steps must be 1..40')
        if self.on_failure not in ('block', 'retry', 'replan'):
            raise ValueError("on_failure must be block, retry or replan")

    def as_dict(self) -> dict:
        return {'id': self.id, 'task': self.task, 'agent_id': self.agent_id,
                'depends_on': list(self.depends_on), 'write_set': list(self.write_set),
                'read_only': self.read_only, 'max_steps': self.max_steps,
                'retries': self.retries, 'priority': self.priority,
                'on_failure': self.on_failure, 'metadata': dict(self.metadata)}


def validate_dag(items: list[WorkItem]):
    names = [x.id for x in items]
    if len(names) != len(set(names)):
        raise ValueError('duplicate task IDs')
    if not names or len(names) > 20:
        raise ValueError('1..20 tasks supported')
    graph = {x.id: x.depends_on for x in items}
    for x in items:
        if len(x.depends_on) != len(set(x.depends_on)):
            raise ValueError('duplicate dependency')
        if any(d not in graph or d == x.id for d in x.depends_on):
            raise ValueError('missing or self dependency')
    seen: set[str] = set()
    active: set[str] = set()

    def visit(node: str):
        if node in active:
            raise ValueError('task cycle')
        if node in seen:
            return
        active.add(node)
        for dep in graph[node]:
            visit(dep)
        active.remove(node)
        seen.add(node)

    for name in graph:
        visit(name)
    # Declared write-set conflicts are rejected before any task runs.
    for i, left in enumerate(items):
        for right in items[i + 1:]:
            overlap = set(left.write_set) & set(right.write_set)
            if overlap and not (left.read_only and right.read_only):
                raise ValueError(f'write-set conflict between {left.id} and {right.id}: {sorted(overlap)}')


def detect_write_conflicts(items: list[WorkItem]) -> list[dict]:
    conflicts = []
    for i, left in enumerate(items):
        for right in items[i + 1:]:
            overlap = sorted(set(left.write_set) & set(right.write_set))
            if overlap and not (left.read_only and right.read_only):
                conflicts.append({'left': left.id, 'right': right.id, 'paths': overlap})
    return conflicts


def _safe_parallel(items: list[WorkItem], allow_writes: bool) -> tuple[bool, str]:
    if len(items) < 2:
        return False, 'single task'
    if allow_writes and any(not item.write_set for item in items):
        return False, 'write set is unknown for at least one task'
    if detect_write_conflicts(items):
        return False, 'declared write sets overlap'
    return True, 'read-only or disjoint write sets'


class Orchestrator:
    def __init__(self, runtime: AgentRuntime, *, max_workers: int = 4,
                 event_sink: Callable[[dict], None] | None = None,
                 replan: Callable[[WorkItem, dict], list[WorkItem]] | None = None):
        self.runtime = runtime
        self.max_workers = max(1, min(int(max_workers), 12))
        self.event_sink = event_sink
        self.replan = replan

    def _emit(self, event: dict) -> None:
        if self.event_sink:
            try:
                self.event_sink(event)
            except Exception:
                pass

    def _run_one(self, item: WorkItem, *, allow_writes: bool, allow_checks: bool,
                 max_steps: int) -> dict:
        steps = item.max_steps or max_steps
        session = self.runtime.create(item.task, item.agent_id, steps,
                                      allow_writes=allow_writes and not item.read_only,
                                      allow_checks=allow_checks)
        result = self.runtime.run(session['id'])
        data = {'status': result['status'], 'session_id': session['id'],
                'agent_id': result['agent_id'], 'steps': result['step'],
                'evidence': result['evidence'], 'changed': result['changed'],
                'task': item.task, 'work_id': item.id}
        if result['status'] != 'COMPLETED':
            data['reason'] = result['messages'][-1].get('content') if result.get('messages') else ''
        return data

    def _retryable(self, item: WorkItem, data: dict) -> bool:
        if item.retries <= 0:
            return False
        if item.on_failure == 'retry':
            return True
        return data.get('status') in ('FAILED', 'BLOCKED') and item.on_failure == 'replan'

    def _run_sequential(self, items: list[WorkItem], *, allow_writes: bool,
                        allow_checks: bool, max_steps: int) -> dict:
        pending = {x.id: x for x in items}
        completed: dict[str, dict] = {}
        blocked: dict[str, dict] = {}
        failed: dict[str, dict] = {}
        retries: dict[str, int] = {}
        events: list[dict] = []
        started = time.monotonic()
        while pending:
            ready = [x for x in pending.values()
                     if all(d in completed or d in blocked or d in failed for d in x.depends_on)]
            if not ready:
                raise RuntimeError('DAG deadlock')
            ready.sort(key=lambda x: (-x.priority, x.id))
            for item in ready:
                del pending[item.id]
                if any(dep in blocked or dep in failed for dep in item.depends_on):
                    blocked[item.id] = {'status': 'BLOCKED', 'reason': 'prerequisite failed',
                                        'work_id': item.id, 'task': item.task}
                    self._emit({'work_id': item.id, 'status': 'BLOCKED', 'reason': 'prerequisite failed'})
                    continue
                attempt = 0
                while True:
                    data = self._run_one(item, allow_writes=allow_writes,
                                         allow_checks=allow_checks, max_steps=max_steps)
                    data['attempt'] = attempt + 1
                    events.append({'work_id': item.id, 'status': data['status'], 'attempt': attempt + 1,
                                   'agent_id': data.get('agent_id'), 'session_id': data.get('session_id')})
                    self._emit(events[-1])
                    if data['status'] == 'COMPLETED':
                        completed[item.id] = data
                        break
                    retries[item.id] = retries.get(item.id, 0) + 1
                    if attempt < item.retries and item.on_failure in ('retry', 'replan'):
                        attempt += 1
                        continue
                    if item.on_failure == 'replan' and self.replan:
                        try:
                            additions = self.replan(item, data)
                            if additions:
                                validate_dag(list(pending.values()) + additions)
                                for new_item in additions:
                                    pending[new_item.id] = new_item
                                blocked[item.id] = {**data, 'replanned': [x.id for x in additions]}
                                break
                        except Exception as exc:
                            data['replan_error'] = f'{type(exc).__name__}: {exc}'
                    failed[item.id] = data
                    break
        return {'status': 'COMPLETED' if not (blocked or failed) else 'PARTIAL' if completed else 'BLOCKED',
                'completed': completed, 'blocked': blocked, 'failed': failed,
                'retries': retries, 'events': events, 'parallel': False,
                'duration_seconds': round(time.monotonic() - started, 3)}

    def _run_parallel(self, items: list[WorkItem], *, allow_writes: bool,
                      allow_checks: bool, max_steps: int, max_workers: int) -> dict:
        pending = {x.id: x for x in items}
        completed: dict[str, dict] = {}
        blocked: dict[str, dict] = {}
        failed: dict[str, dict] = {}
        retries: dict[str, int] = {}
        events: list[dict] = []
        started = time.monotonic()
        running: dict[Future, WorkItem] = {}
        attempts: dict[str, int] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            while pending or running:
                for future, item in list(running.items()):
                    if not future.done():
                        continue
                    try:
                        data = future.result()
                    except Exception as exc:
                        data = {'status': 'FAILED', 'work_id': item.id, 'task': item.task,
                                'reason': f'{type(exc).__name__}: {exc}'}
                    running.pop(future, None)
                    events.append({'work_id': item.id, 'status': data.get('status'), 'attempt': attempts.get(item.id, 1),
                                   'agent_id': data.get('agent_id'), 'session_id': data.get('session_id')})
                    self._emit(events[-1])
                    if data.get('status') == 'COMPLETED':
                        completed[item.id] = data
                        continue
                    retries[item.id] = retries.get(item.id, 0) + 1
                    if attempts.get(item.id, 1) <= item.retries and item.on_failure in ('retry', 'replan'):
                        attempts[item.id] = attempts.get(item.id, 1) + 1
                        pending[item.id] = item
                        continue
                    failed[item.id] = data
                ready = []
                for item in pending.values():
                    deps = item.depends_on
                    if any(dep in blocked or dep in failed for dep in deps):
                        del pending[item.id]
                        blocked[item.id] = {'status': 'BLOCKED', 'reason': 'prerequisite failed',
                                            'work_id': item.id, 'task': item.task}
                        self._emit({'work_id': item.id, 'status': 'BLOCKED', 'reason': 'prerequisite failed'})
                        continue
                    if all(dep in completed for dep in deps):
                        ready.append(item)
                ready.sort(key=lambda x: (-x.priority, x.id))
                for item in ready:
                    if len(running) >= max_workers:
                        break
                    del pending[item.id]
                    attempts.setdefault(item.id, 1)
                    future = pool.submit(self._run_one, item, allow_writes=allow_writes,
                                         allow_checks=allow_checks, max_steps=max_steps)
                    running[future] = item
                if running and not ready:
                    done, _ = wait(list(running), timeout=0.2, return_when=FIRST_COMPLETED)
                elif running:
                    done, _ = wait(list(running), timeout=0.2, return_when=FIRST_COMPLETED)
                if not running and not pending:
                    break
                if not running and pending and not any(
                        all(d in completed for d in x.depends_on) for x in pending.values()):
                    for item in list(pending.values()):
                        blocked[item.id] = {'status': 'BLOCKED', 'reason': 'DAG deadlock or failed prerequisite',
                                            'work_id': item.id, 'task': item.task}
                    pending.clear()
        return {'status': 'COMPLETED' if not (blocked or failed) else 'PARTIAL' if completed else 'BLOCKED',
                'completed': completed, 'blocked': blocked, 'failed': failed,
                'retries': retries, 'events': events, 'parallel': True,
                'duration_seconds': round(time.monotonic() - started, 3)}

    def run(self, items: list[WorkItem], *, allow_writes: bool = False,
            allow_checks: bool = False, max_steps: int = 10,
            parallel: bool = True, max_workers: int | None = None) -> dict:
        validate_dag(items)
        workers = self.max_workers if max_workers is None else max(1, min(int(max_workers), 12))
        can_parallel, reason = _safe_parallel(items, allow_writes)
        thread_safe = bool(getattr(self.runtime.provider, 'thread_safe', False))
        if parallel and can_parallel and thread_safe and workers > 1:
            outcome = self._run_parallel(items, allow_writes=allow_writes,
                                         allow_checks=allow_checks, max_steps=max_steps,
                                         max_workers=workers)
        else:
            outcome = self._run_sequential(items, allow_writes=allow_writes,
                                           allow_checks=allow_checks, max_steps=max_steps)
            outcome['parallel_skipped'] = reason if not can_parallel else 'provider is not declared thread-safe'
        outcome['requested_parallel'] = bool(parallel)
        return outcome


def load_work_items(path: Path) -> list[WorkItem]:
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, list):
        raise ValueError('DAG must be a JSON array')
    result = []
    for value in data:
        if not isinstance(value, dict):
            raise ValueError('task must be an object')
        if 'id' not in value or 'task' not in value:
            raise ValueError('task needs id and task')
        result.append(WorkItem(
            id=str(value['id']), task=str(value['task']), agent_id=value.get('agent_id'),
            depends_on=list(value.get('depends_on', []) or []),
            write_set=list(value.get('write_set', []) or []),
            read_only=value.get('read_only'), max_steps=value.get('max_steps'),
            retries=int(value.get('retries', 0) or 0), priority=int(value.get('priority', 0) or 0),
            on_failure=str(value.get('on_failure', 'block')), metadata=value.get('metadata', {}) or {}))
    validate_dag(result)
    return result
