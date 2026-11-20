import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

from loopsieve.tui import data_rows
from loopsieve.webui import make_handler
from loopsieve.runner import run_check
from loopsieve.models import CheckSpec


class WebAndCLITests(unittest.TestCase):
    def test_web_local_read_only_endpoints(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/'.loopsieve.json').write_text('{"checks":[]}',encoding='utf8')
            server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(root))
            thread=threading.Thread(target=server.serve_forever,daemon=True)
            thread.start()
            try:
                with urlopen(f'http://127.0.0.1:{server.server_port}/api/dashboard',timeout=5) as r:
                    payload=json.load(r)
                    self.assertEqual(r.status,200)
                self.assertEqual(payload['counts']['agents'],100)
                with urlopen(f'http://127.0.0.1:{server.server_port}/api/tools',timeout=5) as r:
                    tools=json.load(r)
                self.assertEqual(len(tools),63)
                with urlopen(f'http://127.0.0.1:{server.server_port}/',timeout=5) as r:
                    html=r.read().decode('utf8')
                self.assertIn('LoopSieve',html)
                self.assertIn('Content-Security-Policy',r.headers)
            finally:
                server.shutdown();server.server_close();thread.join(3)

    def test_tui_data_provider_has_every_section(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/'.loopsieve.json').write_text('{"checks":[]}',encoding='utf8')
            for section in ('Dashboard','Agents','Tasks','Tools','Plugins','Skills','Verification','Performance','Settings'):
                with self.subTest(section=section):
                    columns,rows=data_rows(section,root)
                    self.assertTrue(columns)
                    self.assertTrue(isinstance(rows,list))

    def test_cli_doctor_from_project(self):
        env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1]/'src')}
        p=subprocess.run([sys.executable,'-m','loopsieve','doctor'],capture_output=True,text=True,timeout=12,env=env)
        self.assertEqual(p.returncode,0,p.stderr)
        data=json.loads(p.stdout)
        self.assertEqual(data['local_tools'],63)
        self.assertEqual(data['catalogs']['agents'],100)

    def test_runner_bounded_output_under_large_stream(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); f=root/'a.py';f.write_text('x=1')
            cmd=(sys.executable,'-c',"import sys; sys.stdout.write('z'*400000); sys.stdout.flush()")
            spec=CheckSpec(name='stdout stress',command=cmd,max_output_chars=2500,timeout_seconds=5)
            result=run_check(spec,root,[f])
            self.assertTrue(result.passed)
            self.assertLess(len(result.output),3000)
            self.assertIn('omitted',result.output)

    def test_runner_timeout_is_distinct_status(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); f=root/'a.py';f.write_text('x=1')
            cmd=(sys.executable,'-c','import time; time.sleep(4)')
            spec=CheckSpec(name='timeout',command=cmd,timeout_seconds=0.1)
            result=run_check(spec,root,[f])
            self.assertTrue(result.timed_out)
            self.assertEqual(result.returncode,124)

if __name__=='__main__':unittest.main()
