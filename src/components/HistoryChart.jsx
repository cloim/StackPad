import React from 'react';
import { ResponsiveLine } from '@nivo/line';
import { t } from '../i18n.js';

// SVG attributes cannot read CSS variables, so the chart takes the cream LCD colors directly.
const LINE = '#4f6f49';
const theme = {
  text: { fontFamily: 'inherit', fontSize: 11 },
  crosshair: { line: { stroke: '#6e8063', strokeWidth: 1, strokeOpacity: 1 } },
};

function ago(seconds) {
  if (seconds === 0) return t('지금');
  return seconds < 60 ? t('{0}초 전', seconds) : t('{0}분 {1}초 전', Math.floor(seconds / 60), seconds % 60);
}

// Recent CPU or memory samples; CPU is fixed to 0-100% and memory scales to its own range.
export function HistoryChart({ values, interval = 10, metric }) {
  const unit = metric === 'cpu' ? '%' : 'MB';
  const label = metric === 'cpu' ? t('CPU 사용률') : t('메모리 사용량');
  const points = values.map((y, index) => ({ x: index, y, seconds: (values.length - 1 - index) * interval }));
  return <div data-history-chart className="mt-1.5 mb-2.5 h-16" role="img" aria-label={t('{0} 최근 {1}개 기록, 현재 {2}{3}', label, values.length, values.at(-1) ?? 0, unit)}>
    <ResponsiveLine
      data={[{ id: metric, data: points }]}
      margin={{ top: 6, right: 4, bottom: 4, left: 4 }}
      xScale={{ type: 'linear', min: 0, max: Math.max(1, values.length - 1) }}
      yScale={{ type: 'linear', min: 0, max: metric === 'cpu' ? 100 : 'auto' }}
      curve="monotoneX"
      colors={[LINE]}
      lineWidth={2}
      enableArea
      areaOpacity={0.18}
      enablePoints={false}
      enableGridX={false}
      enableGridY={false}
      axisTop={null}
      axisRight={null}
      axisBottom={null}
      axisLeft={null}
      enableSlices="x"
      animate={false}
      theme={theme}
      sliceTooltip={({ slice }) => {
        const point = slice.points[0].data;
        return <div data-chart-tooltip className="flex flex-col gap-0.5 rounded-md border border-line bg-raised px-2.5 py-1.5 text-[12px] leading-[1.4] whitespace-nowrap text-ink-strong shadow-[0_6px_18px_#34442b24]">
          <span className="text-[11px] text-muted">{ago(point.seconds)}</span>
          <span><span className="mr-2 text-muted">{label}</span><strong>{point.y}{unit}</strong></span>
        </div>;
      }}
    />
  </div>;
}
