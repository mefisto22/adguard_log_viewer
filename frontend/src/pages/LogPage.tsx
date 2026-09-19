/**
 * The main log view.
 *
 * Paging uses a keyset cursor (`before_id`) while the default newest-first sort
 * is active, so rows arriving at the top never shift the page under the user.
 * Any other sort falls back to offset paging, and live prepending is disabled
 * there because the position of a new row is not knowable without a refetch.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { FilterBar } from '../components/FilterBar';
import { ALL_COLUMNS, DEFAULT_COLUMNS, QueryTable } from '../components/QueryTable';
import { QueryDetail } from '../components/QueryDetail';
import { Banner, Drawer, Spinner } from '../components/ui';
import { endpoints } from '../api/endpoints';
import type { QueryRequest } from '../api/endpoints';
import { useAppStore } from '../stores/useAppStore';
import { useFilterStore } from '../stores/useFilterStore';
import { useLiveUpdates } from '../hooks/useLiveUpdates';
import { formatCompact, formatRelative } from '../utils/format';
import { useT } from '../i18n/useT';
import type { QueryRow } from '../types/api';

const PAGE_SIZE = 150;

export function LogPage() {
  const t = useT();
  const filters = useFilterStore();
  const revision = useFilterStore((state) => state.revision);
  const { liveUpdates, setLiveUpdates, pageSize } = useAppStore();

  const [rows, setRows] = useState<QueryRow[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [capped, setCapped] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<QueryRow | null>(null);
  const [columns, setColumns] = useState<string[]>(DEFAULT_COLUMNS);
  const [columnsOpen, setColumnsOpen] = useState(false);
  const [newCount, setNewCount] = useState(0);
  // 0 until the first successful load; `formatRelative` renders that as 'never'.
  const [lastRefresh, setLastRefresh] = useState(0);

  const [baselineId, setBaselineId] = useState(0);
  const requestToken = useRef(0);
  const isLiveSort = filters.sort === 'time' && filters.direction === 'desc';

  const { lastEvent, connected, mode } = useLiveUpdates();

  useEffect(() => {
    const raw = localStorage.getItem('aglv.columns');
    if (raw) {
      try {
        const parsed = JSON.parse(raw) as string[];
        if (Array.isArray(parsed) && parsed.length) setColumns(parsed);
      } catch {
        /* a corrupted preference just means the defaults are used */
      }
    }
  }, []);

  const persistColumns = (next: string[]) => {
    setColumns(next);
    try {
      localStorage.setItem('aglv.columns', JSON.stringify(next));
    } catch {
      /* private mode: the choice simply does not persist */
    }
  };

  const baseRequest = useCallback(
    (): QueryRequest => ({
      ...filters.buildRequest(),
      limit: Math.min(PAGE_SIZE, Math.max(pageSize, 50)),
    }),
    // The store is a snapshot; `revision` is what actually changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [revision, pageSize],
  );

  /** Load the first page and replace whatever is on screen. */
  const reload = useCallback(async () => {
    const token = ++requestToken.current;
    setLoading(true);
    try {
      const page = await endpoints.searchQueries({ ...baseRequest(), include_total: true });
      if (token !== requestToken.current) return;
      setRows(page.items);
      setTotal(page.total);
      setCapped(page.total_capped);
      setHasMore(page.has_more);
      setBaselineId(page.items[0]?.id ?? page.newest_id);
      setNewCount(0);
      setError(null);
      setLastRefresh(Date.now());
    } catch (err) {
      if (token !== requestToken.current) return;
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      if (token === requestToken.current) setLoading(false);
    }
  }, [baseRequest]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const loadMore = useCallback(async () => {
    if (loading || !hasMore || rows.length === 0) return;
    const token = requestToken.current;
    setLoading(true);
    try {
      const request: QueryRequest = { ...baseRequest(), include_total: false };
      if (isLiveSort) request.before_id = rows[rows.length - 1].id;
      else request.offset = rows.length;

      const page = await endpoints.searchQueries(request);
      if (token !== requestToken.current) return;
      setRows((current) => {
        const seen = new Set(current.map((row) => row.id));
        return [...current, ...page.items.filter((row) => !seen.has(row.id))];
      });
      setHasMore(page.has_more);
    } catch (err) {
      if (token === requestToken.current) {
        setError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      if (token === requestToken.current) setLoading(false);
    }
  }, [loading, hasMore, rows, baseRequest, isLiveSort]);

  /** Pull only the rows that appeared since the newest one on screen. */
  const fetchDelta = useCallback(async () => {
    if (!isLiveSort || rows.length === 0) return;
    const token = requestToken.current;
    try {
      const page = await endpoints.searchQueries({
        ...baseRequest(),
        include_total: false,
        after_id: rows[0].id,
        limit: 200,
      });
      if (token !== requestToken.current || page.items.length === 0) return;
      setRows((current) => {
        const seen = new Set(current.map((row) => row.id));
        const fresh = page.items.filter((row) => !seen.has(row.id));
        if (!fresh.length) return current;
        setNewCount((count) => count + fresh.length);
        setTotal((value) => (value === null ? value : value + fresh.length));
        return [...fresh, ...current];
      });
      setLastRefresh(Date.now());
    } catch {
      /* the next event will try again */
    }
  }, [isLiveSort, rows, baseRequest]);

  useEffect(() => {
    if (!lastEvent) return;
    if (lastEvent.type === 'cleanup') {
      void reload();
      return;
    }
    void fetchDelta();
    // Only react to a genuinely new event.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastEvent?.at_ns, lastEvent?.type]);

  const onSort = (key: string) => {
    if (filters.sort === key) {
      filters.setSort(key, filters.direction === 'desc' ? 'asc' : 'desc');
    } else {
      filters.setSort(key, 'desc');
    }
  };

  return (
    <div className="main flush">
      <FilterBar />

      <div
        className="row wrap"
        style={{
          gap: 10,
          padding: '8px 14px',
          borderBottom: '1px solid var(--border)',
          background: 'var(--bg-sunken)',
          fontSize: 12,
        }}
      >
        <span className="muted">
          {t('log.matching', {
            count: total === null ? '—' : `${formatCompact(total)}${capped ? '+' : ''}`,
          })}
          {rows.length ? t('log.showing', { count: formatCompact(rows.length) }) : ''}
        </span>

        {newCount > 0 ? (
          <span className="badge allowlisted">
            {t('log.new', { count: formatCompact(newCount) })}
          </span>
        ) : null}

        <span className="spacer" />

        <button
          type="button"
          className="btn sm ghost"
          onClick={() => setLiveUpdates(!liveUpdates)}
          title={
            liveUpdates
              ? mode === 'stream'
                ? t('log.liveOnStream')
                : t('log.liveOnPolling')
              : t('log.liveOff')
          }
        >
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: 4,
              background: liveUpdates
                ? connected || mode === 'poll'
                  ? 'var(--success)'
                  : 'var(--warning)'
                : 'var(--text-faint)',
              display: 'inline-block',
            }}
          />
          {liveUpdates ? t('log.live') : t('log.paused')}
        </button>

        <span className="faint nowrap">
          {t('log.updated', { when: formatRelative(lastRefresh * 1_000_000) })}
        </span>

        <button type="button" className="btn sm" onClick={() => void reload()}>
          {t('common.refresh')}
        </button>

        <div style={{ position: 'relative' }}>
          <button type="button" className="btn sm" onClick={() => setColumnsOpen((v) => !v)}>
            {t('log.columns')}
          </button>
          {columnsOpen ? (
            <div
              className="card"
              style={{
                position: 'absolute',
                right: 0,
                top: 'calc(100% + 4px)',
                width: 220,
                padding: 6,
                zIndex: 40,
                boxShadow: 'var(--shadow-lg)',
              }}
              onMouseLeave={() => setColumnsOpen(false)}
            >
              {ALL_COLUMNS.map((column) => (
                <label
                  key={column.key}
                  className="row"
                  style={{ gap: 8, padding: '4px 6px', cursor: 'pointer' }}
                >
                  <input
                    type="checkbox"
                    checked={columns.includes(column.key)}
                    onChange={() =>
                      persistColumns(
                        columns.includes(column.key)
                          ? columns.filter((key) => key !== column.key)
                          : ALL_COLUMNS.filter(
                              (item) => columns.includes(item.key) || item.key === column.key,
                            ).map((item) => item.key),
                      )
                    }
                  />
                  {t(column.label)}
                </label>
              ))}
              <button
                type="button"
                className="btn sm ghost"
                style={{ width: '100%', marginTop: 4 }}
                onClick={() => persistColumns(DEFAULT_COLUMNS)}
              >
                {t('log.resetColumns')}
              </button>
            </div>
          ) : null}
        </div>
      </div>

      {error ? (
        <div style={{ padding: 12 }}>
          <Banner
            kind="error"
            title={t('log.loadFailed')}
            action={
              <button type="button" className="btn sm" onClick={() => void reload()}>
                {t('common.retry')}
              </button>
            }
          >
            {error}
          </Banner>
        </div>
      ) : null}

      {loading && rows.length === 0 ? (
        <div style={{ padding: 24 }}>
          <Spinner label={t('log.loadingLog')} />
        </div>
      ) : (
        <QueryTable
          rows={rows}
          columns={columns}
          sort={filters.sort}
          direction={filters.direction}
          onSort={onSort}
          onSelect={setSelected}
          onLoadMore={() => void loadMore()}
          loading={loading}
          hasMore={hasMore}
          highlightNewUntilId={newCount > 0 ? baselineId : undefined}
        />
      )}

      {selected ? (
        <Drawer title={t('detail.title')} onClose={() => setSelected(null)}>
          <QueryDetail row={selected} />
        </Drawer>
      ) : null}
    </div>
  );
}
