import json
import tempfile
import unittest
from pathlib import Path

from loopsieve.commands import TerminalWorkbench


class FakeProvider:
    provider_id = 'fake:test'
    thread_safe = True

    def __init__(self):
        self.calls = 0

    def probe(self):
        return {'state': 'READY', 'kind': 'OK', 'installed_models': ['llama3.2:3b']}

    def complete(self, messages, agent):
        self.calls += 1
        return {'action': 'tree'} if len(messages) < 3 else {'action': 'finish', 'summary': 'reviewed'}


class CommandWorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'README.md').write_text('# demo\n', encoding='utf-8')
        (self.root / '.loopsieve.json').write_text(json.dumps({
            'checks': [{'name': 'syntax', 'command': ['{python}', '-m', 'compileall', '-q', '.'],
                        'kinds': ['any'], 'timeout_seconds': 20}]}), encoding='utf-8')
        self.workbench = TerminalWorkbench(self.root, provider=FakeProvider(), provider_name='fake')

    def test_status_and_hardware(self):
        status = self.workbench.run('/status')
        self.assertTrue(status['ok'])
        self.assertIn('workspace', status['data'])
        hardware = self.workbench.run('/hardware')
        self.assertTrue(hardware['ok'])
        self.assertIn('hardware', hardware['data'])

    def test_models_and_model_commands(self):
        models = self.workbench.run('/models')
        self.assertTrue(models['ok'])
        self.assertTrue(models['data']['models'])
        selected = self.workbench.run('/model select llama3.2:3b')
        self.assertTrue(selected['ok'])
        self.assertEqual(selected['data']['selected'], 'llama3.2:3b')
        memory = self.workbench.run('/model memory llama3.2:3b')
        self.assertTrue(memory['ok'])
        auto = self.workbench.run('/model auto fix a python bug')
        self.assertTrue(auto['ok'])
        benchmark = self.workbench.run('/model benchmark llama3.2:3b')
        self.assertTrue(benchmark['ok'])

    def test_provider_and_fallback(self):
        status = self.workbench.run('/provider status')
        self.assertTrue(status['ok'])
        self.assertEqual(status['data']['state'], 'READY')
        enabled = self.workbench.run('/fallback enable')
        self.assertTrue(enabled['ok'])
        self.assertTrue(enabled['data']['enabled'])
        disabled = self.workbench.run('/fallback disable')
        self.assertFalse(disabled['data']['enabled'])
        reset = self.workbench.run('/fallback reset')
        self.assertTrue(reset['ok'])

    def test_agent_run_and_handoff(self):
        result = self.workbench.run('/agent run Review the repository')
        self.assertTrue(result['ok'], result['text'])
        session = result['data']['id']
        handoff = self.workbench.run(f'/handoff {session} {self.root / "handoff.json"}')
        self.assertTrue(handoff['ok'], handoff['text'])
        self.assertEqual(handoff['data']['status'], 'HANDED_OFF')
        accepted = __import__('loopsieve.handoff', fromlist=['VerifiedTaskHandoff']).VerifiedTaskHandoff(
            self.workbench.journal).accept(self.root / 'handoff.json')
        self.assertEqual(accepted['status'], 'ACCEPTED')
        checkpoints = self.workbench.run(f'/checkpoint {session}')
        self.assertTrue(checkpoints['ok'])
        self.assertIn('checkpoints', checkpoints['data'])

    def test_team_dag(self):
        dag = self.root / 'dag.json'
        dag.write_text(json.dumps([
            {'id': 'a', 'task': 'Review architecture', 'agent_id': '001-chief-architect'},
            {'id': 'b', 'task': 'Review API', 'agent_id': '014-api-engineer', 'depends_on': ['a']},
        ]), encoding='utf-8')
        result = self.workbench.run(f'/team {dag}')
        self.assertTrue(result['ok'], result['text'])
        self.assertEqual(result['data']['status'], 'COMPLETED')

    def test_read_only_commands(self):
        for line in ('/mascot', '/tools', '/budget', '/reliability', '/risk README.md',
                     '/route 001-chief-architect review the code', '/recover'):
            with self.subTest(line=line):
                value = self.workbench.run(line)
                self.assertTrue(value['ok'], value['text'])
        self.assertFalse(self.workbench.run('/unknown').get('ok'))


if __name__ == '__main__':
    unittest.main()
