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

export function DomainDetailPage({ id }: { id: number }) {
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
        <Spinner label="Loading domain…" />
      </div>
    );

  const domain = data.domain;
  const allTags = [...domain.categories, ...domain.tags];

  return (
    <div className="main">
      <div className="row wrap" style={{ gap: 10, marginBottom: 12 }}>
        <div style={{ minWidth: 0 }}>
          <div className="small muted">
            <Link to="/domains">Domains</Link> /
          </div>
          <h1 style={{ overflowWrap: 'anywhere' }}>{domain.name}</h1>
          <div className="muted small">
            Registrable: <span className="mono">{domain.registrable_domain}</span> · first seen{' '}
            {formatDateTime(domain.first_seen_ns)} · last seen{' '}
            {formatDateTime(domain.last_seen_ns)}
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
              <span className="faint small">No tags — add one, or write a rule.</span>
            )}
          </div>
        </div>
        <span className="spacer" />
        <RangePicker range={range} onChange={setRange} />
        <button type="button" className="btn" onClick={openTags}>
          Edit tags
        </button>
        <button type="button" className="btn primary" onClick={showInLog}>
          Show in log
        </button>
      </div>

      {loading ? <Spinner /> : null}
      <SummaryCards detail={data} />
      <DetailSections detail={data} />

      {data.related_domains.length ? (
        <div style={{ marginTop: 12 }}>
          <Section title={`Related domains under ${domain.registrable_domain}`}>
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
          title={`Tags for ${domain.name}`}
          onClose={() => setTagsOpen(false)}
          footer={
            <>
              <span className="spacer" />
              <button type="button" className="btn" onClick={() => setTagsOpen(false)}>
                Cancel
              </button>
              <button type="button" className="btn primary" onClick={() => void saveTags()}>
                Save
              </button>
            </>
          }
        >
          <p className="muted small" style={{ marginTop: 0 }}>
            Tags you set here stay put when the rules change. Automatic tags are managed by the
            rule engine and are not listed.
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
