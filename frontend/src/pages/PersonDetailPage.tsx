/** Everything one person's devices did. */

import { useCallback, useState } from 'react';
import { DetailSections, RangePicker, SummaryCards } from '../components/DetailPanels';
import { Banner, Chip, Spinner } from '../components/ui';
import { endpoints } from '../api/endpoints';
import { useAsync } from '../hooks/useAsync';
import { Link, navigate } from '../router';
import { useFilterStore } from '../stores/useFilterStore';

export function PersonDetailPage({ id }: { id: number }) {
  const [range, setRange] = useState('24h');
  const load = useCallback(() => endpoints.personDetail(id, range), [id, range]);
  const { data, error, loading } = useAsync(load, [id, range]);
  const filters = useFilterStore();

  const showInLog = () => {
    filters.reset();
    filters.setRange(range);
    filters.setQuick({ personIds: [id] });
    navigate('/log');
  };

  if (error) return <div className="main"><Banner kind="error">{error}</Banner></div>;
  if (!data)
    return (
      <div className="main">
        <Spinner label="Loading person…" />
      </div>
    );

  return (
    <div className="main">
      <div className="row wrap" style={{ gap: 10, marginBottom: 12 }}>
        <div>
          <div className="small muted">
            <Link to="/persons">People</Link> /
          </div>
          <h1>{data.person.name}</h1>
          <div className="row wrap" style={{ gap: 4, marginTop: 4 }}>
            {data.person.devices.map((device) => (
              <Chip
                key={device.id}
                label={device.name}
                title={device.ip}
                onClick={() => navigate(`/devices/${device.id}`)}
              />
            ))}
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
