/**
 * The log table.
 *
 * Rows are virtualised, so only what fits on screen is in the DOM — the table
 * stays responsive with a hundred thousand rows loaded. Pages come from the
 * backend already filtered and sorted; the browser never holds the full log.
 */

import { useCallback, useEffect, useMemo, useRef } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import type { QueryRow } from '../types/api';
import { Empty, ResultBadge, Spinner, TagChips } from './ui';
import { formatMs, formatSmart } from '../utils/format';
import { Link } from '../router';

export interface ColumnDef {
  key: string;
  label: string;
  width: string;
  sortKey?: string;
  align?: 'left' | 'right';
  render: (row: QueryRow) => React.ReactNode;
}

export const ALL_COLUMNS: ColumnDef[] = [
  {
    key: 'time',
    label: 'Time',
    width: '108px',
    sortKey: 'time',
    render: (row) => <span className="mono nowrap">{formatSmart(row.ts_ns)}</span>,
  },
  {
    key: 'domain',
    label: 'Domain',
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
    label: 'Device',
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
    label: 'Person',
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
    label: 'Type',
    width: '64px',
    sortKey: 'query_type',
    render: (row) => <span className="mono">{row.query_type}</span>,
  },
  {
    key: 'result',
    label: 'Result',
    width: '104px',
    sortKey: 'blocked',
    render: (row) => <ResultBadge result={row.result} />,
  },
  {
    key: 'response_status',
    label: 'Status',
    width: '90px',
    sortKey: 'response_status',
    render: (row) => <span className="mono small">{row.response_status || '—'}</span>,
  },
  {
    key: 'categories',
    label: 'Categories',
    width: 'minmax(140px, 1fr)',
    render: (row) => <TagChips tags={row.categories} limit={2} />,
  },
  {
    key: 'tags',
    label: 'Tags',
    width: 'minmax(140px, 1fr)',
    render: (row) => <TagChips tags={row.tags} limit={2} />,
  },
  {
    key: 'answer',
    label: 'Answer',
    width: 'minmax(120px, 1fr)',
    render: (row) => (
      <span className="mono small truncate" title={row.answer}>
        {row.answer || '—'}
      </span>
    ),
  },
  {
    key: 'rule',
    label: 'Rule',
    width: 'minmax(140px, 1fr)',
    render: (row) => (
      <span className="mono small truncate" title={row.rule}>
        {row.rule || '—'}
      </span>
    ),
  },
  {
    key: 'upstream',
    label: 'Upstream',
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
    label: 'Latency',
    width: '80px',
    sortKey: 'response_time',
    align: 'right',
    render: (row) => <span className="mono small">{formatMs(row.response_time_ms)}</span>,
  },
  {
    key: 'client_proto',
    label: 'Proto',
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

export function QueryTable({
  rows,
  columns,
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
  const parent = useRef<HTMLDivElement>(null);

  const visible = useMemo(
    () => ALL_COLUMNS.filter((column) => columns.includes(column.key)),
    [columns],
  );
  const template = useMemo(
    () => visible.map((column) => column.width).join(' '),
    [visible],
  );

  const rowHeight = useMemo(() => {
    const value = getComputedStyle(document.documentElement).getPropertyValue('--row-height');
    return Number.parseInt(value, 10) || 38;
  }, []);

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parent.current,
    estimateSize: () => rowHeight,
    overscan: 12,
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
        style={{
          display: 'grid',
          gridTemplateColumns: template,
          gap: 10,
          padding: '0 14px',
          borderBottom: '1px solid var(--border)',
          background: 'var(--bg-elevated)',
          flex: '0 0 auto',
        }}
      >
        {visible.map((column) => (
          <button
            key={column.key}
            type="button"
            className="btn ghost sm"
            disabled={!column.sortKey}
            onClick={() => column.sortKey && onSort(column.sortKey)}
            style={{
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
            {column.label}
            {column.sortKey === sort ? (direction === 'desc' ? ' ↓' : ' ↑') : ''}
          </button>
        ))}
      </div>

      <div
        ref={parent}
        onScroll={handleScroll}
        style={{ flex: '1 1 auto', overflow: 'auto', minHeight: 0 }}
      >
        {rows.length === 0 && !loading ? (
          <Empty>No DNS queries match this filter.</Empty>
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
                    transform: `translateY(${item.start}px)`,
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
            <Spinner label="Loading…" />
          </div>
        ) : null}
      </div>
    </div>
  );
}
