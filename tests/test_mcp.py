import json,tempfile,unittest
from pathlib import Path
from loopsieve.mcp_manager import inspect_mcp
class MCPTests(unittest.TestCase):
 def test_redacted_mcp_config_and_missing_dependency(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)
   (p/'.mcp.json').write_text(json.dumps({'mcpServers':{
      'never':{'command':'obviously-not-installed-ls-xyz','args':['--token','SUPERSECRET'],'env':{'KEY':'SUPERSECRET'}}}}))
   out=inspect_mcp(p)
   self.assertEqual(out['servers'][0]['status'],'REQUIRES_DEPENDENCY')
   self.assertNotIn('SUPERSECRET',json.dumps(out))
 def test_invalid_json_fail_closed(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'.mcp.json').write_text('{broken')
   self.assertEqual(inspect_mcp(p)['servers'][0]['status'],'ERROR')
if __name__=='__main__':unittest.main()
