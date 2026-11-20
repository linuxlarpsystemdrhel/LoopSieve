"""Verified task handoff: a task may be passed on only with passing evidence."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from .agent_runtime import Journal
from .toolkit import safe_path


class VerifiedTaskHandoff:
    def __init__(self, journal: Journal):
        self.journal = journal

    def verify(self, session_id: str) -> dict:
        session = self.journal.get(session_id)
        problems = []
        if session['status'] != 'COMPLETED':
            problems.append(f"session status is {session['status']}, not COMPLETED")
        evidence = [e for e in session.get('evidence', []) if e.get('status') == 'PASS']
        if session.get('changed') and not evidence:
            problems.append('changed files have no passing verification evidence')
        files = []
        for name in session.get('changed', []):
            try:
                path = safe_path(self.journal.root, name)
                if not path.is_file():
                    problems.append(f'{name} no longer exists')
                    continue
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                files.append({'path': name, 'sha256': digest, 'size': path.stat().st_size})
            except (OSError, PermissionError, ValueError) as exc:
                problems.append(f'{name}: {type(exc).__name__}: {exc}')
        return {'session_id': session_id, 'agent_id': session['agent_id'],
                'status': 'VERIFIED' if not problems else 'REJECTED',
                'problems': problems, 'evidence': evidence, 'files': files,
                'task': session['task']}

    def handoff(self, session_id: str, target: Path | str) -> dict:
        report = self.verify(session_id)
        if report['status'] != 'VERIFIED':
            raise ValueError('handoff rejected: ' + '; '.join(report['problems']))
        target = Path(target)
        if target.exists():
            raise FileExistsError('handoff target already exists')
        payload = {'schema_version': 1, 'created_at': time.time(), **report}
        raw = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False).encode()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        return {'status': 'HANDED_OFF', 'path': str(target),
                'sha256': hashlib.sha256(raw).hexdigest(), 'report': report}

    def accept(self, path: Path | str) -> dict:
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(p)
        raw = p.read_bytes()
        try:
            payload = json.loads(raw)
        except ValueError as exc:
            raise ValueError('invalid handoff JSON') from exc
        if payload.get('status') != 'VERIFIED':
            raise ValueError('handoff was not verified')
        for item in payload.get('files', []):
            try:
                target = safe_path(self.journal.root, item['path'])
                if hashlib.sha256(target.read_bytes()).hexdigest() != item['sha256']:
                    raise ValueError(f"handoff file hash changed: {item['path']}")
            except (OSError, PermissionError, KeyError) as exc:
                raise ValueError(f"handoff file unavailable: {item.get('path')}: {exc}") from exc
        return {'status': 'ACCEPTED', 'sha256': hashlib.sha256(raw).hexdigest(),
                'session_id': payload.get('session_id'), 'agent_id': payload.get('agent_id')}
