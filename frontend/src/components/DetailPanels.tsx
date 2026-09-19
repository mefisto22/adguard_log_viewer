/** Shared layout for the device, person and domain detail pages. */

import { TimelineChart } from './TimelineChart';
import { Section, StatCard, TopList } from './ui';
import type { TopListItem } from './ui';
import type { DetailPayload } from '../api/endpoints';
import { navigate } from '../router';
import { formatCompact, formatMs, formatNumber, formatPercent } from '../utils/format';
import { rangeKey } from '../i18n';
import { useT } from '../i18n/useT';
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
  const t = useT();
  const summary = detail.summary;
  return (
    <div
      className="grid"
      style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', marginBottom: 12 }}
    >
      <StatCard label={t('common.queries')} value={formatNumber(summary.total)} />
      <StatCard
        label={t('common.blocked')}
        value={formatNumber(summary.blocked)}
        sub={formatPercent(summary.blocked_percent)}
        accent="var(--danger)"
      />
      <StatCard
        label={t('common.allowed')}
        value={formatNumber(summary.allowed)}
        accent="var(--success)"
      />
      <StatCard label={t('common.uniqueDomains')} value={formatNumber(summary.unique_domains)} />
      <StatCard
        label={t('common.avgResponse')}
        value={formatMs(summary.avg_response_time_ms)}
        sub={t('common.cachedSuffix', { count: formatCompact(summary.cached) })}
      />
    </div>
  );
}

export function DetailSections({ detail }: { detail: DetailPayload }) {
  const t = useT();
  return (
    <>
      <div style={{ marginBottom: 12 }}>
        <Section title={t('dashboard.activity')}>
          <TimelineChart timeline={detail.timeline} height={150} />
        </Section>
      </div>

      <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))' }}>
        {detail.top_domains ? (
          <Section title={t('dashboard.topDomains')}>
            <TopList items={domainItems(detail.top_domains)} />
          </Section>
        ) : null}
        {detail.top_blocked_domains ? (
          <Section title={t('dashboard.topBlockedDomains')}>
            <TopList items={domainItems(detail.top_blocked_domains)} />
          </Section>
        ) : null}
        {detail.top_clients ? (
          <Section title={t('dashboard.topDevices')}>
            <TopList items={clientItems(detail.top_clients)} />
          </Section>
        ) : null}
        {detail.top_categories ? (
          <Section title={t('dashboard.categories')}>
            <TopList items={tagItems(detail.top_categories)} />
          </Section>
        ) : null}
        {detail.top_tags ? (
          <Section title={t('dashboard.tags')}>
            <TopList items={tagItems(detail.top_tags)} />
          </Section>
        ) : null}
        {detail.top_query_types ? (
          <Section title={t('dashboard.queryTypes')}>
            <TopList
              items={(detail.top_query_types ?? []).map((row) => ({
                key: row.query_type ?? '',
                label: row.query_type || t('chart.noneLabel'),
                count: row.count,
                blocked: row.blocked,
              }))}
            />
          </Section>
        ) : null}
        {detail.top_upstreams ? (
          <Section title={t('dashboard.upstreamServers')}>
            <TopList
              items={(detail.top_upstreams ?? []).map((row) => ({
                key: row.upstream ?? '',
                label: row.upstream || t('chart.cacheLabel'),
                count: row.count,
                blocked: row.blocked,
              }))}
            />
          </Section>
        ) : null}
        {detail.top_persons ? (
          <Section title={t('dashboard.people')}>
            <TopList
              items={(detail.top_persons ?? []).map((row) => ({
                key: String(row.person_id),
                label: row.person ?? '',
                count: row.count,
                blocked: row.blocked,
                onClick: () => navigate(`/persons/${row.person_id}`),
              }))}
              emptyLabel={t('dashboard.noPersonAssigned')}
            />
          </Section>
        ) : null}
      </div>
    </>
  );
}

const DETAIL_RANGES = ['1h', '24h', '7d', '30d', 'all'];

export function RangePicker({
  range,
  onChange,
}: {
  range: string;
  onChange: (range: string) => void;
}) {
  const t = useT();
  return (
    <select value={range} onChange={(event) => onChange(event.target.value)}>
      {DETAIL_RANGES.map((value) => {
        const key = rangeKey(value);
        return (
          <option key={value} value={value}>
            {key ? t(key) : value}
          </option>
        );
      })}
    </select>
  );
}
