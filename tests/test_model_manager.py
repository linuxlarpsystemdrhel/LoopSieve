import hashlib
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from loopsieve.hardware import HardwareProfile, GpuInfo, detect_hardware
from loopsieve.model_manager import ModelDownloader, ModelManager, ModelSpec, fit_status, load_catalog
from loopsieve.quantization import estimate_memory, recommend_quantization, validate_quantization_request


class ModelManagerTests(unittest.TestCase):
    def test_hardware_has_explicit_unknowns(self):
        value = detect_hardware().as_dict()
        self.assertIn('ram_total_mb', value)
        self.assertIn('gpus', value)
        self.assertIsInstance(value['gpus'], list)

    def test_memory_estimate_is_transparent_and_positive(self):
        value = estimate_memory(7.0, 'q4_k_m', context_tokens=4096)
        self.assertGreater(value['total_mb'], value['weights_mb'])
        self.assertEqual(value['kind'], 'ESTIMATE_NOT_MEASUREMENT')
        with self.assertRaises(ValueError):
            estimate_memory(7.0, 'not-a-quant')

    def test_fit_labels_are_explicit(self):
        hw = HardwareProfile(os_name='Test', architecture='x86_64', cpu='test', cpu_count=4,
                             ram_total_mb=8192, ram_free_mb=4096,
                             gpus=(GpuInfo('RTX', vram_total_mb=4096, vram_free_mb=3500),))
        model = ModelSpec(id='tiny', name='Tiny', params_b=0.5, context_tokens=4096)
        value = fit_status(model, hw, installed=True, quantization='q4_k_m')
        self.assertIn(value['status'], ('READY', 'HYBRID', 'CPU ONLY', 'INSUFFICIENT MEMORY'))
        self.assertIn('estimate', value)

    def test_manager_select_auto_and_memory(self):
        manager = ModelManager()
        selected = manager.select('llama3.2:3b', 'q4_k_m')
        self.assertEqual(selected['selected'], 'llama3.2:3b')
        self.assertIn('fit', selected)
        auto = manager.auto('fix python coding bug')
        self.assertIn('selected', auto)
        memory = manager.memory('llama3.2:3b')
        self.assertIn('estimate', memory)

    def test_quantization_validation_does_not_claim_conversion(self):
        value = validate_quantization_request(7.0, 'q5_k_m', backend='ollama')
        self.assertEqual(value['status'], 'VALIDATED_METADATA')
        self.assertEqual(value['conversion'], 'NOT_PERFORMED')
        self.assertEqual(validate_quantization_request(7.0, 'q4_k_m', backend='unknown')['status'],
                         'UNSUPPORTED_BACKEND')

    def test_downloader_requires_checksum_and_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            downloader = ModelDownloader(tmp)
            with self.assertRaises(PermissionError):
                downloader.download('https://example.invalid/x.gguf', Path(tmp) / 'x.gguf', sha256='a' * 64,
                                    license='MIT', accept_license=True, approve=False)
            with self.assertRaises(ValueError):
                downloader.download('https://example.invalid/x.gguf', Path(tmp) / 'x.gguf', license='MIT',
                                    accept_license=True, approve=True)

    def test_loopback_download_verifies_checksum(self):
        payload = b'fake gguf weights for a checksum test'
        checksum = hashlib.sha256(payload).hexdigest()

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                target = Path(tmp) / 'model.gguf'
                downloader = ModelDownloader(tmp)
                value = downloader.download(
                    f'http://127.0.0.1:{server.server_port}/model.gguf', target,
                    sha256=checksum, license='MIT', accept_license=True, approve=True,
                    allow_http_loopback=True)
                self.assertEqual(value['status'], 'PASS')
                self.assertEqual(target.read_bytes(), payload)
                self.assertEqual(downloader.verify(target, checksum)['status'], 'PASS')
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
