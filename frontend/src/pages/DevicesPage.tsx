/** Device inventory: every client IP AdGuard has seen, with naming and owners. */

import { useCallback, useState } from 'react';
import { Banner, Empty, Modal, Section, Spinner } from '../components/ui';
import { endpoints } from '../api/endpoints';
import { useAsync } from '../hooks/useAsync';
import { useAppStore } from '../stores/useAppStore';
import { Link, navigate } from '../router';
import { formatCompact, formatRelative } from '../utils/format';
import { useT } from '../i18n/useT';
import type { Device } from '../types/api';

export function DevicesPage() {
  const t = useT();
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
        title={t('devices.title')}
        actions={
          <div className="row wrap" style={{ gap: 8, flex: '1 1 auto', justifyContent: 'flex-end' }}>
            <input
              type="search"
              placeholder={t('devices.searchPlaceholder')}
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              style={{ flex: '1 1 150px', minWidth: 0, maxWidth: 240 }}
            />
            <select value={sort} onChange={(event) => setSort(event.target.value)}>
              <option value="query_count">{t('devices.sortQueries')}</option>
              <option value="blocked">{t('devices.sortBlocked')}</option>
              <option value="last_seen">{t('devices.sortLastSeen')}</option>
              <option value="first_seen">{t('devices.sortFirstSeen')}</option>
              <option value="name">{t('devices.sortName')}</option>
              <option value="ip">{t('devices.sortIp')}</option>
            </select>
          </div>
        }
        bodyStyle={{ padding: 0 }}
      >
        {error ? <Banner kind="error">{error}</Banner> : null}
        {loading && !data ? (
          <div style={{ padding: 16 }}>
            <Spinner label={t('devices.loading')} />
          </div>
        ) : null}

        {data && data.items.length === 0 ? (
          <Empty>{t('devices.empty')}</Empty>
        ) : null}

        {data && data.items.length > 0 ? (
          <table className="data">
            <thead>
              <tr>
                <th>{t('devices.colName')}</th>
                <th>{t('devices.colIp')}</th>
                <th>{t('devices.colAdguardName')}</th>
                <th>{t('devices.colPerson')}</th>
                <th className="right">{t('devices.colQueries')}</th>
                <th className="right">{t('devices.colBlocked')}</th>
                <th>{t('devices.colFirstSeen')}</th>
                <th>{t('devices.colLastSeen')}</th>
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
                      <span className="faint">{t('common.unassigned')}</span>
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
                      {t('common.edit')}
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
          title={t('devices.editTitle', { ip: editing.ip })}
          onClose={() => setEditing(null)}
          footer={
            <>
              <span className="spacer" />
              <button type="button" className="btn" onClick={() => setEditing(null)}>
                {t('common.cancel')}
              </button>
              <button type="button" className="btn primary" onClick={() => void save()}>
                {t('common.save')}
              </button>
            </>
          }
        >
          {saveError ? <Banner kind="error">{saveError}</Banner> : null}
          <div className="grid" style={{ gap: 12 }}>
            <label className="field">
              {t('devices.yourName')}
              <input
                type="text"
                value={alias}
                autoFocus
                placeholder={editing.adguard_name || editing.ip}
                onChange={(event) => setAlias(event.target.value)}
              />
              <span className="faint">
                {editing.adguard_name
                  ? t('devices.yourNameHintWith', { name: editing.adguard_name })
                  : `${t('devices.yourNameHint')}.`}
              </span>
            </label>

            <label className="field">
              {t('devices.colPerson')}
              <select value={personId} onChange={(event) => setPersonId(event.target.value)}>
                <option value="">{t('devices.personUnassigned')}</option>
                {persons.map((person) => (
                  <option key={person.id} value={person.id}>
                    {person.name}
                  </option>
                ))}
              </select>
              <span className="faint">{t('devices.personHint')}</span>
            </label>
          </div>
        </Modal>
      ) : null}
    </div>
  );
}
