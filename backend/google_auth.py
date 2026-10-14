"""Google sign-in handled by the engine: Authorization Code with PKCE, then ID token checks and an account allowlist."""
import base64
import hashlib
import re
import secrets
import threading
import time
from urllib.parse import urlencode

import httpx
import jwt

AUTHORIZE_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_URL = 'https://oauth2.googleapis.com/token'
CERTS_URL = 'https://www.googleapis.com/oauth2/v3/certs'
ISSUERS = ('https://accounts.google.com', 'accounts.google.com')
FLOW_TTL = 600
TICKET_TTL = 600
PAIRING_TTL = 300
CALLBACK_PATH = '/api/auth/google/callback'
EMAIL = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def _challenge(verifier):
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')


def normalize_email(value):
    email = (value or '').strip().lower()
    if not EMAIL.match(email) or len(email) > 254:
        raise ValueError('Google 계정 이메일을 확인해 주세요.')
    return email


class GoogleAuth:
    def __init__(self, engine, http=None):
        self.engine = engine
        self.http = http or httpx.Client(timeout=15)
        self.lock = threading.Lock()
        self.flows = {}
        self.tickets = {}
        self.pairing = None
        self._keys = None

    # Settings live in the engine config so a storage move carries them along.
    @property
    def settings(self):
        return self.engine.config.get('auth') or {}

    def _update(self, **values):
        with self.engine.lock:
            settings = self.engine.config.setdefault('auth', {})
            settings.update(values)
            self.engine.save()

    @property
    def configured(self):
        return bool(self.settings.get('client_id') and self.settings.get('client_secret'))

    @property
    def owner(self):
        return self.settings.get('owner')

    @property
    def external_url(self):
        return self.settings.get('external_url')

    def accounts(self):
        return list(self.settings.get('allowed') or [])

    def save_client(self, client_id, client_secret):
        client_id = client_id.strip()
        client_secret = client_secret.strip() or self.settings.get('client_secret', '')
        if not client_id.endswith('.apps.googleusercontent.com') or len(client_id) > 200:
            raise ValueError('OAuth 클라이언트 ID를 확인해 주세요. `.apps.googleusercontent.com`으로 끝나야 합니다.')
        if not client_secret or len(client_secret) > 200:
            raise ValueError('OAuth 클라이언트 보안 비밀번호를 입력해 주세요.')
        self._update(client_id=client_id, client_secret=client_secret)

    def save_external_url(self, url):
        self._update(external_url=url)

    def add_account(self, email):
        email = normalize_email(email)
        allowed = self.accounts()
        if email in allowed:
            raise ValueError('이미 허용된 계정입니다.')
        if len(allowed) >= 20:
            raise ValueError('허용 계정은 20개까지 등록할 수 있습니다.')
        self._update(allowed=[*allowed, email])
        return email

    def remove_account(self, email):
        email = normalize_email(email)
        if email == self.owner:
            raise ValueError('소유자 계정은 삭제할 수 없습니다.')
        allowed = self.accounts()
        if email not in allowed:
            raise KeyError('허용 계정을 찾을 수 없습니다.')
        self._update(allowed=[item for item in allowed if item != email])
        return email

    def admit(self, email, local):
        """Register the first local sign-in as owner; afterwards only allowed accounts get in."""
        with self.engine.lock:
            if not self.owner:
                if not local:
                    raise PermissionError('StackPad가 실행 중인 PC에서 먼저 로그인해 주세요.')
                self._update(owner=email, allowed=[email])
                return
            if email not in self.accounts():
                raise PermissionError(f'{email} 계정은 허용되지 않았습니다. PC의 환경 설정에서 계정을 추가해 주세요.')

    def _prune(self, now):
        self.flows = {key: flow for key, flow in self.flows.items() if now - flow['created'] < FLOW_TTL}
        self.tickets = {key: ticket for key, ticket in self.tickets.items() if now - ticket['created'] < TICKET_TTL}

    def begin(self, redirect_uri, local, ticket=None):
        if not self.configured:
            raise RuntimeError('Google 로그인 설정을 먼저 마쳐 주세요.')
        state, verifier, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(64), secrets.token_urlsafe(32)
        now = time.time()
        with self.lock:
            self._prune(now)
            if len(self.flows) >= 100:
                raise RuntimeError('로그인 요청이 많습니다. 잠시 후 다시 시도해 주세요.')
            if ticket is not None and ticket not in self.tickets:
                raise ValueError('PC 앱에서 로그인을 다시 시작해 주세요.')
            self.flows[state] = {'verifier': verifier, 'nonce': nonce, 'redirect_uri': redirect_uri, 'local': local,
                                 'ticket': ticket, 'created': now}
        query = urlencode({'client_id': self.settings['client_id'], 'redirect_uri': redirect_uri, 'response_type': 'code',
                           'scope': 'openid email', 'state': state, 'nonce': nonce, 'code_challenge': _challenge(verifier),
                           'code_challenge_method': 'S256', 'prompt': 'select_account'})
        return f'{AUTHORIZE_URL}?{query}', state

    def finish(self, state, code):
        with self.lock:
            flow = self.flows.pop(state, None)
        if not flow or time.time() - flow['created'] >= FLOW_TTL:
            raise ValueError('로그인 시간이 지났습니다. 다시 로그인해 주세요.')
        response = self.http.post(TOKEN_URL, data={'code': code, 'client_id': self.settings['client_id'],
                                                   'client_secret': self.settings['client_secret'], 'redirect_uri': flow['redirect_uri'],
                                                   'grant_type': 'authorization_code', 'code_verifier': flow['verifier']})
        if response.status_code != 200:
            raise ValueError('Google 로그인을 확인하지 못했습니다. OAuth 클라이언트 설정과 리디렉션 주소를 확인해 주세요.')
        email = self.verify(response.json().get('id_token', ''), flow['nonce'])
        return email, flow

    def verify(self, id_token, nonce):
        try:
            if self._keys is None:
                self._keys = jwt.PyJWKClient(CERTS_URL, timeout=10)
            key = self._keys.get_signing_key_from_jwt(id_token)
            claims = jwt.decode(id_token, key.key, algorithms=['RS256'], audience=self.settings['client_id'],
                                options={'require': ['exp', 'iat', 'iss', 'aud', 'sub', 'email']})
        except (jwt.PyJWTError, ValueError, TypeError) as error:
            raise ValueError('Google 로그인 정보를 확인하지 못했습니다.') from error
        if claims.get('iss') not in ISSUERS or claims.get('nonce') != nonce or claims.get('email_verified') is not True:
            raise ValueError('Google 로그인 정보를 확인하지 못했습니다.')
        return normalize_email(claims['email'])

    # The desktop window cannot show Google sign-in, so the default browser signs in and the window claims the result.
    def create_ticket(self):
        ticket, secret = secrets.token_urlsafe(16), secrets.token_urlsafe(32)
        with self.lock:
            self._prune(time.time())
            if len(self.tickets) >= 20:
                raise RuntimeError('로그인 요청이 많습니다. 잠시 후 다시 시도해 주세요.')
            self.tickets[ticket] = {'secret': hashlib.sha256(secret.encode()).hexdigest(), 'email': None, 'created': time.time()}
        return ticket, secret

    def complete_ticket(self, ticket, email):
        with self.lock:
            if ticket in self.tickets:
                self.tickets[ticket]['email'] = email

    def claim_ticket(self, ticket, secret):
        """Returns the signed-in email once, None while pending; raises when the ticket is unknown."""
        with self.lock:
            self._prune(time.time())
            entry = self.tickets.get(ticket)
            if not entry or not secrets.compare_digest(entry['secret'], hashlib.sha256(secret.encode()).hexdigest()):
                raise ValueError('PC 앱에서 로그인을 다시 시작해 주세요.')
            if not entry['email']:
                return None
            self.tickets.pop(ticket)
            return entry['email']

    # Phones pair by scanning a short-lived code shown on the PC.
    def create_pairing(self, email):
        code = secrets.token_urlsafe(24)
        with self.lock:
            self.pairing = {'code': hashlib.sha256(code.encode()).hexdigest(), 'email': email, 'created': time.time()}
        return code, PAIRING_TTL

    def claim_pairing(self, code):
        with self.lock:
            pairing = self.pairing
            valid = (pairing and time.time() - pairing['created'] < PAIRING_TTL
                     and secrets.compare_digest(pairing['code'], hashlib.sha256(code.encode()).hexdigest()))
            if not valid:
                raise PermissionError('연결 코드가 만료되었습니다. PC에서 새 QR 코드를 띄워 주세요.')
            self.pairing = None
        if pairing['email'] not in self.accounts():
            raise PermissionError('연결 코드를 만든 계정이 더 이상 허용되지 않습니다.')
        return pairing['email']
