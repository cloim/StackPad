"""Read CLI usage without refreshing or modifying credentials."""
import copy
import json
import math
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

_cache = {}
_cache_lock = threading.Lock()
CACHE_SECONDS = 60
MIN_REFRESH_INTERVAL = 10
API_TIMEOUT_SECONDS = 4


def _utc(value=None):
    if value is None:
        return datetime.now(timezone.utc).isoformat()
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc).isoformat()
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return parsed.replace(tzinfo=timezone.utc).isoformat() if parsed.tzinfo is None else parsed.astimezone(timezone.utc).isoformat()


def _result(provider, name, status='ok', message=None):
    return dict(id=provider, name=name, status=status, plan=None, windows=[], message=message, fetched_at=_utc())


def _window(key, label, percent, resets_at):
    percent = float(percent)
    if not math.isfinite(percent):
        raise ValueError('invalid utilization')
    return dict(key=key, label=label, used_percent=max(0.0, min(100.0, percent)), resets_at=_utc(resets_at) if resets_at is not None else None)


def _home(home):
    return Path(home or os.environ.get('STACKPAD_USAGE_HOME') or Path.home())


def _fetch(provider, name, home, filename, read_token, url, headers, map_response):
    result = _result(provider, name)
    try:
        credentials = json.loads((_home(home) / filename).read_text(encoding='utf-8'))
        token, extra_headers, expires_at, plan = read_token(credentials)
        if not token or (expires_at is not None and float(expires_at) <= time.time() * 1000):
            return _result(provider, name, 'login_required', 'CLI 사용 시 갱신' if token else 'CLI 로그인 필요')
        request = Request(url, headers={**headers, **extra_headers, 'Authorization': 'Bearer ' + token})
        with urlopen(request, timeout=API_TIMEOUT_SECONDS) as response:
            data = json.load(response)
        result['plan'], result['windows'] = map_response(data, plan)
    except FileNotFoundError:
        return _result(provider, name, 'login_required', 'CLI 로그인 필요')
    except HTTPError as error:
        if error.code in (401, 403):
            return _result(provider, name, 'login_required', 'CLI 사용 시 갱신')
        result.update(status='error', message='사용량 조회 실패')
    except Exception:
        # Never expose credentials, provider response bodies or exception text.
        result.update(status='error', message='사용량 조회 실패')
    result['fetched_at'] = _utc()
    return result


def collect_claude_usage(home=None):
    def credentials(data):
        oauth = data.get('claudeAiOauth', {})
        return oauth.get('accessToken'), {}, oauth.get('expiresAt'), oauth.get('subscriptionType')

    def windows(data, plan):
        return plan, [_window(key, label, data[source]['utilization'], data[source].get('resets_at'))
                      for source, key, label in [('five_hour', 'five_hour', '5h'), ('seven_day', 'weekly', 'w')]]

    return _fetch('claude', 'Claude', home, '.claude/.credentials.json', credentials,
                  'https://api.anthropic.com/api/oauth/usage', {'anthropic-beta': 'oauth-2025-04-20'}, windows)


def collect_codex_usage(home=None):
    def credentials(data):
        tokens = data.get('tokens', {})
        account_id = tokens.get('account_id')
        return tokens.get('access_token') if account_id else None, {'ChatGPT-Account-Id': account_id or ''}, tokens.get('expiresAt'), None

    def windows(data, plan):
        result = []
        for source in ('primary_window', 'secondary_window'):
            window = data['rate_limit'].get(source)
            if window is None:
                continue
            seconds = window['limit_window_seconds']
            key, label = {18000: ('five_hour', '5h'), 604800: ('weekly', 'w')}.get(seconds, (source, f'{seconds // 3600}h'))
            result.append(_window(key, label, window['used_percent'], window.get('reset_at')))
        return data.get('plan_type'), result

    return _fetch('codex', 'Codex', home, '.codex/auth.json', credentials,
                  'https://chatgpt.com/backend-api/wham/usage', {'User-Agent': 'codex-cli'}, windows)


def collect_antigravity_usage(home=None):
    providers = [_result('antigravity-gemini', 'AG Gemini'), _result('antigravity-3p', 'AG Claude/GPT')]
    try:
        snapshot = json.loads((_home(home) / '.gemini/antigravity-cli/usage-snapshot.json').read_text(encoding='utf-8'))
        captured_at = _utc(snapshot['captured_at'])
        elapsed = datetime.now(timezone.utc).timestamp() - datetime.fromisoformat(captured_at).timestamp()
        quota = snapshot['quota']
        for provider, prefix in zip(providers, ('gemini', '3p')):
            for suffix, key, label in (('5h', 'five_hour', '5h'), ('weekly', 'weekly', 'w')):
                bucket = quota.get(f'{prefix}-{suffix}')
                if not isinstance(bucket, dict) or 'remaining_fraction' not in bucket:
                    continue
                reset = next((bucket[field] for field in ('reset_time', 'resetTime', 'reset_at') if bucket.get(field) is not None), None)
                window = _window(key, label, (1 - float(bucket['remaining_fraction'])) * 100, reset)
                if window['resets_at'] and datetime.fromisoformat(window['resets_at']).timestamp() <= time.time():
                    window['used_percent'] = 0.0
                provider['windows'].append(window)
            if not provider['windows']:
                provider.update(status='unavailable', message='Antigravity 실행 후 표시')
            if elapsed > 600:
                provider['stale_minutes'] = int(elapsed // 60)
    except FileNotFoundError:
        for provider in providers:
            provider.update(status='unavailable', message='Antigravity 실행 후 표시')
    except Exception:
        for provider in providers:
            provider.update(status='error', message='사용량 조회 실패', windows=[])
    return providers


COLLECTORS = {'claude': collect_claude_usage, 'codex': collect_codex_usage, 'antigravity': collect_antigravity_usage}


def collect_usage(home=None, refresh=False, enabled=None):
    """Return isolated snapshots of the enabled CLIs; concurrent requests share one collection."""
    home = _home(home).resolve()
    names = tuple(name for name in COLLECTORS if enabled is None or name in enabled)
    if not names:
        return []
    key = (home, names)
    # perf_counter: Windows monotonic ticks every 15 ms, which made a refresh look like a concurrent request.
    requested_at = time.perf_counter()
    with _cache_lock:
        cached = _cache.get(key)
        if cached and ((not refresh and requested_at - cached[0] < CACHE_SECONDS) or (refresh and requested_at - cached[0] < MIN_REFRESH_INTERVAL) or cached[0] >= requested_at):
            return copy.deepcopy(cached[1])
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(lambda name: COLLECTORS[name](home), names))
            providers = [provider for result in results for provider in (result if isinstance(result, list) else [result])]
        _cache[key] = (time.perf_counter(), providers)
        return copy.deepcopy(providers)
