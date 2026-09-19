/**
 * Visual filter builder.
 *
 * Renders the same nested AND/OR tree the backend evaluates, so
 * `(A OR B) AND (C OR D)` is expressible here and goes to the server
 * unchanged. Field metadata — which operators a field accepts, what values it
 * offers — comes from `/api/meta`, so adding a filterable field on the backend
 * makes it appear here with no frontend change.
 */

import { useMemo } from 'react';
import type { FieldSpec, FilterNode, Group, Predicate } from '../types/api';
import { useAppStore } from '../stores/useAppStore';

const OPERATOR_LABELS: Record<string, string> = {
  equals: 'is',
  not_equals: 'is not',
  contains: 'contains',
  not_contains: 'does not contain',
  startswith: 'starts with',
  endswith: 'ends with',
  regex: 'matches regex',
  not_regex: 'does not match regex',
  in: 'is one of',
  not_in: 'is none of',
  is_empty: 'is empty',
  is_not_empty: 'is not empty',
  gt: '>',
  gte: '≥',
  lt: '<',
  lte: '≤',
};

const VALUELESS = new Set(['is_empty', 'is_not_empty']);
const LIST_OPERATORS = new Set(['in', 'not_in']);

const isGroupNode = (node: FilterNode): node is Group =>
  typeof (node as Group).op === 'string';

function defaultPredicate(fields: FieldSpec[]): Predicate {
  const field = fields.find((item) => item.name === 'domain') ?? fields[0];
  return { field: field.name, operator: field.operators[0], value: '' };
}

export function emptyGroup(): Group {
  return { op: 'and', children: [] };
}

function replaceAt(group: Group, index: number, node: FilterNode | null): Group {
  const children = [...group.children];
  if (node === null) children.splice(index, 1);
  else children[index] = node;
  return { ...group, children };
}

function ValueEditor({
  field,
  predicate,
  onChange,
}: {
  field: FieldSpec;
  predicate: Predicate;
  onChange: (patch: Partial<Predicate>) => void;
}) {
  if (VALUELESS.has(predicate.operator)) return null;

  if (LIST_OPERATORS.has(predicate.operator)) {
    return (
      <input
        type="text"
        value={(predicate.values ?? []).join(', ')}
        placeholder="value, value, value"
        onChange={(event) =>
          onChange({
            values: event.target.value
              .split(',')
              .map((part) => part.trim())
              .filter(Boolean),
          })
        }
        style={{ flex: '1 1 180px', minWidth: 140 }}
      />
    );
  }

  if (field.kind === 'bool') {
    return (
      <select
        value={String(predicate.value ?? 'true')}
        onChange={(event) => onChange({ value: event.target.value === 'true' })}
      >
        <option value="true">yes</option>
        <option value="false">no</option>
      </select>
    );
  }

  if (field.choices.length) {
    return (
      <select
        value={String(predicate.value ?? '')}
        onChange={(event) => onChange({ value: event.target.value })}
        style={{ flex: '1 1 160px' }}
      >
        <option value="">—</option>
        {field.choices.map((choice) => (
          <option key={choice} value={choice}>
            {choice || '(empty)'}
          </option>
        ))}
      </select>
    );
  }

  return (
    <input
      type={field.kind === 'number' ? 'number' : 'text'}
      value={String(predicate.value ?? '')}
      placeholder={field.kind === 'time' ? 'now-24h or 2024-05-01T10:00' : 'value'}
      onChange={(event) =>
        onChange({
          value: field.kind === 'number' ? Number(event.target.value) : event.target.value,
        })
      }
      style={{ flex: '1 1 180px', minWidth: 140 }}
    />
  );
}

function PredicateRow({
  predicate,
  fields,
  onChange,
  onRemove,
}: {
  predicate: Predicate;
  fields: FieldSpec[];
  onChange: (node: Predicate) => void;
  onRemove: () => void;
}) {
  const field = fields.find((item) => item.name === predicate.field) ?? fields[0];

  return (
    <div className="row wrap" style={{ gap: 6 }}>
      <select
        value={predicate.field}
        onChange={(event) => {
          const next = fields.find((item) => item.name === event.target.value);
          if (!next) return;
          onChange({
            field: next.name,
            operator: next.operators.includes(predicate.operator)
              ? predicate.operator
              : next.operators[0],
            value: '',
          });
        }}
        title={field.description}
      >
        {fields.map((item) => (
          <option key={item.name} value={item.name}>
            {item.label}
          </option>
        ))}
      </select>

      <select
        value={predicate.operator}
        onChange={(event) => onChange({ ...predicate, operator: event.target.value })}
      >
        {field.operators.map((operator) => (
          <option key={operator} value={operator}>
            {OPERATOR_LABELS[operator] ?? operator}
          </option>
        ))}
      </select>

      <ValueEditor
        field={field}
        predicate={predicate}
        onChange={(patch) => onChange({ ...predicate, ...patch })}
      />

      <button
        type="button"
        className="btn ghost icon"
        onClick={onRemove}
        aria-label="Remove condition"
        title="Remove condition"
      >
        ×
      </button>
    </div>
  );
}

export function GroupEditor({
  group,
  fields,
  onChange,
  onRemove,
  depth = 0,
}: {
  group: Group;
  fields: FieldSpec[];
  onChange: (group: Group) => void;
  onRemove?: () => void;
  depth?: number;
}) {
  return (
    <div
      style={{
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-sm)',
        padding: 10,
        background: depth % 2 === 0 ? 'var(--bg-sunken)' : 'var(--bg-elevated)',
      }}
    >
      <div className="row" style={{ gap: 6, marginBottom: 8 }}>
        <select
          value={group.op}
          onChange={(event) => onChange({ ...group, op: event.target.value as Group['op'] })}
          title="How the conditions in this group combine"
        >
          <option value="and">Match ALL (AND)</option>
          <option value="or">Match ANY (OR)</option>
          <option value="not">NOT</option>
        </select>
        <span className="spacer" />
        <button
          type="button"
          className="btn sm"
          onClick={() =>
            onChange({ ...group, children: [...group.children, defaultPredicate(fields)] })
          }
        >
          + Condition
        </button>
        {depth < 4 ? (
          <button
            type="button"
            className="btn sm"
            onClick={() => onChange({ ...group, children: [...group.children, emptyGroup()] })}
          >
            + Group
          </button>
        ) : null}
        {onRemove ? (
          <button type="button" className="btn sm ghost" onClick={onRemove} title="Remove group">
            ×
          </button>
        ) : null}
      </div>

      {group.children.length === 0 ? (
        <div className="faint small">No conditions yet — every row matches.</div>
      ) : (
        <div className="grid" style={{ gap: 6 }}>
          {group.children.map((child, index) =>
            isGroupNode(child) ? (
              <GroupEditor
                key={index}
                group={child}
                fields={fields}
                depth={depth + 1}
                onChange={(next) => onChange(replaceAt(group, index, next))}
                onRemove={() => onChange(replaceAt(group, index, null))}
              />
            ) : (
              <PredicateRow
                key={index}
                predicate={child}
                fields={fields}
                onChange={(next) => onChange(replaceAt(group, index, next))}
                onRemove={() => onChange(replaceAt(group, index, null))}
              />
            ),
          )}
        </div>
      )}
    </div>
  );
}

export function FilterBuilder({
  value,
  onChange,
}: {
  value: Group | null;
  onChange: (group: Group | null) => void;
}) {
  const meta = useAppStore((state) => state.meta);
  const fields = useMemo(() => meta?.fields ?? [], [meta]);
  const group = value ?? emptyGroup();

  if (!fields.length) return <div className="muted">Loading fields…</div>;

  return (
    <div className="grid" style={{ gap: 10 }}>
      <GroupEditor group={group} fields={fields} onChange={onChange} />
      <div className="row">
        <button type="button" className="btn sm ghost" onClick={() => onChange(null)}>
          Clear the whole filter
        </button>
      </div>
    </div>
  );
}
