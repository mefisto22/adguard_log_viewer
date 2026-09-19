/** The filter row shown above the log table and the dashboard. */

import { useMemo, useState } from 'react';
import { MultiSearch } from './MultiSearch';
import { MultiSelect } from './MultiSelect';
import { FilterBuilder, emptyGroup } from './FilterBuilder';
import { Banner, Modal } from './ui';
import { useAppStore } from '../stores/useAppStore';
import {
  countEffectiveConditions,
  groupHasContent,
  pruneGroup,
  useFilterStore,
} from '../stores/useFilterStore';
import { endpoints } from '../api/endpoints';
import { RANGE_LABELS } from '../utils/format';
import type { ResultKind } from '../types/api';

export function FilterBar({ compact = false }: { compact?: boolean }) {
  const { meta, tags, persons, devices, savedFilters, refreshSavedFilters } = useAppStore();
  const store = useFilterStore();
  const [builderOpen, setBuilderOpen] = useState(false);
  const [draft, setDraft] = useState(store.advanced ?? emptyGroup());
  const [saveOpen, setSaveOpen] = useState(false);
  const [saveName, setSaveName] = useState('');
  const [saveError, setSaveError] = useState<string | null>(null);

  const ranges = meta?.ranges ?? ['15m', '1h', '24h', '7d', '30d', 'all'];
  // Counted after pruning, so the badge can never claim a condition that
  // the backend would drop.
  const advancedCount = countEffectiveConditions(store.advanced);

  const categoryOptions = useMemo(
    () =>
      tags
        .filter((tag) => tag.kind === 'category')
        .map((tag) => ({ value: tag.name, label: tag.name, color: tag.color })),
    [tags],
  );
  const tagOptions = useMemo(
    () =>
      tags
        .filter((tag) => tag.kind === 'tag')
        .map((tag) => ({ value: tag.name, label: tag.name, color: tag.color })),
    [tags],
  );
  const personOptions = useMemo(
    () =>
      persons.map((person) => ({
        value: String(person.id),
        label: person.name,
        hint: `${person.device_count} devices`,
        color: person.color || undefined,
      })),
    [persons],
  );
  const deviceOptions = useMemo(
    () =>
      devices.map((device) => ({
        value: String(device.id),
        label: device.name,
        hint: device.ip,
      })),
    [devices],
  );

  const queryTypeOptions = useMemo(() => {
    const field = meta?.fields.find((item) => item.name === 'query_type');
    return (field?.choices ?? []).map((choice) => ({ value: choice, label: choice }));
  }, [meta]);

  const openBuilder = () => {
    setDraft(store.advanced ?? emptyGroup());
    setBuilderOpen(true);
  };

  const applyBuilder = () => {
    const pruned = pruneGroup(draft);
    store.setAdvanced(pruned);
    setBuilderOpen(false);
  };

  // The search terms are part of what the user sees narrowing the list, so a
  // saved filter has to carry them. Saving activeFilterNode() alone stored an
  // empty filter whenever the only thing set was a search term.
  const saveable = store.saveableFilterNode();

  const saveCurrent = async () => {
    setSaveError(null);
    if (!saveable) {
      setSaveError('There is nothing to save yet — add a search term or a condition first.');
      return;
    }
    try {
      await endpoints.createSavedFilter({ name: saveName, filter: saveable });
      await refreshSavedFilters();
      setSaveOpen(false);
      setSaveName('');
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : String(error));
    }
  };

  return (
    <div
      className="row wrap"
      style={{
        gap: 8,
        padding: compact ? 0 : '10px 12px',
        background: compact ? undefined : 'var(--bg-elevated)',
        borderBottom: compact ? undefined : '1px solid var(--border)',
      }}
    >
      <select
        value={store.range}
        onChange={(event) => store.setRange(event.target.value)}
        title="Time range"
      >
        {ranges.map((range) => (
          <option key={range} value={range}>
            {RANGE_LABELS[range] ?? range}
          </option>
        ))}
      </select>

      <MultiSearch />

      <MultiSelect
        label="Person"
        options={personOptions}
        selected={store.quick.personIds.map(String)}
        onToggle={(value) => store.toggleQuick('personIds', Number(value))}
        onClear={() => store.setQuick({ personIds: [] })}
      />

      <MultiSelect
        label="Device"
        options={deviceOptions}
        selected={store.quick.clientIds.map(String)}
        onToggle={(value) => store.toggleQuick('clientIds', Number(value))}
        onClear={() => store.setQuick({ clientIds: [] })}
      />

      <MultiSelect
        label="Category"
        options={categoryOptions}
        selected={store.quick.categories}
        onToggle={(value) => store.toggleQuick('categories', value)}
        onClear={() => store.setQuick({ categories: [] })}
      />

      <MultiSelect
        label="Tag"
        options={tagOptions}
        selected={store.quick.tags}
        onToggle={(value) => store.toggleQuick('tags', value)}
        onClear={() => store.setQuick({ tags: [] })}
      />

      <MultiSelect
        label="Type"
        options={queryTypeOptions}
        selected={store.quick.queryTypes}
        onToggle={(value) => store.toggleQuick('queryTypes', value)}
        onClear={() => store.setQuick({ queryTypes: [] })}
        searchable={false}
        width={160}
      />

      <select
        value={store.quick.result}
        onChange={(event) =>
          store.setQuick({ result: event.target.value as ResultKind | '' })
        }
        title="Result"
      >
        <option value="">Any result</option>
        <option value="blocked">Blocked</option>
        <option value="allowed">Allowed</option>
        <option value="rewritten">Rewritten</option>
        <option value="allowlisted">Allow-listed</option>
        <option value="error">Error</option>
      </select>

      <button
        type="button"
        className="btn"
        onClick={openBuilder}
        style={
          advancedCount
            ? { borderColor: 'var(--primary)', color: 'var(--primary-strong)' }
            : undefined
        }
      >
        Advanced{advancedCount ? ` (${advancedCount})` : ''}
      </button>

      <select
        value={store.savedFilterId ?? ''}
        onChange={(event) => {
          const id = event.target.value ? Number(event.target.value) : null;
          if (id === null) {
            store.applySavedFilter(null, '', null);
            store.setAdvanced(null);
            return;
          }
          const saved = savedFilters.find((item) => item.id === id);
          if (saved) store.applySavedFilter(saved.id, saved.name, saved.filter);
        }}
        title="Saved filters"
      >
        <option value="">Saved filters…</option>
        {savedFilters.map((saved) => (
          <option key={saved.id} value={saved.id}>
            {saved.name}
          </option>
        ))}
      </select>

      {store.hasFilters() ? (
        <>
          <button
            type="button"
            className="btn"
            disabled={!saveable}
            title={
              saveable
                ? 'Save these conditions for later'
                : 'Add a search term or a condition first'
            }
            onClick={() => setSaveOpen(true)}
          >
            Save
          </button>
          <button type="button" className="btn ghost" onClick={store.reset}>
            Reset
          </button>
        </>
      ) : null}

      {builderOpen ? (
        <Modal
          title="Advanced filter"
          onClose={() => setBuilderOpen(false)}
          wide
          footer={
            <>
              <span className="spacer" />
              <button type="button" className="btn" onClick={() => setBuilderOpen(false)}>
                Cancel
              </button>
              <button type="button" className="btn primary" onClick={applyBuilder}>
                Apply
              </button>
            </>
          }
        >
          <p className="muted small" style={{ marginTop: 0 }}>
            Groups can be nested, so <code>(A OR B) AND (C OR D)</code> is expressible. The whole
            tree is evaluated by the backend in SQL.
          </p>
          <FilterBuilder value={draft} onChange={(group) => setDraft(group ?? emptyGroup())} />
          {!groupHasContent(draft) ? (
            <p className="faint small">Empty conditions are dropped when the filter is applied.</p>
          ) : null}
        </Modal>
      ) : null}

      {saveOpen ? (
        <Modal
          title="Save this filter"
          onClose={() => setSaveOpen(false)}
          footer={
            <>
              <span className="spacer" />
              <button type="button" className="btn" onClick={() => setSaveOpen(false)}>
                Cancel
              </button>
              <button
                type="button"
                className="btn primary"
                disabled={!saveName.trim()}
                onClick={() => void saveCurrent()}
              >
                Save
              </button>
            </>
          }
        >
          {saveError ? <Banner kind="error">{saveError}</Banner> : null}
          <label className="field">
            Name
            <input
              type="text"
              autoFocus
              value={saveName}
              placeholder="YouTube activity"
              onChange={(event) => setSaveName(event.target.value)}
            />
          </label>
          <p className="faint small">
            The search terms, the quick filters and the advanced filter are all saved. The time
            range is not — it stays as you set it each time.
          </p>
        </Modal>
      ) : null}
    </div>
  );
}
