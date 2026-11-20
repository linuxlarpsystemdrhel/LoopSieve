import json
import tempfile
import unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from loopsieve.agent_runtime import AgentRuntime, Journal, RuntimeErrorState
from loopsieve.providers import OllamaProvider, ProviderError, _decode_action


class ScriptProvider:
    def __init__(self, actions): self.actions=iter(actions); self.calls=0
    def complete(self, messages, agent):
        self.calls+=1
        return next(self.actions)


class AgentRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'repo';self.root.mkdir()
        (self.root/'calc.py').write_text('def add(a,b):\n    return a - b\n')
        (self.root/'test_calc.py').write_text('import unittest\nfrom calc import add\nclass T(unittest.TestCase):\n    def test_add(self): self.assertEqual(add(2,3),5)\n')
        (self.root/'.loopsieve.json').write_text(json.dumps({'checks':[{'name':'unittest','command':['{python}','-m','unittest','discover','-p','test_calc.py'], 'kinds':['python'],'timeout_seconds':15}]}))
        self.journal=Journal(self.root,Path(self.tmp.name)/'state')

    def test_real_code_patch_and_real_verification(self):
        provider=ScriptProvider([
            {'action':'inspect','path':'calc.py'},
            {'action':'patch','path':'calc.py','find':'return a - b','replace':'return a + b'},
            {'action':'verify','files':['calc.py']},
            {'action':'finish','summary':'Fixed subtraction bug and verified unittest'}])
        runtime=AgentRuntime(self.root,provider,self.journal)
        session=runtime.create('Fix calc add bug', '002-python-engineer', max_steps=7,allow_writes=True,allow_checks=True)
        result=runtime.run(session['id'])
        self.assertEqual(result['status'],'COMPLETED')
        self.assertEqual(result['step'],4)
        self.assertEqual(provider.calls,4)
        self.assertIn('return a + b',(self.root/'calc.py').read_text())
        self.assertTrue(result['evidence'])
        self.assertEqual(result['evidence'][-1]['status'],'PASS')
        self.assertEqual(len(self.journal.events(session['id'])),5)

    def test_no_writes_without_explicit_optin(self):
        runtime=AgentRuntime(self.root,ScriptProvider([{'action':'patch','path':'calc.py','find':'a - b','replace':'a + b'},{'action':'blocked','reason':'read only'}]),self.journal)
        result=runtime.run(runtime.create('Fix bug','002-python-engineer',max_steps=3)['id'])
        self.assertEqual(result['status'],'BLOCKED')
        self.assertIn('return a - b',(self.root/'calc.py').read_text())
        self.assertIn('PermissionError',result['messages'][-3]['content'])

    def test_cannot_claim_success_after_edit_without_check(self):
        runtime=AgentRuntime(self.root,ScriptProvider([
            {'action':'patch','path':'calc.py','find':'a - b','replace':'a + b'},
            {'action':'finish','summary':'unverified work'}, {'action':'blocked','reason':'cannot verify'}]),self.journal)
        result=runtime.run(runtime.create('Fix', '002-python-engineer',max_steps=3,allow_writes=True)['id'])
        self.assertEqual(result['status'],'BLOCKED')
        self.assertFalse(result['evidence'])

    def test_pause_resume_and_persistent_recovery(self):
        provider=ScriptProvider([{'action':'inspect','path':'calc.py'},{'action':'finish','summary':'inspected'}])
        runtime=AgentRuntime(self.root,provider,self.journal)
        sid=runtime.create('Review code','001-chief-architect')['id']
        runtime.step(sid);runtime.pause(sid)
        with self.assertRaises(RuntimeErrorState):runtime.step(sid)
        recovered=AgentRuntime(self.root,provider,Journal(self.root,Path(self.tmp.name)/'state'))
        self.assertEqual(recovered.resume(sid)['status'],'COMPLETED')

    def test_budget_and_strict_workspaces(self):
        runtime=AgentRuntime(self.root,ScriptProvider([{'action':'inspect','path':'../../etc/passwd'}]),self.journal)
        s=runtime.run(runtime.create('read','001-chief-architect',max_steps=1)['id'])
        self.assertEqual(s['status'],'FAILED')
        self.assertIn('PermissionError',s['messages'][-1]['content'])

    def test_patch_must_match_once(self):
        runtime=AgentRuntime(self.root,ScriptProvider([{'action':'patch','path':'calc.py','find':'a','replace':'e'}]),self.journal)
        s=runtime.run(runtime.create('patch','002-python-engineer',max_steps=1,allow_writes=True)['id'])
        self.assertEqual(s['status'],'FAILED')
        self.assertIn('return a - b',(self.root/'calc.py').read_text())

    def test_ollama_http_adapter_with_fake_local_api(self):
        class Fake(BaseHTTPRequestHandler):
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                assert body['model']=='fixture'
                response=json.dumps({'message':{'content':'{"action":"tree"}'}}).encode()
                self.send_response(200);self.send_header('Content-Length',str(len(response)));self.end_headers();self.wfile.write(response)
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Fake)
        worker=Thread(target=server.serve_forever,daemon=True);worker.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        provider=OllamaProvider('fixture',f'http://127.0.0.1:{server.server_port}/api/chat')
        from loopsieve.catalog import load
        self.assertEqual(provider.complete([{'role':'user','content':'list files'}],load('agents','001-chief-architect')),{'action':'tree'})

    def test_provider_rejects_non_json_or_remote_ollama(self):
        with self.assertRaises(ProviderError):_decode_action('The answer is 42')
        with self.assertRaises(ValueError):OllamaProvider('bad','https://server.example.com/api/chat')

    def test_no_ssh_or_git_write(self):
        (self.root/'.git').mkdir()
        (self.root/'.git'/'config').write_text('secret=false')
        runtime=AgentRuntime(self.root,ScriptProvider([{'action':'patch','path':'.git/config','find':'false','replace':'true'}]),self.journal)
        s=runtime.run(runtime.create('edit git', '002-python-engineer', max_steps=1,allow_writes=True)['id'])
        self.assertEqual(s['status'],'FAILED')
        self.assertEqual((self.root/'.git/config').read_text(),'secret=false')

if __name__=='__main__': unittest.main()

class CancellationSafety(unittest.TestCase):
    def test_cancel_during_provider_reasoning_prevents_patch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'work.py').write_text('a = 1\n')
            journal=Journal(root,root/'state')
            class LateProvider:
                def __init__(self):self.r=None;self.sid=None
                def complete(self,messages,agent):
                    self.r.cancel(self.sid)
                    return {'action':'patch','path':'work.py','find':'a = 1','replace':'a = 2'}
            p=LateProvider()
            runtime=AgentRuntime(root,p,journal)
            sid=runtime.create('Edit work.py','002-python-engineer',allow_writes=True)['id']
            p.r=runtime;p.sid=sid
            s=runtime.run(sid)
            self.assertEqual(s['status'],'CANCELLED')
            self.assertEqual((root/'work.py').read_text(),'a = 1\n')
            self.assertTrue(any(e['kind']=='discarded_late_decision' for e in journal.events(sid)))
