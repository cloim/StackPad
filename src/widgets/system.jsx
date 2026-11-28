import React, { useEffect, useState } from 'react';
import { HistoryChart } from '../components/HistoryChart.jsx';
import { t } from '../i18n.js';

function SystemWidget({ api }) {
  const [snapshot, setSnapshot] = useState(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let active = true;
    let pending = false;
    let timer;
    async function load() {
      if (pending || document.hidden) return;
      pending = true;
      try {
        const data = await api('/system/metrics', { cache: 'no-store' });
        if (active) { setSnapshot(data); setFailed(false); }
      } catch {
        if (active) setFailed(true);
      } finally { pending = false; }
    }
    function visibility() {
      clearInterval(timer);
      if (!document.hidden) {
        load();
        timer = setInterval(load, 2100);
      }
    }
    visibility();
    document.addEventListener('visibilitychange', visibility);
    return () => {
      active = false;
      clearInterval(timer);
      document.removeEventListener('visibilitychange', visibility);
    };
  }, [api]);

  const metrics = [
    ['cpu', 'CPU', t('CPU 사용률')],
    ['memory', t('메모리'), t('메모리 사용률')],
    ['gpu', 'GPU', t('GPU 사용률')],
  ];
  return <section className="min-w-0 rounded-[4px] border border-line bg-well px-2.5 py-1.5 shadow-[inset_0_1px_2px_#45533c20]" aria-label={t('시스템 정보')}>
    <div className="grid min-w-0 grid-cols-3 gap-2">
      {metrics.map(([key, name, label]) => {
        const values = snapshot?.[key] ?? [];
        const current = values.at(-1);
        const ready = !failed && Number.isFinite(current);
        const unavailable = failed || values.length > 1;
        return <div className="min-w-0 rounded-[3px] bg-white/30 px-1.5" key={key} data-system-metric={key}>
          <div className="flex items-center justify-between gap-1 whitespace-nowrap text-[10px] leading-4">
            <span className="font-semibold">{name}</span>
            <span className="tabular-nums text-muted">{ready ? `${Math.round(current)}%` : unavailable ? t('조회 불가') : '…'}</span>
          </div>
          {ready ? <HistoryChart values={values} interval={snapshot.interval} metric={key} label={label} unit="%" compact /> : <div className="h-8" />}
        </div>;
      })}
    </div>
  </section>;
}

export default { name: () => t('시스템 정보'), order: 20, View: SystemWidget };
