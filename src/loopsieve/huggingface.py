"""Official Hugging Face API explorer with server-side pagination.

The client uses the public HTTP API and does not download weights or execute
remote model code. It supports an optional token from the environment or the
local secret store. No token is written to caches or logs.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urlparse
from urllib.request import Request, urlopen

DEFAULT_BASE = 'https://huggingface.co'
BACKSLASH = chr(92)

CATEGORY_MAP = {
    'text-generation': 'Text Generation',
    'text2text-generation': 'Text Generation',
    'code': 'Code',
    'image-text-to-text': 'Vision-Language',
    'visual-question-answering': 'Vision-Language',
    'text-to-image': 'Text-to-Image',
    'image-to-image': 'Image-to-Image',
    'text-to-video': 'Text-to-Video',
    'image-to-video': 'Image-to-Video',
    'text-to-3d': 'Text-to-3D',
    'image-to-3d': 'Image-to-3D',
    'automatic-speech-recognition': 'Speech-to-Text',
    'text-to-speech': 'Text-to-Speech',
    'audio-classification': 'Audio',
    'image-segmentation': 'Segmentation',
    'object-detection': 'Detection',
    'feature-extraction': 'Embeddings',
    'sentence-similarity': 'Embeddings',
}


@dataclass
class HFModel:
    id: str
    author: str = ''
    pipeline_tag: str = ''
    category: str = 'Other'
    tags: tuple[str, ...] = ()
    downloads: int = 0
    likes: int = 0
    last_modified: str | None = None
    license: str = 'UNKNOWN'
    params: int | None = None
    formats: tuple[str, ...] = ()
    gated: bool | str = False
    library: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    def as_dict(self) -> dict:
        value = asdict(self)
        value['tags'] = list(self.tags)
        value['formats'] = list(self.formats)
        value.pop('raw', None)
        return value


def normalize_model(value: dict[str, Any]) -> HFModel:
    raw = value if isinstance(value, dict) else {}
    model_id = str(raw.get('id') or raw.get('modelId') or '')
    author = str(raw.get('author') or (model_id.split('/')[0] if '/' in model_id else ''))
    tags = tuple(str(x) for x in (raw.get('tags') or []))
    pipeline = str(raw.get('pipeline_tag') or '')
    license_value = 'UNKNOWN'
    card = raw.get('cardData') if isinstance(raw.get('cardData'), dict) else {}
    if isinstance(card.get('license'), str):
        license_value = card['license']
    else:
        for tag in tags:
            if tag.lower().startswith('license:'):
                license_value = tag.split(':', 1)[1]
                break
    params = None
    safetensors = raw.get('safetensors') if isinstance(raw.get('safetensors'), dict) else {}
    if isinstance(safetensors.get('total'), int):
        params = safetensors['total']
    formats = []
    for tag in tags:
        lower = tag.lower()
        if lower in ('gguf', 'safetensors', 'onnx', 'pytorch', 'tensorflow', 'mlx'):
            formats.append(lower)
    gated = raw.get('gated', False)
    return HFModel(
        id=model_id, author=author, pipeline_tag=pipeline,
        category=CATEGORY_MAP.get(pipeline, 'Other'), tags=tags,
        downloads=int(raw.get('downloads') or 0), likes=int(raw.get('likes') or 0),
        last_modified=raw.get('lastModified') or raw.get('last_modified'),
        license=license_value, params=params,
        formats=tuple(sorted(set(formats))), gated=gated,
        library=raw.get('library_name'), raw=raw,
    )


def _next_cursor(link_header: str | None) -> str | None:
    if not link_header:
        return None
    for part in link_header.split(','):
        if 'rel="next"' not in part:
            continue
        start = part.find('<')
        end = part.find('>')
        if start == -1 or end == -1:
            continue
        query = parse_qs(urlparse(part[start + 1:end]).query)
        values = query.get('cursor')
        if values:
            return values[0]
    return None


class HuggingFaceClient:
    def __init__(self, base_url: str = DEFAULT_BASE, token: str | None = None,
                 cache_dir: Path | str | None = None, cache_ttl: int = 900,
                 timeout: int = 20):
        parsed = urlparse(base_url)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname:
            raise ValueError('Hugging Face base URL must be http(s)')
        self.base_url = base_url.rstrip('/')
        self.token = token or os.environ.get('HF_TOKEN') or os.environ.get('HUGGING_FACE_HUB_TOKEN')
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.cache_ttl = max(0, int(cache_ttl))
        self.timeout = max(1, int(timeout))

    def _headers(self) -> dict[str, str]:
        headers = {'User-Agent': 'LoopSieve/0.6 HuggingFace explorer', 'Accept': 'application/json'}
        return headers

    def _get(self, path: str, params: dict[str, Any] | None = None) -> tuple[Any, str | None]:
        url = self.base_url + path
        if params:
            clean = {k: v for k, v in params.items() if v not in (None, '', [])}
            url += ('&' if '?' in url else '?') + urlencode(clean, doseq=True)
        request = Request(url, headers=self._headers())
        if self.token:
            request.add_unredirected_header('Authorization', 'Bearer ' + self.token)
        with urlopen(request, timeout=self.timeout) as response:
            if response.status != 200:
                raise RuntimeError(f'Hugging Face API returned HTTP {response.status}')
            payload = json.loads(response.read(4 * 1024 * 1024))
            return payload, _next_cursor(response.headers.get('Link'))

    def search(self, query: str = '', *, author: str | None = None,
               pipeline_tag: str | None = None, tags: list[str] | None = None,
               sort: str = 'downloads', direction: int = -1, limit: int = 20,
               cursor: str | None = None) -> dict:
        params = {
            'search': query or None, 'author': author or None,
            'pipeline_tag': pipeline_tag or None, 'filter': tags or None,
            'sort': sort, 'direction': direction,
            'limit': max(1, min(int(limit), 100)), 'cursor': cursor or None,
            'full': 'true',
        }
        payload, next_cursor = self._get('/api/models', params)
        if not isinstance(payload, list):
            raise RuntimeError('Hugging Face search response was not an array')
        models = [normalize_model(x) for x in payload if isinstance(x, dict) and x.get('id')]
        return {'models': [m.as_dict() for m in models], 'next_cursor': next_cursor,
                'has_more': bool(next_cursor), 'query': query, 'limit': limit,
                'source': self.base_url, 'kind': 'metadata_only'}

    def model_info(self, model_id: str) -> dict:
        if not model_id or '..' in model_id or BACKSLASH in model_id:
            raise ValueError('invalid model id')
        payload, _ = self._get('/api/models/' + quote(model_id, safe='/'))
        if not isinstance(payload, dict):
            raise RuntimeError('Hugging Face model response was not an object')
        return normalize_model(payload).as_dict()

    def files(self, model_id: str, revision: str = 'main') -> list[dict]:
        if not model_id or '..' in model_id or BACKSLASH in model_id:
            raise ValueError('invalid model id')
        payload, _ = self._get(f'/api/models/{quote(model_id, safe="/")}/tree/{quote(revision, safe="")}')
        if not isinstance(payload, list):
            raise RuntimeError('Hugging Face tree response was not an array')
        return [{'path': x.get('path'), 'size': x.get('size'), 'type': x.get('type')}
                for x in payload if isinstance(x, dict)][:500]

    def categories(self) -> list[str]:
        return sorted(set(CATEGORY_MAP.values()) | {'Other'})


def search_compatible(manager, client: HuggingFaceClient, query: str = '', *, limit: int = 10,
                      pipeline_tag: str | None = 'text-generation') -> dict:
    """Search HF metadata and annotate each hit with a local fit estimate."""
    from .model_manager import ModelSpec, fit_status
    result = client.search(query, pipeline_tag=pipeline_tag, limit=limit)
    rows = []
    for item in result['models']:
        params = item.get('params')
        spec = ModelSpec(id=item['id'], name=item['id'], architecture='llama',
                         params_b=(params / 1e9) if params else 0.0,
                         license=item.get('license', 'UNKNOWN'), tags=tuple(item.get('tags', [])))
        fit = fit_status(spec, manager.hardware, installed=False)
        item = dict(item)
        item['fit'] = fit
        rows.append(item)
    result['models'] = rows
    result['policy'] = 'HF metadata + local estimate; no remote code or weights were downloaded.'
    return result
