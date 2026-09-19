/** Domain inventory. */

import { useCallback, useState } from 'react';
import { Banner, Empty, Section, Spinner, TagChips } from '../components/ui';
import { endpoints } from '../api/endpoints';
import { useAsync } from '../hooks/useAsync';
import { Link } from '../router';
import { formatCompact, formatRelative } from '../utils/format';
import { useT } from '../i18n/useT';

const PAGE = 100;

export function DomainsPage() {
  const t = useT();
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState('query_count');
  const [page, setPage] = useState(0);

  const load = useCallback(
    () => endpoints.domains({ search, sort, limit: PAGE, offset: page * PAGE }),
    [search, sort, page],
  );
  const { data, error, loading } = useAsync(load, [search, sort, page]);
  const total = data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE));

  return (
    <div className="main">
      <Section
        title={t('domains.title')}
        actions={
          <div className="row wrap" style={{ gap: 8, flex: '1 1 auto', justifyContent: 'flex-end' }}>
            <input
              type="search"
              placeholder={t('domains.searchPlaceholder')}
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setPage(0);
              }}
              style={{ flex: '1 1 150px', minWidth: 0, maxWidth: 240 }}
            />
            <select
              value={sort}
              onChange={(event) => {
                setSort(event.target.value);
                setPage(0);
              }}
            >
              <option value="query_count">{t('devices.sortQueries')}</option>
              <option value="blocked">{t('devices.sortBlocked')}</option>
              <option value="last_seen">{t('devices.sortLastSeen')}</option>
              <option value="first_seen">{t('devices.sortFirstSeen')}</option>
              <option value="name">{t('devices.sortName')}</option>
            </select>
          </div>
        }
        bodyStyle={{ padding: 0 }}
      >
        {error ? <Banner kind="error">{error}</Banner> : null}
        {loading && !data ? (
          <div style={{ padding: 16 }}>
            <Spinner label={t('domains.loading')} />
          </div>
        ) : null}

        {data && data.items.length === 0 ? <Empty>{t('domains.empty')}</Empty> : null}

        {data && data.items.length > 0 ? (
          <>
            <table className="data">
              <thead>
                <tr>
                  <th>{t('domains.colDomain')}</th>
                  <th>{t('domains.colRegistrable')}</th>
                  <th>{t('column.categories')}</th>
                  <th>{t('column.tags')}</th>
                  <th className="right">{t('common.queries')}</th>
                  <th className="right">{t('common.blocked')}</th>
                  <th>{t('devices.colLastSeen')}</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((domain) => (
                  <tr key={domain.id}>
                    <td>
                      <Link to={`/domains/${domain.id}`}>{domain.name}</Link>
                    </td>
                    <td className="mono small muted">{domain.registrable_domain}</td>
                    <td>
                      <TagChips tags={domain.categories} limit={3} />
                    </td>
                    <td>
                      <TagChips tags={domain.tags} limit={3} />
                    </td>
                    <td className="right mono">{formatCompact(domain.query_count)}</td>
                    <td className="right mono">{formatCompact(domain.blocked_count)}</td>
                    <td className="muted small nowrap">{formatRelative(domain.last_seen_ns)}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            <div className="row" style={{ padding: 10, gap: 8 }}>
              <span className="muted small">
                {t('domains.pageInfo', {
                  total: formatCompact(total),
                  page: page + 1,
                  pages,
                })}
              </span>
              <span className="spacer" />
              <button
                type="button"
                className="btn sm"
                disabled={page === 0}
                onClick={() => setPage((value) => value - 1)}
              >
                {t('common.previous')}
              </button>
              <button
                type="button"
                className="btn sm"
                disabled={page + 1 >= pages}
                onClick={() => setPage((value) => value + 1)}
              >
                {t('common.next')}
              </button>
            </div>
          </>
        ) : null}
      </Section>
    </div>
  );
}
