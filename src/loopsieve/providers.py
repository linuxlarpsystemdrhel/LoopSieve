"""Opt-in model adapters. No API keys are stored by LoopSieve.

All providers are *planners*: they return one bounded JSON decision. LoopSieve
itself validates and executes decisions. There are no provider-side file tools.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener, urlopen

class ProviderError(RuntimeError):
    """A provider failure with a stable classification used by health/fallback logic."""
    def __init__(self, message: str, kind: str = 'PROVIDER_ERROR', retryable: bool = True):
        super().__init__(message)
        self.kind = kind
        self.retryable = retryable


def _decode_action(text: str) -> dict:
    value = text.strip()
    if value.startswith('```'):
        lines = value.splitlines()
        value = '\n'.join(lines[1:-1]) if len(lines) >= 3 else value
    try:
        action = json.loads(value)
    except (ValueError, TypeError) as exc:
        raise ProviderError('provider did not return exactly one JSON action') from exc
    if not isinstance(action, dict) or not isinstance(action.get('action'), str):
        raise ProviderError('provider action must be a JSON object with action')
    return action


def instruction(messages: list[dict], agent: dict, max_chars: int=18000) -> str:
    # Avoid injecting the full 100-role catalog into any single prompt.
    records = json.dumps(messages[-7:], ensure_ascii=False)
    if len(records)>max_chars: records=records[-max_chars:]
    return (f'You are {agent["name"]}: {agent["instructions"]}\n'
            'You control a local tool runner. Respond with ONE JSON OBJECT only.\n'
            'Actions: {"action":"inspect","path":"relative/path"}; '
            '{"action":"tree"}; '
            '{"action":"patch","path":"relative/path","find":"exact old text","replace":"new text"}; '
            '{"action":"verify","files":["relative/path"]}; '
            '{"action":"finish","summary":"..."}; '
            '{"action":"blocked","reason":"..."}.\n'
            'Do not assume patches or checks succeeded. Read tool responses before finishing. '
            'Never claim a PASS unless tool evidence confirms it. '
            'Do not request network, shell commands, or secrets. '
            'Use exact-match minimal patches; do not propose huge rewrites.\n'
            'Recent conversation JSON follows:\n' + records)


class _LocalRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # A loopback adapter keeps both metadata requests and prompts local.
        raise HTTPError(req.full_url, code, "Ollama redirects are unsupported", headers, fp)


def _open_ollama(request: Request, timeout: int):
    opener = build_opener(ProxyHandler({}), _LocalRedirectHandler())
    try:
        return opener.open(request, timeout=timeout)
    except HTTPError as exc:
        exc.close()
        raise


@dataclass
class OllamaProvider:
    thread_safe = True
    model: str
    endpoint: str = 'http://127.0.0.1:11434/api/chat'
    timeout: int = 90

    def __post_init__(self):
        parsed = urlparse(self.endpoint)
        if parsed.scheme not in ('http', 'https') or parsed.hostname not in ('localhost','127.0.0.1','::1'):
            raise ValueError('Ollama endpoint must be loopback; use an explicit compatible provider for remote APIs')

    @property
    def provider_id(self) -> str:
        return f'ollama:{self.model}'

    def probe(self) -> dict:
        """Check the local server and whether the configured model is installed."""
        base = self.endpoint.rsplit('/api/', 1)[0]
        request = Request(base + '/api/tags', headers={'Accept':'application/json'})
        try:
            with _open_ollama(request, timeout=min(self.timeout, 10)) as result:
                if result.status != 200:
                    return {'state':'SERVER_UNAVAILABLE','kind':'HTTP','reason':f'HTTP {result.status}','provider':self.provider_id}
                data = json.loads(result.read(1024*1024))
            models = [x.get('name','') for x in data.get('models',[]) if isinstance(x,dict)]
            installed = self.model in models or any(x.split(':')[0] == self.model for x in models)
            return {'state':'READY' if installed else 'REQUIRES_DOWNLOAD','kind':'MODEL' if not installed else 'OK',
                    'provider':self.provider_id,'model':self.model,'installed_models':models[:40]}
        except (OSError, ValueError) as exc:
            return {'state':'SERVER_UNAVAILABLE','kind':'CONNECTION','reason':f'{type(exc).__name__}: {exc}','provider':self.provider_id}

    def complete(self, messages: list[dict], agent: dict) -> dict:
        payload = {'model':self.model, 'stream':False, 'format':'json',
                   'messages':[{'role':'user','content':instruction(messages,agent)}]}
        request = Request(self.endpoint, data=json.dumps(payload).encode(),
                          headers={'Content-Type':'application/json'}, method='POST')
        try:
            with _open_ollama(request, timeout=self.timeout) as result:
                if result.status != 200: raise ProviderError(f'Ollama HTTP {result.status}', kind='HTTP')
                blob = result.read(1024*1024)
            response = json.loads(blob)
            return _decode_action(response['message']['content'])
        except ProviderError:
            raise
        except (OSError, ValueError, KeyError) as exc:
            kind = 'TIMEOUT' if 'timed out' in str(exc).lower() else 'CONNECTION'
            raise ProviderError(f'Ollama request failed: {type(exc).__name__}: {exc}', kind=kind) from exc


@dataclass
class CompatibleProvider:
    """OpenAI-compatible chat completion; explicit HTTPS endpoint, opt-in API key env."""
    thread_safe = True
    model: str
    endpoint: str
    api_key_env: str='LOOPSIEVE_API_KEY'
    timeout: int=90
    api_key: str | None = None

    def __post_init__(self):
        parsed=urlparse(self.endpoint)
        if parsed.scheme != 'https' and not (parsed.scheme=='http' and parsed.hostname in ('localhost','127.0.0.1','::1')):
            raise ValueError('remote provider must use HTTPS')
        if parsed.username or parsed.password or parsed.fragment:
            raise ValueError('endpoint may not include URL credentials or fragments')

    @property
    def provider_id(self) -> str:
        return f'compatible:{self.model}'

    def _request(self, url: str, data: bytes | None = None) -> Request:
        key=self.api_key or os.environ.get(self.api_key_env,'')
        if not key and urlparse(self.endpoint).hostname not in ('localhost','127.0.0.1','::1'):
            raise ProviderError(f'missing API key environment variable {self.api_key_env}',kind='AUTH',retryable=False)
        request = Request(url, data=data, headers={'Content-Type':'application/json'})
        if key:
            request.add_unredirected_header('Authorization', 'Bearer ' + key)
        return request

    def probe(self) -> dict:
        parsed=urlparse(self.endpoint)
        base=f'{parsed.scheme}://{parsed.netloc}'
        try:
            with urlopen(self._request(base+'/models'),timeout=min(self.timeout,10)) as r:
                if r.status!=200:return {'state':'MISCONFIGURED','kind':'HTTP','reason':f'HTTP {r.status}','provider':self.provider_id}
                data=json.loads(r.read(1024*1024))
            models=[x.get('id','') for x in data.get('data',[]) if isinstance(x,dict)]
            return {'state':'READY','kind':'OK','provider':self.provider_id,'model':self.model,'installed_models':models[:40]}
        except ProviderError as exc:
            return {'state':'AUTH_REQUIRED' if exc.kind=='AUTH' else 'MISCONFIGURED','kind':exc.kind,'reason':str(exc),'provider':self.provider_id}
        except (OSError,ValueError) as exc:
            return {'state':'SERVER_UNAVAILABLE','kind':'CONNECTION','reason':f'{type(exc).__name__}: {exc}','provider':self.provider_id}

    def complete(self, messages:list[dict], agent:dict) -> dict:
        payload={'model':self.model,'messages':[{'role':'user','content':instruction(messages,agent)}],
                 'temperature':0,'response_format':{'type':'json_object'}}
        try:
            with urlopen(self._request(self.endpoint, json.dumps(payload).encode()), timeout=self.timeout) as r:
                if r.status!=200:raise ProviderError(f'compatible provider HTTP {r.status}',kind='HTTP')
                resp=json.loads(r.read(1024*1024))
            return _decode_action(resp['choices'][0]['message']['content'])
        except ProviderError:raise
        except (OSError,KeyError,ValueError,IndexError) as exc:
            kind='TIMEOUT' if 'timed out' in str(exc).lower() else 'PROVIDER_ERROR'
            raise ProviderError(f'compatible provider request failed: {type(exc).__name__}',kind=kind) from exc


@dataclass
class CLIProvider:
    """Optional bridge: official CLI performs reasoning only, NEVER tools or edits."""
    thread_safe = True
    executable: str
    timeout: int=120

    @property
    def provider_id(self) -> str:
        return f'cli:{self.executable}'

    def probe(self) -> dict:
        if self.executable not in ('claude','codex'):
            return {'state':'MISCONFIGURED','kind':'EXECUTABLE','reason':'only claude/codex are supported','provider':self.provider_id}
        found=shutil.which(self.executable)
        return {'state':'READY' if found else 'REQUIRES_DEPENDENCY','kind':'OK' if found else 'MISSING_EXECUTABLE',
                'provider':self.provider_id,'executable':found or self.executable}

    def complete(self,messages:list[dict],agent:dict)->dict:
        if self.executable not in ('claude','codex'):
            raise ProviderError('only supported official CLI executables are allowed',kind='MISCONFIGURED',retryable=False)
        if not shutil.which(self.executable):
            raise ProviderError(f'{self.executable} CLI is not installed',kind='MISSING_EXECUTABLE',retryable=False)
        prompt=instruction(messages,agent)
        if self.executable=='claude':
            argv=['claude','-p','--tools','','--output-format','text',prompt]
        else:
            argv=['codex','exec','--sandbox','read-only','--skip-git-repo-check',prompt]
        try:
            result=subprocess.run(argv, capture_output=True, text=True, timeout=self.timeout,
                                  stdin=subprocess.DEVNULL, check=False)
        except subprocess.TimeoutExpired as exc:
            raise ProviderError(f'{self.executable} timed out',kind='TIMEOUT') from exc
        except OSError as exc:
            raise ProviderError(f'{self.executable} unavailable',kind='MISSING_EXECUTABLE') from exc
        if result.returncode:
            text=result.stderr[-350:].lower()
            kind='RATE_LIMIT' if 'rate limit' in text or '429' in text else 'AUTH' if 'auth' in text or '401' in text else 'PROVIDER_ERROR'
            raise ProviderError(f'{self.executable} returned {result.returncode}: {result.stderr[-350:]}',kind=kind)
        return _decode_action(result.stdout[-100000:])
