import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { UsageProviders } from './components/UsageBar.jsx';
import { t } from './i18n.js';
import './styles.css';
import './tray-usage.css';

document.title = t('AI 사용량');

function TrayUsage() {
  const [snapshot, setSnapshot] = useState(window.__STACKPAD_USAGE__ ?? null);
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const update = () => { setSnapshot(window.__STACKPAD_USAGE__); setNow(Date.now()); };
    const language = event => { if (event.key === 'stackpad-lang') window.location.reload(); };
    window.addEventListener('stackpad-usage', update);
    window.addEventListener('storage', language);
    const timer = setInterval(() => setNow(Date.now()), 10000);
    return () => { window.removeEventListener('stackpad-usage', update); window.removeEventListener('storage', language); clearInterval(timer); };
  }, []);
  // Native snapshots contain no credentials; provider messages use the UI language.
  const providers = snapshot?.providers?.map(provider => ({ ...provider, message: provider.status === 'login_required'
    ? provider.message === 'CLI 사용 시 갱신' ? t('CLI 사용 시 갱신') : t('CLI 로그인 필요')
    : provider.status === 'unavailable' ? t('Antigravity 실행 후 표시') : t('사용량 조회 실패') }));
  return <main className="tray-usage" aria-label={t('AI 사용량')}>
    <header><h1>{t('AI 사용량')}</h1>{snapshot?.update_available && <span className="tray-update">{t('업데이트 가능')}</span>}</header>
    {!snapshot || (!snapshot.error && !Array.isArray(snapshot.providers)) ? <div className="tray-loading" role="status" aria-label={t('사용량 조회 중')}>
      {[0, 1].map(index => <div className="tray-loading-row" key={index}><i className="skeleton"/><i className="skeleton"/><i className="skeleton"/></div>)}
    </div> : snapshot.error ? <p className="tray-message" role="status">{t('사용량 조회 실패')}</p>
      : !providers?.length ? <p className="tray-message" role="status">{t('사용량 표시가 꺼져 있어요.')}</p>
        : <UsageProviders providers={providers} now={now} />}
  </main>;
}

createRoot(document.getElementById('root')).render(<TrayUsage />);
