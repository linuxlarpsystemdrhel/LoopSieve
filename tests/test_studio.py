import json, tempfile, unittest
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer
from threading import Thread
from loopsieve.studio import make_handler
class StudioTests(unittest.TestCase):
    def test_loopback_studio_mascot_and_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            handler=make_handler(root,token='testtoken')
            server=ThreadingHTTPServer(('127.0.0.1',0),handler)
            th=Thread(target=server.serve_forever,daemon=True);th.start()
            try:
                base=f'http://127.0.0.1:{server.server_port}'
                with urlopen(base+'/') as r:
                    text=r.read().decode()
                    self.assertIn('testtoken',text)
                    self.assertIn('Create session',text)
                    self.assertIn('getContext(\'webgl\'',text)
                with urlopen(base+'/assets/pip.gltf') as r:
                    mesh=json.load(r)
                    self.assertEqual(mesh['asset']['version'],'2.0')
                    self.assertGreaterEqual(len(mesh['nodes']),15)
                def request(path,data=None,token=None):
                    b=json.dumps(data or {}).encode()
                    return Request(base+path,b,headers={'Content-Type':'application/json','X-LoopSieve-Token':token or '', 'Host':f'127.0.0.1:{server.server_port}'})
                with self.assertRaises(HTTPError) as exc:urlopen(request('/api/create',{'task':'inspect'}))
                self.assertEqual(exc.exception.code,403)
                exc.exception.close()
                with urlopen(request('/api/create',{'task':'Inspect code','provider':'ollama'},'testtoken')) as r:
                    data=json.load(r)
                    self.assertIn('id',data)
                with urlopen(base+'/api/sessions') as r:
                    self.assertEqual(len(json.load(r)),1)
                with urlopen(request('/api/pause/'+data['id'],{},'testtoken')) as r:
                    self.assertEqual(json.load(r)['status'],'PAUSED')
            finally:
                server.shutdown();server.server_close()
if __name__=='__main__':unittest.main()
