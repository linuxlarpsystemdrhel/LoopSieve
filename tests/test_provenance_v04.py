"""v0.4 evidence, impact and context regression suite."""
import contextlib
import io
import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

from loopsieve.provenance import EvidenceLedger,ArtifactStore,acceptance_gate,portable_capsule,sanitize
from loopsieve.project_intelligence import python_impact,compile_context,check_contract,detect_doc_conflicts
from loopsieve.memory import ProjectMemory
from loopsieve.release_quality import run_required_checks,evaluate_release_evidence


class ProofTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def test_append_audit_and_tamper_detection(self):
        ledger=EvidenceLedger(self.root/'proof.sqlite')
        one=ledger.append('agent-1','test_pass',{'exit_code':0})
        ledger.append('agent-2','check_failed',{'exit_code':4})
        self.assertNotEqual(one['hash'],ledger.audit()['head'])
        self.assertEqual(ledger.audit()['status'],'PASS')
        with contextlib.closing(sqlite3.connect(ledger.db)) as conn:
            conn.execute("UPDATE evidence SET payload='fake-pass' WHERE id=1")
            conn.commit()
        self.assertEqual(ledger.audit()['status'],'FAIL')

    def test_concurrent_evidence_append(self):
        from concurrent.futures import ThreadPoolExecutor
        ledger=EvidenceLedger(self.root/'proof.sqlite')
        with ThreadPoolExecutor(max_workers=7) as pool:
            list(pool.map(lambda i: ledger.append('task','event',{'i':i}),range(40)))
        self.assertEqual(ledger.audit()['entries_checked'],40)
        self.assertEqual(ledger.audit()['status'],'PASS')

    def test_secret_redaction(self):
        line=sanitize('authorization=abc123 api_key=super-secret password=pwd123 -----BEGIN OPENSSH PRIVATE KEY-----')
        self.assertNotIn('super-secret',line)
        self.assertNotIn('pwd123',line)
        self.assertNotIn('OPENSSH PRIVATE KEY',line)

    def test_artifact_content_addressed_and_corruption(self):
        s=ArtifactStore(self.root/'objects')
        one=s.put(b'test data')
        self.assertEqual(one['ref'],s.put(b'test data')['ref'])
        self.assertEqual(s.get(one['ref']),b'test data')
        with self.assertRaises(ValueError):s.get('sha256:../../secrets')
        path=s.root/one['sha256'][:2]/one['sha256']
        path.write_bytes(b'corrupt')
        with self.assertRaises(ValueError):s.get(one['ref'])

    def test_release_gate_no_false_success(self):
        expected=['lint','tests']
        data={'lint':{'status':'PASS','evidence_id':'id1','authenticity':'real'},
              'tests':{'status':'PASS','evidence_id':'id2','authenticity':'mock'}}
        self.assertEqual(acceptance_gate(expected,data).status,'BLOCKED')
        data['tests']['authenticity']='real'
        self.assertEqual(acceptance_gate(expected,data).status,'PASS')
        data['tests']['status']='SKIPPED_UNVERIFIED'
        self.assertEqual(acceptance_gate(expected,data).status,'BLOCKED')
        self.assertEqual(evaluate_release_evidence(self.root,{},['test'])['status'],'BLOCKED')

    def test_capsule_excludes_messages_and_keys(self):
        session={'id':'abc','agent_id':'001','status':'COMPLETED','step':3,'max_steps':8,
                 'messages':[{'content':'token=secret'}],'changed':['lib.py'],
                 'evidence':[{'status':'PASS','files':['lib.py'],'output':'password=secret'}]}
        target=self.root/'bundle.zip'
        info=portable_capsule(session,[{'kind':'step','created':42,'details':'secret=secret'}],target)
        self.assertEqual(len(info['sha256']),64)
        with zipfile.ZipFile(target) as z:
            text=z.read('capsule.json').decode()
            self.assertNotIn('token=secret',text)
            self.assertNotIn('password=secret',text)
            self.assertIn('COMPLETED',text)
        with self.assertRaises(FileExistsError):portable_capsule(session,[],target)

    def test_python_reverse_dependency_impact(self):
        (self.root/'service.py').write_text('def process(): return 1\n')
        (self.root/'api.py').write_text('import service\n')
        (self.root/'main.py').write_text('from api import something\n')
        r=python_impact(self.root,['service.py'])
        self.assertEqual([x['file'] for x in r['potentially_affected']],['api.py','main.py'])
        self.assertFalse(r['verified'])

    def test_context_has_provenance_and_budget(self):
        (self.root/'code.py').write_text('def process_transaction(amount):\n    return amount * 2\n')
        result=compile_context(self.root,'transaction amount',1200)
        self.assertTrue(result['excerpts'])
        self.assertLessEqual(result['approx_chars'],1200)
        self.assertEqual(len(result['excerpts'][0]['source_sha256']),64)

    def test_task_contract_and_no_placeholders(self):
        with self.assertRaises(ValueError):check_contract('create a working API',['TODO'])
        r=check_contract('create a working API',['GET /health responds 200 with JSON status'])
        self.assertEqual(r['criteria'][0]['status'],'UNVERIFIED')

    def test_conflicting_dependency_pins(self):
        (self.root/'requirements.txt').write_text('requests==2.30.0\n')
        (self.root/'requirements-dev.txt').write_text('requests==2.32.0\n')
        r=detect_doc_conflicts(self.root)
        self.assertEqual(r[0]['package'],'requests')

    def test_memory_invalidation_and_conflicts(self):
        source=self.root/'spec.txt';source.write_text('version A')
        memory=ProjectMemory(self.root,self.root/'memory.sqlite')
        memory.remember('api.version','v1','spec.txt')
        self.assertEqual(memory.query('api.version')['api.version']['facts'][0]['status'],'CURRENT')
        source.write_text('version B')
        self.assertEqual(memory.query('api.version')['api.version']['facts'][0]['status'],'STALE')
        with self.assertRaises(PermissionError):memory.remember('secret','x','.env')

    def test_opt_in_real_check_and_failure(self):
        import sys
        result=run_required_checks(self.root,{'success':[sys.executable,'-c','print("ok")'],
                                              'failure':[sys.executable,'-c','raise SystemExit(3)']},timeout=5)
        self.assertEqual(result['gate']['status'],'BLOCKED')
        self.assertEqual(result['results']['success']['status'],'PASS')
        self.assertEqual(result['results']['failure']['status'],'FAIL')


if __name__ == '__main__': unittest.main()
