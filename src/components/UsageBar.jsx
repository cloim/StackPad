import React, { useEffect, useState } from 'react';
import { Clock3 } from 'lucide-react';
import { t } from '../i18n.js';
import { shareUsage } from '../native.js';

function remaining(reset, now) {
  if (!reset) return null;
  const timestamp = Date.parse(reset);
  if (!Number.isFinite(timestamp)) return null;
  const minutes = Math.max(0, Math.ceil((timestamp - now) / 60000));
  if (minutes >= 1440) return `${Math.floor(minutes / 1440)}d ${Math.floor(minutes % 1440 / 60)}h`;
  if (minutes >= 60) return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
  return `${minutes}m`;
}

export function UsageBar({ api, expected = 0 }) {
  const [providers, setProviders] = useState(null);
  const [now, setNow] = useState(Date.now());
  const [error, setError] = useState(false);
  useEffect(() => {
    let active = true;
    let pending = false;
    let timer;
    async function load() {
      if (pending || document.visibilityState !== 'visible') return;
      pending = true;
      try {
        const data = await api('/usage');
        shareUsage(data);
        if (active) { setProviders(data.enabled?.length ? data.providers : []); setNow(Date.now()); setError(false); }
      } catch {
        if (active) setError(true);
      } finally { pending = false; }
    }
    function visibility() {
      clearInterval(timer);
      if (document.visibilityState === 'visible') {
        load();
        timer = setInterval(load, 60000);
      }
    }
    visibility();
    document.addEventListener('visibilitychange', visibility);
    return () => { active = false; clearInterval(timer); document.removeEventListener('visibilitychange', visibility); };
  }, [api]);

  return <UsageProviders providers={providers} now={now} error={error} expected={expected} />;
}

export function UsageProviders({ providers, now, error = false, expected = 0 }) {
  // Before the first answer, enabled providers hold their rows with skeletons so the pads below do not jump.
  if (!providers && expected) return <div className="usage-bar" aria-label={t('AI 사용량')} aria-busy="true">
    {error ? <span className="usage-message" role="status">{t('사용량 조회 실패')}</span> : Array.from({ length: expected }, (_, index) => <div className="usage-provider" key={index}><span className="usage-loading skeleton" /><span className="usage-loading skeleton" aria-label={t('사용량 조회 중')} /></div>)}
  </div>;
  if (!providers?.length) return null;
  return <div className="usage-bar" aria-label={t('AI 사용량')}>
    {providers.map(provider =>
      <div className="usage-provider" key={provider.id}>
        <strong>{provider.name}{provider.stale_minutes != null && <small style={{ color: 'var(--muted)', fontSize: 7, fontWeight: 400, marginLeft: 3 }}>{provider.stale_minutes >= 60 ? t('{0}시간 전', Math.floor(provider.stale_minutes / 60)) : t('{0}분 전', provider.stale_minutes)}</small>}</strong>
        {error ? <span className="usage-message" role="status">{t('조회 실패')}</span> : provider.status !== 'ok' ?
          <span className="usage-message">{provider.message || t('조회 실패')}</span> :
          <div className="usage-windows">{provider.windows.map(window => {
            const percent = Math.max(0, Math.min(100, Number(window.used_percent)));
            const reset = remaining(window.resets_at, now);
            const segments = window.key === 'five_hour' ? 5 : window.key === 'weekly' ? 7 : 1;
            return <div className={`usage-window ${percent >= 90 ? 'warning' : percent >= 70 ? 'caution' : ''}`} key={window.key}>
              <span className="usage-label">{window.label}</span>
              <span className="usage-track" data-window={window.key} role="progressbar" aria-label={t('{0} {1} 사용량', provider.name, window.label)} aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}><i style={{ width: `${percent}%` }} /><span className="usage-segments" aria-hidden="true" style={{ gridTemplateColumns: `repeat(${segments}, minmax(0, 1fr))` }}>{Array.from({ length: segments }, (_, index) => <b key={index} />)}</span></span>
              <span className="usage-percent">{Math.round(percent)}%</span>
              <span className="usage-reset">{reset && <><Clock3 size={10} aria-hidden="true" />{reset}</>}</span>
            </div>;
          })}</div>}
      </div>)}
  </div>;
}
