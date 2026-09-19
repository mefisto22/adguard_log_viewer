/**
 * Tags, categories and the rules that apply them automatically.
 *
 * A rule is a name, a match mode, a list of conditions and the tags to apply.
 * The built-in set ships with the add-on and is read-only; anything the user
 * adds sits alongside it and wins at equal priority.
 */

import { useState } from 'react';
import { Banner, Chip, Empty, Modal, Section, Spinner } from '../components/ui';
import { endpoints } from '../api/endpoints';
import { useAsync } from '../hooks/useAsync';
import { useAppStore } from '../stores/useAppStore';
import type { Rule, RuleCondition, TagKind } from '../types/api';

const OPERATORS: { value: string; label: string }[] = [
  { value: 'suffix', label: 'is or is under (domain suffix)' },
  { value: 'equals', label: 'equals exactly' },
  { value: 'contains', label: 'contains' },
  { value: 'startswith', label: 'starts with' },
  { value: 'endswith', label: 'ends with' },
  { value: 'wildcard', label: 'matches wildcard' },
  { value: 'regex', label: 'matches regex' },
];

const emptyRule = (): Omit<Rule, 'id' | 'builtin'> => ({
  name: '',
  enabled: true,
  priority: 100,
  match_mode: 'any',
  conditions: [{ field: 'domain', operator: 'suffix', value: '' }],
  tags: [{ name: '', kind: 'tag' }],
});

export function RulesPage() {
  const { tags, refreshTags } = useAppStore();
  const { data, error, loading, reload } = useAsync(() => endpoints.rules(), []);

  const [editing, setEditing] = useState<Rule | 'new' | null>(null);
  const [draft, setDraft] = useState<Omit<Rule, 'id' | 'builtin'>>(emptyRule());
  const [formError, setFormError] = useState<string | null>(null);
  const [testDomain, setTestDomain] = useState('');
  const [testResult, setTestResult] = useState<string | null>(null);
  const [showBuiltin, setShowBuiltin] = useState(false);
  const [busy, setBusy] = useState(false);

  const openNew = () => {
    setDraft(emptyRule());
    setEditing('new');
    setFormError(null);
    setTestResult(null);
  };

  const openEdit = (rule: Rule) => {
    setDraft({
      name: rule.name,
      enabled: rule.enabled,
      priority: rule.priority,
      match_mode: rule.match_mode,
      conditions: rule.conditions.length
        ? rule.conditions
        : [{ field: 'domain', operator: 'suffix', value: '' }],
      tags: rule.tags.length ? rule.tags : [{ name: '', kind: 'tag' }],
    });
    setEditing(rule);
    setFormError(null);
    setTestResult(null);
  };

  const save = async () => {
    setFormError(null);
    const payload = {
      ...draft,
      conditions: draft.conditions.filter((condition) => condition.value.trim()),
      tags: draft.tags.filter((tag) => tag.name.trim()),
    };
    if (!payload.name.trim()) {
      setFormError('The rule needs a name.');
      return;
    }
    if (!payload.conditions.length) {
      setFormError('Add at least one condition.');
      return;
    }
    if (!payload.tags.length) {
      setFormError('Add at least one tag to apply.');
      return;
    }
    try {
      if (editing === 'new') await endpoints.createRule(payload);
      else if (editing) await endpoints.updateRule(editing.id, payload);
      setEditing(null);
      reload();
      await refreshTags();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : String(err));
    }
  };

  const remove = async (rule: Rule) => {
    if (!window.confirm(`Delete the rule “${rule.name}”?`)) return;
    await endpoints.deleteRule(rule.id);
    reload();
  };

  const runTest = async () => {
    if (!testDomain.trim()) return;
    try {
      const result = await endpoints.testRule(testDomain.trim(), {
        ...draft,
        conditions: draft.conditions.filter((condition) => condition.value.trim()),
        tags: draft.tags.filter((tag) => tag.name.trim()),
        name: draft.name || 'draft',
      });
      setTestResult(
        result.matched
          ? `Matches — would apply: ${result.tags.map((tag) => tag.name).join(', ')}`
          : 'Does not match this domain.',
      );
    } catch (err) {
      setTestResult(err instanceof Error ? err.message : String(err));
    }
  };

  const reclassify = async () => {
    setBusy(true);
    try {
      await endpoints.reclassify();
      reload();
    } finally {
      setBusy(false);
    }
  };

  const patchCondition = (index: number, patch: Partial<RuleCondition>) =>
    setDraft((current) => ({
      ...current,
      conditions: current.conditions.map((condition, position) =>
        position === index ? { ...condition, ...patch } : condition,
      ),
    }));

  return (
    <div className="main">
      {error ? <Banner kind="error">{error}</Banner> : null}

      {data && data.pending_reclassification > 0 ? (
        <Banner
          kind="info"
          action={
            <button type="button" className="btn sm" disabled={busy} onClick={() => void reclassify()}>
              {busy ? 'Working…' : 'Re-classify now'}
            </button>
          }
        >
          {data.pending_reclassification} domain(s) are still tagged with an older rule set. They
          are re-classified in the background as ingest runs.
        </Banner>
      ) : null}

      <div style={{ marginBottom: 12 }}>
        <Section
          title="Your rules"
          actions={
            <button type="button" className="btn primary" onClick={openNew}>
              Add rule
            </button>
          }
          bodyStyle={{ padding: 0 }}
        >
          {loading && !data ? (
            <div style={{ padding: 16 }}>
              <Spinner label="Loading rules…" />
            </div>
          ) : null}

          {data && data.items.length === 0 ? (
            <Empty>
              No rules of your own yet. The built-in set already covers the big services — add a
              rule when you want your own label, for example tagging your work domains.
            </Empty>
          ) : null}

          {data && data.items.length > 0 ? (
            <table className="data">
              <thead>
                <tr>
                  <th>Rule</th>
                  <th>Match</th>
                  <th>Conditions</th>
                  <th>Applies</th>
                  <th className="right">Priority</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.items.map((rule) => (
                  <tr key={rule.id}>
                    <td>
                      <strong>{rule.name}</strong>
                      {!rule.enabled ? <span className="faint small"> (disabled)</span> : null}
                    </td>
                    <td className="small muted">{rule.match_mode === 'any' ? 'ANY' : 'ALL'}</td>
                    <td className="small mono">
                      {rule.conditions.map((condition, index) => (
                        <div key={index}>
                          {condition.operator} <strong>{condition.value}</strong>
                        </div>
                      ))}
                    </td>
                    <td>
                      <div className="row wrap" style={{ gap: 4 }}>
                        {rule.tags.map((tag) => (
                          <Chip key={`${tag.kind}:${tag.name}`} label={tag.name} />
                        ))}
                      </div>
                    </td>
                    <td className="right mono">{rule.priority}</td>
                    <td className="right nowrap">
                      <button type="button" className="btn sm" onClick={() => openEdit(rule)}>
                        Edit
                      </button>{' '}
                      <button
                        type="button"
                        className="btn sm danger"
                        onClick={() => void remove(rule)}
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
        </Section>
      </div>

      <Section
        title={`Built-in rules (${data?.builtin.length ?? 0})`}
        actions={
          <button type="button" className="btn sm" onClick={() => setShowBuiltin((v) => !v)}>
            {showBuiltin ? 'Hide' : 'Show'}
          </button>
        }
        bodyStyle={showBuiltin ? { padding: 0 } : undefined}
      >
        {showBuiltin ? (
          <table className="data">
            <thead>
              <tr>
                <th>Rule</th>
                <th>Matches</th>
                <th>Applies</th>
              </tr>
            </thead>
            <tbody>
              {(data?.builtin ?? []).map((rule) => (
                <tr key={rule.name}>
                  <td>{rule.name}</td>
                  <td className="small mono" style={{ maxWidth: 420 }}>
                    <span className="truncate" title={rule.conditions.map((c) => c.value).join(', ')}>
                      {rule.conditions.map((c) => c.value).join(', ')}
                    </span>
                  </td>
                  <td>
                    <div className="row wrap" style={{ gap: 4 }}>
                      {rule.tags.map((tag) => (
                        <Chip key={`${tag.kind}:${tag.name}`} label={tag.name} />
                      ))}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="muted small" style={{ margin: 0 }}>
            The add-on ships with a rule set covering the common services — Google, Meta, streaming,
            advertising, telemetry, IoT vendors and more. It is bundled with the image; nothing is
            downloaded at runtime.
          </p>
        )}
      </Section>

      {editing ? (
        <Modal
          title={editing === 'new' ? 'New rule' : `Edit “${editing.name}”`}
          onClose={() => setEditing(null)}
          wide
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
          {formError ? <Banner kind="error">{formError}</Banner> : null}

          <div className="grid" style={{ gap: 12 }}>
            <div className="row wrap" style={{ gap: 10 }}>
              <label className="field" style={{ flex: '2 1 220px' }}>
                Rule name
                <input
                  type="text"
                  autoFocus
                  value={draft.name}
                  placeholder="YouTube"
                  onChange={(event) => setDraft({ ...draft, name: event.target.value })}
                />
              </label>
              <label className="field" style={{ flex: '1 1 130px' }}>
                Match
                <select
                  value={draft.match_mode}
                  onChange={(event) =>
                    setDraft({ ...draft, match_mode: event.target.value as 'any' | 'all' })
                  }
                >
                  <option value="any">ANY condition</option>
                  <option value="all">ALL conditions</option>
                </select>
              </label>
              <label className="field" style={{ flex: '0 0 110px' }}>
                Priority
                <input
                  type="number"
                  value={draft.priority}
                  onChange={(event) =>
                    setDraft({ ...draft, priority: Number(event.target.value) || 100 })
                  }
                />
              </label>
              <label className="field" style={{ flex: '0 0 auto' }}>
                Enabled
                <input
                  type="checkbox"
                  checked={draft.enabled}
                  onChange={(event) => setDraft({ ...draft, enabled: event.target.checked })}
                />
              </label>
            </div>

            <div className="field">
              Conditions
              <div className="grid" style={{ gap: 6 }}>
                {draft.conditions.map((condition, index) => (
                  <div key={index} className="row" style={{ gap: 6 }}>
                    <span className="muted small nowrap" style={{ width: 52 }}>
                      domain
                    </span>
                    <select
                      value={condition.operator}
                      onChange={(event) => patchCondition(index, { operator: event.target.value })}
                    >
                      {OPERATORS.map((operator) => (
                        <option key={operator.value} value={operator.value}>
                          {operator.label}
                        </option>
                      ))}
                    </select>
                    <input
                      type="text"
                      value={condition.value}
                      placeholder="youtube.com"
                      onChange={(event) => patchCondition(index, { value: event.target.value })}
                      style={{ flex: '1 1 160px' }}
                    />
                    <button
                      type="button"
                      className="btn ghost icon"
                      onClick={() =>
                        setDraft({
                          ...draft,
                          conditions: draft.conditions.filter((_, position) => position !== index),
                        })
                      }
                    >
                      ×
                    </button>
                  </div>
                ))}
                <div>
                  <button
                    type="button"
                    className="btn sm"
                    onClick={() =>
                      setDraft({
                        ...draft,
                        conditions: [
                          ...draft.conditions,
                          { field: 'domain', operator: 'contains', value: '' },
                        ],
                      })
                    }
                  >
                    + Condition
                  </button>
                </div>
              </div>
            </div>

            <div className="field">
              Tags to apply
              <div className="grid" style={{ gap: 6 }}>
                {draft.tags.map((tag, index) => (
                  <div key={index} className="row" style={{ gap: 6 }}>
                    <input
                      type="text"
                      list="known-tags"
                      value={tag.name}
                      placeholder="YouTube"
                      onChange={(event) =>
                        setDraft({
                          ...draft,
                          tags: draft.tags.map((item, position) =>
                            position === index ? { ...item, name: event.target.value } : item,
                          ),
                        })
                      }
                      style={{ flex: '1 1 160px' }}
                    />
                    <select
                      value={tag.kind}
                      onChange={(event) =>
                        setDraft({
                          ...draft,
                          tags: draft.tags.map((item, position) =>
                            position === index
                              ? { ...item, kind: event.target.value as TagKind }
                              : item,
                          ),
                        })
                      }
                    >
                      <option value="tag">tag</option>
                      <option value="category">category</option>
                    </select>
                    <button
                      type="button"
                      className="btn ghost icon"
                      onClick={() =>
                        setDraft({
                          ...draft,
                          tags: draft.tags.filter((_, position) => position !== index),
                        })
                      }
                    >
                      ×
                    </button>
                  </div>
                ))}
                <datalist id="known-tags">
                  {tags.map((tag) => (
                    <option key={tag.id} value={tag.name} />
                  ))}
                </datalist>
                <div>
                  <button
                    type="button"
                    className="btn sm"
                    onClick={() =>
                      setDraft({ ...draft, tags: [...draft.tags, { name: '', kind: 'tag' }] })
                    }
                  >
                    + Tag
                  </button>
                </div>
              </div>
            </div>

            <div className="field">
              Try it
              <div className="row" style={{ gap: 6 }}>
                <input
                  type="text"
                  value={testDomain}
                  placeholder="m.youtube.com"
                  onChange={(event) => setTestDomain(event.target.value)}
                  style={{ flex: '1 1 200px' }}
                />
                <button type="button" className="btn" onClick={() => void runTest()}>
                  Test
                </button>
              </div>
              {testResult ? <div className="small muted">{testResult}</div> : null}
            </div>
          </div>
        </Modal>
      ) : null}
    </div>
  );
}
