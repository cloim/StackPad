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
        usage._agy_last_attempt.clear()
        agy_patcher = patch.object(usage, '_find_agy', return_value=None)
        agy_patcher.start()
        self.addCleanup(agy_patcher.stop)

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
            key = (tuple((name, path) for name, path in usage._dirs_for(self.home, None).items()), tuple(usage.COLLECTORS))
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

    def make_home(self, name, claude=None, codex=None):
        home = self.home / name
        for rel, data in (('.claude/.credentials.json', {'claudeAiOauth': {'accessToken': claude, 'expiresAt': (time.time() + 3600) * 1000}} if claude else None),
                          ('.codex/auth.json', {'tokens': {'access_token': codex, 'account_id': 'test-account'}} if codex else None)):
            if data:
                (home / rel).parent.mkdir(parents=True, exist_ok=True)
                (home / rel).write_text(json.dumps(data), encoding='utf-8')
        return home

    def tokens_seen(self):
        seen = {}

        def respond(request, timeout, context=None):
            seen['claude' if 'anthropic.com' in request.full_url else 'codex'] = request.get_header('Authorization')
            data = {'five_hour': {'utilization': 1}, 'seven_day': {'utilization': 2}} if 'anthropic.com' in request.full_url else {'rate_limit': {}}
            return io.BytesIO(json.dumps(data).encode())
        return seen, respond

    def test_dirs_per_cli_and_priority(self):
        default = self.make_home('default', claude='claude-default', codex='codex-default')
        codex_home = self.make_home('codexhome', codex='codex-custom')
        seen, respond = self.tokens_seen()
        with patch.object(usage.Path, 'home', return_value=default), patch.dict('os.environ', {}, clear=False) as env,                 patch.object(usage, 'urlopen', side_effect=respond):
            env.pop('STACKPAD_USAGE_HOME', None)
            usage.collect_usage(dirs={'codex': str(codex_home / '.codex')})
            self.assertEqual(seen, {'claude': 'Bearer claude-default', 'codex': 'Bearer codex-custom'})
            usage._cache.clear()
            seen.clear()
            env['STACKPAD_USAGE_HOME'] = str(default)
            usage.collect_usage(dirs={'codex': str(codex_home / '.codex')})
            self.assertEqual(seen['codex'], 'Bearer codex-default')

    def test_dirs_invalid_values_ignored(self):
        default = self.make_home('default', claude='claude-default', codex='codex-default')
        seen, respond = self.tokens_seen()
        for bad in ('text', ['codex'], None, {'unknown': str(default / '.codex')}, {'codex': 5}, {'codex': ''}, {'codex': '   '}, {'claude': None}):
            usage._cache.clear()
            seen.clear()
            with patch.object(usage.Path, 'home', return_value=default), patch.dict('os.environ', {}, clear=False) as env,                     patch.object(usage, 'urlopen', side_effect=respond):
                env.pop('STACKPAD_USAGE_HOME', None)
                providers = usage.collect_usage(dirs=bad)
            self.assertEqual(seen, {'claude': 'Bearer claude-default', 'codex': 'Bearer codex-default'}, bad)
            self.assertEqual(len(providers), 4)

    def test_dirs_expand_variables_and_user(self):
        custom = self.make_home('custom', codex='codex-custom')
        default = self.make_home('default')
        for value, env in (('%TEST_USAGE_HOME%/.codex', {'TEST_USAGE_HOME': str(custom)}), ('$TEST_USAGE_HOME/.codex', {'TEST_USAGE_HOME': str(custom)}),
                           ('~/custom/.codex', {'HOME': str(self.home), 'USERPROFILE': str(self.home)})):
            usage._cache.clear()
            seen, respond = self.tokens_seen()
            with patch.object(usage.Path, 'home', return_value=default), patch.dict('os.environ', env),                     patch.object(usage, 'urlopen', side_effect=respond):
                os_env = __import__('os').environ
                os_env.pop('STACKPAD_USAGE_HOME', None)
                usage.collect_usage(dirs={'codex': value}, enabled=['codex'])
            self.assertEqual(seen.get('codex'), 'Bearer codex-custom', value)

    def test_different_dirs_do_not_share_cache(self):
        first = self.make_home('first', codex='codex-first')
        second = self.make_home('second', codex='codex-second')
        seen, respond = self.tokens_seen()
        with patch.object(usage, 'urlopen', side_effect=respond) as mock:
            usage.collect_usage(dirs={'codex': str(first / '.codex')}, enabled=['codex'])
            usage.collect_usage(dirs={'codex': str(second / '.codex')}, enabled=['codex'])
            self.assertEqual((mock.call_count, seen['codex']), (2, 'Bearer codex-second'))
            usage.collect_usage(dirs={'codex': str(second / '.codex')}, enabled=['codex'])
            self.assertEqual(mock.call_count, 2)

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


    def test_antigravity_auto_refresh_when_missing(self):
        fake_payload = {
            'command': {
                'name': 'usage',
                'data': {
                    'groups': [
                        {
                            'name': 'Gemini Models',
                            'buckets': [
                                {'id': 'gemini-5h', 'remaining_fraction': 0.8, 'reset_time': '2026-11-20T00:00:00Z'},
                                {'id': 'gemini-weekly', 'remaining_fraction': 0.5, 'reset_time': '2026-11-25T00:00:00Z'},
                            ]
                        },
                        {
                            'name': 'Claude and GPT models',
                            'buckets': [
                                {'id': '3p-5h', 'remaining_fraction': 1.0, 'reset_time': '2026-11-20T00:00:00Z'},
                                {'id': '3p-weekly', 'remaining_fraction': 1.0, 'reset_time': '2026-11-25T00:00:00Z'},
                            ]
                        }
                    ]
                }
            }
        }
        mock_proc = unittest.mock.Mock(returncode=0, stdout=json.dumps(fake_payload))
        with patch.object(usage, '_find_agy', return_value='/path/to/agy'), \
             patch('subprocess.run', return_value=mock_proc) as mock_run:
            providers = usage.collect_antigravity_usage(self.home)
            mock_run.assert_called_once()
            self.assertEqual(len(providers), 2)
            gemini, third_party = providers
            self.assertEqual(gemini['status'], 'ok')
            self.assertAlmostEqual(gemini['windows'][0]['used_percent'], 20.0, places=2)
            self.assertEqual(third_party['status'], 'ok')
            snapshot_path = self.home / '.gemini/antigravity-cli/usage-snapshot.json'
            self.assertTrue(snapshot_path.is_file())

    def test_antigravity_auto_refresh_when_stale_or_forced(self):
        self.snapshot(age=15)
        fake_payload = {
            'command': {
                'name': 'usage',
                'data': {
                    'groups': [
                        {
                            'name': 'Gemini Models',
                            'buckets': [
                                {'id': 'gemini-5h', 'remaining_fraction': 0.9, 'reset_time': '2026-11-20T00:00:00Z'},
                                {'id': 'gemini-weekly', 'remaining_fraction': 0.7, 'reset_time': '2026-11-25T00:00:00Z'},
                            ]
                        }
                    ]
                }
            }
        }
        mock_proc = unittest.mock.Mock(returncode=0, stdout=json.dumps(fake_payload))
        with patch.object(usage, '_find_agy', return_value='/path/to/agy'), \
             patch('subprocess.run', return_value=mock_proc) as mock_run:
            providers = usage.collect_antigravity_usage(self.home, refresh=True)
            mock_run.assert_called_once()
            gemini = providers[0]
            self.assertEqual(gemini['status'], 'ok')
            self.assertAlmostEqual(gemini['windows'][0]['used_percent'], 10.0, places=2)


if __name__ == '__main__':
    unittest.main()
