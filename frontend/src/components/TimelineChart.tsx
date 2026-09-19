/**
 * Activity over time, drawn as inline SVG.
 *
 * Hand-drawn rather than pulled from a charting library: it keeps the bundle
 * small, works offline with no CDN, and the shape needed here — stacked
 * allowed/blocked bars over a time axis — is a few dozen lines.
 */

import { useMemo, useState } from 'react';
import type { Timeline } from '../types/api';
import { formatCompact, formatDateTime } from '../utils/format';

const HEIGHT = 140;
const PADDING_TOP = 8;
const PADDING_BOTTOM = 20;
const MIN_BAR_WIDTH = 2;

function axisLabel(ms: number, bucketSeconds: number): string {
  const date = new Date(ms);
  if (bucketSeconds >= 86_400) {
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  }
  if (bucketSeconds >= 3600) {
    return date.toLocaleString(undefined, { hour: '2-digit', minute: '2-digit', hour12: false });
  }
  return date.toLocaleTimeString(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

export function TimelineChart({
  timeline,
  height = HEIGHT,
  onSelect,
}: {
  timeline: Timeline | null;
  height?: number;
  onSelect?: (fromMs: number, toMs: number) => void;
}) {
  const [hover, setHover] = useState<number | null>(null);

  const points = useMemo(() => timeline?.points ?? [], [timeline]);
  const max = useMemo(() => Math.max(1, ...points.map((point) => point.total)), [points]);

  if (!timeline || !points.length) {
    return (
      <div className="empty" style={{ height, display: 'grid', placeItems: 'center' }}>
        No activity in this period
      </div>
    );
  }

  const plotHeight = height - PADDING_TOP - PADDING_BOTTOM;
  const width = 1000; // viewBox units; the SVG scales to its container
  const slot = width / points.length;
  const barWidth = Math.max(MIN_BAR_WIDTH, slot - Math.min(2, slot * 0.2));

  const labelEvery = Math.max(1, Math.ceil(points.length / 8));
  const active = hover !== null ? points[hover] : null;

  return (
    <div style={{ position: 'relative' }}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        style={{ width: '100%', height, display: 'block' }}
        role="img"
        aria-label="DNS query activity over time"
        onMouseLeave={() => setHover(null)}
      >
        {[0.25, 0.5, 0.75, 1].map((fraction) => (
          <line
            key={fraction}
            x1={0}
            x2={width}
            y1={PADDING_TOP + plotHeight * (1 - fraction)}
            y2={PADDING_TOP + plotHeight * (1 - fraction)}
            stroke="var(--border)"
            strokeWidth={1}
            vectorEffect="non-scaling-stroke"
          />
        ))}

        {points.map((point, index) => {
          const x = index * slot + (slot - barWidth) / 2;
          const totalHeight = (point.total / max) * plotHeight;
          const blockedHeight = (point.blocked / max) * plotHeight;
          const allowedHeight = totalHeight - blockedHeight;
          return (
            <g
              key={point.t}
              onMouseEnter={() => setHover(index)}
              onClick={
                onSelect
                  ? () => onSelect(point.t, point.t + timeline.bucket_seconds * 1000)
                  : undefined
              }
              style={{ cursor: onSelect ? 'pointer' : 'default' }}
            >
              <rect
                x={index * slot}
                y={PADDING_TOP}
                width={slot}
                height={plotHeight}
                fill={hover === index ? 'var(--bg-hover)' : 'transparent'}
              />
              <rect
                x={x}
                y={PADDING_TOP + plotHeight - allowedHeight - blockedHeight}
                width={barWidth}
                height={Math.max(point.allowed > 0 ? 1 : 0, allowedHeight)}
                fill="var(--primary)"
                opacity={hover === null || hover === index ? 1 : 0.55}
              />
              <rect
                x={x}
                y={PADDING_TOP + plotHeight - blockedHeight}
                width={barWidth}
                height={Math.max(point.blocked > 0 ? 1 : 0, blockedHeight)}
                fill="var(--danger)"
                opacity={hover === null || hover === index ? 1 : 0.55}
              />
            </g>
          );
        })}

        <line
          x1={0}
          x2={width}
          y1={PADDING_TOP + plotHeight}
          y2={PADDING_TOP + plotHeight}
          stroke="var(--border-strong)"
          strokeWidth={1}
          vectorEffect="non-scaling-stroke"
        />
      </svg>

      <div
        className="row between faint"
        style={{ fontSize: 10, marginTop: -16, padding: '0 2px', pointerEvents: 'none' }}
      >
        {points
          .filter((_, index) => index % labelEvery === 0)
          .map((point) => (
            <span key={point.t}>{axisLabel(point.t, timeline.bucket_seconds)}</span>
          ))}
      </div>

      <div className="row small" style={{ gap: 14, marginTop: 8 }}>
        <span className="row" style={{ gap: 5 }}>
          <span style={{ width: 9, height: 9, borderRadius: 2, background: 'var(--primary)' }} />
          Allowed
        </span>
        <span className="row" style={{ gap: 5 }}>
          <span style={{ width: 9, height: 9, borderRadius: 2, background: 'var(--danger)' }} />
          Blocked
        </span>
        <span className="spacer" />
        {active ? (
          <span className="muted mono nowrap">
            {formatDateTime(active.t * 1_000_000)} · {formatCompact(active.total)} queries ·{' '}
            {formatCompact(active.blocked)} blocked
          </span>
        ) : (
          <span className="faint">
            {points.length} buckets of {timeline.bucket_seconds}s
          </span>
        )}
      </div>
    </div>
  );
}
