"""Proof-carrying developer workflows, stored locally, with no model dependency.

Evidence is append-only through SQLite and hash chained. This is tamper-evident
against accidental changes, not tamper-proof against an attacker with filesystem access.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import sqlite3
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

_SECRET = re.compile(r'(?i)(\b(?:api[_-]?key|password|authorization|secret|token)\b\s*[:=]\s*)([^\s,}\]]+)')
_PRIVATE = re.compile(r'(?i)(-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----|sk-[A-Za-z0-9_-]{15,})')


def sanitize(value: object, limit: int = 8000) -> str:
    """Bound and redact values before persistence or export."""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)
    return _PRIVATE.sub('[REDACTED]', _SECRET.sub(r'\1[REDACTED]', re.sub(r'(?i)(authorization\s*[:=]\s*bearer\s+)\S+',r'\1[REDACTED]', value[:limit])))


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class EvidenceLedger:
    """SQLite WAL-backed chain, serialized by BEGIN IMMEDIATE on append."""
    def __init__(self, db: Path):
        self.db = Path(db)
        self.db.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS evidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT, created INTEGER NOT NULL,
                source TEXT NOT NULL, event TEXT NOT NULL, payload TEXT NOT NULL,
                previous_hash TEXT NOT NULL, hash TEXT NOT NULL)''')

    @contextlib.contextmanager
    def connect(self):
        """Yield a connection and always close it (required on Windows)."""
        conn = sqlite3.connect(self.db, timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _hash(created: int, source: str, event: str, payload: str, prev: str) -> str:
        return digest(json.dumps([created, source, event, payload, prev], separators=(',', ':'), ensure_ascii=False).encode())

    def append(self, source: str, event: str, payload: object) -> dict:
        if not re.fullmatch(r'[\w.:-]{1,120}', source) or not re.fullmatch(r'[\w.:-]{1,80}', event):
            raise ValueError('invalid evidence source/event')
        content = sanitize(payload)
        with self.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            last = conn.execute('SELECT hash FROM evidence ORDER BY id DESC LIMIT 1').fetchone()
            prev = last['hash'] if last else '0'*64
            created = time.time_ns()
            checksum = self._hash(created, source, event, content, prev)
            cursor = conn.execute('INSERT INTO evidence(created,source,event,payload,previous_hash,hash) VALUES(?,?,?,?,?,?)',
                                  (created, source, event, content, prev, checksum))
            conn.commit()
            return {'id': cursor.lastrowid, 'hash': checksum, 'source': source, 'event': event}

    def audit(self) -> dict:
        with self.connect() as conn:
            rows = conn.execute('SELECT * FROM evidence ORDER BY id').fetchall()
        prev = '0'*64
        for row in rows:
            expected = self._hash(row['created'], row['source'], row['event'], row['payload'], prev)
            if expected != row['hash'] or row['previous_hash'] != prev:
                return {'status': 'FAIL', 'entries_checked': row['id']-1, 'broken_id': row['id']}
            prev = row['hash']
        return {'status': 'PASS', 'entries_checked': len(rows), 'head': prev}

    def recent(self, limit: int = 20) -> list[dict]:
        if not 1 <= limit <= 500: raise ValueError('limit must be 1..500')
        with self.connect() as conn:
            rows = conn.execute('SELECT id,created,source,event,payload,hash FROM evidence ORDER BY id DESC LIMIT ?', (limit,)).fetchall()
        return [dict(row) for row in rows]


class ArtifactStore:
    """Deduplicated immutable content-addressed storage. No path supplied by a model."""
    def __init__(self, path: Path, max_bytes: int = 2_000_000):
        self.root = Path(path)
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max_bytes

    def put(self, blob: bytes) -> dict:
        if not isinstance(blob, bytes) or len(blob) > self.max_bytes:
            raise ValueError('artifact must be bytes within allowed size')
        checksum = digest(blob)
        target = self.root / checksum[:2] / checksum
        target.parent.mkdir(exist_ok=True)
        if target.exists():
            if target.is_symlink() or target.stat().st_size > self.max_bytes or digest(target.read_bytes()) != checksum:
                raise ValueError('existing artifact corrupted or unsafe')
        else:
            fd, tmp = tempfile.mkstemp(dir=target.parent, prefix='.stage-')
            try:
                with os.fdopen(fd, 'wb') as handle:
                    handle.write(blob)
                os.replace(tmp, target)
            finally:
                if os.path.exists(tmp): os.unlink(tmp)
        return {'sha256': checksum, 'size': len(blob), 'ref': 'sha256:'+checksum}

    def get(self, ref: str) -> bytes:
        if not isinstance(ref, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', ref):
            raise ValueError('invalid artifact reference')
        checksum = ref.partition(':')[2]
        p = self.root / checksum[:2] / checksum
        if p.is_symlink() or not p.is_file() or p.stat().st_size > self.max_bytes:
            raise ValueError('artifact missing or unsafe')
        blob = p.read_bytes()
        if digest(blob) != checksum:
            raise ValueError('artifact integrity check failed')
        return blob


@dataclass(frozen=True)
class GateResult:
    status: str
    reasons: tuple[str, ...]
    evidence_ids: tuple[str, ...]

    def as_dict(self):
        return {'status': self.status, 'reasons': list(self.reasons), 'evidence_ids': list(self.evidence_ids)}


def acceptance_gate(required: list[str], results: dict[str, dict]) -> GateResult:
    """Reject unknown, failed, cached-but-unverified, and simulated tests."""
    reasons, confirmed = [], []
    for name in required:
        if name not in results:
            reasons.append(f'{name}: required check not executed')
            continue
        result = results[name]
        if result.get('status') not in ('PASS', 'SKIPPED_VALID_CACHE'):
            reasons.append(f'{name}: {result.get("status", "UNKNOWN")} is not proof of success')
        elif result.get('authenticity') not in ('real', 'validated-cache'):
            reasons.append(f'{name}: mock/synthetic/unknown evidence is insufficient')
        elif not result.get('evidence_id'):
            reasons.append(f'{name}: missing evidence identifier')
        else:
            confirmed.append(str(result['evidence_id']))
    return GateResult('BLOCKED' if reasons else 'PASS', tuple(reasons), tuple(confirmed))


def portable_capsule(session: dict, events: list[dict], destination: Path, *, metadata: dict | None = None) -> dict:
    """Export operational metadata only, never prompts, arbitrary project files or credentials."""
    destination = Path(destination)
    if destination.suffix != '.zip': raise ValueError('capsule needs .zip output')
    if destination.exists(): raise FileExistsError('capsule destination already exists')
    summary = {
        'schema_version': 1,
        'session_id': session['id'],
        'agent_id': session['agent_id'],
        'status': session['status'],
        'step': session['step'],
        'max_steps': session['max_steps'],
        'changed': [x for x in session.get('changed', []) if isinstance(x,str) and not x.startswith('/')],
        'evidence': [{'status': x.get('status'), 'files': x.get('files', [])} for x in session.get('evidence',[])],
        'events': [{'kind': str(e['kind']), 'created': e['created']} for e in events],
        'metadata': metadata or {},
    }
    payload = json.dumps(summary, sort_keys=True, ensure_ascii=False, indent=2).encode()
    with zipfile.ZipFile(destination, 'x', compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('capsule.json', payload)
        z.writestr('SHA256SUMS', f'{digest(payload)}  capsule.json\n')
    return {'path': str(destination), 'sha256': digest(destination.read_bytes()), 'entries': len(events)}
