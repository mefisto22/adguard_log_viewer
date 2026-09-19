/** Small presentational building blocks used across the pages. */

import type { ReactNode } from 'react';
import { useEffect } from 'react';
import { colorFor, formatCompact } from '../utils/format';
import type { ResultKind, TagRef } from '../types/api';

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="row" style={{ gap: 8 }}>
      <span className="spinner" aria-hidden />
      {label ? <span className="muted small">{label}</span> : null}
    </span>
  );
}

export function Banner({
  kind = 'info',
  title,
  children,
  action,
}: {
  kind?: 'info' | 'warn' | 'error';
  title?: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className={`banner ${kind}`} role={kind === 'error' ? 'alert' : undefined}>
      <div style={{ flex: '1 1 auto' }}>
        {title ? <strong style={{ display: 'block' }}>{title}</strong> : null}
        {children}
      </div>
      {action}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function Chip({
  label,
  color,
  onRemove,
  onClick,
  title,
}: {
  label: string;
  color?: string;
  onRemove?: () => void;
  onClick?: () => void;
  title?: string;
}) {
  const dot = color || colorFor(label);
  return (
    <span
      className={`chip${onRemove ? ' removable' : ''}`}
      title={title ?? label}
      onClick={onClick}
      style={onClick ? { cursor: 'pointer' } : undefined}
    >
      <span className="dot" style={{ background: dot }} />
      <span className="truncate">{label}</span>
      {onRemove ? (
        <button
          type="button"
          aria-label={`Remove ${label}`}
          onClick={(event) => {
            event.stopPropagation();
            onRemove();
          }}
        >
          ×
        </button>
      ) : null}
    </span>
  );
}

export function TagChips({ tags, limit = 4 }: { tags: TagRef[]; limit?: number }) {
  if (!tags.length) return <span className="faint">—</span>;
  const shown = tags.slice(0, limit);
  const rest = tags.length - shown.length;
  // Kept on a single line: the log table has a fixed row height, so wrapping
  // chips would spill into the row below.
  return (
    <span className="row" style={{ gap: 4, flexWrap: 'nowrap', overflow: 'hidden' }}>
      {shown.map((tag) => (
        <Chip key={tag.name} label={tag.name} color={tag.color} />
      ))}
      {rest > 0 ? (
        <span className="faint small nowrap" title={tags.map((tag) => tag.name).join(', ')}>
          +{rest}
        </span>
      ) : null}
    </span>
  );
}

const RESULT_LABELS: Record<ResultKind, string> = {
  allowed: 'Allowed',
  blocked: 'Blocked',
  rewritten: 'Rewritten',
  allowlisted: 'Allowed (list)',
  error: 'Error',
};

export function ResultBadge({ result }: { result: ResultKind }) {
  return <span className={`badge ${result}`}>{RESULT_LABELS[result] ?? result}</span>;
}

export function StatCard({
  label,
  value,
  sub,
  accent,
  onClick,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  accent?: string;
  onClick?: () => void;
}) {
  return (
    <div
      className="card"
      onClick={onClick}
      style={{ padding: '12px 14px', cursor: onClick ? 'pointer' : undefined }}
    >
      <div className="small muted" style={{ marginBottom: 2 }}>
        {label}
      </div>
      <div style={{ fontSize: 24, fontWeight: 650, color: accent, lineHeight: 1.15 }}>{value}</div>
      {sub ? <div className="small faint">{sub}</div> : null}
    </div>
  );
}

export interface TopListItem {
  key: string;
  label: string;
  count: number;
  blocked?: number;
  color?: string;
  onClick?: () => void;
}

export function TopList({
  items,
  emptyLabel = 'No data in this period',
}: {
  items: TopListItem[];
  emptyLabel?: string;
}) {
  if (!items.length) return <Empty>{emptyLabel}</Empty>;
  const max = Math.max(...items.map((item) => item.count), 1);
  return (
    <div className="grid" style={{ gap: 4 }}>
      {items.map((item) => (
        <div
          key={item.key}
          className="row"
          style={{ gap: 10, cursor: item.onClick ? 'pointer' : undefined }}
          onClick={item.onClick}
        >
          <div style={{ flex: '1 1 auto', minWidth: 0, overflow: 'hidden' }}>
            <div className="row" style={{ gap: 6, minWidth: 0 }}>
              {item.color ? (
                <span
                  className="dot"
                  style={{ width: 8, height: 8, borderRadius: 4, background: item.color }}
                />
              ) : null}
              <span className="truncate" title={item.label}>
                {item.label}
              </span>
            </div>
            <div
              style={{
                height: 4,
                maxWidth: '100%',
                borderRadius: 2,
                background: 'var(--bg-sunken)',
                marginTop: 3,
                overflow: 'hidden',
              }}
            >
              <div
                style={{
                  width: `${(item.count / max) * 100}%`,
                  height: '100%',
                  background: 'var(--primary)',
                }}
              />
            </div>
          </div>
          <div className="right mono nowrap" style={{ minWidth: 64 }}>
            {formatCompact(item.count)}
            {item.blocked ? (
              <span className="faint" title={`${item.blocked} blocked`}>
                {' '}
                / {formatCompact(item.blocked)}
              </span>
            ) : null}
          </div>
        </div>
      ))}
    </div>
  );
}

export function Modal({
  title,
  children,
  onClose,
  footer,
  wide,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  footer?: ReactNode;
  wide?: boolean;
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div
        className="modal"
        style={wide ? { width: 'min(980px, 100%)' } : undefined}
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <header>
          <h2 style={{ flex: '1 1 auto' }}>{title}</h2>
          <button type="button" className="btn ghost icon" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>
        <div className="body">{children}</div>
        {footer ? <footer>{footer}</footer> : null}
      </div>
    </div>
  );
}

export function Drawer({
  title,
  children,
  onClose,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} role="presentation" />
      <aside className="drawer" role="dialog" aria-label={title}>
        <header>
          <h2 style={{ flex: '1 1 auto' }}>{title}</h2>
          <button type="button" className="btn ghost icon" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>
        <div className="body">{children}</div>
      </aside>
    </>
  );
}

export function Section({
  title,
  actions,
  children,
  bodyStyle,
}: {
  title: string;
  actions?: ReactNode;
  children: ReactNode;
  bodyStyle?: React.CSSProperties;
}) {
  return (
    <section className="card">
      <div className="card-header">
        <h2>{title}</h2>
        {actions}
      </div>
      <div className="card-body" style={bodyStyle}>
        {children}
      </div>
    </section>
  );
}
