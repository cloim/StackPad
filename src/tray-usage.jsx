import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { UsageProviders } from './components/UsageBar.jsx';
import { t } from './i18n.js';
import './theme.css';
import './styles.css';
import './tray-usage.css';
import './cream.css';

document.title = 'StackPad';

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
  return <main className="h-full overflow-auto border border-[#c2c7b6] bg-surface p-4 text-ink" aria-label={t('AI 사용량')}>
    <header className="flex items-center justify-between gap-2 pb-3"><h1 className="text-[14px] leading-5 font-bold tracking-[-.2px] text-[#555c51]">StackPad</h1>{snapshot?.update_available && <span className="text-[10px] text-[#8b715b]">{t('업데이트 가능')}</span>}</header>
    {!snapshot || (!snapshot.error && !Array.isArray(snapshot.providers)) ? <div role="status" aria-label={t('사용량 조회 중')}>
      {[0, 1].map(index => <div className="grid gap-2 border-t border-[#c7cbbd] py-3" key={index}><i className="skeleton mb-1 h-3 w-[78px] rounded-[3px]"/><i className="skeleton h-1.5 rounded-[3px]"/><i className="skeleton h-1.5 rounded-[3px]"/></div>)}
    </div> : snapshot.error ? <p className="block py-2.5 text-[11px] leading-5 text-muted" role="status">{t('사용량 조회 실패')}</p>
      : !providers?.length ? <p className="block py-2.5 text-[11px] leading-5 text-muted" role="status">{t('사용량 표시가 꺼져 있어요.')}</p>
        : <UsageProviders providers={providers} now={now} variant="tray" />}
  </main>;
}

createRoot(document.getElementById('root')).render(<TrayUsage />);
