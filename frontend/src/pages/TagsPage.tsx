/** The tag and category catalogue. */

import { useState } from 'react';
import { Banner, Chip, Modal, Section, Spinner } from '../components/ui';
import { endpoints } from '../api/endpoints';
import { useAsync } from '../hooks/useAsync';
import { useAppStore } from '../stores/useAppStore';
import { formatCompact } from '../utils/format';
import { useT } from '../i18n/useT';
import type { Tag, TagKind } from '../types/api';

const PALETTE = [
  '#03a9f4', '#43a047', '#fb8c00', '#8e24aa', '#e53935',
  '#00897b', '#3949ab', '#d81b60', '#6d4c41', '#546e7a',
];

export function TagsPage() {
  const t = useT();
  const { refreshTags } = useAppStore();
  const { data, error, loading, reload } = useAsync(() => endpoints.tags(), []);
  const [editing, setEditing] = useState<Tag | 'new' | null>(null);
  const [name, setName] = useState('');
  const [kind, setKind] = useState<TagKind>('tag');
  const [color, setColor] = useState(PALETTE[0]);
  const [description, setDescription] = useState('');
  const [formError, setFormError] = useState<string | null>(null);

  const open = (tag: Tag | 'new') => {
    setEditing(tag);
    setFormError(null);
    if (tag === 'new') {
      setName('');
      setKind('tag');
      setColor(PALETTE[0]);
      setDescription('');
    } else {
      setName(tag.name);
      setKind(tag.kind);
      setColor(tag.color || PALETTE[0]);
      setDescription(tag.description);
    }
  };

  const save = async () => {
    setFormError(null);
    try {
      if (editing === 'new') await endpoints.createTag({ name, kind, color, description });
      else if (editing) await endpoints.updateTag(editing.id, { name, color, description });
      setEditing(null);
      reload();
      await refreshTags();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : String(err));
    }
  };

  const remove = async (tag: Tag) => {
    if (!window.confirm(t('tags.deleteConfirm', { name: tag.name }))) return;
    try {
      await endpoints.deleteTag(tag.id);
      reload();
      await refreshTags();
    } catch (err) {
      window.alert(err instanceof Error ? err.message : String(err));
    }
  };

  const groups: { kind: TagKind; title: string }[] = [
    { kind: 'category', title: t('tags.categories') },
    { kind: 'tag', title: t('tags.tags') },
  ];

  return (
    <div className="main">
      {error ? <Banner kind="error">{error}</Banner> : null}
      {loading && !data ? <Spinner label={t('tags.loading')} /> : null}

      <div className="grid" style={{ gap: 12 }}>
        {groups.map((group) => (
          <Section
            key={group.kind}
            title={group.title}
            actions={
              <button type="button" className="btn primary" onClick={() => open('new')}>
                {t('common.add')}
              </button>
            }
            bodyStyle={{ padding: 0 }}
          >
            <table className="data">
              <thead>
                <tr>
                  <th>{t('common.name')}</th>
                  <th>{t('common.description')}</th>
                  <th className="right">{t('tags.colDomains')}</th>
                  <th>{t('tags.colSource')}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {(data?.items ?? [])
                  .filter((tag) => tag.kind === group.kind)
                  .map((tag) => (
                    <tr key={tag.id}>
                      <td>
                        <Chip label={tag.name} color={tag.color} />
                      </td>
                      <td className="muted small">{tag.description || '—'}</td>
                      <td className="right mono">{formatCompact(tag.domain_count)}</td>
                      <td className="small muted">{tag.builtin ? t('tags.builtin') : t('tags.yours')}</td>
                      <td className="right nowrap">
                        <button type="button" className="btn sm" onClick={() => open(tag)}>
                          {t('common.edit')}
                        </button>{' '}
                        {!tag.builtin ? (
                          <button
                            type="button"
                            className="btn sm danger"
                            onClick={() => void remove(tag)}
                          >
                            {t('common.delete')}
                          </button>
                        ) : null}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </Section>
        ))}
      </div>

      {editing ? (
        <Modal
          title={
            editing === 'new' ? t('tags.newTitle') : t('tags.editTitle', { name: editing.name })
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
                onChange={(event) => setName(event.target.value)}
              />
            </label>
            {editing === 'new' ? (
              <label className="field">
                {t('tags.kind')}
                <select value={kind} onChange={(event) => setKind(event.target.value as TagKind)}>
                  <option value="tag">{t('tags.kindTag')}</option>
                  <option value="category">{t('tags.kindCategory')}</option>
                </select>
              </label>
            ) : null}
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
              {t('common.description')}
              <input
                type="text"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
            </label>
          </div>
        </Modal>
      ) : null}
    </div>
  );
}
