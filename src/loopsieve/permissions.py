"""Deny-by-default executable permission policy.

Permissions are checked at the runtime boundary, not only in the prompt.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


class PermissionLevel(IntEnum):
    READ_ONLY = 10
    WORKSPACE_WRITE = 20
    TEST_EXECUTION = 30
    LOCAL_PROCESS = 40
    PACKAGE_INSTALL = 50
    NETWORK_ACCESS = 60
    COMPUTER_CONTROL = 70
    SENSITIVE_OPERATION = 80


LEVEL_NAMES = {v.name: v for v in PermissionLevel}


class PermissionDenied(PermissionError):
    pass


@dataclass
class Grant:
    level: PermissionLevel
    reason: str = ''
    expires_at: float | None = None
    created_at: float = field(default_factory=time.time)

    def active(self) -> bool:
        return self.expires_at is None or self.expires_at > time.time()

    def as_dict(self) -> dict:
        return {'level': self.level.name, 'reason': self.reason,
                'expires_at': self.expires_at, 'created_at': self.created_at}


ACTION_REQUIREMENTS = {
    'inspect': PermissionLevel.READ_ONLY,
    'tree': PermissionLevel.READ_ONLY,
    'search': PermissionLevel.READ_ONLY,
    'diff': PermissionLevel.READ_ONLY,
    'finish': PermissionLevel.READ_ONLY,
    'blocked': PermissionLevel.READ_ONLY,
    'tool': PermissionLevel.READ_ONLY,
    'patch': PermissionLevel.WORKSPACE_WRITE,
    'restore': PermissionLevel.WORKSPACE_WRITE,
    'verify': PermissionLevel.TEST_EXECUTION,
    'process': PermissionLevel.LOCAL_PROCESS,
    'install': PermissionLevel.PACKAGE_INSTALL,
    'network': PermissionLevel.NETWORK_ACCESS,
    'computer': PermissionLevel.COMPUTER_CONTROL,
    'sensitive': PermissionLevel.SENSITIVE_OPERATION,
}


class PermissionEngine:
    """Session-scoped grants with explicit policy and audit records."""
    def __init__(self, policy: dict[str, str] | None = None):
        self._lock = threading.RLock()
        self._grants: dict[str, list[Grant]] = {}
        self._audit: list[dict] = []
        self.policy = policy or {
            'default': 'deny',
            'read_only': 'allow',
            'workspace_write': 'explicit',
            'test_execution': 'explicit',
            'local_process': 'deny',
            'package_install': 'deny',
            'network_access': 'deny',
            'computer_control': 'deny',
            'sensitive_operation': 'deny',
        }

    def grant(self, session_id: str, level: str | PermissionLevel, *, reason: str = '',
              ttl_seconds: int | None = None) -> Grant:
        level = LEVEL_NAMES[level] if isinstance(level, str) else level
        if not isinstance(level, PermissionLevel):
            raise ValueError('invalid permission level')
        expires_at = time.time() + ttl_seconds if ttl_seconds else None
        grant = Grant(level, reason, expires_at)
        with self._lock:
            self._grants.setdefault(session_id, []).append(grant)
            self._record(session_id, 'grant', level.name, reason)
        return grant

    def revoke(self, session_id: str, level: str | PermissionLevel) -> bool:
        level = LEVEL_NAMES[level] if isinstance(level, str) else level
        with self._lock:
            before = self._grants.get(session_id, [])
            after = [g for g in before if g.level != level]
            self._grants[session_id] = after
            self._record(session_id, 'revoke', level.name, '')
            return len(after) != len(before)

    def levels(self, session_id: str) -> set[PermissionLevel]:
        with self._lock:
            active = [g.level for g in self._grants.get(session_id, []) if g.active()]
        return set(active)

    def has(self, session_id: str, level: str | PermissionLevel) -> bool:
        level = LEVEL_NAMES[level] if isinstance(level, str) else level
        return level in self.levels(session_id)

    def require(self, session_id: str, level: str | PermissionLevel, *,
                action: str = '', details: str = '') -> None:
        level = LEVEL_NAMES[level] if isinstance(level, str) else level
        if not self.has(session_id, level):
            with self._lock:
                self._record(session_id, 'deny', level.name, details or action)
            raise PermissionDenied(f'{level.name} is not granted for action {action or "unknown"}')

    def required_for_action(self, action: str, tool: str | None = None) -> PermissionLevel:
        # All registered local tools are read-only by contract. A future process
        # or network tool must declare a stronger action name explicitly.
        return ACTION_REQUIREMENTS.get(str(action), PermissionLevel.SENSITIVE_OPERATION)

    def bind_agent(self, session_id: str, agent: dict, *, allow_writes: bool = False,
                   allow_checks: bool = False) -> dict:
        self.grant(session_id, PermissionLevel.READ_ONLY, reason=f"role {agent.get('id', 'unknown')}")
        if allow_writes:
            self.grant(session_id, PermissionLevel.WORKSPACE_WRITE,
                       reason='explicit --allow-writes')
        if allow_checks:
            self.grant(session_id, PermissionLevel.TEST_EXECUTION,
                       reason='explicit --allow-checks')
        return {'session_id': session_id, 'levels': [x.name for x in sorted(self.levels(session_id))]}

    def audit(self, session_id: str | None = None) -> list[dict]:
        with self._lock:
            rows = self._audit if session_id is None else [x for x in self._audit if x['session_id'] == session_id]
            return [dict(row) for row in rows]

    def _record(self, session_id: str, event: str, level: str, details: str) -> None:
        self._audit.append({'session_id': session_id, 'event': event, 'level': level,
                            'details': str(details)[:300], 'created_at': time.time()})
        self._audit = self._audit[-2000:]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {'policy': dict(self.policy), 'sessions': len(self._grants),
                    'audit_events': len(self._audit),
                    'levels': [x.name for x in PermissionLevel]}
