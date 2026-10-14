import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowUpRight, LoaderCircle, LockKeyhole, Radio } from 'lucide-react';
import { OAuthClientForm, OAuthGuide, TailscaleConnect } from './AuthSetup.jsx';
import { t } from '../i18n.js';

const isDesktop = () => !!window.__TAURI_INTERNALS__;

function takeUrlError() {
  const params = new URLSearchParams(window.location.search);
  const message = params.get('auth_error');
  if (message) {
    params.delete('auth_error');
    window.history.replaceState(null, '', window.location.pathname + (params.size ? `?${params}` : ''));
  }
  return message || '';
}

function Card({ logo, title, children }) {
  return <div className="login-shell"><div className="login-card">
    <div className="brand">{logo}<strong>StackPad</strong></div>
    <div className="login-icon"><LockKeyhole size={26} /></div>
    <h1>{title}</h1>
    {children}
    <span className="login-foot"><Radio size={12} /> {t('이 PC의 서비스와 연결됩니다')}</span>
  </div><div className="login-caption">{t('당신의 서버, 손끝에서.')}</div></div>;
}

// First run on this PC: optional Tailscale address, then the user's own Google OAuth client.
function Setup({ api, logo, onDone }) {
  const [settings, setSettings] = useState(null);
  const [error, setError] = useState('');
  const load = useCallback(async () => { try { setSettings(await api('/auth/settings')); } catch (e) { setError(e.message); } }, [api]);
  useEffect(() => { load(); }, [load]);
  return <Card logo={logo} title={t('StackPad 시작하기')}>
    <p>{t('Google 계정으로 로그인하도록 설정합니다. 이 PC에서 한 번만 하면 돼요.')}</p>
    <div className="setup-steps">
      <section><h2>{t('1. 외부 접속')} <span className="optional">{t('선택')}</span></h2><p className="optional">{t('휴대폰에서도 쓰려면 Tailscale로 이 PC에 HTTPS 주소를 연결하세요. 나중에 환경 설정에서 연결해도 됩니다.')}</p>
        <TailscaleConnect api={api} onConnected={load} onError={setError} /></section>
      <section><h2>{t('2. Google 로그인 설정')}</h2><OAuthGuide redirectUris={settings?.redirect_uris} />
        <OAuthClientForm api={api} current={settings} onSaved={onDone} onError={setError} /></section>
    </div>
    {error && <p role="alert" className="inline-error">{error}</p>}
  </Card>;
}

export function SignIn({ auth, api, logo, onLogin }) {
  const [error, setError] = useState(takeUrlError);
  const [waiting, setWaiting] = useState(false);
  const [editing, setEditing] = useState(false);
  const cancelled = useRef(false);
  useEffect(() => () => { cancelled.current = true; }, []);
  if (!auth.configured || editing) {
    if (!auth.local) return <Card logo={logo} title={t('PC에서 설정을 마쳐 주세요')}><p>{t('StackPad가 실행 중인 PC에서 Google 로그인 설정을 마친 뒤 다시 접속해 주세요.')}</p></Card>;
    return <Setup api={api} logo={logo} onDone={() => { setEditing(false); onLogin(); }} />;
  }
  async function signIn() {
    setError('');
    if (!isDesktop()) { window.location.assign('/api/auth/google/start'); return; }
    // The app window cannot show Google sign-in, so the default browser signs in and this window collects the result.
    setWaiting(true); cancelled.current = false;
    try {
      const ticket = await api('/auth/desktop', { method: 'POST' });
      const deadline = Date.now() + 10 * 60 * 1000;
      while (!cancelled.current && Date.now() < deadline) {
        await new Promise(resolve => setTimeout(resolve, 1500));
        if (cancelled.current) break;
        const result = await api('/auth/desktop/claim', { method: 'POST', body: JSON.stringify(ticket) });
        if (!result.pending) { onLogin(); return; }
      }
      if (!cancelled.current) setError(t('로그인 시간이 지났습니다. 다시 로그인해 주세요.'));
    } catch (e) { setError(e.message); } finally { setWaiting(false); }
  }
  const blocked = !auth.owner && !auth.local;
  return <Card logo={logo} title={t('컨트롤 룸에 입장하기')}>
    <p>{blocked ? t('StackPad가 실행 중인 PC에서 먼저 로그인해 주세요. 처음 로그인한 계정이 소유자가 됩니다.') : !auth.owner ? t('처음 로그인한 Google 계정이 이 StackPad의 소유자로 등록됩니다.') : t('허용된 Google 계정으로 로그인하고 서비스 현황을 확인하세요.')}</p>
    {!blocked && <div className="login-actions">
      <button className="primary wide" disabled={waiting} onClick={signIn}>{waiting ? <LoaderCircle className="spin" size={17} /> : <ArrowUpRight size={17} />}{waiting ? t('브라우저에서 로그인을 마쳐 주세요') : t('Google로 로그인')}</button>
      {waiting && <button className="secondary wide" onClick={() => { cancelled.current = true; setWaiting(false); }}>{t('취소')}</button>}
      {auth.local && !auth.owner && !waiting && <button className="secondary wide" onClick={() => setEditing(true)}>{t('Google 로그인 설정 다시 입력')}</button>}
    </div>}
    {error && <p role="alert" className="inline-error">{error}</p>}
  </Card>;
}
