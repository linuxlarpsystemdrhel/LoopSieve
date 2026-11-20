import json
import tempfile
import unittest
from pathlib import Path

from loopsieve.agent_runtime import Journal
from loopsieve.budget import AdaptiveSwarmBudget
from loopsieve.conflict import CrossAgentConflictResolver
from loopsieve.failure import predict_failure
from loopsieve.handoff import VerifiedTaskHandoff
from loopsieve.hardware import GpuInfo, HardwareProfile
from loopsieve.reliability import rank_agents
from loopsieve.routing import route_tools
from loopsieve.tui import SECTIONS, data_rows


class FeatureV05Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'service.py').write_text('def process(): return 1\n', encoding='utf-8')
        (self.root / 'api.py').write_text('import service\n', encoding='utf-8')
        (self.root / 'README.md').write_text('# demo\n', encoding='utf-8')
        self.journal = Journal(self.root, self.root / 'state')

    def _completed(self):
        session = {'id': 's1', 'agent_id': '002-python-engineer', 'task': 'verify',
                   'status': 'COMPLETED', 'step': 2, 'max_steps': 4, 'allow_writes': True,
                   'allow_checks': True, 'messages': [{'role': 'user', 'content': 'x'}],
                   'changed': ['service.py'],
                   'evidence': [{'status': 'PASS', 'files': ['service.py'], 'changed_files': ['service.py']}]}
        self.journal.save(session)
        return session['id']

    def test_verified_handoff_and_tamper_detection(self):
        sid = self._completed()
        handoff = VerifiedTaskHandoff(self.journal)
        report = handoff.verify(sid)
        self.assertEqual(report['status'], 'VERIFIED')
        target = self.root / 'handoff.json'
        value = handoff.handoff(sid, target)
        self.assertEqual(value['status'], 'HANDED_OFF')
        self.assertEqual(handoff.accept(target)['status'], 'ACCEPTED')
        (self.root / 'service.py').write_text('def process(): return 2\n', encoding='utf-8')
        with self.assertRaises(ValueError):
            handoff.accept(target)

    def test_conflict_resolver(self):
        resolver = CrossAgentConflictResolver()
        conflicts = resolver.detect({'a': ['src/x.py'], 'b': ['src/x.py', 'src/y.py']})
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(resolver.resolve(conflicts, 'block')['status'], 'BLOCKED')
        self.assertEqual(resolver.resolve(conflicts, 'first')['winner'], 'a')
        self.assertEqual(resolver.resolve([], 'block')['status'], 'CLEAR')

    def test_reliability_and_budget(self):
        self._completed()
        rows = rank_agents(self.journal)
        self.assertEqual(rows[0]['agent_id'], '002-python-engineer')
        self.assertGreater(rows[0]['score'], 0)
        hw = HardwareProfile(os_name='Test', architecture='x86_64', cpu='test', cpu_count=4,
                             ram_total_mb=8192, ram_free_mb=4096,
                             gpus=(GpuInfo('RTX', vram_total_mb=4096, vram_free_mb=3500),))
        budget = AdaptiveSwarmBudget(hw, max_agents=4, max_memory_mb=4096)
        value = budget.recommend(active=1, model_mb=1024)
        self.assertIn('max_workers', value)
        self.assertIn('memory_slots', value['reason'])

    def test_failure_prediction_and_routing(self):
        risk = predict_failure(self.root, ['service.py'])
        self.assertIn(risk['risk'], ('LOW', 'MEDIUM', 'HIGH'))
        self.assertEqual(risk['confidence'], 'HEURISTIC_NOT_MEASURED')
        agent = json.loads((Path(__file__).resolve().parents[1] / 'src' / 'loopsieve' / 'data' /
                            'agents' / '001-chief-architect.json').read_text(encoding='utf-8'))
        route = route_tools(agent, 'review and inspect the code')
        self.assertIn('workspace_tree', route['tools'])

    def test_tui_sections_are_safe(self):
        for section in SECTIONS:
            headers, rows = data_rows(section, self.root)
            self.assertTrue(headers, section)
            self.assertIsInstance(rows, list, section)


if __name__ == '__main__':
    unittest.main()
