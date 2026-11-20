import tempfile
import unittest
from pathlib import Path
from loopsieve.demo import run_offline_demo

class HonestDemoTests(unittest.TestCase):
 def test_demo_real_verification_and_scripted_label(self):
  with tempfile.TemporaryDirectory() as td:
   output=Path(td)/'report.json'
   result=run_offline_demo(output)
   self.assertEqual(result['status'],'COMPLETED')
   self.assertEqual(result['demo_type'],'SCRIPTED_PROVIDER_NOT_REAL_LLM')
   self.assertEqual(result['proof']['status'],'PASS')
   self.assertEqual(result['verification'][0]['status'],'PASS')
   self.assertTrue(output.is_file())
