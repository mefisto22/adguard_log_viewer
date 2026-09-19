/** Shared layout for the device, person and domain detail pages. */

import { TimelineChart } from './TimelineChart';
import { Section, StatCard, TopList } from './ui';
import type { TopListItem } from './ui';
import type { DetailPayload } from '../api/endpoints';
import { navigate } from '../router';
import { formatCompact, formatMs, formatNumber, formatPercent } from '../utils/format';
import type { TopRow } from '../types/api';

export function domainItems(rows: TopRow[] | undefined): TopListItem[] {
  return (rows ?? []).map((row) => ({
    key: String(row.domain_id),
    label: row.domain ?? '',
    count: row.count,
    blocked: row.blocked,
    onClick: () => navigate(`/domains/${row.domain_id}`),
  }));
}

export function clientItems(rows: TopRow[] | undefined): TopListItem[] {
  return (rows ?? []).map((row) => ({
    key: String(row.client_id),
    label: row.client_name || row.client_ip || '',
    count: row.count,
    blocked: row.blocked,
    onClick: () => navigate(`/devices/${row.client_id}`),
  }));
}

export function tagItems(rows: TopRow[] | undefined): TopListItem[] {
  return (rows ?? []).map((row) => ({
    key: String(row.tag_id),
    label: row.name ?? '',
    count: row.count,
    blocked: row.blocked,
    color: row.color || undefined,
  }));
}

export function SummaryCards({ detail }: { detail: DetailPayload }) {
  const summary = detail.summary;
  return (
    <div
      className="grid"
      style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', marginBottom: 12 }}
    >
      <StatCard label="Queries" value={formatNumber(summary.total)} />
      <StatCard
        label="Blocked"
        value={formatNumber(summary.blocked)}
        sub={formatPercent(summary.blocked_percent)}
        accent="var(--danger)"
      />
      <StatCard label="Allowed" value={formatNumber(summary.allowed)} accent="var(--success)" />
      <StatCard label="Unique domains" value={formatNumber(summary.unique_domains)} />
      <StatCard
        label="Avg response"
        value={formatMs(summary.avg_response_time_ms)}
        sub={`${formatCompact(summary.cached)} cached`}
      />
    </div>
  );
}

export function DetailSections({ detail }: { detail: DetailPayload }) {
  return (
    <>
      <div style={{ marginBottom: 12 }}>
        <Section title="Activity">
          <TimelineChart timeline={detail.timeline} height={150} />
        </Section>
      </div>

      <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))' }}>
        {detail.top_domains ? (
          <Section title="Top domains">
            <TopList items={domainItems(detail.top_domains)} />
          </Section>
        ) : null}
        {detail.top_blocked_domains ? (
          <Section title="Top blocked domains">
            <TopList items={domainItems(detail.top_blocked_domains)} />
          </Section>
        ) : null}
        {detail.top_clients ? (
          <Section title="Top devices">
            <TopList items={clientItems(detail.top_clients)} />
          </Section>
        ) : null}
        {detail.top_categories ? (
          <Section title="Categories">
            <TopList items={tagItems(detail.top_categories)} />
          </Section>
        ) : null}
        {detail.top_tags ? (
          <Section title="Tags">
            <TopList items={tagItems(detail.top_tags)} />
          </Section>
        ) : null}
        {detail.top_query_types ? (
          <Section title="Query types">
            <TopList
              items={(detail.top_query_types ?? []).map((row) => ({
                key: row.query_type ?? '',
                label: row.query_type || '(none)',
                count: row.count,
                blocked: row.blocked,
              }))}
            />
          </Section>
        ) : null}
        {detail.top_upstreams ? (
          <Section title="Upstream servers">
            <TopList
              items={(detail.top_upstreams ?? []).map((row) => ({
                key: row.upstream ?? '',
                label: row.upstream || '(cache)',
                count: row.count,
                blocked: row.blocked,
              }))}
            />
          </Section>
        ) : null}
        {detail.top_persons ? (
          <Section title="People">
            <TopList
              items={(detail.top_persons ?? []).map((row) => ({
                key: String(row.person_id),
                label: row.person ?? '',
                count: row.count,
                blocked: row.blocked,
                onClick: () => navigate(`/persons/${row.person_id}`),
              }))}
              emptyLabel="No devices assigned to a person"
            />
          </Section>
        ) : null}
      </div>
    </>
  );
}

export function RangePicker({
  range,
  onChange,
}: {
  range: string;
  onChange: (range: string) => void;
}) {
  return (
    <select value={range} onChange={(event) => onChange(event.target.value)}>
      <option value="1h">Last hour</option>
      <option value="24h">Last 24 hours</option>
      <option value="7d">Last 7 days</option>
      <option value="30d">Last 30 days</option>
      <option value="all">All time</option>
    </select>
  );
}
