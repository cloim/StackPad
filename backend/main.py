import argparse
import contextlib
import html
import json
import logging
import os
import secrets
import shutil
import sys
import threading
import time
from collections import defaultdict, deque
from typing import Literal
from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from urllib.parse import urlencode
import httpx
from pydantic import BaseModel, Field

from engine import AnyServiceInput, Engine, vscode_path
from remote import RemoteSpec, ssh_hosts
import recommend
from usage import collect_usage
from groups import GroupInput, PadInput
from padsets import PadsetInput
from folder_picker import select_folder
from storage_location import StorageLocation, resolve_data_dir
from session_store import SessionStore, SESSION_TTL, DEVICE_TTL
from google_auth import GoogleAuth, CALLBACK_PATH, FLOW_TTL
import tailscale
from widget_tokens import WidgetTokens
from i18n import request_lang, translate, translate_payload


# Keep in step with package.json; tests/test_version.py checks it.
VERSION = '1.0.1'


def create_app(data_dir, web_dir, desktop_exe=None, location_file=None, control_token=None):
    engine = Engine(data_dir, desktop_exe)
    sessions = SessionStore(data_dir)
    google = GoogleAuth(engine)
    widget_tokens = WidgetTokens(lambda: engine.data_dir)
    storage_location = StorageLocation(engine, sessions, location_file or Path(data_dir) / 'storage-location.json')
    engine.bootstrap_dir = storage_location.pointer.parent
    attempts = defaultdict(deque)
    SESSION_COOKIE, STATE_COOKIE = 'stackpad_session', 'stackpad_oauth'
    auth_lock = threading.RLock()

    @contextlib.asynccontextmanager
    async def lifespan(app):
        engine.monitor.start()
        engine.remote_monitor.start()
        def boot():
            grouped = {sid for group in engine.config.get('groups', []) for sid in group['member_ids']}
            for group in list(engine.config.get('groups', [])):
                if group['autostart']:
                    try:
                        engine.group_action(group['id'], 'start', skip_remote=True)
                    except Exception as error:
                        logging.error('Group startup failed: %s', error)
            for service in list(engine.config['services']):
                if service['id'] not in grouped and service['autostart'] and not engine.is_remote_service(service) and not engine.owned(service):
                    try:
                        engine.start(service['id'])
                    except Exception as error:
                        with engine.lock:
                            service['error'] = str(error)
                            engine.save()
        threading.Thread(target=boot, daemon=True).start()
        yield
        engine.closed.set()

    app = FastAPI(title='StackPad', lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.engine = engine
    app.state.storage_location = storage_location
    app.state.sessions = sessions
    app.state.google = google

    @app.middleware('http')
    async def guards(request, call_next):
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            origin = request.headers.get('origin', '')
            expected = f"{request.url.scheme}://{request.headers.get('host', '')}"
            # The Android app sends requests natively without Origin; a custom header cannot be added cross-site without a CORS preflight.
            native_app = not origin and request.headers.get('x-stackpad-client') == 'android'
            # The desktop tray proves itself with the token the engine wrote into the user's own folder.
            desktop_tray = bool(control_token) and secrets.compare_digest(request.headers.get('x-stackpad-control', ''), control_token)
            if origin != expected and not native_app and not desktop_tray:
                return JSONResponse({'detail': translate('같은 앱 화면에서 요청해 주세요.', request_lang(request.headers))}, status_code=403)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
        response.headers['Cache-Control'] = 'no-store' if request.url.path.startswith('/api') else 'no-cache'
        lang = request_lang(request.headers)
        if lang != 'ko' and response.headers.get('content-type', '').startswith('application/json'):
            # Messages are written in Korean; English clients get them translated without touching user data.
            body = b''.join([chunk async for chunk in response.body_iterator])
            headers = {key: value for key, value in response.headers.items() if key.lower() not in ('content-length', 'content-type')}
            return JSONResponse(translate_payload(json.loads(body), lang), status_code=response.status_code, headers=headers)
        return response

    for exception_type, status_code in ((ValueError, 409), (KeyError, 404), (RuntimeError, 500)):
        async def handler(request, error, code=status_code):
            return JSONResponse({'detail': str(error).strip("'")}, status_code=code)
        app.add_exception_handler(exception_type, handler)

    def current_session(request):
        return sessions.get(request.cookies.get(SESSION_COOKIE))

    def authenticated(request: Request):
        record = current_session(request)
        if record:
            return record
        raise HTTPException(401, '로그인해 주세요.')

    def is_local(request):
        # Tailscale keeps the original Host and adds X-Forwarded-For, so proxied requests never pass as this PC.
        return (request.client.host in ('127.0.0.1', '::1') and request.url.hostname in ('localhost', '127.0.0.1', '::1')
                and not request.headers.get('x-forwarded-for') and not tailscale.same_origin(google.external_url, request.url.scheme, request.headers.get('host')))

    def local_only(request: Request):
        if not is_local(request):
            raise HTTPException(403, 'StackPad가 실행 중인 PC에서 설정해 주세요.')

    def setup_access(request: Request):
        # Before the owner signs in, this PC may configure sign-in without a session.
        local_only(request)
        if google.owner and not current_session(request):
            raise HTTPException(401, '로그인해 주세요.')

    def limit(request, name, per_client=10, overall=50):
        # Also cap globally to bound work when proxy source identities vary.
        now = time.time()
        with auth_lock:
            for key in (f'{name}:global', f'{name}:{request.client.host}'):
                queue = attempts[key]
                while queue and queue[0] < now - 300:
                    queue.popleft()
                if len(queue) >= (overall if key.endswith(':global') else per_client):
                    raise HTTPException(429, '잠시 후 다시 시도해 주세요.')
                queue.append(now)

    def session_response(request, email, kind='browser', name='', body=None, redirect=None):
        token = secrets.token_urlsafe(32)
        sessions.create(token, email, kind, name)
        response = RedirectResponse(redirect, status_code=303) if redirect else JSONResponse(body or {'ok': True})
        max_age = DEVICE_TTL if kind == 'device' else SESSION_TTL
        response.set_cookie(SESSION_COOKIE, token, httponly=True, secure=request.url.scheme == 'https', samesite='lax', max_age=max_age)
        return response

    def redirect_uri(request):
        if is_local(request):
            return f'http://127.0.0.1:{request.url.port or 80}{CALLBACK_PATH}'
        if tailscale.same_origin(google.external_url, request.url.scheme, request.headers.get('host')):
            return google.external_url + CALLBACK_PATH
        raise HTTPException(403, '설정된 외부 주소로 접속해 주세요.')

    def message_page(request, title, message, status_code=200):
        lang = request_lang(request.headers)
        title, message = translate(title, lang), translate(message, lang)
        page = (f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
                f'<title>StackPad</title></head><body style="font-family:system-ui,sans-serif;background:#202122;color:#f5f5f4;display:grid;'
                f'place-items:center;min-height:100vh;margin:0"><main style="max-width:420px;padding:24px;text-align:center"><h1 style="font-size:20px">'
                f'{html.escape(title)}</h1><p style="color:#b8b8b4;line-height:1.6">{html.escape(message)}</p></main></body></html>')
        return HTMLResponse(page, status_code=status_code)

    @app.get('/api/health')
    def health():
        return {'app': 'stackpad', 'version': VERSION}

    def touches_remote(pad_id):
        try:
            return bool(pad_id) and engine.pad_has_remote(pad_id)
        except KeyError:
            return False

    def guard_remote(request, touches):
        # Remote commands run with this user's SSH keys, so only this PC may register or change them.
        if touches and not is_local(request):
            raise HTTPException(403, '원격 서버 패드는 이 PC에서 접속해 등록하고 변경해 주세요.')

    @app.get('/api/auth')
    def auth_state(request: Request):
        record = current_session(request)
        return {'configured': google.configured, 'owner': bool(google.owner), 'authenticated': bool(record),
                'email': record['email'] if record else None, 'local': is_local(request)}

    @app.get('/api/auth/google/start')
    def google_start(request: Request, ticket: str | None = None):
        limit(request, 'start', 20, 100)
        if is_local(request) and request.url.hostname != '127.0.0.1':
            # Google accepts the loopback redirect registered for 127.0.0.1, so sign-in always runs there.
            query = f'?ticket={ticket}' if ticket else ''
            return RedirectResponse(f'http://127.0.0.1:{request.url.port or 80}/api/auth/google/start{query}', status_code=303)
        if ticket and not is_local(request):
            raise HTTPException(403, 'PC 앱 로그인은 이 PC에서만 진행할 수 있습니다.')
        try:
            url, state = google.begin(redirect_uri(request), is_local(request), ticket)
        except (RuntimeError, ValueError) as error:
            return message_page(request, '로그인을 시작하지 못했어요', str(error), 400)
        response = RedirectResponse(url, status_code=303)
        # Binds the callback to the browser that started sign-in.
        response.set_cookie(STATE_COOKIE, state, httponly=True, secure=request.url.scheme == 'https', samesite='lax', max_age=FLOW_TTL, path=CALLBACK_PATH)
        return response

    @app.get(CALLBACK_PATH)
    def google_callback(request: Request, state: str = '', code: str = '', error: str = ''):
        limit(request, 'callback')
        flow_ticket = google.flows.get(state, {}).get('ticket')
        def fail(message):
            if flow_ticket:
                return message_page(request, '로그인하지 못했어요', message, 403)
            return RedirectResponse('/?' + urlencode({'auth_error': translate(message, request_lang(request.headers))}), status_code=303)
        if error or not code or not state or not secrets.compare_digest(request.cookies.get(STATE_COOKIE, ''), state):
            google.flows.pop(state, None)
            return fail('Google 로그인을 취소했거나 시간이 지났습니다. 다시 로그인해 주세요.')
        try:
            email, flow = google.finish(state, code)
            if flow['local'] != is_local(request):
                raise ValueError('로그인을 시작한 주소에서 다시 로그인해 주세요.')
            google.admit(email, flow['local'])
        except (ValueError, PermissionError, httpx.HTTPError) as problem:
            return fail(str(problem) if not isinstance(problem, httpx.HTTPError) else 'Google에 연결하지 못했습니다. 네트워크를 확인해 주세요.')
        if flow['ticket']:
            google.complete_ticket(flow['ticket'], email)
            response = message_page(request, '로그인을 마쳤어요', 'StackPad 앱으로 돌아가 주세요. 이 창은 닫아도 됩니다.')
        else:
            response = session_response(request, email, redirect='/')
        response.delete_cookie(STATE_COOKIE, path=CALLBACK_PATH)
        return response

    @app.post('/api/auth/desktop', dependencies=[Depends(local_only)])
    def desktop_login(request: Request):
        limit(request, 'desktop', 20, 100)
        ticket, secret = google.create_ticket()
        port = request.url.port or 80
        os.startfile(f'http://127.0.0.1:{port}/api/auth/google/start?ticket={ticket}')
        return {'ticket': ticket, 'secret': secret}

    class DesktopClaim(BaseModel):
        ticket: str = Field(min_length=1, max_length=100)
        secret: str = Field(min_length=1, max_length=100)

    @app.post('/api/auth/desktop/claim', dependencies=[Depends(local_only)])
    def desktop_claim(values: DesktopClaim, request: Request):
        email = google.claim_ticket(values.ticket, values.secret)
        if email is None:
            return {'pending': True}
        return session_response(request, email, body={'pending': False})

    @app.post('/api/logout')
    def logout(request: Request):
        sessions.pop(request.cookies.get(SESSION_COOKIE))
        response = JSONResponse({'ok': True})
        response.delete_cookie(SESSION_COOKIE)
        return response

    @app.get('/api/auth/settings', dependencies=[Depends(setup_access)])
    def auth_settings(request: Request):
        port = request.url.port or 80
        return {'configured': google.configured, 'client_id': google.settings.get('client_id', ''), 'owner': google.owner,
                'accounts': google.accounts(), 'external_url': google.external_url,
                'redirect_uris': [f'http://127.0.0.1:{port}{CALLBACK_PATH}', *([google.external_url + CALLBACK_PATH] if google.external_url else [])]}

    class OAuthClient(BaseModel):
        client_id: str = Field(min_length=1, max_length=200)
        client_secret: str = Field(default='', max_length=200)

    @app.put('/api/auth/client', dependencies=[Depends(setup_access)])
    def save_oauth_client(values: OAuthClient):
        google.save_client(values.client_id, values.client_secret)
        return {'ok': True}

    class Account(BaseModel):
        email: str = Field(min_length=3, max_length=254)

    @app.post('/api/auth/accounts', dependencies=[Depends(local_only), Depends(authenticated)])
    def add_account(values: Account):
        return {'email': google.add_account(values.email)}

    @app.delete('/api/auth/accounts/{email}', dependencies=[Depends(local_only), Depends(authenticated)])
    def remove_account(email: str):
        removed = google.remove_account(email)
        sessions.revoke_email(removed)
        return {'ok': True}

    @app.get('/api/tailscale', dependencies=[Depends(setup_access)])
    def tailscale_status(request: Request):
        return tailscale.status(request.url.port or 80)

    @app.post('/api/tailscale/connect', dependencies=[Depends(setup_access)])
    def tailscale_connect(request: Request):
        url = tailscale.connect(request.url.port or 80)
        google.save_external_url(url)
        return {'url': url}

    @app.post('/api/pairing', dependencies=[Depends(local_only)])
    def create_pairing(session=Depends(authenticated)):
        if not google.external_url:
            raise HTTPException(409, '먼저 Tailscale로 외부 주소를 연결해 주세요.')
        code, ttl = google.create_pairing(session['email'])
        return {'url': google.external_url, 'code': code, 'expires_in': ttl,
                'link': 'stackpad://pair?' + urlencode({'server': google.external_url, 'code': code})}

    class PairingClaim(BaseModel):
        code: str = Field(min_length=1, max_length=100)
        name: str = Field(default='Android', max_length=60)

    @app.post('/api/pairing/claim')
    def claim_pairing(values: PairingClaim, request: Request):
        limit(request, 'pairing')
        try:
            email = google.claim_pairing(values.code)
        except PermissionError as problem:
            raise HTTPException(403, str(problem)) from None
        return session_response(request, email, 'device', values.name.strip() or 'Android', body={'ok': True, 'email': email})

    @app.get('/api/devices', dependencies=[Depends(authenticated)])
    def list_devices(request: Request):
        return {'devices': sessions.devices(), 'current': sessions.device_id(request.cookies.get(SESSION_COOKIE))}

    @app.delete('/api/devices/{device_id}', dependencies=[Depends(authenticated)])
    def revoke_device(device_id: str):
        sessions.revoke_device(device_id)
        widget_tokens.revoke_device(device_id)
        return {'ok': True}

    @app.get('/api/usage', dependencies=[Depends(authenticated)])
    def usage(refresh: int = 0):
        enabled = engine.config.get('usage_providers', [])
        return {'providers': collect_usage(refresh=refresh == 1, enabled=enabled), 'enabled': enabled}

    class WidgetDevice(BaseModel):
        name: str = Field(min_length=1, max_length=60)

    @app.post('/api/widget/tokens', dependencies=[Depends(authenticated)])
    def issue_widget_token(values: WidgetDevice, request: Request):
        token_id, token = widget_tokens.issue(values.name.strip() or 'Android', sessions.device_id(request.cookies.get(SESSION_COOKIE)))
        return {'id': token_id, 'token': token}

    @app.get('/api/widget/tokens', dependencies=[Depends(authenticated)])
    def list_widget_tokens():
        return {'devices': widget_tokens.list()}

    @app.delete('/api/widget/tokens/{token_id}', dependencies=[Depends(authenticated)])
    def revoke_widget_token(token_id: str):
        widget_tokens.revoke(token_id)
        return {'ok': True}

    # The widget token only reaches this read-only route; every other API still requires the login cookie.
    @app.get('/api/widget/usage')
    def widget_usage(request: Request):
        scheme, _, token = request.headers.get('authorization', '').partition(' ')
        if scheme.lower() != 'bearer' or not widget_tokens.verify(token):
            raise HTTPException(401, '위젯 연결을 다시 설정해 주세요.')
        enabled = engine.config.get('usage_providers', [])
        return {'providers': collect_usage(enabled=enabled), 'enabled': enabled}

    @app.get('/api/services', dependencies=[Depends(authenticated)])
    def services():
        result = engine.snapshot()
        for item in result:
            item.pop('_cpu_time', None)
            item.pop('_sample_time', None)
        return {'services': result, 'groups': engine.config.get('groups', []), 'links': engine.pad_links(), 'padsets': engine.config['padsets']}

    @app.post('/api/padsets', dependencies=[Depends(authenticated)])
    def add_padset(values: PadsetInput):
        return {'id': engine.save_padset(values)}

    class PadsetOrder(BaseModel):
        ids: list[str] = Field(min_length=1)

    @app.put('/api/padsets/order', dependencies=[Depends(authenticated)])
    def reorder_padsets(values: PadsetOrder):
        engine.reorder_padsets(values.ids)
        return {'ok': True}

    @app.put('/api/padsets/{padset_id}', dependencies=[Depends(authenticated)])
    def update_padset(padset_id: str, values: PadsetInput):
        return {'id': engine.save_padset(values, padset_id)}

    @app.delete('/api/padsets/{padset_id}', dependencies=[Depends(authenticated)])
    def delete_padset(padset_id: str):
        engine.delete_padset(padset_id)
        return {'ok': True}

    @app.get('/api/docker/containers', dependencies=[Depends(authenticated)])
    def docker_containers():
        return {'containers': engine.docker_containers()}

    @app.post('/api/groups', dependencies=[Depends(authenticated)])
    def add_group(values: GroupInput):
        return {'id': engine.save_group(values)}

    @app.post('/api/pads', dependencies=[Depends(authenticated)])
    def add_pad(values: PadInput, request: Request):
        guard_remote(request, any(c.kind == 'remote' for c in values.components))
        return {'id': engine.save_pad(values)}

    @app.put('/api/pads/{pad_id}', dependencies=[Depends(authenticated)])
    def update_pad(pad_id: str, values: PadInput, request: Request):
        guard_remote(request, any(c.kind == 'remote' for c in values.components) or touches_remote(pad_id))
        return {'id': engine.save_pad(values, pad_id)}

    @app.delete('/api/pads/{pad_id}', dependencies=[Depends(authenticated)])
    def delete_pad(pad_id: str):
        engine.delete_pad(pad_id)
        return {'ok': True}

    class PadMove(BaseModel):
        slot: int = Field(ge=0, le=15)
        padset_id: str | None = None

    @app.put('/api/pads/{pad_id}/position', dependencies=[Depends(authenticated)])
    def move_pad(pad_id: str, values: PadMove):
        engine.move_pad(pad_id, values.slot, values.padset_id)
        return {'ok': True}

    @app.post('/api/pads/{pad_id}/code', dependencies=[Depends(authenticated)])
    def open_pad_in_code(pad_id: str):
        return {'folder': engine.open_in_code(pad_id)}

    class PadLink(BaseModel):
        target: Literal['domain', 'local']

    @app.post('/api/pads/{pad_id}/open', dependencies=[Depends(authenticated)])
    def open_pad_link(pad_id: str, values: PadLink, request: Request):
        # The desktop window cannot open new browser windows, so this PC's default browser opens the address.
        if not is_local(request):
            raise HTTPException(403, '이 PC에서 접속한 화면에서 열 수 있습니다.')
        return {'url': engine.open_link(pad_id, values.target)}

    @app.put('/api/groups/{group_id}', dependencies=[Depends(authenticated)])
    def update_group(group_id: str, values: GroupInput):
        return {'id': engine.save_group(values, group_id)}

    @app.delete('/api/groups/{group_id}', dependencies=[Depends(authenticated)])
    def dissolve_group(group_id: str):
        engine.dissolve_group(group_id)
        return {'ok': True}

    @app.post('/api/groups/{group_id}/start', dependencies=[Depends(authenticated)])
    def start_group(group_id: str, takeover: bool = False):
        engine.group_action(group_id, 'start', takeover)
        return {'ok': True}

    @app.post('/api/groups/{group_id}/stop', dependencies=[Depends(authenticated)])
    def stop_group(group_id: str):
        engine.group_action(group_id, 'stop')
        return {'ok': True}

    @app.post('/api/services/{service_id}/restart', dependencies=[Depends(authenticated)])
    def restart_service(service_id: str):
        engine.restart(service_id)
        return {'ok': True}

    @app.post('/api/services', dependencies=[Depends(authenticated)])
    def add(values: AnyServiceInput, request: Request):
        guard_remote(request, values.kind == 'remote')
        return {'id': engine.add(values)}

    @app.put('/api/services/{service_id}', dependencies=[Depends(authenticated)])
    def update(service_id: str, values: AnyServiceInput, request: Request):
        guard_remote(request, values.kind == 'remote' or touches_remote(service_id))
        return {'id': engine.add(values, service_id)}

    @app.get('/api/remote/hosts', dependencies=[Depends(authenticated)])
    def remote_hosts():
        return {'hosts': [h['alias'] for h in ssh_hosts()]}

    class RemoteTest(BaseModel):
        host: str = Field(min_length=1, max_length=255)

    @app.post('/api/remote/test', dependencies=[Depends(authenticated)])
    def remote_test(values: RemoteTest, request: Request):
        guard_remote(request, True)
        host = RemoteSpec.destination(values.host.strip())
        return engine.test_connection(host)

    @app.delete('/api/services/{service_id}', dependencies=[Depends(authenticated)])
    def delete(service_id: str):
        engine.delete(service_id)
        return {'ok': True}

    @app.post('/api/services/{service_id}/start', dependencies=[Depends(authenticated)])
    def start(service_id: str, takeover: bool = False):
        engine.start(service_id, takeover)
        return {'ok': True}

    @app.post('/api/services/{service_id}/stop', dependencies=[Depends(authenticated)])
    def stop(service_id: str):
        engine.stop(service_id)
        return {'ok': True}

    @app.get('/api/services/{service_id}/logs', dependencies=[Depends(authenticated)])
    def logs(service_id: str):
        return {'text': engine.tail(service_id)}

    class Shutdown(BaseModel):
        stop_services: bool = False

    @app.post('/api/engine/shutdown', dependencies=[Depends(local_only)])
    def shutdown(values: Shutdown, request: Request):
        if not control_token or not secrets.compare_digest(request.headers.get('x-stackpad-control', ''), control_token):
            raise HTTPException(403, 'StackPad가 실행 중인 PC에서 설정해 주세요.')
        failed = engine.stop_all_local() if values.stop_services else []
        # Answer first, then end the process; services started by StackPad keep running unless asked to stop.
        threading.Timer(0.5, lambda: os._exit(0)).start()
        return {'ok': True, 'failed': failed}

    @app.get('/api/settings', dependencies=[Depends(authenticated)])
    def settings(request: Request):
        return {'tools': {'vscode': bool(vscode_path()), 'docker': bool(shutil.which('docker'))}, 'autostart': engine.startup_path.exists(), 'data_dir': str(engine.data_dir),
                'can_select_data_dir': is_local(request),
                'log_retention_days': engine.config.get('log_retention_days', 14),
                'recommend_roots': engine.config.get('recommend', {}).get('roots') or recommend.DEFAULT_ROOTS, 'recommend_hidden': recommend.hidden_entries(engine.config),
                'onboarding_done': bool(engine.config.get('onboarding_done')), 'usage_providers': engine.config.get('usage_providers', [])}

    class LogRetention(BaseModel):
        days: int = Field(ge=0, le=365)

    @app.put('/api/settings/log-retention', dependencies=[Depends(authenticated)])
    def log_retention(values: LogRetention):
        with engine.lock:
            engine.config['log_retention_days'] = values.days
            engine.save()
            engine.purge_expired_logs()
        return {'ok': True, 'log_retention_days': values.days}

    @app.post('/api/settings/data-directory', dependencies=[Depends(authenticated)])
    def select_data_directory(request: Request):
        if not is_local(request):
            raise HTTPException(403, '이 PC에서 접속한 화면에서 저장 폴더를 선택해 주세요.')
        if not storage_location.selection_lock.acquire(blocking=False):
            raise HTTPException(409, '열려 있는 폴더 선택 창을 먼저 닫아 주세요.')
        try:
            selected = select_folder(engine.data_dir)
            if selected is None:
                return {'cancelled': True, 'data_dir': str(engine.data_dir)}
            return {'cancelled': False, 'data_dir': storage_location.change(selected)}
        finally:
            storage_location.selection_lock.release()

    class Startup(BaseModel):
        enabled: bool

    @app.put('/api/settings/autostart', dependencies=[Depends(authenticated)])
    def startup(values: Startup):
        engine.autostart(values.enabled)
        return {'ok': True}

    class RecommendRoots(BaseModel):
        roots: list[str] = Field(min_length=1, max_length=10)

    class RecommendHide(BaseModel):
        key: str = Field(min_length=1, max_length=3000)
        name: str = Field(default='', max_length=200)
        cwd: str = Field(default='', max_length=1000)
        command: str = Field(default='', max_length=3000)

    class RecommendKey(BaseModel):
        key: str = Field(min_length=1, max_length=3000)

    @app.get('/api/recommendations', dependencies=[Depends(authenticated)])
    def recommendations():
        return recommend.scan(engine)

    @app.post('/api/recommendations/hidden', dependencies=[Depends(authenticated)])
    def hide_recommendation(values: RecommendHide):
        recommend.hide(engine, values.key, values.name, values.cwd, values.command)
        return {'ok': True}

    @app.post('/api/recommendations/unhide', dependencies=[Depends(authenticated)])
    def unhide_recommendation(values: RecommendKey):
        recommend.unhide(engine, values.key)
        return {'ok': True}

    @app.delete('/api/recommendations/hidden', dependencies=[Depends(authenticated)])
    def reset_recommendations():
        recommend.reset_hidden(engine)
        return {'ok': True}

    class UsageProviders(BaseModel):
        providers: list[Literal['claude', 'codex', 'antigravity']] = Field(max_length=3)

    @app.put('/api/settings/usage', dependencies=[Depends(authenticated)])
    def usage_providers(values: UsageProviders):
        with engine.lock:
            engine.config['usage_providers'] = [name for name in ('claude', 'codex', 'antigravity') if name in values.providers]
            engine.save()
        return {'providers': engine.config['usage_providers']}

    class Onboarding(BaseModel):
        roots: list[str] = Field(default_factory=list, max_length=10)

    @app.put('/api/settings/onboarding', dependencies=[Depends(authenticated)])
    def finish_onboarding(values: Onboarding):
        roots = recommend.save_roots(engine, values.roots) if any(r.strip() for r in values.roots) else []
        with engine.lock:
            engine.config['onboarding_done'] = True
            engine.save()
        return {'roots': roots}

    @app.post('/api/settings/pick-folder', dependencies=[Depends(local_only), Depends(authenticated)])
    def pick_folder():
        if not storage_location.selection_lock.acquire(blocking=False):
            raise HTTPException(409, '열려 있는 폴더 선택 창을 먼저 닫아 주세요.')
        try:
            return {'folder': select_folder(Path.home(), '폴더를 선택해 주세요.')}
        finally:
            storage_location.selection_lock.release()

    @app.put('/api/settings/recommend', dependencies=[Depends(authenticated)])
    def recommend_roots(values: RecommendRoots):
        return {'roots': recommend.save_roots(engine, values.roots)}

    @app.get('/{path:path}')
    def frontend(path: str):
        root = Path(web_dir).resolve()
        target = (root / path).resolve()
        if not target.is_relative_to(root) or path.startswith('api/'):
            raise HTTPException(404)
        if target.is_file():
            return FileResponse(target)
        if not path or '.' not in Path(path).name:
            index = root / 'index.html'
            if index.is_file():
                return FileResponse(index)
        raise HTTPException(404, '화면 빌드를 확인해 주세요.')

    return app


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir')
    parser.add_argument('--web-dir')
    parser.add_argument('--port', type=int, default=48731)
    parser.add_argument('--desktop-exe')
    args = parser.parse_args()
    if args.data_dir is None:
        args.data_dir = str(Path.home() / '.config' / 'stackpad')
    bootstrap = Path(args.data_dir).resolve()
    args.data_dir = str(resolve_data_dir(bootstrap))
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    web = Path(args.web_dir) if args.web_dir else root / 'dist'
    Path(args.data_dir).mkdir(parents=True, exist_ok=True)
    engine_logs_dir = Path(args.data_dir) / 'logs'
    engine_logs_dir.mkdir(parents=True, exist_ok=True)
    nested_engine_dir = engine_logs_dir / 'engine'
    if nested_engine_dir.is_dir():
        try:
            for item in list(nested_engine_dir.iterdir()):
                target = engine_logs_dir / item.name
                if not target.exists():
                    shutil.move(item, target)
                else:
                    item.unlink()
            shutil.rmtree(nested_engine_dir, ignore_errors=True)
        except Exception:
            pass
    legacy_engine_log = Path(args.data_dir) / 'engine.log'
    if legacy_engine_log.exists():
        try:
            target_legacy = engine_logs_dir / 'engine-legacy.log'
            if not target_legacy.exists():
                shutil.copy2(legacy_engine_log, target_legacy)
                legacy_engine_log.unlink()
        except Exception:
            pass
    # Packaged windowless executables have no stdout or stderr.
    today = time.strftime('%Y-%m-%d')
    output = open(engine_logs_dir / f'engine-{today}.log', 'a', encoding='utf-8', buffering=1)
    sys.stdout = sys.stderr = output
    logging.basicConfig(stream=output, level=logging.INFO)
    # The desktop app reads this token to shut the engine down from the tray.
    control_token = secrets.token_urlsafe(32)
    (bootstrap / 'control-token').write_text(control_token, 'utf-8')
    uvicorn.run(create_app(args.data_dir, web, args.desktop_exe, bootstrap / 'storage-location.json', control_token), host='127.0.0.1', port=args.port, proxy_headers=True, forwarded_allow_ips='127.0.0.1', log_level='info')
