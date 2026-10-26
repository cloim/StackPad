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

// The deck shows providers side by side in one strip; the tray window stacks them with larger text.
const layout = {
  bar: {
    list: 'grid shrink-0 grid-cols-[repeat(auto-fit,minmax(max(400px,calc(50%-10px)),1fr))] gap-x-5 gap-y-0.5 px-3 py-1 text-[10px] leading-5 max-tablet:grid-cols-1 max-tablet:gap-px max-tablet:px-2.5 max-tablet:py-[3px] max-tablet:text-[9px] max-tablet:leading-[18px]',
    provider: 'grid min-w-0 grid-cols-[100px_minmax(0,1fr)] items-center gap-2 whitespace-nowrap max-tablet:grid-cols-[72px_minmax(0,1fr)] max-tablet:gap-1',
    name: 'min-w-0 truncate text-[10px] font-semibold max-tablet:text-[9px]',
    stale: 'ml-[3px] text-[7px]',
    windows: 'grid min-w-0 grid-cols-2 gap-2.5 max-tablet:gap-1.5',
    window: 'grid min-w-0 grid-cols-[14px_minmax(16px,1fr)_28px_46px] items-center gap-1 max-tablet:grid-cols-[12px_minmax(10px,1fr)_24px_30px] max-tablet:gap-0.5',
    track: 'rounded-[1px]',
    percent: '',
    reset: 'inline-flex min-w-0 items-center gap-[3px] overflow-hidden text-[9px] max-tablet:gap-0 max-tablet:text-[8px] max-tablet:[&>svg]:hidden',
    segment: 'border-[#dfe5d9]',
    message: '',
  },
  tray: {
    list: 'flex flex-col px-3 text-[11px] leading-5',
    provider: 'block min-w-0 whitespace-nowrap border-t border-[#c7cbbd] py-3',
    name: 'mb-2 flex min-w-0 items-center justify-between gap-2 truncate text-[12px] leading-[18px] font-semibold',
    stale: 'text-[10px]',
    windows: 'grid grid-cols-1 gap-1.5',
    window: 'grid min-h-5 grid-cols-[20px_minmax(24px,1fr)_34px_76px] items-center gap-[7px]',
    track: 'rounded-[3px]',
    percent: 'text-[11px]',
    reset: 'flex items-center justify-end gap-[3px] text-[10px] [&>svg]:block [&>svg]:size-[11px]',
    segment: 'border-white',
    message: 'block text-[11px] leading-5',
  },
};
// The second and third providers get their own calm colors; caution and warning levels override them.
const providerColors = ['#779d82', '#789cae', '#b28e6f'];
const levelColors = { caution: '#ac865e', warning: '#ac676c' };
const well = 'rounded-[3px] bg-well shadow-[inset_0_1px_2px_#45533c20,0_1px_0_#fffef4,0_0_0_2px_#d1d5c8]';

export function UsageProviders({ providers, now, error = false, expected = 0, variant = 'bar' }) {
  const style = layout[variant];
  const list = `${style.list} ${well} ${variant === 'bar' ? 'border-b border-[#cbd2c1]' : ''}`;
  // Before the first answer, enabled providers hold their rows with skeletons so the pads below do not jump.
  if (!providers && expected) return <div className={list} aria-label={t('AI 사용량')} aria-busy="true">
    {error ? <span className="truncate text-muted" role="status">{t('사용량 조회 실패')}</span> : Array.from({ length: expected }, (_, index) => <div className={style.provider} key={index}><span className="skeleton h-1 w-[100px] rounded-[3px]" /><span className="skeleton h-1 w-full rounded-[3px]" aria-label={t('사용량 조회 중')} /></div>)}
  </div>;
  if (!providers?.length) return null;
  return <div className={list} aria-label={t('AI 사용량')} data-usage-bar>
    {providers.map((provider, index) =>
      <div className={style.provider} key={provider.id} data-usage-provider>
        <strong className={style.name}>{provider.name}{provider.stale_minutes != null && <small className={`${style.stale} font-normal text-muted`}>{provider.stale_minutes >= 60 ? t('{0}시간 전', Math.floor(provider.stale_minutes / 60)) : t('{0}분 전', provider.stale_minutes)}</small>}</strong>
        {error ? <span className={`truncate text-muted ${style.message}`} role="status" data-usage-message>{t('조회 실패')}</span> : provider.status !== 'ok' ?
          <span className={`truncate text-muted ${style.message}`} data-usage-message>{provider.message || t('조회 실패')}</span> :
          <div className={style.windows}>{provider.windows.map(window => {
            const percent = Math.max(0, Math.min(100, Number(window.used_percent)));
            const reset = remaining(window.resets_at, now);
            const segments = window.key === 'five_hour' ? 5 : window.key === 'weekly' ? 7 : 1;
            const level = percent >= 90 ? 'warning' : percent >= 70 ? 'caution' : 'normal';
            const color = levelColors[level] || providerColors[index] || providerColors[0];
            return <div className={style.window} key={window.key} data-usage-level={level}>
              <span className="text-muted">{window.label}</span>
              <span className={`relative block h-1.5 overflow-hidden bg-[#cbd3c3] shadow-[inset_0_1px_2px_#697a5712] ${style.track}`} data-window={window.key} role="progressbar" aria-label={t('{0} {1} 사용량', provider.name, window.label)} aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}><i className="block h-full" style={{ width: `${percent}%`, background: color }} /><span className="pointer-events-none absolute inset-0 grid" aria-hidden="true" style={{ gridTemplateColumns: `repeat(${segments}, minmax(0, 1fr))` }}>{Array.from({ length: segments }, (_, index) => <b key={index} data-usage-segment className={`min-w-0 border-r last:border-r-0 ${style.segment}`} />)}</span></span>
              <span className={`text-right tabular-nums ${style.percent}`} style={{ color }} data-usage-percent>{Math.round(percent)}%</span>
              <span className={`tabular-nums text-muted ${style.reset}`} data-usage-reset>{reset && <><Clock3 size={10} aria-hidden="true" />{reset}</>}</span>
            </div>;
          })}</div>}
      </div>)}
  </div>;
}
