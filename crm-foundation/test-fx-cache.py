"""Isolated tests for the daily USD/CNY cache and failure status."""
import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch


SOURCE = Path(__file__).with_name('order-report.py')
spec = importlib.util.spec_from_file_location('order_report_fx_under_test', SOURCE)
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode('utf-8')

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


class FxCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        report.OUT = Path(self.temp.name)
        self.moment = datetime(2026, 10, 12, 0, 0, tzinfo=timezone.utc)
        report.now = lambda: self.moment

    def tearDown(self):
        self.temp.cleanup()

    def write_cache(self, *, next_update, attempt, expired=False, last_error=None):
        report.atomic(report.OUT / 'fx-cache.json', {
            'rate': '6.7',
            'publishedAt': (self.moment - timedelta(days=1)).isoformat(),
            'publishedUnix': int(self.moment.timestamp()) - 86400,
            'sourceDate': '2026-10-11',
            'nextUpdateUnix': next_update,
            'fetchedAt': self.moment.isoformat(),
            'attemptUnix': attempt,
            'provider': 'https://www.exchangerate-api.com',
            'endpoint': report.ENDPOINT,
            'expired': expired,
            'lastError': last_error,
        })

    def test_due_fetch_failure_persists_expired_marker_and_keeps_last_rate(self):
        now_unix = self.moment.timestamp()
        self.write_cache(next_update=now_unix - 10, attempt=now_unix - 4000)

        with patch.object(report.urllib.request, 'urlopen', side_effect=TimeoutError()):
            result = report.get_fx()

        cached = json.loads((report.OUT / 'fx-cache.json').read_text(encoding='utf-8'))
        self.assertEqual(result['rate'], '6.7')
        self.assertTrue(result['expired'])
        self.assertIsNotNone(result['error'])
        self.assertTrue(cached['expired'])
        self.assertEqual(cached['lastError'], result['error'])

    def test_successful_retry_clears_expired_marker_and_saves_new_rate(self):
        now_unix = self.moment.timestamp()
        self.write_cache(next_update=now_unix - 10, attempt=now_unix - 4000,
                         expired=True, last_error='TimeoutError: FX source unavailable')
        self.moment += timedelta(seconds=3601)
        now_unix = self.moment.timestamp()
        payload = {
            'result': 'success',
            'base_code': 'USD',
            'rates': {'CNY': 7.123456},
            'time_last_update_unix': int(now_unix) - 60,
            'time_next_update_unix': int(now_unix) + 86400,
        }

        with patch.object(report.urllib.request, 'urlopen', return_value=FakeResponse(payload)):
            result = report.get_fx()

        cached = json.loads((report.OUT / 'fx-cache.json').read_text(encoding='utf-8'))
        self.assertEqual(result['rate'], '7.123456')
        self.assertFalse(result['expired'])
        self.assertIsNone(result['error'])
        self.assertFalse(cached['expired'])
        self.assertIsNone(cached['lastError'])

    def test_old_published_day_without_failed_refresh_is_not_marked_expired(self):
        now_unix = self.moment.timestamp()
        self.write_cache(next_update=now_unix + 3600, attempt=now_unix - 60)

        with patch.object(report.urllib.request, 'urlopen') as fetch:
            result = report.get_fx()

        fetch.assert_not_called()
        self.assertFalse(result['currentDay'])
        self.assertFalse(result['expired'])
        self.assertIsNone(result['error'])

    def test_page_has_visible_expired_rate_message(self):
        page = SOURCE.with_suffix('.html').read_text(encoding='utf-8')
        self.assertIn('更新失败 · 旧汇率已过期（继续显示上次值）', page)


if __name__ == '__main__':
    unittest.main(verbosity=2)
