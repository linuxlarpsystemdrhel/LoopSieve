"""Source-aware, expiring local project facts. No hidden model memory."""
from __future__ import annotations

import contextlib
import hashlib
import json
import sqlite3
import time
from pathlib import Path

from .provenance import sanitize
from .toolkit import safe_path


class ProjectMemory:
    def __init__(self, root: Path, db: Path):
        self.root = Path(root).resolve()
        self.path = Path(db)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS facts (
                key TEXT NOT NULL, value TEXT NOT NULL, source TEXT NOT NULL,
                source_sha256 TEXT NOT NULL, created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL, status TEXT NOT NULL,
                PRIMARY KEY(key,source))''')

    @contextlib.contextmanager
    def _connect(self):
        con=sqlite3.connect(self.path,timeout=10)
        con.row_factory=sqlite3.Row
        try:
            yield con
            con.commit()
        except BaseException:
            con.rollback()
            raise
        finally:
            con.close()

    def _source_digest(self, source: str) -> str:
        p = safe_path(self.root, source)
        if not p.is_file() or p.stat().st_size > 2_000_000:
            raise ValueError('missing or oversized source')
        return hashlib.sha256(p.read_bytes()).hexdigest()

    def remember(self, key: str, value: str, source: str, lifetime_seconds: int=86400) -> dict:
        if not (key.isascii() and key.replace('-', '_').replace('.', '_').replace('_','').isalnum()) or not 1 <= len(key) <= 100:
            raise ValueError('key must be a short ASCII identifier')
        if not isinstance(value, str) or not 1 <= len(value) <= 1600:
            raise ValueError('value is too long or missing')
        if not 1 <= lifetime_seconds <= 365*86400: raise ValueError('invalid TTL')
        source_hash=self._source_digest(source)
        now=int(time.time())
        with self._connect() as conn:
            conn.execute('INSERT OR REPLACE INTO facts VALUES(?,?,?,?,?,?,?)',
                         (key,sanitize(value,1600),source,source_hash,now,now+lifetime_seconds,'ASSERTED'))
        return {'key':key,'source':source,'status':'ASSERTED','sha256':source_hash}

    def query(self, key: str|None=None) -> dict:
        with self._connect() as conn:
            if key is None: rows=conn.execute('SELECT * FROM facts ORDER BY key,source').fetchall()
            else: rows=conn.execute('SELECT * FROM facts WHERE key=? ORDER BY source',(key,)).fetchall()
        now=int(time.time());group={}
        for row in rows:
            data=dict(row)
            if data['expires_at']<=now: status='EXPIRED'
            else:
                try: status='CURRENT' if self._source_digest(data['source'])==data['source_sha256'] else 'STALE'
                except (ValueError,PermissionError,OSError):status='UNVERIFIABLE'
            data['status']=status
            group.setdefault(data['key'],[]).append(data)
        return {name:{'facts':facts, 'conflict': len({x['value'] for x in facts if x['status']=='CURRENT'})>1}
                for name,facts in group.items()}
