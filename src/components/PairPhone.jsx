import React, { useState } from 'react';
import { Link2, LoaderCircle, QrCode, Radio, Smartphone } from 'lucide-react';
import { t } from '../i18n.js';
import { pair, scanPairingCode, serverOrigin } from '../native.js';

// The Android app signs in by scanning the one-time QR code shown in the PC settings.
export function PairPhone({ api, logo, onPaired }) {
  const [link, setLink] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function connect(value) {
    setBusy(true); setError('');
    try { await pair(api, value); onPaired(); }
    catch (e) { setError(e.message === 'INVALID_LINK' ? t('StackPad 연결 QR 코드가 아니에요. PC에서 띄운 QR 코드를 찍어 주세요.') : e.message); }
    finally { setBusy(false); }
  }
  async function scan() {
    setError('');
    try { const value = await scanPairingCode(); if (value) await connect(value); }
    catch (e) { setError(e.message || t('카메라를 열지 못했어요. 연결 링크를 붙여 넣어 주세요.')); }
  }
  return <div className="login-shell"><div className="login-card">
    <div className="brand">{logo}<strong>StackPad</strong></div>
    <div className="login-icon"><Smartphone size={26} /></div>
    <h1>{serverOrigin() ? t('PC와 다시 연결하기') : t('PC와 연결하기')}</h1>
    <p>{t('PC의 StackPad에서 환경 설정 > 계정 > 휴대폰 연결을 열고 QR 코드를 띄운 뒤 스캔하세요. 휴대폰의 Tailscale이 켜져 있어야 해요.')}</p>
    <div className="login-actions">
      <button className="primary wide" disabled={busy} onClick={scan}>{busy ? <LoaderCircle className="spin" size={17} /> : <QrCode size={17} />}{t('QR 코드 스캔')}</button>
    </div>
    <form className="pair-link" onSubmit={event => { event.preventDefault(); connect(link); }}>
      <label>{t('또는 연결 링크 붙여넣기')}<input value={link} onChange={e => setLink(e.target.value)} placeholder="stackpad://pair?…" autoComplete="off" spellCheck={false} /></label>
      <button className="secondary wide" disabled={busy || !link.trim()}><Link2 size={15} />{t('연결')}</button>
    </form>
    {error && <p role="alert" className="inline-error">{error}</p>}
    <span className="login-foot"><Radio size={12} /> {serverOrigin() || t('연결된 PC 없음')}</span>
  </div></div>;
}
