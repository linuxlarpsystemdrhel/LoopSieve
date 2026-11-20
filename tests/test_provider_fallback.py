import json
import tempfile
import unittest
from pathlib import Path

from loopsieve.provider_health import (FallbackController, FallbackProvider, ProviderHealthMonitor,
                                       ProviderSlot, classify_error)
from loopsieve.providers import ProviderError


class OkProvider:
    provider_id = 'fake:ok'
    thread_safe = True

    def __init__(self, value=None):
        self.value = value or {'action': 'tree'}
        self.calls = 0

    def probe(self):
        return {'state': 'READY', 'kind': 'OK', 'installed_models': ['fake:ok']}

    def complete(self, messages, agent):
        self.calls += 1
        return self.value


class BadProvider:
    provider_id = 'fake:bad'
    thread_safe = True

    def __init__(self, kind='RATE_LIMIT'):
        self.kind = kind
        self.calls = 0

    def probe(self):
        return {'state': 'AUTH_REQUIRED', 'kind': 'AUTH', 'reason': 'missing key'}

    def complete(self, messages, agent):
        self.calls += 1
        raise ProviderError('rate limited', kind=self.kind)


class ProviderFallbackTests(unittest.TestCase):
    def test_classification_is_stable(self):
        info = classify_error(ProviderError('missing key', kind='AUTH', retryable=False))
        self.assertEqual(info['state'], 'AUTH_REQUIRED')
        self.assertFalse(info['retryable'])
        info = classify_error(ProviderError('busy', kind='RATE_LIMIT'))
        self.assertEqual(info['state'], 'RATE_LIMIT')
        self.assertTrue(info['retryable'])

    def test_health_monitor_persists_and_probes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'health.json'
            monitor = ProviderHealthMonitor(path)
            value = monitor.probe(OkProvider())
            self.assertEqual(value['state'], 'READY')
            monitor.record_failure('fake:bad', ProviderError('timeout', kind='TIMEOUT'))
            self.assertEqual(monitor.health('fake:bad')['state'], 'TIMEOUT')
            reloaded = ProviderHealthMonitor(path)
            self.assertEqual(reloaded.health('fake:bad')['state'], 'TIMEOUT')
            self.assertEqual(reloaded.status()['states']['fake:ok'], 'READY')

    def test_fallback_switches_and_records_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'fallback.json'
            bad = BadProvider()
            ok = OkProvider()
            chain = FallbackProvider([ProviderSlot(bad, 'primary'), ProviderSlot(ok, 'fallback')],
                                     state_path=path)
            self.assertEqual(chain.complete([{'role': 'user', 'content': 'x'}], {'name': 'x'}), {'action': 'tree'})
            self.assertEqual(chain.active_index, 1)
            self.assertEqual(chain.switches, 1)
            self.assertEqual(bad.calls, 1)
            self.assertEqual(ok.calls, 1)
            self.assertEqual(chain.status()['providers'][0]['health']['state'], 'RATE_LIMIT')
            reloaded = FallbackProvider([ProviderSlot(bad, 'primary'), ProviderSlot(ok, 'fallback')],
                                        state_path=path)
            self.assertEqual(reloaded.active_index, 1)

    def test_disabled_fallback_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            chain = FallbackProvider([ProviderSlot(BadProvider(), 'primary'), ProviderSlot(OkProvider(), 'fallback')],
                                     state_path=Path(tmp) / 'f.json', enabled=False)
            with self.assertRaises(ProviderError):
                chain.complete([{'role': 'user', 'content': 'x'}], {'name': 'x'})
            controller = FallbackController(chain)
            self.assertTrue(controller.enable()['enabled'])
            self.assertEqual(chain.complete([], {'name': 'x'}), {'action': 'tree'})


if __name__ == '__main__':
    unittest.main()
