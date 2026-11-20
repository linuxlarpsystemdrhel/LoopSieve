"""Honest offline demo with real file edits and test subprocess.

The provider here is scripted. The changes and unittest execution are real.
It MUST NOT be described as an autonomous LLM benchmark.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from .agent_runtime import AgentRuntime,Journal


class ScriptedFix:
    def __init__(self):
        self.actions=iter([
            {'action':'inspect','path':'calculator.py'},
            {'action':'patch','path':'calculator.py','find':'return a - b','replace':'return a + b'},
            {'action':'verify','files':['calculator.py']},
            {'action':'finish','summary':'Fixed the addition bug, confirmed by a real unittest run'},
        ])
    def complete(self,messages:list[dict],agent:dict)->dict:
        return next(self.actions)


def run_offline_demo(output:Path|None=None)->dict:
    with tempfile.TemporaryDirectory(prefix='loopsieve-demo-') as td:
        root=Path(td)/'project';root.mkdir()
        (root/'calculator.py').write_text('def add(a, b):\n    return a - b\n',encoding='utf-8')
        (root/'test_calculator.py').write_text('import unittest\nfrom calculator import add\n\nclass MathTests(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(add(4, 5), 9)\n',encoding='utf-8')
        (root/'.loopsieve.json').write_text(json.dumps({'checks':[{'name':'unittest',
              'command':['{python}','-m','unittest','discover','-p','test_calculator.py'],
              'kinds':['python'],'timeout_seconds':10}]}),encoding='utf-8')
        store=Journal(root,Path(td)/'state')
        runtime=AgentRuntime(root,ScriptedFix(),store)
        session=runtime.create('Fix addition and verify behavior',agent_id='002-python-engineer',
                               max_steps=6,allow_writes=True,allow_checks=True)
        final=runtime.run(session['id'])
        proof=store.proof.audit()
        summary={'demo_type':'SCRIPTED_PROVIDER_NOT_REAL_LLM', 'file_edit':'REAL',
                 'test_execution':'REAL', 'status':final['status'],'step_count':final['step'],
                 'changed':final['changed'], 'verification':final['evidence'],
                 'proof':proof, 'event_kinds':[e['kind'] for e in store.events(session['id'])]}
        if output:
            output=Path(output)
            if output.exists():raise FileExistsError('refusing to overwrite an existing demo report')
            output.write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        return summary
