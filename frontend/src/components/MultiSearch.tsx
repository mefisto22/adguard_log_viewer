/**
 * The multi-term search box.
 *
 * Terms become chips. ANY returns rows matching at least one term — the
 * "googl / youtube / googlevideo" case — while ALL requires every one of them.
 * The field selector decides what the terms are matched against.
 */

import { useState } from 'react';
import { Chip } from './ui';
import { useFilterStore } from '../stores/useFilterStore';
import { useAppStore } from '../stores/useAppStore';

const SEARCHABLE_FIELDS = [
  'domain',
  'registrable_domain',
  'client_ip',
  'client_name',
  'person',
  'answer',
  'rule',
  'upstream',
];

export function MultiSearch() {
  const [draft, setDraft] = useState('');
  const terms = useFilterStore((state) => state.terms);
  const mode = useFilterStore((state) => state.searchMode);
  const fields = useFilterStore((state) => state.searchFields);
  const addTerm = useFilterStore((state) => state.addTerm);
  const removeTerm = useFilterStore((state) => state.removeTerm);
  const setSearchMode = useFilterStore((state) => state.setSearchMode);
  const setSearchFields = useFilterStore((state) => state.setSearchFields);
  const meta = useAppStore((state) => state.meta);

  const fieldLabel = (name: string) =>
    meta?.fields.find((field) => field.name === name)?.label ?? name;

  const commit = () => {
    // A comma or space separated paste becomes several terms at once.
    const parts = draft
      .split(/[,\n]/)
      .map((part) => part.trim())
      .filter(Boolean);
    parts.forEach(addTerm);
    setDraft('');
  };

  return (
    <div
      className="row"
      style={{
        gap: 6,
        flexWrap: 'wrap',
        flex: '1 1 320px',
        minWidth: 280,
        border: '1px solid var(--border-strong)',
        borderRadius: 'var(--radius-sm)',
        background: 'var(--bg-elevated)',
        padding: '3px 6px',
      }}
    >
      {terms.map((term) => (
        <Chip key={term} label={term} onRemove={() => removeTerm(term)} />
      ))}

      <input
        type="search"
        value={draft}
        placeholder={terms.length ? 'Add another term…' : 'Search domain, client, answer…'}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ',') {
            event.preventDefault();
            commit();
          } else if (event.key === 'Backspace' && !draft && terms.length) {
            removeTerm(terms[terms.length - 1]);
          }
        }}
        onBlur={commit}
        style={{
          flex: '1 1 140px',
          minWidth: 120,
          border: 0,
          padding: '3px 2px',
          background: 'transparent',
        }}
      />

      {terms.length > 1 ? (
        <button
          type="button"
          className="btn sm"
          title={
            mode === 'any'
              ? 'Matching at least one term (OR). Click for ALL.'
              : 'Matching every term (AND). Click for ANY.'
          }
          onClick={() => setSearchMode(mode === 'any' ? 'all' : 'any')}
          style={{ borderColor: 'var(--primary)', color: 'var(--primary-strong)' }}
        >
          {mode === 'any' ? 'ANY' : 'ALL'}
        </button>
      ) : null}

      <select
        value={fields.length === 1 ? fields[0] : '__multi__'}
        onChange={(event) => {
          const value = event.target.value;
          if (value === '__all__') {
            setSearchFields(SEARCHABLE_FIELDS);
          } else if (value !== '__multi__') {
            setSearchFields([value]);
          }
        }}
        title="Which field the terms are matched against"
        style={{ border: 0, background: 'transparent', fontSize: 12, color: 'var(--text-muted)' }}
      >
        {SEARCHABLE_FIELDS.map((name) => (
          <option key={name} value={name}>
            in {fieldLabel(name)}
          </option>
        ))}
        <option value="__all__">in any field</option>
        {fields.length > 1 ? (
          <option value="__multi__">in {fields.length} fields</option>
        ) : null}
      </select>
    </div>
  );
}
