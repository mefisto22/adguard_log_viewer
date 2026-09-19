/** Overview of DNS activity for the selected period and filter. */

import { useCallback } from 'react';
import { FilterBar } from '../components/FilterBar';
import { TimelineChart } from '../components/TimelineChart';
import { Banner, Section, Spinner, StatCard, TopList } from '../components/ui';
import type { TopListItem } from '../components/ui';
import { endpoints } from '../api/endpoints';
import { useAsync } from '../hooks/useAsync';
import { useFilterStore } from '../stores/useFilterStore';
import { useLiveUpdates } from '../hooks/useLiveUpdates';
import { formatCompact, formatMs, formatNumber, formatPercent } from '../utils/format';
import { navigate } from '../router';
import type { TopRow } from '../types/api';

export function DashboardPage() {
  const revision = useFilterStore((state) => state.revision);
  const buildFilterRequest = useFilterStore((state) => state.buildFilterRequest);
  const { lastEvent } = useLiveUpdates();

  const load = useCallback(
    () => endpoints.dashboard({ ...buildFilterRequest(), top_limit: 10, buckets: 72 }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [revision, lastEvent?.at_ns],
  );
  const { data, error, loading, reload } = useAsync(load, [revision, lastEvent?.at_ns]);

  const summary = data?.summary;

  const domainItems = (rows: TopRow[] | undefined): TopListItem[] =>
    (rows ?? []).map((row) => ({
      key: String(row.domain_id),
      label: row.domain ?? '',
      count: row.count,
      blocked: row.blocked,
      onClick: () => navigate(`/domains/${row.domain_id}`),
    }));

  const tagItems = (rows: TopRow[] | undefined): TopListItem[] =>
    (rows ?? []).map((row) => ({
      key: String(row.tag_id),
      label: row.name ?? '',
      count: row.count,
      blocked: row.blocked,
      color: row.color || undefined,
    }));

  return (
    <div className="main">
      <div className="card" style={{ marginBottom: 12 }}>
        <FilterBar />
      </div>

      {error ? (
        <Banner
          kind="error"
          title="Could not load the dashboard"
          action={
            <button type="button" className="btn sm" onClick={reload}>
              Retry
            </button>
          }
        >
          {error}
        </Banner>
      ) : null}

      {loading && !data ? (
        <div style={{ padding: 24 }}>
          <Spinner label="Crunching the numbers…" />
        </div>
      ) : null}

      {summary ? (
        <>
          <div
            className="grid"
            style={{
              gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
              marginBottom: 12,
            }}
          >
            <StatCard label="DNS queries" value={formatNumber(summary.total)} />
            <StatCard
              label="Blocked"
              value={formatNumber(summary.blocked)}
              sub={formatPercent(summary.blocked_percent)}
              accent="var(--danger)"
            />
            <StatCard
              label="Allowed"
              value={formatNumber(summary.allowed)}
              accent="var(--success)"
            />
            <StatCard label="Unique domains" value={formatNumber(summary.unique_domains)} />
            <StatCard label="Active devices" value={formatNumber(summary.active_clients)} />
            <StatCard label="People seen" value={formatNumber(summary.active_persons)} />
            <StatCard
              label="Avg response"
              value={formatMs(summary.avg_response_time_ms)}
              sub={`${formatCompact(summary.cached)} from cache`}
            />
          </div>

          <div style={{ marginBottom: 12 }}>
            <Section title="Query activity">
              <TimelineChart timeline={data?.timeline ?? null} height={170} />
            </Section>
          </div>

          <div
            className="grid"
            style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))' }}
          >
            <Section title="Top domains">
              <TopList items={domainItems(data?.top_domains)} />
            </Section>
            <Section title="Top blocked domains">
              <TopList items={domainItems(data?.top_blocked_domains)} />
            </Section>
            <Section title="Top devices">
              <TopList
                items={(data?.top_clients ?? []).map((row) => ({
                  key: String(row.client_id),
                  label: row.client_name || row.client_ip || '',
                  count: row.count,
                  blocked: row.blocked,
                  onClick: () => navigate(`/devices/${row.client_id}`),
                }))}
              />
            </Section>
            <Section title="Top people">
              <TopList
                items={(data?.top_persons ?? []).map((row) => ({
                  key: String(row.person_id),
                  label: row.person ?? '',
                  count: row.count,
                  blocked: row.blocked,
                  onClick: () => navigate(`/persons/${row.person_id}`),
                }))}
                emptyLabel="No devices are assigned to a person yet"
              />
            </Section>
            <Section title="Top categories">
              <TopList items={tagItems(data?.top_categories)} />
            </Section>
            <Section title="Top tags">
              <TopList items={tagItems(data?.top_tags)} />
            </Section>
            <Section title="Query types">
              <TopList
                items={(data?.top_query_types ?? []).map((row) => ({
                  key: row.query_type ?? '',
                  label: row.query_type || '(none)',
                  count: row.count,
                  blocked: row.blocked,
                }))}
              />
            </Section>
            <Section title="Upstream servers">
              <TopList
                items={(data?.top_upstreams ?? []).map((row) => ({
                  key: row.upstream ?? '',
                  label: row.upstream || '(cache)',
                  count: row.count,
                  blocked: row.blocked,
                }))}
                emptyLabel="AdGuard did not report an upstream"
              />
            </Section>
          </div>
        </>
      ) : null}
    </div>
  );
}
