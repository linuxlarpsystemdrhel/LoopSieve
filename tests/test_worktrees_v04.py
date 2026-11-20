import subprocess
import tempfile
import unittest
from pathlib import Path
from loopsieve.worktrees import prepare_experiment, worktree_status

class WorktreesTests(unittest.TestCase):
 def test_isolated_detached_branch_opt_in(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td)/'repo';root.mkdir()
   subprocess.run(['git','init','-q',str(root)],check=True)
   (root/'main.py').write_text('VALUE=1\n')
   subprocess.run(['git','-C',str(root),'add','.'],check=True)
   subprocess.run(['git','-C',str(root),'-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','base'],check=True)
   with self.assertRaises(PermissionError):prepare_experiment(root,'s1',Path(td)/'external')
   info=prepare_experiment(root,'s1',Path(td)/'external',approve=True)
   created=Path(info['path']);self.assertTrue(created.is_dir())
   (created/'main.py').write_text('VALUE=2\n')
   self.assertEqual((root/'main.py').read_text(),'VALUE=1\n')
   self.assertEqual(len(worktree_status(root)),2)
   with self.assertRaises(ValueError):prepare_experiment(root,'../../bad',Path(td)/'external',approve=True)
   # The test is the owner of this disposable worktree and cleans it explicitly.
   subprocess.run(['git','-C',str(root),'worktree','remove','--force',str(created)],check=True)
 def test_dirty_root_refused(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td)/'repo';root.mkdir();subprocess.run(['git','init','-q',str(root)],check=True)
   (root/'x').write_text('a');subprocess.run(['git','-C',str(root),'add','.'],check=True)
   subprocess.run(['git','-C',str(root),'-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','base'],check=True)
   (root/'x').write_text('b')
   with self.assertRaises(ValueError):prepare_experiment(root,'s1',Path(td)/'exp',approve=True)
