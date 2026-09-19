/** Everything known about a single DNS query. */

import { Chip, ResultBadge } from './ui';
import { Link } from '../router';
import { formatDateTime, formatMs } from '../utils/format';
import type { QueryRow } from '../types/api';

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </>
  );
}

export function QueryDetail({ row }: { row: QueryRow }) {
  return (
    <div className="grid" style={{ gap: 16 }}>
      <div>
        <div className="row" style={{ gap: 8, marginBottom: 6 }}>
          <ResultBadge result={row.result} />
          <span className="mono">{row.query_type}</span>
          {row.cached ? <span className="chip">cached</span> : null}
        </div>
        <h2 style={{ overflowWrap: 'anywhere' }}>{row.domain}</h2>
        <Link to={`/domains/${row.domain_id}`}>Open domain details →</Link>
      </div>

      <dl className="kv">
        <Row label="Time">{formatDateTime(row.ts_ns)}</Row>
        <Row label="Device">
          <Link to={`/devices/${row.client_id}`}>{row.client_name || row.client_ip}</Link>{' '}
          <span className="faint mono">({row.client_ip})</span>
        </Row>
        <Row label="Person">
          {row.person ? <Link to={`/persons/${row.person_id}`}>{row.person}</Link> : '—'}
        </Row>
        <Row label="Registrable domain">
          <span className="mono">{row.registrable_domain || '—'}</span>
        </Row>
        <Row label="Query class">
          <span className="mono">{row.query_class}</span>
        </Row>
        <Row label="Response status">
          <span className="mono">{row.response_status || '—'}</span>
        </Row>
        <Row label="AdGuard reason">
          <span className="mono">{row.reason || 'NotFilteredNotFound'}</span>
        </Row>
        <Row label="Filter rule">
          <span className="mono">{row.rule || '—'}</span>
        </Row>
        <Row label="Filter list id">{row.filter_list_id >= 0 ? row.filter_list_id : '—'}</Row>
        <Row label="Upstream">
          <span className="mono">{row.upstream || (row.cached ? 'cache' : '—')}</span>
        </Row>
        <Row label="Response time">{formatMs(row.response_time_ms)}</Row>
        <Row label="Client protocol">
          <span className="mono">{row.client_proto || 'plain DNS'}</span>
        </Row>
      </dl>

      <div>
        <h3 style={{ marginBottom: 6 }}>Answer</h3>
        {row.answers.length ? (
          <table className="data">
            <thead>
              <tr>
                <th>Type</th>
                <th>Value</th>
                <th className="right">TTL</th>
              </tr>
            </thead>
            <tbody>
              {row.answers.map((answer, index) => (
                <tr key={index}>
                  <td className="mono">{answer.type}</td>
                  <td className="mono" style={{ overflowWrap: 'anywhere' }}>
                    {answer.value || '—'}
                  </td>
                  <td className="right mono">{answer.ttl}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="faint small">No answer records.</div>
        )}
      </div>

      <div>
        <h3 style={{ marginBottom: 6 }}>Categories</h3>
        <div className="row wrap" style={{ gap: 4 }}>
          {row.categories.length ? (
            row.categories.map((tag) => <Chip key={tag.name} label={tag.name} color={tag.color} />)
          ) : (
            <span className="faint small">None</span>
          )}
        </div>
      </div>

      <div>
        <h3 style={{ marginBottom: 6 }}>Tags</h3>
        <div className="row wrap" style={{ gap: 4 }}>
          {row.tags.length ? (
            row.tags.map((tag) => <Chip key={tag.name} label={tag.name} color={tag.color} />)
          ) : (
            <span className="faint small">None</span>
          )}
        </div>
      </div>
    </div>
  );
}
