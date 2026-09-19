/** Domain inventory. */

import { useCallback, useState } from 'react';
import { Banner, Empty, Section, Spinner, TagChips } from '../components/ui';
import { endpoints } from '../api/endpoints';
import { useAsync } from '../hooks/useAsync';
import { Link } from '../router';
import { formatCompact, formatRelative } from '../utils/format';

const PAGE = 100;

export function DomainsPage() {
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
        title="Domains"
        actions={
          <div className="row wrap" style={{ gap: 8, flex: '1 1 auto', justifyContent: 'flex-end' }}>
            <input
              type="search"
              placeholder="Search domains…"
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
              <option value="query_count">Most queries</option>
              <option value="blocked">Most blocked</option>
              <option value="last_seen">Last seen</option>
              <option value="first_seen">First seen</option>
              <option value="name">Name</option>
            </select>
          </div>
        }
        bodyStyle={{ padding: 0 }}
      >
        {error ? <Banner kind="error">{error}</Banner> : null}
        {loading && !data ? (
          <div style={{ padding: 16 }}>
            <Spinner label="Loading domains…" />
          </div>
        ) : null}

        {data && data.items.length === 0 ? <Empty>No domains match.</Empty> : null}

        {data && data.items.length > 0 ? (
          <>
            <table className="data">
              <thead>
                <tr>
                  <th>Domain</th>
                  <th>Registrable</th>
                  <th>Categories</th>
                  <th>Tags</th>
                  <th className="right">Queries</th>
                  <th className="right">Blocked</th>
                  <th>Last seen</th>
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
                {formatCompact(total)} domains · page {page + 1} of {pages}
              </span>
              <span className="spacer" />
              <button
                type="button"
                className="btn sm"
                disabled={page === 0}
                onClick={() => setPage((value) => value - 1)}
              >
                Previous
              </button>
              <button
                type="button"
                className="btn sm"
                disabled={page + 1 >= pages}
                onClick={() => setPage((value) => value + 1)}
              >
                Next
              </button>
            </div>
          </>
        ) : null}
      </Section>
    </div>
  );
}
