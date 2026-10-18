import React from 'react';

/**
 * 60 columns x 8 rows dot matrix sparkline in LCD style.
 * Latest point is at the right.
 * CPU is fixed 0-100%, memory is normalized to the maximum value in the range.
 */
export default function DotMatrix({ data = [], type = 'cpu' }) {
  const COLS = 60;
  const ROWS = 8;
  const values = Array.isArray(data) ? data : [];
  const maxVal = type === 'cpu'
    ? 100
    : Math.max(...values, 1);

  // Align to the right: rightmost column is the most recent data point
  const offset = Math.max(0, COLS - values.length);

  // Build a 60-element array where empty slots have null
  const colValues = Array.from({ length: COLS }, (_, colIdx) => {
    const dataIdx = colIdx - offset;
    return dataIdx >= 0 && dataIdx < values.length ? values[dataIdx] : null;
  });

  return (
    <svg
      className="dot-matrix-svg"
      viewBox="0 0 240 32"
      width="100%"
      height="32"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      {colValues.map((val, col) => {
        let litCount = 0;
        if (val !== null && val > 0 && maxVal > 0) {
          const ratio = Math.min(1, Math.max(0, val / maxVal));
          litCount = Math.min(ROWS, Math.max(1, Math.round(ratio * ROWS)));
        }
        return (
          <g key={col}>
            {Array.from({ length: ROWS }, (_, row) => {
              // row 0 is top (y = 0), row 7 is bottom (y = 28)
              // lit starts from bottom (row 7) upwards
              const isLit = (ROWS - 1 - row) < litCount;
              return (
                <rect
                  key={row}
                  x={col * 4}
                  y={row * 4}
                  width={3}
                  height={3}
                  rx={0.5}
                  fill={isLit ? '#a9d6bb' : 'rgba(169, 214, 187, 0.08)'}
                />
              );
            })}
          </g>
        );
      })}
    </svg>
  );
}
