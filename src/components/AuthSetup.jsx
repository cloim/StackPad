import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Check, Copy, Globe, KeyRound, LoaderCircle } from 'lucide-react';
import { t } from '../i18n.js';

export function CopyValue({ value, label }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try { await navigator.clipboard.writeText(value); setCopied(true); setTimeout(() => setCopied(false), 1500); }
    catch { /* 복사를 막은 환경에서는 직접 선택해 복사한다. */ }
  }
  return <div className="copy-value"><code>{value}</code><button type="button" className="secondary" onClick={copy} aria-label={t('{0} 복사', label)}>{copied ? <Check size={13} /> : <Copy size={13} />}{copied ? t('복사됨') : t('복사')}</button></div>;
}

// Tailscale serve gives this PC an HTTPS address that only the user's own devices can reach.
export function TailscaleConnect({ api, onConnected, onError }) {
  const [state, setState] = useState(null);
  const [busy, setBusy] = useState(false);
  const report = useRef(onError);
  report.current = onError;
  const load = useCallback(async () => {
    try { setState(await api('/tailscale')); } catch (e) { setState({ installed: false, running: false, error: e.message }); }
  }, [api]);
  useEffect(() => { load(); }, [load]);
  async function connect() {
    setBusy(true);
    try { const { url } = await api('/tailscale/connect', { method: 'POST' }); await load(); onConnected?.(url); }
    catch (e) { report.current(e.message); } finally { setBusy(false); }
  }
  if (!state) return <div className="widget-device skeleton" aria-label={t('Tailscale 상태 확인 중')} />;
  if (state.url) return <div className="stack-gap"><p className="optional">{t('이 주소로 내 Tailscale 기기에서 접속할 수 있어요.')}</p><CopyValue value={state.url} label={t('외부 주소')} /></div>;
  if (!state.installed) return <p className="optional">{t('Tailscale이 설치되어 있지 않아요. 설치하고 로그인한 뒤 다시 확인해 주세요.')} <a className="text-link" href="https://tailscale.com/download/windows" target="_blank" rel="noreferrer">tailscale.com</a> <button type="button" className="secondary inline-button" onClick={load}>{t('다시 확인')}</button></p>;
  if (!state.running) return <p className="optional">{t('Tailscale에 로그인하고 연결한 뒤 다시 확인해 주세요.')} <button type="button" className="secondary inline-button" onClick={load}>{t('다시 확인')}</button></p>;
  return <div className="settings-actions"><p className="optional">{t('{0}에 HTTPS 주소를 만들어요. 다른 serve 설정은 그대로 둡니다.', state.host)}</p><button type="button" className="primary" disabled={busy} onClick={connect}>{busy ? <LoaderCircle className="spin" size={15} /> : <Globe size={15} />}{t('연결')}</button></div>;
}

export function OAuthClientForm({ api, current, onSaved, onError }) {
  const [clientId, setClientId] = useState(current?.client_id || '');
  const [secret, setSecret] = useState('');
  const [busy, setBusy] = useState(false);
  async function save(event) {
    event.preventDefault();
    setBusy(true);
    try { await api('/auth/client', { method: 'PUT', body: JSON.stringify({ client_id: clientId, client_secret: secret }) }); setSecret(''); await onSaved?.(); }
    catch (e) { onError(e.message); } finally { setBusy(false); }
  }
  return <form className="service-form" onSubmit={save}>
    <label>{t('클라이언트 ID')}<input required value={clientId} onChange={e => setClientId(e.target.value)} placeholder="000000000000-xxxx.apps.googleusercontent.com" autoComplete="off" spellCheck={false} /></label>
    <label>{t('클라이언트 보안 비밀번호')}<input type="password" required={!current?.configured} value={secret} onChange={e => setSecret(e.target.value)} placeholder={current?.configured ? t('바꿀 때만 입력') : 'GOCSPX-…'} autoComplete="off" /></label>
    <div className="settings-actions"><span /><button className="primary" disabled={busy}>{busy ? <LoaderCircle className="spin" size={15} /> : <KeyRound size={15} />}{t('저장')}</button></div>
  </form>;
}

export function OAuthGuide({ redirectUris }) {
  return <div className="connection-guide"><strong>{t('Google OAuth 클라이언트 만들기')}</strong><ol>
    <li>{t('프로젝트를 고르거나 새로 만듭니다:')} <a className="text-link" href="https://console.cloud.google.com/auth/clients" target="_blank" rel="noreferrer">Google Cloud Console</a></li>
    <li>{t("처음이라면 Google 인증 플랫폼을 구성합니다. 대상은 '외부'로 고르고 '테스트 사용자'에 로그인할 Google 계정을 추가하세요. 게시 상태를 '프로덕션'으로 바꾸려면 브랜딩에 홈페이지와 개인정보처리방침 링크가 필요해요.")}</li>
    <li>{t("'클라이언트 만들기'에서 유형을 '웹 애플리케이션'으로 고르고, 승인된 리디렉션 URI에 아래 주소를 모두 추가합니다.")}</li>
    <li>{t('만든 클라이언트 ID와 보안 비밀번호를 아래에 입력합니다.')}</li>
  </ol>{!!redirectUris?.length && <div className="stack-gap guide-values">{redirectUris.map(uri => <CopyValue key={uri} value={uri} label={t('리디렉션 URI')} />)}</div>}
    {redirectUris?.length === 1 && <p className="optional">{t('외부 주소를 연결하면 리디렉션 URI가 하나 더 생겨요. 그때 같은 클라이언트에 추가해 주세요.')}</p>}
  </div>;
}
