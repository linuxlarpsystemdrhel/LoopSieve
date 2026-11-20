"""Cross-agent conflict detection and deterministic resolution policies."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Conflict:
    left: str
    right: str
    paths: list[str]
    policy: str = 'block'

    def as_dict(self) -> dict:
        return {'left': self.left, 'right': self.right, 'paths': self.paths, 'policy': self.policy}


class CrossAgentConflictResolver:
    """Detect overlapping edits and choose a safe, reviewable outcome."""
    POLICIES = {'block', 'first', 'last', 'manual'}

    def detect(self, changed_by_agent: dict[str, list[str]]) -> list[Conflict]:
        conflicts: list[Conflict] = []
        names = sorted(changed_by_agent)
        for i, left in enumerate(names):
            left_paths = set(changed_by_agent.get(left, []))
            for right in names[i + 1:]:
                overlap = sorted(left_paths & set(changed_by_agent.get(right, [])))
                if overlap:
                    conflicts.append(Conflict(left, right, overlap))
        return conflicts

    def resolve(self, conflicts: list[Conflict], policy: str = 'block') -> dict:
        if policy not in self.POLICIES:
            raise ValueError(f'unknown conflict policy: {policy}')
        if not conflicts:
            return {'status': 'CLEAR', 'policy': policy, 'conflicts': [], 'winner': None}
        if policy == 'block':
            return {'status': 'BLOCKED', 'policy': policy, 'conflicts': [c.as_dict() for c in conflicts],
                    'winner': None, 'action': 'ask_human'}
        if policy == 'manual':
            return {'status': 'MANUAL_REVIEW', 'policy': policy, 'conflicts': [c.as_dict() for c in conflicts],
                    'winner': None, 'action': 'open_both_versions'}
        winner = conflicts[0].left if policy == 'first' else conflicts[0].right
        return {'status': 'RESOLVED', 'policy': policy, 'conflicts': [c.as_dict() for c in conflicts],
                'winner': winner, 'action': f'keep_{winner}_and_reverify'}
