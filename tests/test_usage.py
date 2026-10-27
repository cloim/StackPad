import io
import json
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import usage


class UsageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        usage._cache.clear()
        usage._last_good.clear()

    def credentials(self, expired=False):
        for name, data in [('.claude/.credentials.json', {'claudeAiOauth': {
            'accessToken': 'test-claude', 'expiresAt': (time.time() + (-10 if expired else 3600)) * 1000,
            'subscriptionType': 'max'}}), ('.codex/auth.json', {'tokens': {
                'access_token': 'test-codex', 'account_id': 'test-account'}})]:
            path = self.home / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data), encoding='utf-8')

    def response(self, request, timeout, context=None):
        self.assertEqual(timeout, 4)
        if 'anthropic.com' in request.full_url:
            self.assertEqual(request.get_header('Authorization'), 'Bearer test-claude')
            self.assertEqual(request.get_header('Anthropic-beta'), 'oauth-2025-04-20')
            data = {'five_hour': {'utilization': 27.5, 'resets_at': '2026-10-05T04:00:00Z'},
                    'seven_day': {'utilization': 81, 'resets_at': None}}
        else:
            self.assertEqual(request.get_header('Chatgpt-account-id'), 'test-account')
            self.assertEqual(request.get_header('User-agent'), 'codex-cli')
            data = {'plan_type': 'pro', 'rate_limit': {
                'primary_window': {'used_percent': 20, 'limit_window_seconds': 18000, 'reset_at': 1791172800},
                'secondary_window': {'used_percent': 95, 'limit_window_seconds': 604800, 'reset_at': None}}}
        return io.BytesIO(json.dumps(data).encode())

    def test_mapping(self):
        self.credentials()
        with patch.object(usage, 'urlopen', side_effect=self.response) as mock:
            providers = usage.collect_usage(self.home)
        self.assertEqual(mock.call_count, 2)
        claude, codex, gemini, third_party = providers
        self.assertEqual((claude['status'], claude['plan']), ('ok', 'max'))
        self.assertEqual(claude['windows'][0]['used_percent'], 27.5)
        self.assertEqual(claude['windows'][0]['resets_at'], '2026-10-05T04:00:00+00:00')
        self.assertEqual((codex['status'], codex['plan']), ('ok', 'pro'))
        for provider in (claude, codex):
            self.assertEqual([w['key'] for w in provider['windows']], ['five_hour', 'weekly'])
            self.assertEqual([w['label'] for w in provider['windows']], ['5h', 'w'])
        self.assertEqual(codex['windows'][0]['resets_at'], '2026-10-05T04:00:00+00:00')
        self.assertEqual([p['id'] for p in providers], ['claude', 'codex', 'antigravity-gemini', 'antigravity-3p'])
        self.assertEqual([gemini['status'], third_party['status']], ['unavailable'] * 2)

    def test_missing_and_expired(self):
        with patch.object(usage, 'urlopen') as mock:
            providers = usage.collect_usage(self.home)
            self.assertEqual([p['status'] for p in providers[:2]], ['login_required'] * 2)
            self.credentials(expired=True)
            result = usage.collect_claude_usage(self.home)
            self.assertEqual(result['status'], 'login_required')
            self.assertEqual(result['message'], 'CLI 사용 시 갱신')
            codex_path = self.home / '.codex/auth.json'
            credentials = json.loads(codex_path.read_text(encoding='utf-8'))
            credentials['tokens']['expiresAt'] = (time.time() - 10) * 1000
            codex_path.write_text(json.dumps(credentials), encoding='utf-8')
            self.assertEqual(usage.collect_codex_usage(self.home)['message'], 'CLI 사용 시 갱신')
            mock.assert_not_called()

    def test_http_auth_and_error(self):
        self.credentials()
        for code in (401, 403, 500):
            with self.subTest(code=code), patch.object(usage, 'urlopen', side_effect=HTTPError('https://test', code, 'private response', {}, None)):
                for collect in (usage.collect_claude_usage, usage.collect_codex_usage):
                    result = collect(self.home)
                    self.assertEqual(result['status'], 'error' if code == 500 else 'login_required')
                    self.assertEqual(result['message'], '사용량 조회 실패' if code == 500 else 'CLI 사용 시 갱신')
                    self.assertNotIn('private', json.dumps(result))

    def test_cache_refresh_expiry_and_isolation(self):
        self.credentials()
        with patch.object(usage, 'urlopen', side_effect=self.response) as mock:
            first = usage.collect_usage(self.home)
            first[0]['windows'].clear()
            self.assertEqual(len(usage.collect_usage(self.home)[0]['windows']), 2)
            self.assertEqual(mock.call_count, 2)
            # Immediate refresh is throttled (under 10s) and returns cached results.
            usage.collect_usage(self.home, refresh=True)
            self.assertEqual(mock.call_count, 2)
            # Refresh after throttle interval fetches fresh results.
            key = (self.home.resolve(), tuple(usage.COLLECTORS))
            stamp, providers = usage._cache[key]
            usage._cache[key] = (stamp - 11, providers)
            usage.collect_usage(self.home, refresh=True)
            self.assertEqual(mock.call_count, 4)
            # Expiry after CACHE_SECONDS re-fetches even without refresh.
            stamp, providers = usage._cache[key]
            usage._cache[key] = (stamp - 61, providers)
            usage.collect_usage(self.home)
            self.assertEqual(mock.call_count, 6)

    def test_failed_refresh_keeps_last_good_numbers(self):
        self.credentials()
        with patch.object(usage, 'urlopen', side_effect=self.response):
            first = usage.collect_usage(self.home, enabled=['claude', 'codex'])
        throttled = HTTPError('https://test', 429, 'Too Many Requests', {}, None)
        for key in list(usage._cache):
            stamp, providers = usage._cache[key]
            usage._cache[key] = (stamp - 11, providers)
        with patch.object(usage, 'urlopen', side_effect=throttled):
            second = usage.collect_usage(self.home, refresh=True, enabled=['claude', 'codex'])
        self.assertEqual(second, first)
        # An answer older than ten minutes is marked so the bar and widget show its age.
        for value in usage._last_good.values():
            value['fetched_at'] = (datetime.now(timezone.utc) - timedelta(minutes=25)).isoformat()
        for key in list(usage._cache):
            stamp, providers = usage._cache[key]
            usage._cache[key] = (stamp - 11, providers)
        with patch.object(usage, 'urlopen', side_effect=throttled):
            third = usage.collect_usage(self.home, refresh=True, enabled=['claude', 'codex'])
        self.assertEqual([provider['status'] for provider in third], ['ok', 'ok'])
        self.assertEqual([provider['stale_minutes'] for provider in third], [25, 25])

    def test_disabled_providers_are_not_read(self):
        self.credentials()
        with patch.object(usage, 'urlopen', side_effect=self.response) as mock:
            self.assertEqual(usage.collect_usage(self.home, enabled=[]), [])
            self.assertEqual(mock.call_count, 0)
            self.assertEqual([p['id'] for p in usage.collect_usage(self.home, enabled=['codex'])], ['codex'])
            self.assertEqual(mock.call_count, 1)

    def test_concurrent_requests_and_home_environment(self):
        self.credentials()
        with patch.object(usage, 'urlopen', side_effect=self.response) as mock, patch.dict('os.environ', {'STACKPAD_USAGE_HOME': str(self.home)}):
            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(lambda _: usage.collect_usage(), range(8)))
            self.assertEqual(mock.call_count, 2)
            self.assertTrue(all(result[0]['status'] == 'ok' for result in results))

    def snapshot(self, age=0):
        now = datetime.now(timezone.utc)
        data = {'captured_at': (now - timedelta(minutes=age)).isoformat(), 'quota': {
            'gemini-5h': {'remaining_fraction': 0.75, 'reset_time': (now + timedelta(hours=1)).isoformat()},
            'gemini-weekly': {'remaining_fraction': 0.2, 'resetTime': (now + timedelta(days=3)).isoformat()},
            '3p-5h': {'remaining_fraction': 0.4, 'reset_at': (now - timedelta(seconds=1)).timestamp()},
            '3p-weekly': {'remaining_fraction': 0.3}}}
        path = self.home / '.gemini/antigravity-cli/usage-snapshot.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding='utf-8')

    def test_antigravity_mapping_and_past_reset(self):
        self.snapshot()
        gemini, third_party = usage.collect_antigravity_usage(self.home)
        self.assertEqual((gemini['name'], third_party['name']), ('AG Gemini', 'AG Claude/GPT'))
        self.assertEqual([w['used_percent'] for w in gemini['windows']], [25, 80])
        self.assertEqual([w['used_percent'] for w in third_party['windows']], [0, 70])
        for provider in (gemini, third_party):
            self.assertEqual(provider['status'], 'ok')
            self.assertEqual([w['key'] for w in provider['windows']], ['five_hour', 'weekly'])
            self.assertNotIn('stale_minutes', provider)
        self.assertIsNone(third_party['windows'][1]['resets_at'])

    def test_antigravity_missing_and_stale(self):
        for provider in usage.collect_antigravity_usage(self.home):
            self.assertEqual(provider['status'], 'unavailable')
            self.assertEqual(provider['message'], 'Antigravity 실행 후 표시')
        self.snapshot(age=75)
        for provider in usage.collect_antigravity_usage(self.home):
            self.assertEqual(provider['status'], 'ok')
            self.assertEqual(provider['stale_minutes'], 75)

    def test_login_message_without_credentials(self):
        with patch.object(usage, 'urlopen') as mock:
            for collect in (usage.collect_claude_usage, usage.collect_codex_usage):
                self.assertEqual(collect(self.home)['message'], 'CLI 로그인 필요')
            mock.assert_not_called()


if __name__ == '__main__':
    unittest.main()
