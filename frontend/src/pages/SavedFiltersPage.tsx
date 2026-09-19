/** Saved filters: create, rename, edit and apply. */

import { useState } from 'react';
import { Banner, Empty, Modal, Section, Spinner } from '../components/ui';
import { FilterBuilder, emptyGroup } from '../components/FilterBuilder';
import { endpoints } from '../api/endpoints';
import { useAsync } from '../hooks/useAsync';
import { useAppStore } from '../stores/useAppStore';
import { pruneGroup, useFilterStore } from '../stores/useFilterStore';
import { navigate } from '../router';
import { useT } from '../i18n/useT';
import type { Group, SavedFilter } from '../types/api';

function describe(filter: SavedFilter['filter']): string {
  const walk = (node: unknown): string => {
    if (!node || typeof node !== 'object') return '';
    const record = node as { op?: string; children?: unknown[]; field?: string; operator?: string; value?: unknown; values?: unknown[] };
    if (record.op && Array.isArray(record.children)) {
      const joiner = record.op === 'or' ? ' OR ' : record.op === 'not' ? 'NOT ' : ' AND ';
      const parts = record.children.map(walk).filter(Boolean);
      if (record.op === 'not') return `NOT (${parts.join('')})`;
      return parts.length > 1 ? `(${parts.join(joiner)})` : parts.join('');
    }
    const value = record.values ? record.values.join(', ') : String(record.value ?? '');
    return `${record.field} ${record.operator} ${value}`;
  };
  return walk(filter);
}

export function SavedFiltersPage() {
  const t = useT();
  const { refreshSavedFilters } = useAppStore();
  const { data, error, loading, reload } = useAsync(() => endpoints.savedFilters(), []);
  const filters = useFilterStore();

  const [editing, setEditing] = useState<SavedFilter | 'new' | null>(null);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [draft, setDraft] = useState<Group>(emptyGroup());
  const [formError, setFormError] = useState<string | null>(null);

  const open = (saved: SavedFilter | 'new') => {
    setEditing(saved);
    setFormError(null);
    if (saved === 'new') {
      setName('');
      setDescription('');
      setDraft(emptyGroup());
    } else {
      setName(saved.name);
      setDescription(saved.description);
      setDraft(
        saved.filter && 'op' in saved.filter
          ? (saved.filter as Group)
          : saved.filter
            ? { op: 'and', children: [saved.filter] }
            : emptyGroup(),
      );
    }
  };

  const save = async () => {
    setFormError(null);
    try {
      const filter = pruneGroup(draft);
      if (editing === 'new') {
        await endpoints.createSavedFilter({ name, description, filter });
      } else if (editing) {
        await endpoints.updateSavedFilter(editing.id, { name, description, filter });
      }
      setEditing(null);
      reload();
      await refreshSavedFilters();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : String(err));
    }
  };

  const remove = async (saved: SavedFilter) => {
    if (!window.confirm(t('saved.deleteConfirm', { name: saved.name }))) return;
    await endpoints.deleteSavedFilter(saved.id);
    reload();
    await refreshSavedFilters();
  };

  const apply = (saved: SavedFilter) => {
    filters.reset();
    filters.applySavedFilter(saved.id, saved.name, saved.filter);
    navigate('/log');
  };

  return (
    <div className="main">
      {error ? <Banner kind="error">{error}</Banner> : null}

      <Section
        title={t('saved.title')}
        actions={
          <button type="button" className="btn primary" onClick={() => open('new')}>
            {t('saved.new')}
          </button>
        }
        bodyStyle={{ padding: 0 }}
      >
        {loading && !data ? (
          <div style={{ padding: 16 }}>
            <Spinner label={t('common.loading')} />
          </div>
        ) : null}

        {data && data.items.length === 0 ? (
          <Empty>{t('saved.empty')}</Empty>
        ) : null}

        {data && data.items.length > 0 ? (
          <table className="data">
            <thead>
              <tr>
                <th>{t('common.name')}</th>
                <th>{t('saved.colCondition')}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.items.map((saved) => (
                <tr key={saved.id}>
                  <td>
                    <strong>{saved.name}</strong>
                    {saved.description ? (
                      <div className="faint small">{saved.description}</div>
                    ) : null}
                  </td>
                  <td className="mono small" style={{ maxWidth: 520, overflowWrap: 'anywhere' }}>
                    {describe(saved.filter) || t('saved.matchesEverything')}
                  </td>
                  <td className="right nowrap">
                    <button
                      type="button"
                      className="btn sm primary"
                      onClick={() => apply(saved)}
                    >
                      {t('common.apply')}
                    </button>{' '}
                    <button type="button" className="btn sm" onClick={() => open(saved)}>
                      {t('common.edit')}
                    </button>{' '}
                    <button
                      type="button"
                      className="btn sm danger"
                      onClick={() => void remove(saved)}
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
            editing === 'new'
              ? t('saved.newTitle')
              : t('saved.editTitle', { name: editing.name })
          }
          onClose={() => setEditing(null)}
          wide
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
            <div className="row wrap" style={{ gap: 10 }}>
              <label className="field" style={{ flex: '1 1 200px' }}>
                {t('common.name')}
                <input
                  type="text"
                  autoFocus
                  value={name}
                  placeholder={t('filter.saveNamePlaceholder')}
                  onChange={(event) => setName(event.target.value)}
                />
              </label>
              <label className="field" style={{ flex: '2 1 260px' }}>
                {t('common.description')}
                <input
                  type="text"
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                />
              </label>
            </div>
            <FilterBuilder value={draft} onChange={(group) => setDraft(group ?? emptyGroup())} />
          </div>
        </Modal>
      ) : null}
    </div>
  );
}
