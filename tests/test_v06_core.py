import hashlib
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from loopsieve.agent_runtime import AgentRuntime, Journal
from loopsieve.capability import CapabilityRegistry
from loopsieve.huggingface import HuggingFaceClient
from loopsieve.model_manager import ModelDownloader, ModelManager
from loopsieve.model_team import ModelTeam, TeamStore
from loopsieve.permissions import PermissionDenied, PermissionEngine, PermissionLevel
from loopsieve.provider_catalog import ProviderCatalog
from loopsieve.quantization import estimate_memory, method_catalog, recommend_profiles
from loopsieve.secure_store import SecretStore
from loopsieve.tui import SECTIONS, data_rows


class FakeProvider:
    provider_id = 'fake:test'
    thread_safe = True

    def __init__(self, prefix='ok'):
        self.prefix = prefix
        self.calls = 0

    def probe(self):
        return {'state': 'READY', 'kind': 'OK'}

    def complete(self, messages, agent):
        self.calls += 1
        return {'action': 'tree'} if len(messages) < 3 else {'action': 'finish', 'summary': self.prefix + ' done'}


class V06CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_permission_engine_is_deny_by_default(self):
        engine = PermissionEngine()
        with self.assertRaises(PermissionDenied):
            engine.require('s1', PermissionLevel.WORKSPACE_WRITE, action='patch')
        engine.grant('s1', PermissionLevel.WORKSPACE_WRITE, reason='test')
        engine.require('s1', PermissionLevel.WORKSPACE_WRITE, action='patch')
        self.assertIn(PermissionLevel.WORKSPACE_WRITE, engine.levels('s1'))
        self.assertGreaterEqual(len(engine.audit('s1')), 2)
        self.assertEqual(engine.required_for_action('verify'), PermissionLevel.TEST_EXECUTION)

    def test_permission_engine_blocks_agent_write(self):
        class P:
            thread_safe = True
            def complete(self, messages, agent):
                return {'action': 'patch', 'path': 'calc.py', 'find': 'a - b', 'replace': 'a + b'}
        (self.root / 'calc.py').write_text('def add(a,b):\n    return a - b\n')
        engine = PermissionEngine()
        runtime = AgentRuntime(self.root, P(), Journal(self.root, self.root / 'state'),
                               permission_engine=engine)
        session = runtime.create('patch', '002-python-engineer', max_steps=1, allow_writes=False)
        result = runtime.run(session['id'])
        self.assertEqual(result['status'], 'FAILED')
        self.assertIn('PermissionDenied', result['messages'][-1]['content'])
        self.assertIn('a - b', (self.root / 'calc.py').read_text())

    def test_secure_store_roundtrip_without_plaintext(self):
        store = SecretStore(self.root / 'secrets.json')
        info = store.set('provider:test', 'demo-secret-value')
        self.assertEqual(store.get('provider:test'), 'demo-secret-value')
        self.assertTrue(store.names())
        self.assertNotIn('demo-secret-value', (self.root / 'secrets.json').read_text())
        self.assertTrue(store.delete('provider:test'))
        self.assertIsNone(store.get('provider:test'))
        self.assertIn(info['scheme'], ('dpapi', 'keyring', 'file'))

    def test_capability_registry_and_router(self):
        registry = CapabilityRegistry()
        self.assertEqual(len(registry.list('tool')), 63)
        self.assertEqual(len(registry.list('agent')), 100)
        route = registry.route('python unit test debug')
        self.assertTrue(route['selected'])
        self.assertTrue(any(x['kind'] == 'agent' for x in route['selected']))
        self.assertEqual(registry.get('workspace_tree').kind, 'tool')

    def test_quantization_methods_and_profiles(self):
        methods = method_catalog()['methods']
        self.assertGreaterEqual(len(methods), 14)
        self.assertIn('iq4_xs', {x['id'] for x in methods})
        self.assertIn('gptq', {x['id'] for x in methods})
        estimate = estimate_memory(7.6, 'q4_k_m')
        self.assertGreater(estimate['total_mb'], estimate['weights_mb'])
        profiles = recommend_profiles(7.6, 8151)
        self.assertIsNotNone(profiles['balanced'])
        self.assertIsNotNone(profiles['quality_first'])

    def test_provider_catalog_and_custom_profile(self):
        catalog = ProviderCatalog()
        self.assertGreaterEqual(len(catalog.providers), 40)
        self.assertTrue(catalog.search('ollama'))
        custom = catalog.add_custom({'id': 'my-lab', 'name': 'My Lab',
                                     'base_url': 'http://127.0.0.1:9999/v1',
                                     'protocol': 'openai', 'modalities': ['text']})
        self.assertEqual(custom.id, 'my-lab')
        self.assertIn('my-lab', [x.id for x in catalog.search('my-lab')])
        self.assertIn('status_counts', catalog.status())

    def test_model_team_1500_logical_agents_and_real_dialogue(self):
        journal = Journal(self.root, self.root / 'state')
        team = ModelTeam(self.root, store=TeamStore(self.root / 'team.db'), journal=journal)
        for i in range(15):
            team.add_model(f'm{i}', FakeProvider())
        with self.assertRaises(ValueError):
            team.add_model('overflow', FakeProvider())
        for i in range(15):
            team.register_agents(f'm{i}')
        status = team.status()
        self.assertEqual(status['registered_agents'], 1500)
        self.assertEqual(status['models'], 15)
        result = team.run('Review the repository layout', model_id='m0')
        self.assertEqual(result['state'], 'COMPLETED')
        self.assertEqual(team.status()['completed_tasks'], 1)
        self.assertEqual(team.status()['inference_calls'], 2)
        messages = team.dialogue()['messages']
        self.assertTrue(any(x['kind'] == 'TASK' for x in messages))
        self.assertTrue(any(x['kind'] == 'VERIFIED' for x in messages))
        exported = team.export_dialogue(self.root / 'dialogue.json')
        self.assertEqual(exported['messages'], len(messages))

    def test_parallel_solutions(self):
        journal = Journal(self.root, self.root / 'state')
        team = ModelTeam(self.root, store=TeamStore(self.root / 'team.db'), journal=journal)
        team.add_model('a', FakeProvider('a'))
        team.add_model('b', FakeProvider('b'))
        result = team.run_parallel_solutions('Review files')
        self.assertEqual(result['total'], 2)
        self.assertEqual(result['pass_count'], 2)
        self.assertIsNotNone(result['winner'])

    def test_huggingface_pagination_with_fake_api(self):
        calls = []
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                calls.append(self.path)
                if 'cursor=next' in self.path:
                    body = json.dumps([{'id': 'org/second', 'pipeline_tag': 'text-generation',
                                        'tags': ['license:mit'], 'downloads': 2}]).encode()
                    link = None
                else:
                    body = json.dumps([{'id': 'org/first', 'pipeline_tag': 'text-generation',
                                        'tags': ['license:apache-2.0', 'gguf'], 'downloads': 10,
                                        'safetensors': {'total': 7000000000}}]).encode()
                    link = '<http://127.0.0.1/api/models?cursor=next>; rel="next"'
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                if link:
                    self.send_header('Link', link)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            client = HuggingFaceClient(base_url=f'http://127.0.0.1:{server.server_port}', timeout=5)
            first = client.search('first', limit=1)
            self.assertEqual(first['models'][0]['id'], 'org/first')
            self.assertEqual(first['models'][0]['license'], 'apache-2.0')
            self.assertEqual(first['models'][0]['formats'], ['gguf'])
            self.assertTrue(first['has_more'])
            second = client.search('first', limit=1, cursor=first['next_cursor'])
            self.assertEqual(second['models'][0]['id'], 'org/second')
            self.assertFalse(second['has_more'])
            self.assertEqual(len(calls), 2)
        finally:
            server.shutdown()
            server.server_close()

    def test_model_downloader_resume(self):
        payload = b'0123456789' * 1000
        checksum = hashlib.sha256(payload).hexdigest()
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                range_header = self.headers.get('Range')
                if range_header:
                    start = int(range_header.split('=')[1].split('-')[0])
                    body = payload[start:]
                    self.send_response(206)
                    self.send_header('Content-Range', f'bytes {start}-{len(payload)-1}/{len(payload)}')
                else:
                    body = payload
                    self.send_response(200)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            target = self.root / 'weights.gguf'
            partial = target.with_suffix(target.suffix + '.part')
            partial.write_bytes(payload[:4000])
            downloader = ModelDownloader(self.root)
            result = downloader.download(
                f'http://127.0.0.1:{server.server_port}/weights.gguf', target,
                sha256=checksum, license='MIT', accept_license=True, approve=True,
                allow_http_loopback=True, resume=True)
            self.assertEqual(result['status'], 'PASS')
            self.assertTrue(result['resumed'])
            self.assertEqual(target.read_bytes(), payload)
        finally:
            server.shutdown()
            server.server_close()

    def test_tui_has_new_sections(self):
        for name in ('Capabilities', 'Providers', 'Hugging Face', 'Quantization',
                     'Model Team', 'Team Dialogue', 'Security', 'Activity'):
            self.assertIn(name, SECTIONS)
            headers, rows = data_rows(name, self.root)
            self.assertTrue(headers, name)
            self.assertIsInstance(rows, list, name)

    def test_compatibility_labels(self):
        manager = ModelManager()
        plan = manager.select('llama3.2:3b')
        self.assertIn(plan['compatibility'], ('READY_GPU', 'READY_HYBRID', 'CPU_ONLY',
                                               'NEEDS_DOWNLOAD', 'INSUFFICIENT_MEMORY',
                                               'UNSUPPORTED_BACKEND', 'GATED',
                                               'LICENSE_RESTRICTED', 'UNKNOWN'))


if __name__ == '__main__':
    unittest.main()
