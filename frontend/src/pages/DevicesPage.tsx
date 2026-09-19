/** Device inventory: every client IP AdGuard has seen, with naming and owners. */

import { useCallback, useState } from 'react';
import { Banner, Empty, Modal, Section, Spinner } from '../components/ui';
import { endpoints } from '../api/endpoints';
import { useAsync } from '../hooks/useAsync';
import { useAppStore } from '../stores/useAppStore';
import { Link, navigate } from '../router';
import { formatCompact, formatRelative } from '../utils/format';
import type { Device } from '../types/api';

export function DevicesPage() {
  const { persons, refreshDevices, refreshPersons } = useAppStore();
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState('query_count');
  const [editing, setEditing] = useState<Device | null>(null);
  const [alias, setAlias] = useState('');
  const [personId, setPersonId] = useState<string>('');
  const [saveError, setSaveError] = useState<string | null>(null);

  const load = useCallback(() => endpoints.devices({ search, sort }), [search, sort]);
  const { data, error, loading, reload } = useAsync(load, [search, sort]);

  const openEditor = (device: Device) => {
    setEditing(device);
    setAlias(device.alias);
    setPersonId(device.person_id ? String(device.person_id) : '');
    setSaveError(null);
  };

  const save = async () => {
    if (!editing) return;
    try {
      await endpoints.updateDevice(editing.id, {
        alias,
        ...(personId ? { person_id: Number(personId) } : { clear_person: true }),
      });
      setEditing(null);
      reload();
      await Promise.all([refreshDevices(), refreshPersons()]);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div className="main">
      <Section
        title="Devices"
        actions={
          <div className="row" style={{ gap: 8 }}>
            <input
              type="search"
              placeholder="Search IP, name or person…"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              style={{ width: 240 }}
            />
            <select value={sort} onChange={(event) => setSort(event.target.value)}>
              <option value="query_count">Most queries</option>
              <option value="blocked">Most blocked</option>
              <option value="last_seen">Last seen</option>
              <option value="first_seen">First seen</option>
              <option value="name">Name</option>
              <option value="ip">IP address</option>
            </select>
          </div>
        }
        bodyStyle={{ padding: 0 }}
      >
        {error ? <Banner kind="error">{error}</Banner> : null}
        {loading && !data ? (
          <div style={{ padding: 16 }}>
            <Spinner label="Loading devices…" />
          </div>
        ) : null}

        {data && data.items.length === 0 ? (
          <Empty>
            No devices yet. They appear as soon as AdGuard logs a query from them.
          </Empty>
        ) : null}

        {data && data.items.length > 0 ? (
          <table className="data">
            <thead>
              <tr>
                <th>Name</th>
                <th>IP</th>
                <th>AdGuard name</th>
                <th>Person</th>
                <th className="right">Queries</th>
                <th className="right">Blocked</th>
                <th>First seen</th>
                <th>Last seen</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.items.map((device) => (
                <tr key={device.id} className="clickable">
                  <td onClick={() => navigate(`/devices/${device.id}`)}>
                    <Link to={`/devices/${device.id}`}>{device.name}</Link>
                  </td>
                  <td className="mono">{device.ip}</td>
                  <td className="muted">{device.adguard_name || '—'}</td>
                  <td>
                    {device.person ? (
                      <Link to={`/persons/${device.person_id}`}>{device.person}</Link>
                    ) : (
                      <span className="faint">unassigned</span>
                    )}
                  </td>
                  <td className="right mono">{formatCompact(device.query_count)}</td>
                  <td className="right mono">{formatCompact(device.blocked_count)}</td>
                  <td className="muted small nowrap">{formatRelative(device.first_seen_ns)}</td>
                  <td className="muted small nowrap">{formatRelative(device.last_seen_ns)}</td>
                  <td className="right">
                    <button
                      type="button"
                      className="btn sm"
                      onClick={(event) => {
                        event.stopPropagation();
                        openEditor(device);
                      }}
                    >
                      Edit
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </Section>

      {editing ? (
        <Modal
          title={`Edit ${editing.ip}`}
          onClose={() => setEditing(null)}
          footer={
            <>
              <span className="spacer" />
              <button type="button" className="btn" onClick={() => setEditing(null)}>
                Cancel
              </button>
              <button type="button" className="btn primary" onClick={() => void save()}>
                Save
              </button>
            </>
          }
        >
          {saveError ? <Banner kind="error">{saveError}</Banner> : null}
          <div className="grid" style={{ gap: 12 }}>
            <label className="field">
              Your name for this device
              <input
                type="text"
                value={alias}
                autoFocus
                placeholder={editing.adguard_name || editing.ip}
                onChange={(event) => setAlias(event.target.value)}
              />
              <span className="faint">
                Leave empty to use the name AdGuard reports
                {editing.adguard_name ? ` (“${editing.adguard_name}”)` : ''}.
              </span>
            </label>

            <label className="field">
              Person
              <select value={personId} onChange={(event) => setPersonId(event.target.value)}>
                <option value="">— unassigned —</option>
                {persons.map((person) => (
                  <option key={person.id} value={person.id}>
                    {person.name}
                  </option>
                ))}
              </select>
              <span className="faint">
                Assigning a person lets you filter every one of their devices at once.
              </span>
            </label>
          </div>
        </Modal>
      ) : null}
    </div>
  );
}
