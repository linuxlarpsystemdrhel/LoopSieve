"""Checkpoint time machine over the agent journal's immutable file snapshots."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .agent_runtime import Journal


class CheckpointTimeMachine:
    def __init__(self, journal: Journal):
        self.journal = journal

    def list(self, session_id: str) -> list[dict]:
        return self.journal.checkpoints(session_id)

    def restore(self, session_id: str, checkpoint_id: int) -> dict:
        return self.journal.restore_checkpoint(session_id, checkpoint_id)

    def latest(self, session_id: str, path: str | None = None) -> dict | None:
        rows = self.journal.checkpoints(session_id)
        for row in rows:
            if path is None or row['path'] == path:
                return row
        return None

    def rollback_latest(self, session_id: str, path: str) -> dict:
        row = self.latest(session_id, path)
        if row is None:
            raise KeyError(f'no checkpoint for {path} in {session_id}')
        return self.restore(session_id, row['id'])

    def summary(self, session_id: str) -> dict:
        rows = self.journal.checkpoints(session_id)
        return {'session_id': session_id, 'count': len(rows), 'checkpoints': rows}
