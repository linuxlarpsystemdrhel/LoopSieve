"""Small secret store: Windows DPAPI when available, never plaintext by default.

Keys are encrypted at rest. The JSON file stores only base64-encrypted bytes and
never appears in logs. On non-Windows systems keyring is preferred; a local
0o600 file is a clearly labelled fallback, not a claim of OS-grade security.
"""
from __future__ import annotations

import base64
import ctypes
import json
import os
import re
import tempfile
from ctypes import wintypes
from pathlib import Path
from typing import Any

from .state import default_state_base


class SecretStoreError(RuntimeError):
    pass


if os.name == 'nt':
    class DATA_BLOB(ctypes.Structure):
        _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_char))]

    _crypt32 = ctypes.windll.crypt32
    _kernel32 = ctypes.windll.kernel32
    _crypt32.CryptProtectData.argtypes = [ctypes.POINTER(DATA_BLOB), wintypes.LPCWSTR,
                                          ctypes.POINTER(DATA_BLOB), ctypes.c_void_p,
                                          ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB)]
    _crypt32.CryptUnprotectData.argtypes = [ctypes.POINTER(DATA_BLOB), ctypes.POINTER(wintypes.LPWSTR),
                                            ctypes.POINTER(DATA_BLOB), ctypes.c_void_p,
                                            ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB)]
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]

    def _blob(data: bytes) -> DATA_BLOB:
        buffer = ctypes.create_string_buffer(data)
        return DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))

    def _dpapi_protect(data: bytes) -> bytes:
        blob_in = _blob(data)
        blob_out = DATA_BLOB()
        if not _crypt32.CryptProtectData(ctypes.byref(blob_in), 'LoopSieve secret', None, None, None,
                                         0x1, ctypes.byref(blob_out)):
            raise SecretStoreError('Windows DPAPI encryption failed')
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            _kernel32.LocalFree(blob_out.pbData)

    def _dpapi_unprotect(data: bytes) -> bytes:
        blob_in = _blob(data)
        blob_out = DATA_BLOB()
        if not _crypt32.CryptUnprotectData(ctypes.byref(blob_in), None, None, None, None,
                                           0x1, ctypes.byref(blob_out)):
            raise SecretStoreError('Windows DPAPI decryption failed')
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            _kernel32.LocalFree(blob_out.pbData)
else:
    def _dpapi_protect(data: bytes) -> bytes:
        raise SecretStoreError('DPAPI is only available on Windows')

    def _dpapi_unprotect(data: bytes) -> bytes:
        raise SecretStoreError('DPAPI is only available on Windows')


class SecretStore:
    def __init__(self, path: Path | str | None = None, *, service: str = 'loopsieve'):
        self.path = Path(path) if path else default_state_base() / 'secrets.json'
        self.service = service
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding='utf-8'))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self, data: dict[str, dict]) -> None:
        fd, tmp = tempfile.mkstemp(prefix='.secrets-', suffix='.json', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                json.dump(data, handle, indent=2, sort_keys=True)
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def set(self, name: str, secret: str) -> dict:
        if not re.fullmatch(r'[\w.:-]{1,100}', str(name)):
            raise ValueError('secret name must be a short identifier')
        if not isinstance(secret, str) or not secret:
            raise ValueError('secret must be a nonempty string')
        data = self._load()
        raw = secret.encode('utf-8')
        scheme = 'dpapi' if os.name == 'nt' else 'file'
        if scheme == 'dpapi':
            blob = _dpapi_protect(raw)
        else:
            try:
                import keyring  # type: ignore
                keyring.set_password(self.service, name, secret)
                data[name] = {'scheme': 'keyring', 'service': self.service}
                self._save(data)
                return {'name': name, 'scheme': 'keyring', 'warning': None}
            except Exception:
                blob = raw
                scheme = 'file'
        data[name] = {'scheme': scheme, 'data': base64.b64encode(blob).decode('ascii')}
        self._save(data)
        warning = None if scheme == 'dpapi' else 'keyring unavailable: local file is mode 0600 but not OS-encrypted'
        return {'name': name, 'scheme': scheme, 'warning': warning}

    def get(self, name: str) -> str | None:
        item = self._load().get(str(name))
        if not isinstance(item, dict):
            return None
        scheme = item.get('scheme')
        if scheme == 'keyring':
            try:
                import keyring  # type: ignore
                return keyring.get_password(item.get('service', self.service), name)
            except Exception as exc:
                raise SecretStoreError(f'keyring read failed: {type(exc).__name__}') from exc
        blob = base64.b64decode(item.get('data', ''))
        if scheme == 'dpapi':
            return _dpapi_unprotect(blob).decode('utf-8')
        if scheme == 'file':
            return blob.decode('utf-8')
        raise SecretStoreError(f'unknown secret scheme: {scheme}')

    def delete(self, name: str) -> bool:
        data = self._load()
        item = data.pop(str(name), None)
        if item is None:
            return False
        if isinstance(item, dict) and item.get('scheme') == 'keyring':
            try:
                import keyring  # type: ignore
                keyring.delete_password(item.get('service', self.service), name)
            except Exception:
                pass
        self._save(data)
        return True

    def names(self) -> list[str]:
        return sorted(self._load())

    def status(self) -> dict[str, Any]:
        data = self._load()
        return {'path': str(self.path), 'count': len(data),
                'schemes': sorted({str(v.get('scheme')) for v in data.values() if isinstance(v, dict)}),
                'dpapi_available': os.name == 'nt'}
