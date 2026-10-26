import React, { useCallback, useEffect, useRef, useState } from 'react';
import QRCode from 'qrcode';
import { LogOut, QrCode, Smartphone, UserPlus, Users } from 'lucide-react';
import { isNative, pinWidget } from '../native.js';
import { ConfirmModal } from './ConfirmModal.jsx';
import { useFieldError } from './FieldError.jsx';
import { t } from '../i18n.js';

function dateLabel(seconds) {
  return new Date(seconds * 1000).toLocaleString(undefined, { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function Accounts({ settings, api, reload, onError }) {
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [removing, setRemoving] = useState(null);
  const fieldError = useFieldError();
  async function run(action) {
    setBusy(true);
    try { await action(); await reload(); } catch (e) { onError(e.message); } finally { setBusy(false); }
  }
  return <section className="settings-card vertical">
    <div className="section-heading"><Users size={22} /><div><h2>{t('허용 계정')}</h2><p>{t('이 Google 계정들만 로그인할 수 있어요. 계정을 삭제하면 그 계정의 로그인도 바로 해제됩니다.')}</p></div></div>
    <div className="mt-4 flex flex-col gap-3.5">{settings.accounts.map(account => <div className="component-row" key={account}>
      <div><strong>{account}</strong>{account === settings.owner && <p>{t('소유자')}</p>}</div>
      {account !== settings.owner && <div className="component-actions"><button className="secondary" disabled={busy} onClick={() => setRemoving(account)} aria-label={t('{0} 삭제', account)}>{t('삭제')}</button></div>}
    </div>)}</div>
    <p className="optional">{t('Google OAuth 클라이언트가 테스트 상태라면 추가한 계정을 Google 인증 플랫폼의 테스트 사용자에도 넣어 주세요.')}</p>
    <form className="compact-input-row" noValidate onSubmit={event => { event.preventDefault(); if (!fieldError.validate(event.currentTarget)) return; run(async () => { await api('/auth/accounts', { method: 'POST', body: JSON.stringify({ email }) }); setEmail(''); }); }}>
      <input type="email" required aria-label={t('추가할 Google 계정')} placeholder="name@gmail.com" value={email} onChange={e => setEmail(e.target.value)} />
      <button className="primary" disabled={busy}><UserPlus size={15} />{t('추가')}</button>
    </form>
    {fieldError.popover}
    <ConfirmModal isOpen={!!removing} title={t('허용 계정 삭제')} confirmLabel={t('삭제')} message={t('{0} 계정을 삭제할까요? 이 계정의 로그인이 바로 해제됩니다.', removing)} onCancel={() => setRemoving(null)} onConfirm={() => { const account = removing; setRemoving(null); run(() => api(`/auth/accounts/${encodeURIComponent(account)}`, { method: 'DELETE' })); }} />
  </section>;
}

// The QR carries the external address and a five-minute, single-use code; the phone app scans it to sign in.
function PhonePairing({ settings, api, onError }) {
  const [pairing, setPairing] = useState(null);
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!pairing) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [pairing]);
  async function show() {
    try {
      const result = await api('/pairing', { method: 'POST' });
      const svg = await QRCode.toString(result.link, { type: 'svg', margin: 1, errorCorrectionLevel: 'M', color: { dark: '#111111', light: '#ffffff' } });
      setPairing({ svg, expires: Date.now() + result.expires_in * 1000 }); setNow(Date.now());
    } catch (e) { onError(e.message); }
  }
  const left = pairing ? Math.max(0, Math.round((pairing.expires - now) / 1000)) : 0;
  return <section className="settings-card vertical">
    <div className="flex flex-wrap items-center justify-end gap-2"><div className="section-heading mr-auto min-w-[220px] flex-1"><QrCode size={22} /><div><h2>{t('휴대폰 연결')}</h2><p>{t('휴대폰에 Tailscale과 StackPad Android 앱을 설치하고, 앱에서 이 QR 코드를 찍으면 바로 연결돼요.')}</p></div></div>
      <button className="secondary min-h-8 px-[11px] py-1.5 text-[12px]" disabled={!settings.external_url} onClick={show}>{pairing ? t('새 QR 코드') : t('QR 코드 표시')}</button></div>
    {!settings.external_url && <p className="optional">{t('휴대폰 연결을 사용하려면 StackPad에 외부 주소가 설정되어 있어야 해요.')}</p>}
    {pairing && (left > 0 ? <div className="flex flex-col items-center gap-2.5"><div className="w-[220px] max-w-full rounded-lg bg-white p-2 [&_svg]:block [&_svg]:h-auto [&_svg]:w-full" role="img" aria-label={t('휴대폰 연결 QR 코드')} dangerouslySetInnerHTML={{ __html: pairing.svg }} /><p className="optional">{t('{0}분 {1}초 동안 한 번 사용할 수 있어요.', Math.floor(left / 60), left % 60)}</p></div>
      : <p className="optional">{t('QR 코드가 만료되었습니다. 새 QR 코드를 띄워 주세요.')}</p>)}
    <p className="optional">{t('Android 앱 내려받기:')} <a className="text-[#8b715b] underline underline-offset-[3px]" href="https://github.com/cloim/StackPad/releases/latest" target="_blank" rel="noreferrer">GitHub Releases</a>. {t('iPhone은 Safari에서 외부 주소를 열고 홈 화면에 추가하세요.')}</p>
  </section>;
}

function Devices({ api, onError }) {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [revoking, setRevoking] = useState(null);
  const report = useRef(onError);
  report.current = onError;
  const load = useCallback(async () => {
    try { setData(await api('/devices')); } catch (e) { setData({ devices: [] }); report.current(e.message); }
  }, [api]);
  useEffect(() => { load(); }, [load]);
  async function revoke(device) {
    setBusy(true);
    try { await api(`/devices/${device.id}`, { method: 'DELETE' }); await load(); }
    catch (e) { onError(e.message); } finally { setBusy(false); }
  }
  return <section className="settings-card vertical">
    <div className="flex flex-wrap items-center justify-end gap-2"><div className="section-heading mr-auto min-w-[220px] flex-1"><Smartphone size={22} /><div><h2>{t('연결된 기기')}</h2><p>{t('QR 코드로 연결한 휴대폰입니다. 해제하면 앱과 홈 화면 위젯의 연결이 바로 끊어져요.')}</p></div></div>
      {isNative && <button className="secondary min-h-8 px-[11px] py-1.5 text-[12px]" onClick={() => pinWidget().catch(e => onError(e.message))}>{t('위젯 추가')}</button>}</div>
    {data === null ? <div className="skeleton h-[52px] rounded-lg" aria-label={t('연결된 기기 불러오는 중')} /> : !data.devices.length ? <p className="optional">{t('연결된 기기가 없습니다.')}</p> : <div className="mt-4 flex flex-col gap-3.5">{data.devices.map(device => <div className="component-row" key={device.id}>
      <div><strong>{device.name}{device.id === data.current ? t(' (이 기기)') : ''}</strong><p>{device.email} {t('| 연결')} {dateLabel(device.created_at)}</p></div>
      <div className="component-actions"><button className="secondary" disabled={busy} onClick={() => setRevoking(device)} aria-label={t('{0} 연결 해제', device.name)}>{t('해제')}</button></div>
    </div>)}</div>}
    <ConfirmModal isOpen={!!revoking} title={t('기기 연결 해제')} confirmLabel={t('해제')} message={t('{0} 연결을 해제할까요? 앱과 홈 화면 위젯의 연결이 바로 끊어집니다.', revoking?.name)} onCancel={() => setRevoking(null)} onConfirm={() => { const device = revoking; setRevoking(null); revoke(device); }} />
  </section>;
}

export function AccountSettings({ auth, api, onError, onLogout }) {
  const [settings, setSettings] = useState(null);
  const report = useRef(onError);
  report.current = onError;
  const load = useCallback(async () => {
    if (!auth.local) return;
    try { setSettings(await api('/auth/settings')); } catch (e) { report.current(e.message); }
  }, [api, auth.local]);
  useEffect(() => { load(); }, [load]);
  return <>
    <section className="settings-card"><div className="settings-icon"><LogOut size={22} /></div><div><h2>{auth.email}</h2><p>{isNative ? t('이 기기의 로그인을 해제합니다.') : t('이 브라우저의 로그인을 해제합니다.')}</p></div><button className="secondary ml-auto min-h-9 shrink-0 px-3.5 py-[7px] text-[12px]" onClick={onLogout}>{t('로그아웃')}</button></section>
    {!auth.local && <p className="optional">{t('허용 계정과 휴대폰 연결은 StackPad가 실행 중인 PC에서 설정할 수 있어요.')}</p>}
    {settings && <>
      <Accounts {...{ settings, api, onError }} reload={load} />
      <PhonePairing {...{ settings, api, onError }} />
    </>}
    <Devices {...{ api, onError }} />
  </>;
}
