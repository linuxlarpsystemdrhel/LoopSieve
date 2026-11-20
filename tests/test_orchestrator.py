import json,tempfile,unittest
from pathlib import Path
from loopsieve.orchestrator import WorkItem,validate_dag,Orchestrator
from loopsieve.agent_runtime import AgentRuntime,Journal
class RepeatProvider:
    def complete(self,messages,agent):
        return {'action':'tree'} if len(messages)<3 else {'action':'finish','summary':'inspected work; no changes needed'}
class OrchestratorTests(unittest.TestCase):
    def test_dag_cycle_rejected(self):
        with self.assertRaises(ValueError):validate_dag([WorkItem('a','a',depends_on=['b']),WorkItem('b','b',depends_on=['a'])])
    def test_dependencies_and_role_assignment(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            runtime=AgentRuntime(p,RepeatProvider(),Journal(p,p/'state'))
            outcome=Orchestrator(runtime).run([WorkItem('a','Review backend','001-chief-architect'),WorkItem('b','Review API','014-api-engineer',['a'])])
            self.assertEqual(outcome['status'],'COMPLETED')
            self.assertEqual(len(outcome['completed']),2)
            self.assertEqual(len(runtime.journal.list()),2)
if __name__=='__main__':unittest.main()
