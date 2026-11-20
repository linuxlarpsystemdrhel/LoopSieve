import tempfile
import unittest
from pathlib import Path

from loopsieve.agent_runtime import AgentRuntime, Journal
from loopsieve.orchestrator import Orchestrator, WorkItem, detect_write_conflicts, validate_dag
from loopsieve.providers import ProviderError


class ParallelProvider:
    thread_safe = True

    def __init__(self):
        self.calls = 0

    def complete(self, messages, agent):
        self.calls += 1
        return {'action': 'tree'} if len(messages) < 3 else {'action': 'finish', 'summary': 'reviewed'}


class FailingProvider:
    thread_safe = True

    def __init__(self):
        self.calls = 0

    def complete(self, messages, agent):
        self.calls += 1
        if self.calls == 1:
            raise ProviderError('temporary provider failure', kind='RATE_LIMIT')
        return {'action': 'tree'} if len(messages) < 3 else {'action': 'finish', 'summary': 'recovered'}


class OrchestratorV05Tests(unittest.TestCase):
    def test_parallel_read_only_tasks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            provider = ParallelProvider()
            runtime = AgentRuntime(root, provider, Journal(root, root / 'state'))
            outcome = Orchestrator(runtime, max_workers=2).run([
                WorkItem('a', 'Review architecture', '001-chief-architect'),
                WorkItem('b', 'Review API', '014-api-engineer'),
            ], parallel=True, max_workers=2)
            self.assertEqual(outcome['status'], 'COMPLETED')
            self.assertTrue(outcome['parallel'])
            self.assertEqual(len(outcome['completed']), 2)
            self.assertEqual(len(runtime.journal.list()), 2)

    def test_write_conflict_is_rejected_before_execution(self):
        with self.assertRaises(ValueError):
            validate_dag([
                WorkItem('a', 'Edit file', '002-python-engineer', write_set=['src/a.py']),
                WorkItem('b', 'Edit same file', '002-python-engineer', write_set=['src/a.py']),
            ])
        conflict = detect_write_conflicts([
            WorkItem('a', 'x', write_set=['src/a.py']),
            WorkItem('b', 'y', write_set=['src/a.py']),
        ])
        self.assertEqual(conflict[0]['paths'], ['src/a.py'])

    def test_unknown_write_set_runs_sequentially(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = AgentRuntime(root, ParallelProvider(), Journal(root, root / 'state'))
            outcome = Orchestrator(runtime).run([WorkItem('a', 'Review', '001-chief-architect')],
                                                 allow_writes=True, parallel=True)
            self.assertFalse(outcome['parallel'])
            self.assertIn('parallel_skipped', outcome)

    def test_retry_after_transient_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = AgentRuntime(root, FailingProvider(), Journal(root, root / 'state'))
            outcome = Orchestrator(runtime).run([
                WorkItem('a', 'Review', '001-chief-architect', retries=1, on_failure='retry')])
            self.assertEqual(outcome['status'], 'COMPLETED')
            self.assertEqual(outcome['retries']['a'], 1)

    def test_replan_adds_a_new_item(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = AgentRuntime(root, FailingProvider(), Journal(root, root / 'state'))
            def replan(item, data):
                return [WorkItem('recovery', 'Recover after failure', '001-chief-architect')]
            outcome = Orchestrator(runtime, replan=replan).run([
                WorkItem('a', 'Review', '001-chief-architect', on_failure='replan')])
            self.assertEqual(outcome['status'], 'PARTIAL')
            self.assertIn('recovery', outcome['completed'])
            self.assertIn('a', outcome['blocked'])


if __name__ == '__main__':
    unittest.main()
