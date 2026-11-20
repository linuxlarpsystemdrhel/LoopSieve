import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen
from loopsieve.studio import make_handler

class ProofPanelTests(unittest.TestCase):
 def test_studio_proof_endpoints(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);(root/'.loopsieve.json').write_text('{"checks": []}')
   server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(root))
   thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
   try:
    with urlopen(f'http://127.0.0.1:{server.server_port}/api/evidence',timeout=3) as res:
     data=json.load(res)
     self.assertEqual(data['audit']['status'],'PASS')
    with urlopen(f'http://127.0.0.1:{server.server_port}/api/impact',timeout=3) as res:
     data=json.load(res)
     self.assertFalse(data['verified'])
    with urlopen(f'http://127.0.0.1:{server.server_port}/',timeout=3) as res:
     html=res.read().decode()
     self.assertIn("'Evidence'",html)
   finally:
    server.shutdown();server.server_close();thread.join(timeout=3)
