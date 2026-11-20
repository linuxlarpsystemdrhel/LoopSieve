"""The shared executor must accept each of the 100 unique role manifests."""
import tempfile, unittest
from pathlib import Path
from loopsieve.agent_runtime import AgentRuntime,Journal
from loopsieve.catalog import list_entries

class DeterministicFixture:
    def complete(self,messages,agent):
        return {'action':'tree'} if len(messages)<3 else {'action':'finish','summary':'Reviewed directory with '+agent['name']}

class RoleRuntimeCoverage(unittest.TestCase):
    def test_all_one_hundred_roles_can_execute_readonly_session(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'README.md').write_text('# Test\n')
            rt=AgentRuntime(p,DeterministicFixture(),Journal(p,p/'state'))
            agents=list_entries('agents')
            self.assertEqual(len(agents),100)
            for a in agents:
                result=rt.run(rt.create('Read repository layout',a['id'],max_steps=3)['id'])
                self.assertEqual(result['status'],'COMPLETED',msg=a['name'])
                self.assertEqual(result['step'],2,msg=a['name'])
                self.assertFalse(result['changed'])
            self.assertEqual(len(rt.journal.list()),100)
if __name__=='__main__':unittest.main()
