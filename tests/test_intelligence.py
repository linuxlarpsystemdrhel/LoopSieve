import json,tempfile,unittest,zipfile
from pathlib import Path
from loopsieve.intelligence import context_packet,symbol_index,import_graph,session_capsule,permission_preview,reliability_profiles
from loopsieve.agent_runtime import Journal,AgentRuntime
from loopsieve.toolkit import safe_path
class Fixture:
    def complete(self,messages,agent):return {'action':'tree'} if len(messages)<3 else {'action':'finish','summary':'examined'}
class IntelligenceTests(unittest.TestCase):
 def test_symbol_index_context_imports_and_budget(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'app.py').write_text('import json\ndef calibrate_threshold(x):\n    return json.dumps(x)\n')
   self.assertIn('calibrate_threshold',[x['name'] for x in symbol_index(root)])
   self.assertEqual(import_graph(root)['app.py'],['json'])
   packet=context_packet(root,'calibrate threshold',max_chars=1000)
   self.assertTrue(packet['matches'])
   self.assertLessEqual(packet['packed_chars'],1000)
 def test_permission_preview_and_capsule(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)
   j=Journal(root,root/'state')
   r=AgentRuntime(root,Fixture(),j)
   s=r.run(r.create('Audit code','001-chief-architect')['id'])
   preview=permission_preview('001-chief-architect',allow_writes=True)
   self.assertNotIn('patch',preview['available_actions'])
   out=root/'capsule.zip'
   session_capsule(j,s['id'],out)
   with zipfile.ZipFile(out) as z:
    self.assertEqual(z.namelist(),['manifest.json','REPLAY.md'])
    self.assertNotIn('messages',json.loads(z.read('manifest.json')))
   self.assertEqual(reliability_profiles(j)[0]['completed'],1)
 def test_sensitive_directories_and_private_keys_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)
   for name in ['.git/config','.claude/settings.json','.env','x.pem','secret.key','../outside']:
    with self.assertRaises(PermissionError,msg=name):safe_path(root,name)
if __name__=='__main__':unittest.main()
