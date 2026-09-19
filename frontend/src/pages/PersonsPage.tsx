/** People, and which devices belong to them. */

import { useState } from 'react';
import { Banner, Chip, Empty, Modal, Section, Spinner } from '../components/ui';
import { endpoints } from '../api/endpoints';
import { useAsync } from '../hooks/useAsync';
import { useAppStore } from '../stores/useAppStore';
import { Link } from '../router';
import { colorFor, formatCompact, formatRelative } from '../utils/format';
import { useT } from '../i18n/useT';
import type { Person } from '../types/api';

const PALETTE = [
  '#03a9f4', '#43a047', '#fb8c00', '#8e24aa', '#e53935',
  '#00897b', '#3949ab', '#d81b60', '#6d4c41', '#546e7a',
];

export function PersonsPage() {
  const t = useT();
  const { devices, refreshPersons, refreshDevices } = useAppStore();
  const { data, error, loading, reload } = useAsync(() => endpoints.persons(), []);

  const [editing, setEditing] = useState<Person | 'new' | null>(null);
  const [name, setName] = useState('');
  const [color, setColor] = useState(PALETTE[0]);
  const [note, setNote] = useState('');
  const [selectedDevices, setSelectedDevices] = useState<number[]>([]);
  const [formError, setFormError] = useState<string | null>(null);

  const openNew = () => {
    setEditing('new');
    setName('');
    setColor(PALETTE[(data?.items.length ?? 0) % PALETTE.length]);
    setNote('');
    setSelectedDevices([]);
    setFormError(null);
  };

  const openEdit = (person: Person) => {
    setEditing(person);
    setName(person.name);
    setColor(person.color || colorFor(person.name));
    setNote(person.note);
    setSelectedDevices(person.devices.map((device) => device.id));
    setFormError(null);
  };

  const save = async () => {
    setFormError(null);
    try {
      let personId: number;
      if (editing === 'new') {
        personId = (await endpoints.createPerson({ name, color, note })).id;
      } else if (editing) {
        personId = editing.id;
        await endpoints.updatePerson(personId, { name, color, note });
      } else {
        return;
      }

      const previous = editing === 'new' ? [] : editing.devices.map((device) => device.id);
      const added = selectedDevices.filter((id) => !previous.includes(id));
      const removed = previous.filter((id) => !selectedDevices.includes(id));
      if (added.length) await endpoints.assignDevices(personId, added);
      if (removed.length) await endpoints.assignDevices(null, removed);

      setEditing(null);
      reload();
      await Promise.all([refreshPersons(), refreshDevices()]);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : String(err));
    }
  };

  const remove = async (person: Person) => {
    if (!window.confirm(t('people.deleteConfirm', { name: person.name }))) return;
    await endpoints.deletePerson(person.id);
    reload();
    await Promise.all([refreshPersons(), refreshDevices()]);
  };

  return (
    <div className="main">
      <Section
        title={t('people.title')}
        actions={
          <button type="button" className="btn primary" onClick={openNew}>
            {t('people.add')}
          </button>
        }
        bodyStyle={{ padding: 0 }}
      >
        {error ? <Banner kind="error">{error}</Banner> : null}
        {loading && !data ? (
          <div style={{ padding: 16 }}>
            <Spinner label={t('people.loading')} />
          </div>
        ) : null}

        {data && data.items.length === 0 ? (
          <Empty>{t('people.empty')}</Empty>
        ) : null}

        {data && data.items.length > 0 ? (
          <table className="data">
            <thead>
              <tr>
                <th>{t('common.name')}</th>
                <th>{t('people.colDevices')}</th>
                <th className="right">{t('common.queries')}</th>
                <th className="right">{t('common.blocked')}</th>
                <th>{t('people.colLastActivity')}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.items.map((person) => (
                <tr key={person.id}>
                  <td>
                    <Link to={`/persons/${person.id}`}>
                      <span className="row" style={{ gap: 6 }}>
                        <span
                          style={{
                            width: 10,
                            height: 10,
                            borderRadius: 5,
                            background: person.color || colorFor(person.name),
                          }}
                        />
                        {person.name}
                      </span>
                    </Link>
                    {person.note ? <div className="faint small">{person.note}</div> : null}
                  </td>
                  <td>
                    <div className="row wrap" style={{ gap: 4 }}>
                      {person.devices.length ? (
                        person.devices.map((device) => (
                          <Chip key={device.id} label={device.name} title={device.ip} />
                        ))
                      ) : (
                        <span className="faint">{t('common.none')}</span>
                      )}
                    </div>
                  </td>
                  <td className="right mono">{formatCompact(person.query_count)}</td>
                  <td className="right mono">{formatCompact(person.blocked_count)}</td>
                  <td className="muted small nowrap">{formatRelative(person.last_seen_ns)}</td>
                  <td className="right nowrap">
                    <button type="button" className="btn sm" onClick={() => openEdit(person)}>
                      {t('common.edit')}
                    </button>{' '}
                    <button
                      type="button"
                      className="btn sm danger"
                      onClick={() => void remove(person)}
                    >
                      {t('common.delete')}
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
          title={
            editing === 'new' ? t('people.add') : t('people.editTitle', { name: editing.name })
          }
          onClose={() => setEditing(null)}
          footer={
            <>
              <span className="spacer" />
              <button type="button" className="btn" onClick={() => setEditing(null)}>
                {t('common.cancel')}
              </button>
              <button
                type="button"
                className="btn primary"
                disabled={!name.trim()}
                onClick={() => void save()}
              >
                {t('common.save')}
              </button>
            </>
          }
        >
          {formError ? <Banner kind="error">{formError}</Banner> : null}
          <div className="grid" style={{ gap: 12 }}>
            <label className="field">
              {t('common.name')}
              <input
                type="text"
                autoFocus
                value={name}
                placeholder={t('people.namePlaceholder')}
                onChange={(event) => setName(event.target.value)}
              />
            </label>

            <div className="field">
              {t('common.colour')}
              <div className="row wrap" style={{ gap: 6 }}>
                {PALETTE.map((option) => (
                  <button
                    key={option}
                    type="button"
                    aria-label={option}
                    onClick={() => setColor(option)}
                    style={{
                      width: 26,
                      height: 26,
                      borderRadius: 13,
                      background: option,
                      border:
                        option === color ? '3px solid var(--text)' : '1px solid var(--border)',
                      cursor: 'pointer',
                    }}
                  />
                ))}
              </div>
            </div>

            <label className="field">
              {t('common.note')}
              <input
                type="text"
                value={note}
                onChange={(event) => setNote(event.target.value)}
                placeholder={t('common.optional')}
              />
            </label>

            <div className="field">
              {t('people.devices')}
              <div
                style={{
                  maxHeight: 220,
                  overflow: 'auto',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-sm)',
                  padding: 4,
                }}
              >
                {devices.length === 0 ? (
                  <div className="faint small" style={{ padding: 8 }}>
                    {t('people.noDevicesSeen')}
                  </div>
                ) : (
                  devices.map((device) => (
                    <label
                      key={device.id}
                      className="row"
                      style={{ gap: 8, padding: '4px 6px', cursor: 'pointer' }}
                    >
                      <input
                        type="checkbox"
                        checked={selectedDevices.includes(device.id)}
                        onChange={() =>
                          setSelectedDevices((current) =>
                            current.includes(device.id)
                              ? current.filter((id) => id !== device.id)
                              : [...current, device.id],
                          )
                        }
                      />
                      <span style={{ flex: '1 1 auto' }}>{device.name}</span>
                      <span className="faint mono small">{device.ip}</span>
                      {device.person && device.person_id !== (editing === 'new' ? -1 : editing.id) ? (
                        <span className="faint small">({device.person})</span>
                      ) : null}
                    </label>
                  ))
                )}
              </div>
            </div>
          </div>
        </Modal>
      ) : null}
    </div>
  );
}
