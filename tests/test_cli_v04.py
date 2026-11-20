import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from loopsieve.cli import build_parser

class CLIProofTests(unittest.TestCase):
 def _run(self, argv):
  p=build_parser();a=p.parse_args(argv)
  b=io.StringIO()
  with contextlib.redirect_stdout(b): code=a.func(a)
  return code,json.loads(b.getvalue())

 def test_proof_audit_and_impact(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);(root/'api.py').write_text('from services import process\n')
   (root/'services.py').write_text('def process(): pass\n')
   code,a=self._run(['proof','evidence','audit','--root',td]);self.assertEqual(code,0)
   self.assertEqual(a['status'],'PASS')
   _,b=self._run(['proof','impact','--root',td,'services.py'])
   self.assertEqual(b['potentially_affected'][0]['file'],'api.py')

 def test_gate_and_opt_in_commands(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'checks.json'
   p.write_text(json.dumps({'python':['/usr/bin/true']}))
   parser=build_parser()
   args=parser.parse_args(['proof','check-suite','--root',td,'--input',str(p)])
   with self.assertRaises(PermissionError):args.func(args)
