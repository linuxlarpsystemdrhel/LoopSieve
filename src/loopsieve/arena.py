"""Model performance arena: the same real coding task for each model/provider.

The arena uses the same bounded agent runtime and a real subprocess test. It is
not a benchmark of a model's marketing claims and it never starts a model by
itself; the caller supplies each provider.
"""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from typing import Any

from .agent_runtime import AgentRuntime, Journal


FIXTURE = {
    'calculator.py': 'def add(a, b):\n    return a - b\n',
    'test_calculator.py': ('import unittest\nfrom calculator import add\n\n'
                           'class MathTests(unittest.TestCase):\n'
                           '    def test_add(self):\n'
                           '        self.assertEqual(add(4, 5), 9)\n'),
    '.loopsieve.json': json.dumps({
        'checks': [{'name': 'unittest', 'command': ['{python}', '-m', 'unittest', 'discover', '-p', 'test_calculator.py'],
                    'kinds': ['python'], 'timeout_seconds': 15}]
    }),
}


def _make_fixture(root: Path) -> None:
    for name, content in FIXTURE.items():
        (root / name).write_text(content, encoding='utf-8')


class ModelPerformanceArena:
    def __init__(self, max_steps: int = 8):
        self.max_steps = max(1, min(int(max_steps), 20))

    def run_model(self, provider: Any, model_id: str = 'provider', *,
                  max_steps: int | None = None) -> dict:
        with tempfile.TemporaryDirectory(prefix='loopsieve-arena-') as tmp:
            root = Path(tmp) / 'project'
            root.mkdir()
            _make_fixture(root)
            journal = Journal(root, Path(tmp) / 'state')
            runtime = AgentRuntime(root, provider, journal)
            session = runtime.create('Fix the calculator add bug and verify the real unittest.',
                                     '002-python-engineer', max_steps or self.max_steps,
                                     allow_writes=True, allow_checks=True)
            started = time.monotonic()
            result = runtime.run(session['id'])
            elapsed = round(time.monotonic() - started, 3)
            content = (root / 'calculator.py').read_text(encoding='utf-8')
            evidence = result.get('evidence', [])
            passed = result['status'] == 'COMPLETED' and 'a + b' in content and any(
                e.get('status') == 'PASS' for e in evidence)
            return {'model': model_id, 'status': 'PASS' if passed else 'FAIL',
                    'agent_status': result['status'], 'steps': result['step'],
                    'wall_clock_seconds': elapsed, 'changed': result.get('changed', []),
                    'evidence': evidence, 'session_id': session['id'],
                    'proof': journal.proof.audit(),
                    'criterion': 'real file edit + real unittest subprocess',
                    'limitations': 'One fixture and one local run; not a statistical model ranking.'}

    def compare(self, providers: dict[str, Any]) -> dict:
        results = []
        for name, provider in providers.items():
            results.append(self.run_model(provider, name))
        results.sort(key=lambda x: (x['status'] != 'PASS', x['wall_clock_seconds']))
        return {'task': 'calculator addition bug', 'results': results,
                'pass_count': sum(1 for x in results if x['status'] == 'PASS'),
                'total': len(results),
                'policy': 'Same fixture and checks; provider latency is measured, coding quality is binary on this fixture.'}
