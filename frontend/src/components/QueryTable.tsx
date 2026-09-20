/**
 * The log table.
 *
 * Rows are virtualised, so only what fits on screen is in the DOM — the table
 * stays responsive with a hundred thousand rows loaded. Pages come from the
 * backend already filtered and sorted; the browser never holds the full log.
 */

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import type { QueryRow } from '../types/api';
import { Empty, ResultBadge, Spinner, TagChips } from './ui';
import { formatDateTime, formatMs, formatSmart } from '../utils/format';
import { Link } from '../router';
import { useT } from '../i18n/useT';
import type { TranslationKey } from '../i18n';

export interface ColumnDef {
  key: string;
  /** Translated where the column is rendered, not here. */
  label: TranslationKey;
  /** Default sizing, used until the reader drags the column's edge. */
  width: string;
  /** Floor for a drag, so a column cannot be pulled shut and lost. */
  minWidth?: number;
  sortKey?: string;
  align?: 'left' | 'right';
  render: (row: QueryRow) => React.ReactNode;
}

/** Narrowest a column may be dragged when it names no minimum of its own. */
const MIN_COLUMN_WIDTH = 56;

export const ALL_COLUMNS: ColumnDef[] = [
  {
    // Today's rows show the clock alone, older ones the whole stamp — and the
    // whole stamp is what has to fit. It is longer in Hungarian
    // ("2026. 09. 19. 17:28:06") than in English, so the default is sized for
    // the longer of the two rather than for what today happens to render.
    key: 'time',
    label: 'column.time',
    width: '176px',
    minWidth: 72,
    sortKey: 'time',
    render: (row) => (
      <span className="mono nowrap truncate" title={formatDateTime(row.ts_ns)}>
        {formatSmart(row.ts_ns)}
      </span>
    ),
  },
  {
    key: 'domain',
    label: 'column.domain',
    width: 'minmax(220px, 2.2fr)',
    sortKey: 'domain',
    render: (row) => (
      <Link to={`/domains/${row.domain_id}`} className="truncate" title={row.domain}>
        {row.domain}
      </Link>
    ),
  },
  {
    key: 'client',
    label: 'column.device',
    width: 'minmax(130px, 1fr)',
    sortKey: 'client_name',
    render: (row) => (
      <Link
        to={`/devices/${row.client_id}`}
        className="truncate"
        title={`${row.client_name || row.client_ip} (${row.client_ip})`}
      >
        {row.client_name || row.client_ip}
      </Link>
    ),
  },
  {
    key: 'person',
    label: 'column.person',
    width: 'minmax(90px, 0.7fr)',
    sortKey: 'person',
    render: (row) =>
      row.person ? (
        <Link to={`/persons/${row.person_id}`} className="truncate">
          {row.person}
        </Link>
      ) : (
        <span className="faint">—</span>
      ),
  },
  {
    key: 'query_type',
    label: 'column.type',
    width: '64px',
    sortKey: 'query_type',
    render: (row) => <span className="mono">{row.query_type}</span>,
  },
  {
    key: 'result',
    label: 'column.result',
    width: '104px',
    sortKey: 'blocked',
    render: (row) => <ResultBadge result={row.result} />,
  },
  {
    key: 'response_status',
    label: 'column.status',
    width: '90px',
    sortKey: 'response_status',
    render: (row) => <span className="mono small">{row.response_status || '—'}</span>,
  },
  {
    key: 'categories',
    label: 'column.categories',
    width: 'minmax(140px, 1fr)',
    render: (row) => <TagChips tags={row.categories} limit={2} />,
  },
  {
    key: 'tags',
    label: 'column.tags',
    width: 'minmax(140px, 1fr)',
    render: (row) => <TagChips tags={row.tags} limit={2} />,
  },
  {
    key: 'answer',
    label: 'column.answer',
    width: 'minmax(120px, 1fr)',
    render: (row) => (
      <span className="mono small truncate" title={row.answer}>
        {row.answer || '—'}
      </span>
    ),
  },
  {
    key: 'rule',
    label: 'column.rule',
    width: 'minmax(140px, 1fr)',
    render: (row) => (
      <span className="mono small truncate" title={row.rule}>
        {row.rule || '—'}
      </span>
    ),
  },
  {
    key: 'upstream',
    label: 'column.upstream',
    width: 'minmax(130px, 1fr)',
    sortKey: 'upstream',
    render: (row) => (
      <span className="mono small truncate" title={row.upstream}>
        {row.upstream || (row.cached ? 'cache' : '—')}
      </span>
    ),
  },
  {
    key: 'response_time',
    label: 'column.latency',
    width: '80px',
    sortKey: 'response_time',
    align: 'right',
    render: (row) => <span className="mono small">{formatMs(row.response_time_ms)}</span>,
  },
  {
    key: 'client_proto',
    label: 'column.proto',
    width: '70px',
    render: (row) => <span className="mono small">{row.client_proto || 'plain'}</span>,
  },
];

export const DEFAULT_COLUMNS = [
  'time',
  'domain',
  'client',
  'person',
  'query_type',
  'result',
  'categories',
  'tags',
  'response_time',
];

/**
 * The draggable edge between two columns.
 *
 * The move and release listeners go on the window rather than on the handle:
 * during a drag the pointer spends most of its time well away from a 14px
 * strip, and pointer capture alone leaves the column stuck behind the cursor
 * whenever an event misses the element. Double-clicking puts the column back on
 * its default sizing, and the arrow keys do the pointer's job for anyone not
 * using one.
 */
function ResizeHandle({
  label,
  minWidth,
  measure,
  onResize,
  onReset,
}: {
  label: string;
  minWidth: number;
  measure: () => number;
  onResize: (width: number) => void;
  onReset: () => void;
}) {
  const [dragging, setDragging] = useState(false);
  // The width this handle last asked for. Measuring the rendered cell instead
  // would lag a render behind, so a held-down arrow key would keep adding its
  // step to the same stale number rather than to the growing one.
  const pending = useRef<number | null>(null);

  const apply = useCallback(
    (width: number) => {
      const value = Math.max(minWidth, Math.round(width));
      pending.current = value;
      onResize(value);
    },
    [minWidth, onResize],
  );

  const reset = () => {
    pending.current = null;
    onReset();
  };

  const begin = (clientX: number) => {
    const startWidth = measure();
    pending.current = startWidth;
    const move = (event: PointerEvent | MouseEvent) =>
      apply(startWidth + (event.clientX - clientX));
    const end = () => {
      setDragging(false);
      window.removeEventListener('pointermove', move);
      window.removeEventListener('mousemove', move);
      window.removeEventListener('pointerup', end);
      window.removeEventListener('mouseup', end);
    };
    setDragging(true);
    // Both families, because a synthetic mouse event — a remote desktop, a
    // test driver — does not always come with its pointer counterpart.
    window.addEventListener('pointermove', move);
    window.addEventListener('mousemove', move);
    window.addEventListener('pointerup', end);
    window.addEventListener('mouseup', end);
  };

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      tabIndex={0}
      className={dragging ? 'col-resize dragging' : 'col-resize'}
      onPointerDown={(event) => {
        if (event.button !== 0) return;
        event.preventDefault();
        event.stopPropagation();
        begin(event.clientX);
      }}
      onDoubleClick={reset}
      onKeyDown={(event) => {
        const step = event.shiftKey ? 32 : 8;
        const from = pending.current ?? measure();
        if (event.key === 'ArrowLeft') apply(from - step);
        else if (event.key === 'ArrowRight') apply(from + step);
        else if (event.key === 'Enter' || event.key === 'Backspace') reset();
        else return;
        event.preventDefault();
      }}
    />
  );
}

export function QueryTable({
  rows,
  columns,
  widths,
  onResizeColumn,
  onResetColumn,
  sort,
  direction,
  onSort,
  onSelect,
  onLoadMore,
  loading,
  hasMore,
  highlightNewUntilId,
}: {
  rows: QueryRow[];
  columns: string[];
  /** Widths the reader has dragged, by column key. Others size by default. */
  widths: Record<string, number>;
  onResizeColumn: (key: string, width: number) => void;
  onResetColumn: (key: string) => void;
  sort: string;
  direction: 'asc' | 'desc';
  onSort: (key: string) => void;
  onSelect: (row: QueryRow) => void;
  onLoadMore: () => void;
  loading: boolean;
  hasMore: boolean;
  /** Rows with a higher id than this arrived while the user was watching. */
  highlightNewUntilId?: number;
}) {
  const t = useT();
  const parent = useRef<HTMLDivElement>(null);
  const header = useRef<HTMLDivElement>(null);
  const headerCells = useRef(new Map<string, HTMLElement>());

  const visible = useMemo(
    () => ALL_COLUMNS.filter((column) => columns.includes(column.key)),
    [columns],
  );
  const template = useMemo(
    // A dragged column becomes an exact pixel width; the rest keep their
    // default sizing and absorb whatever space is left over.
    () => visible.map((column) => (widths[column.key] ? `${widths[column.key]}px` : column.width)).join(' '),
    [visible, widths],
  );

  const rowHeight = useMemo(() => {
    const value = getComputedStyle(document.documentElement).getPropertyValue('--row-height');
    return Number.parseInt(value, 10) || 38;
  }, []);

  // The header and the rows share one scroll container. They used to be
  // siblings, each clipping on its own, which was fine only while every column
  // was sized to fit: a dragged column can make the grid wider than the card,
  // and a header that does not scroll sideways with its rows is useless.
  const [headerHeight, setHeaderHeight] = useState(0);
  useLayoutEffect(() => {
    const element = header.current;
    if (!element) return;
    const measure = () => setHeaderHeight(element.getBoundingClientRect().height);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parent.current,
    estimateSize: () => rowHeight,
    overscan: 12,
    // The list starts below the sticky header, not at the top of the scroller.
    scrollMargin: headerHeight,
  });

  const handleScroll = useCallback(() => {
    const element = parent.current;
    if (!element || loading || !hasMore) return;
    if (element.scrollHeight - element.scrollTop - element.clientHeight < rowHeight * 20) {
      onLoadMore();
    }
  }, [loading, hasMore, onLoadMore, rowHeight]);

  useEffect(() => {
    // A short page still has to be able to ask for more.
    const element = parent.current;
    if (element && !loading && hasMore && element.scrollHeight <= element.clientHeight) {
      onLoadMore();
    }
  }, [rows.length, loading, hasMore, onLoadMore]);

  const items = virtualizer.getVirtualItems();

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0, flex: '1 1 auto' }}>
      <div
        ref={parent}
        onScroll={handleScroll}
        style={{ flex: '1 1 auto', overflow: 'auto', minHeight: 0 }}
      >
        {/* `max-content` lets the columns keep the widths they were given and
            the scroller take care of the overflow, instead of the grid
            squeezing every column to fit a narrow card. */}
        <div style={{ minWidth: 'max-content' }}>
          <div
            ref={header}
            style={{
              display: 'grid',
              gridTemplateColumns: template,
              gap: 10,
              padding: '0 14px',
              borderBottom: '1px solid var(--border)',
              background: 'var(--bg-elevated)',
              position: 'sticky',
              top: 0,
              zIndex: 2,
            }}
          >
            {visible.map((column) => (
              <div
                key={column.key}
                ref={(element) => {
                  if (element) headerCells.current.set(column.key, element);
                  else headerCells.current.delete(column.key);
                }}
                style={{ position: 'relative', minWidth: 0, display: 'flex' }}
              >
                <button
                  type="button"
                  className="btn ghost sm truncate"
                  disabled={!column.sortKey}
                  onClick={() => column.sortKey && onSort(column.sortKey)}
                  style={{
                    flex: '1 1 auto',
                    justifyContent: column.align === 'right' ? 'flex-end' : 'flex-start',
                    padding: '8px 0',
                    fontSize: 11,
                    textTransform: 'uppercase',
                    letterSpacing: '0.04em',
                    fontWeight: 700,
                    color:
                      column.sortKey === sort ? 'var(--primary-strong)' : 'var(--text-faint)',
                    cursor: column.sortKey ? 'pointer' : 'default',
                    opacity: 1,
                  }}
                >
                  {t(column.label)}
                  {column.sortKey === sort ? (direction === 'desc' ? ' ↓' : ' ↑') : ''}
                </button>
                <ResizeHandle
                  label={t('log.resizeColumn', { column: t(column.label) })}
                  minWidth={column.minWidth ?? MIN_COLUMN_WIDTH}
                  measure={() =>
                    headerCells.current.get(column.key)?.getBoundingClientRect().width ?? 0
                  }
                  onResize={(width) => onResizeColumn(column.key, width)}
                  onReset={() => onResetColumn(column.key)}
                />
              </div>
            ))}
          </div>

        {rows.length === 0 && !loading ? (
          <Empty>{t('log.empty')}</Empty>
        ) : (
          <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
            {items.map((item) => {
              const row = rows[item.index];
              const isNew = highlightNewUntilId !== undefined && row.id > highlightNewUntilId;
              return (
                <div
                  key={row.id}
                  onClick={() => onSelect(row)}
                  style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: '100%',
                    height: item.size,
                    transform: `translateY(${item.start - headerHeight}px)`,
                    display: 'grid',
                    gridTemplateColumns: template,
                    gap: 10,
                    alignItems: 'center',
                    padding: '0 14px',
                    borderBottom: '1px solid var(--border)',
                    cursor: 'pointer',
                    background: isNew ? 'var(--bg-active)' : undefined,
                  }}
                  className="query-row"
                >
                  {visible.map((column) => (
                    <div
                      key={column.key}
                      style={{
                        minWidth: 0,
                        textAlign: column.align ?? 'left',
                        overflow: 'hidden',
                      }}
                    >
                      {column.render(row)}
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
        )}

          {loading ? (
            <div className="row center" style={{ padding: 16, justifyContent: 'center' }}>
              <Spinner label={t('common.loading')} />
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
