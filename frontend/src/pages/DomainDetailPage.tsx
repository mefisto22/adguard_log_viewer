/** Everything about one domain. */

import { useCallback, useState } from 'react';
import { DetailSections, RangePicker, SummaryCards } from '../components/DetailPanels';
import { Banner, Chip, Modal, Section, Spinner } from '../components/ui';
import { endpoints } from '../api/endpoints';
import { useAsync } from '../hooks/useAsync';
import { Link, navigate } from '../router';
import { useAppStore } from '../stores/useAppStore';
import { useFilterStore } from '../stores/useFilterStore';
import { formatCompact, formatDateTime } from '../utils/format';
import { useT } from '../i18n/useT';

export function DomainDetailPage({ id }: { id: number }) {
  const t = useT();
  const [range, setRange] = useState('24h');
  const [tagsOpen, setTagsOpen] = useState(false);
  const [selectedTags, setSelectedTags] = useState<number[]>([]);
  const { tags, refreshTags } = useAppStore();
  const filters = useFilterStore();

  const load = useCallback(() => endpoints.domainDetail(id, range), [id, range]);
  const { data, error, loading, reload } = useAsync(load, [id, range]);

  const showInLog = () => {
    if (!data) return;
    filters.reset();
    filters.setRange(range);
    filters.setTerms([data.domain.name]);
    filters.setSearchFields(['domain']);
    navigate('/log');
  };

  const openTags = () => {
    if (!data) return;
    setSelectedTags(
      [...data.domain.tags, ...data.domain.categories]
        .filter((tag) => tag.source === 'manual')
        .map((tag) => tag.id),
    );
    setTagsOpen(true);
  };

  const saveTags = async () => {
    await endpoints.setDomainTags(id, selectedTags);
    setTagsOpen(false);
    reload();
    await refreshTags();
  };

  if (error) return <div className="main"><Banner kind="error">{error}</Banner></div>;
  if (!data)
    return (
      <div className="main">
        <Spinner label={t('domains.loadingDomain')} />
      </div>
    );

  const domain = data.domain;
  const allTags = [...domain.categories, ...domain.tags];

  return (
    <div className="main">
      <div className="row wrap" style={{ gap: 10, marginBottom: 12 }}>
        <div style={{ minWidth: 0 }}>
          <div className="small muted">
            <Link to="/domains">{t('nav.domains')}</Link> /
          </div>
          <h1 style={{ overflowWrap: 'anywhere' }}>{domain.name}</h1>
          <div className="muted small">
            {t('domains.registrableLine', {
              registrable: domain.registrable_domain,
              first: formatDateTime(domain.first_seen_ns),
              last: formatDateTime(domain.last_seen_ns),
            })}
          </div>
          <div className="row wrap" style={{ gap: 4, marginTop: 6 }}>
            {allTags.length ? (
              allTags.map((tag) => (
                <Chip
                  key={`${tag.id}-${tag.name}`}
                  label={tag.name}
                  color={tag.color}
                  title={`${tag.name} (${tag.source})`}
                />
              ))
            ) : (
              <span className="faint small">{t('domains.noTags')}</span>
            )}
          </div>
        </div>
        <span className="spacer" />
        <RangePicker range={range} onChange={setRange} />
        <button type="button" className="btn" onClick={openTags}>
          {t('domains.editTags')}
        </button>
        <button type="button" className="btn primary" onClick={showInLog}>
          {t('common.showInLog')}
        </button>
      </div>

      {loading ? <Spinner /> : null}
      <SummaryCards detail={data} />
      <DetailSections detail={data} />

      {data.related_domains.length ? (
        <div style={{ marginTop: 12 }}>
          <Section
            title={t('domains.related', { registrable: domain.registrable_domain })}
          >
            <table className="data">
              <tbody>
                {data.related_domains.map((related) => (
                  <tr key={related.id}>
                    <td>
                      <Link to={`/domains/${related.id}`}>{related.name}</Link>
                    </td>
                    <td className="right mono">{formatCompact(related.query_count)}</td>
                    <td className="right mono faint">{formatCompact(related.blocked_count)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Section>
        </div>
      ) : null}

      {tagsOpen ? (
        <Modal
          title={t('domains.tagsModalTitle', { domain: domain.name })}
          onClose={() => setTagsOpen(false)}
          footer={
            <>
              <span className="spacer" />
              <button type="button" className="btn" onClick={() => setTagsOpen(false)}>
                {t('common.cancel')}
              </button>
              <button type="button" className="btn primary" onClick={() => void saveTags()}>
                {t('common.save')}
              </button>
            </>
          }
        >
          <p className="muted small" style={{ marginTop: 0 }}>
            {t('domains.tagsIntro')}
          </p>
          <div style={{ maxHeight: 340, overflow: 'auto' }}>
            {tags.map((tag) => (
              <label
                key={tag.id}
                className="row"
                style={{ gap: 8, padding: '4px 2px', cursor: 'pointer' }}
              >
                <input
                  type="checkbox"
                  checked={selectedTags.includes(tag.id)}
                  onChange={() =>
                    setSelectedTags((current) =>
                      current.includes(tag.id)
                        ? current.filter((value) => value !== tag.id)
                        : [...current, tag.id],
                    )
                  }
                />
                <Chip label={tag.name} color={tag.color} />
                <span className="faint small">{tag.kind}</span>
              </label>
            ))}
          </div>
        </Modal>
      ) : null}
    </div>
  );
}
