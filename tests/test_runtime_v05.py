import json
import tempfile
import unittest
from pathlib import Path

from loopsieve.agent_runtime import AgentRuntime, Journal
from loopsieve.checkpoint import CheckpointTimeMachine


class ScriptProvider:
    thread_safe = True

    def __init__(self, actions):
        self.actions = iter(actions)
        self.calls = 0

    def complete(self, messages, agent):
        self.calls += 1
        return next(self.actions)


class RuntimeV05Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'repo'
        self.root.mkdir()
        (self.root / 'calc.py').write_text('def add(a,b):\n    return a - b\n', encoding='utf-8')
        (self.root / 'README.md').write_text('# fixture\n', encoding='utf-8')
        (self.root / '.loopsieve.json').write_text(json.dumps({
            'checks': [{'name': 'syntax', 'command': ['{python}', '-m', 'compileall', '-q', 'calc.py'],
                        'kinds': ['python'], 'timeout_seconds': 10}]}), encoding='utf-8')
        self.journal = Journal(self.root, Path(self.tmp.name) / 'state')

    def test_checkpoint_restore_and_time_machine(self):
        provider = ScriptProvider([
            {'action': 'patch', 'path': 'calc.py', 'find': 'a - b', 'replace': 'a + b'},
            {'action': 'restore', 'checkpoint_id': 1},
            {'action': 'verify', 'files': ['calc.py']},
            {'action': 'finish', 'summary': 'Restored original bytes and verified'},
        ])
        runtime = AgentRuntime(self.root, provider, self.journal)
        sid = runtime.create('Patch then restore', '002-python-engineer', max_steps=6,
                             allow_writes=True, allow_checks=True)['id']
        result = runtime.run(sid)
        self.assertEqual(result['status'], 'COMPLETED')
        self.assertIn('return a - b', (self.root / 'calc.py').read_text())
        checkpoints = CheckpointTimeMachine(self.journal).list(sid)
        self.assertTrue(checkpoints)
        self.assertEqual(checkpoints[0]['path'], 'calc.py')

    def test_tool_search_and_diff_actions(self):
        provider = ScriptProvider([
            {'action': 'tool', 'tool': 'workspace_tree', 'args': {'limit': 10}},
            {'action': 'diff'},
            {'action': 'finish', 'summary': 'Read-only discovery complete'},
        ])
        runtime = AgentRuntime(self.root, provider, self.journal)
        sid = runtime.create('Discover files', '001-chief-architect', max_steps=5)['id']
        result = runtime.run(sid)
        self.assertEqual(result['status'], 'COMPLETED')
        events = self.journal.events(sid)
        self.assertTrue(any(e['kind'] == 'step' for e in events))

    def test_search_action_uses_permitted_tool(self):
        provider = ScriptProvider([
            {'action': 'search', 'query': 'return'},
            {'action': 'finish', 'summary': 'Search complete'},
        ])
        runtime = AgentRuntime(self.root, provider, self.journal)
        sid = runtime.create('Search source', '070-unit-test-engineer', max_steps=4)['id']
        result = runtime.run(sid)
        self.assertEqual(result['status'], 'COMPLETED')

    def test_tool_permission_is_enforced(self):
        provider = ScriptProvider([{'action': 'tool', 'tool': 'git_status', 'args': {}}])
        runtime = AgentRuntime(self.root, provider, self.journal)
        sid = runtime.create('Try a forbidden tool', '001-chief-architect', max_steps=1)['id']
        result = runtime.run(sid)
        self.assertEqual(result['status'], 'FAILED')
        self.assertIn('PermissionError', result['messages'][-1]['content'])

    def test_recover_interrupted_planning_session(self):
        session = self.journal.get(self.journal.save({
            'id': 'interrupted', 'agent_id': '001-chief-architect', 'task': 'x',
            'status': 'PLANNING', 'step': 0, 'max_steps': 2, 'allow_writes': False,
            'allow_checks': False, 'messages': [{'role': 'user', 'content': 'x'}],
            'changed': [], 'evidence': []}) or 'interrupted')
        # save() returns None; the row exists and is recoverable.
        runtime = AgentRuntime(self.root, ScriptProvider([]), self.journal)
        recovered = runtime.recover()
        self.assertTrue(any(x['id'] == 'interrupted' for x in recovered))
        self.assertEqual(self.journal.get('interrupted')['status'], 'READY')


if __name__ == '__main__':
    unittest.main()
