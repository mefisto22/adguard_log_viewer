/** Everything one device did. */

import { useCallback, useState } from 'react';
import { DetailSections, RangePicker, SummaryCards } from '../components/DetailPanels';
import { Banner, Spinner } from '../components/ui';
import { endpoints } from '../api/endpoints';
import { useAsync } from '../hooks/useAsync';
import { Link, navigate } from '../router';
import { useFilterStore } from '../stores/useFilterStore';
import { formatDateTime } from '../utils/format';

export function DeviceDetailPage({ id }: { id: number }) {
  const [range, setRange] = useState('24h');
  const load = useCallback(() => endpoints.deviceDetail(id, range), [id, range]);
  const { data, error, loading } = useAsync(load, [id, range]);
  const filters = useFilterStore();

  const showInLog = () => {
    filters.reset();
    filters.setRange(range);
    filters.setQuick({ clientIds: [id] });
    navigate('/log');
  };

  if (error) return <div className="main"><Banner kind="error">{error}</Banner></div>;
  if (!data)
    return (
      <div className="main">
        <Spinner label="Loading device…" />
      </div>
    );

  const device = data.device;

  return (
    <div className="main">
      <div className="row wrap" style={{ gap: 10, marginBottom: 12 }}>
        <div>
          <div className="small muted">
            <Link to="/devices">Devices</Link> /
          </div>
          <h1>{device.name}</h1>
          <div className="muted small">
            <span className="mono">{device.ip}</span>
            {device.adguard_name ? ` · AdGuard: ${device.adguard_name}` : ''}
            {device.person ? (
              <>
                {' · '}
                <Link to={`/persons/${device.person_id}`}>{device.person}</Link>
              </>
            ) : null}
          </div>
          <div className="faint small">
            First seen {formatDateTime(device.first_seen_ns)} · last seen{' '}
            {formatDateTime(device.last_seen_ns)}
          </div>
        </div>
        <span className="spacer" />
        <RangePicker range={range} onChange={setRange} />
        <button type="button" className="btn primary" onClick={showInLog}>
          Show in log
        </button>
      </div>

      {loading ? <Spinner /> : null}
      <SummaryCards detail={data} />
      <DetailSections detail={data} />
    </div>
  );
}
