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

// The sign-in, first-run setup and phone pairing screens share this centered card.
export function AuthCard({ logo, icon = <LockKeyhole size={26} />, title, description, error, foot = t('이 PC의 서비스와 연결됩니다'), caption, wide = false, children }) {
  return <div className="flex min-h-dvh flex-col items-center justify-center bg-[radial-gradient(ellipse_at_50%_40%,#f4f3eb,#e2e2d9_70%)] px-[18px] py-[30px]">
    <div className={`max-w-full rounded-[14px] border border-[#c7cbbd] bg-[#f2f0e6] p-[35px] text-ink shadow-[0_15px_45px_#47593a18] max-tablet:px-6 max-tablet:py-[29px] ${wide ? 'w-[560px]' : 'w-[420px]'}`}>
      <div className="mb-[35px] flex items-center gap-[11px] text-[#555c51] max-tablet:mb-[30px]">{logo}<strong className="text-[18px] tracking-[-.7px] max-[1100px]:text-[16px] max-tablet:text-[15px]">StackPad</strong></div>
      <div className="mb-[15px] text-[#bbcfbf]">{icon}</div>
      <h1 className="text-[23px] tracking-[-.9px] text-heading max-tablet:text-[21px]">{title}</h1>
      {description && <p className="mt-[13px] mb-[27px] text-[12px] leading-[1.9] text-[#5c6654]">{description}</p>}
      {children}
      {error && <p role="alert" className="mt-[14px] mb-[27px] bg-[#f0e1df] text-[12px] leading-[1.9] text-danger-ink">{error}</p>}
      <span className="mt-7 flex items-center justify-center gap-1.5 text-[10px] text-[#8d999b]"><Radio size={12} /> {foot}</span>
    </div>
    {caption && <div className="mt-[30px] text-[11px] tracking-[.8px] text-[#828d91]">{caption}</div>}
  </div>;
}

// First run on this PC: optional Tailscale address, then the user's own Google OAuth client.
function Setup({ api, logo, onDone }) {
  const [settings, setSettings] = useState(null);
  const [error, setError] = useState('');
  const load = useCallback(async () => { try { setSettings(await api('/auth/settings')); } catch (e) { setError(e.message); } }, [api]);
  useEffect(() => { load(); }, [load]);
  return <AuthCard logo={logo} wide caption={t('당신의 서버, 손끝에서.')} title={t('StackPad 시작하기')} description={t('Google 계정으로 로그인하도록 설정합니다. 이 PC에서 한 번만 하면 돼요.')} error={error}>
    <div className="mb-1.5 flex flex-col gap-[22px] [&>section]:flex [&>section]:flex-col [&>section]:gap-3 [&_h2]:text-[14px] [&_h2]:text-heading">
      <section><h2>{t('1. 외부 접속')} <span className="optional">{t('선택')}</span></h2><p className="optional">{t('휴대폰에서도 쓰려면 Tailscale로 이 PC에 HTTPS 주소를 연결하세요. 나중에 환경 설정에서 연결해도 됩니다.')}</p>
        <TailscaleConnect api={api} onConnected={load} onError={setError} /></section>
      <section><h2>{t('2. Google 로그인 설정')}</h2><OAuthGuide redirectUris={settings?.redirect_uris} />
        <OAuthClientForm api={api} current={settings} onSaved={onDone} onError={setError} /></section>
    </div>
  </AuthCard>;
}

export function SignIn({ auth, api, logo, onLogin }) {
  const [error, setError] = useState(takeUrlError);
  const [waiting, setWaiting] = useState(false);
  const [editing, setEditing] = useState(false);
  const cancelled = useRef(false);
  useEffect(() => () => { cancelled.current = true; }, []);
  if (!auth.configured || editing) {
    if (!auth.local) return <AuthCard logo={logo} caption={t('당신의 서버, 손끝에서.')} title={t('PC에서 설정을 마쳐 주세요')} description={t('StackPad가 실행 중인 PC에서 Google 로그인 설정을 마친 뒤 다시 접속해 주세요.')} />;
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
  return <AuthCard logo={logo} caption={t('당신의 서버, 손끝에서.')} title={t('컨트롤 룸에 입장하기')} error={error} description={blocked ? t('StackPad가 실행 중인 PC에서 먼저 로그인해 주세요. 처음 로그인한 계정이 소유자가 됩니다.') : !auth.owner ? t('처음 로그인한 Google 계정이 이 StackPad의 소유자로 등록됩니다.') : t('허용된 Google 계정으로 로그인하고 서비스 현황을 확인하세요.')}>
    {!blocked && <div className="mb-1.5 flex flex-col gap-2.5">
      <button className="primary wide" disabled={waiting} onClick={signIn}>{waiting ? <LoaderCircle className="spin" size={17} /> : <ArrowUpRight size={17} />}{waiting ? t('브라우저에서 로그인을 마쳐 주세요') : t('Google로 로그인')}</button>
      {waiting && <button className="secondary wide" onClick={() => { cancelled.current = true; setWaiting(false); }}>{t('취소')}</button>}
      {auth.local && !auth.owner && !waiting && <button className="secondary wide" onClick={() => setEditing(true)}>{t('Google 로그인 설정 다시 입력')}</button>}
    </div>}
  </AuthCard>;
}
