/**
 * The filter tree the UI builds, and the one it reads back from a saved filter.
 *
 * This is where the "saved filter does not filter" defect lived: the Save
 * button appeared as soon as a search term was typed, but saved
 * `activeFilterNode()`, which deliberately leaves the terms out because the
 * backend receives them separately. The result was an empty filter stored as
 * `{}`, which the condition counter then reported as one condition.
 */

import { beforeEach, describe, expect, it } from 'vitest';

import {
  asGroup,
  countEffectiveConditions,
  EMPTY_QUICK,
  pruneGroup,
  useFilterStore,
} from './useFilterStore';
import type { Group, Predicate } from '../types/api';

const store = () => useFilterStore.getState();

beforeEach(() => {
  useFilterStore.setState({
    range: '24h',
    terms: [],
    searchMode: 'any',
    searchFields: ['domain'],
    quick: EMPTY_QUICK,
    advanced: null,
    savedFilterId: null,
    savedFilterName: '',
    sort: 'time',
    direction: 'desc',
  });
});

describe('searchNode', () => {
  it('is null without terms', () => {
    expect(store().searchNode()).toBeNull();
  });

  it('turns a single term into one predicate', () => {
    store().addTerm('youtube');
    expect(store().searchNode()).toEqual({
      field: 'domain',
      operator: 'contains',
      value: 'youtube',
    });
  });

  it('combines terms with OR in "any" mode', () => {
    store().setTerms(['googl', 'youtube', 'googlevideo']);
    const node = store().searchNode() as Group;
    expect(node.op).toBe('or');
    expect(node.children).toHaveLength(3);
  });

  it('combines terms with AND in "all" mode', () => {
    store().setTerms(['googl', 'video']);
    store().setSearchMode('all');
    expect((store().searchNode() as Group).op).toBe('and');
  });

  it('spreads one term across every selected field', () => {
    store().setSearchFields(['domain', 'client_name']);
    store().addTerm('tv');
    const node = store().searchNode() as Group;
    expect(node.op).toBe('or');
    expect(node.children.map((child) => (child as Predicate).field)).toEqual([
      'domain',
      'client_name',
    ]);
  });
});

describe('saveableFilterNode', () => {
  it('is null when nothing narrows the list', () => {
    expect(store().saveableFilterNode()).toBeNull();
  });

  it('includes the search terms', () => {
    // The regression: this used to return null, so pressing Save stored {}.
    store().setTerms(['youtube', 'googlevideo']);
    const node = store().saveableFilterNode();
    expect(node).not.toBeNull();
    expect(JSON.stringify(node)).toContain('googlevideo');
  });

  it('combines the quick filters with the search terms', () => {
    store().setTerms(['youtube']);
    store().setQuick({ personIds: [7] });
    const node = store().saveableFilterNode() as Group;
    expect(node.op).toBe('and');
    expect(JSON.stringify(node)).toContain('person_id');
    expect(JSON.stringify(node)).toContain('youtube');
  });

  it('includes the advanced filter', () => {
    store().setAdvanced({
      op: 'and',
      children: [{ field: 'blocked', operator: 'equals', value: true }],
    });
    expect(JSON.stringify(store().saveableFilterNode())).toContain('blocked');
  });

  it('round-trips through a saved filter', () => {
    store().setTerms(['youtube', 'googlevideo']);
    const saved = store().saveableFilterNode();

    store().reset();
    expect(store().activeFilterNode()).toBeNull();

    store().applySavedFilter(1, 'YouTube activity', saved);
    expect(JSON.stringify(store().activeFilterNode())).toContain('googlevideo');
  });
});

describe('asGroup', () => {
  it('rejects an empty object', () => {
    // A filter saved before the terms were included looks exactly like this.
    expect(asGroup({} as never)).toBeNull();
  });

  it.each([null, undefined])('rejects %s', (value) => {
    expect(asGroup(value)).toBeNull();
  });

  it('wraps a bare predicate', () => {
    const group = asGroup({ field: 'domain', operator: 'contains', value: 'x' });
    expect(group).toEqual({
      op: 'and',
      children: [{ field: 'domain', operator: 'contains', value: 'x' }],
    });
  });

  it('keeps a group as it is', () => {
    const group: Group = {
      op: 'or',
      children: [{ field: 'domain', operator: 'contains', value: 'a' }],
    };
    expect(asGroup(group)).toEqual(group);
  });

  it('drops a group whose conditions are all unusable', () => {
    expect(asGroup({ op: 'and', children: [{} as never] })).toBeNull();
  });
});

describe('countEffectiveConditions', () => {
  it('counts nothing for an empty group', () => {
    expect(countEffectiveConditions({ op: 'and', children: [] })).toBe(0);
  });

  it('does not count a condition the backend would drop', () => {
    // This is what showed "Advanced (1)" while nothing was filtered.
    expect(countEffectiveConditions({ op: 'and', children: [{} as never] })).toBe(0);
    expect(
      countEffectiveConditions({
        op: 'and',
        children: [{ field: 'domain', operator: 'contains', value: '' }],
      }),
    ).toBe(0);
  });

  it('counts nested conditions', () => {
    expect(
      countEffectiveConditions({
        op: 'and',
        children: [
          {
            op: 'or',
            children: [
              { field: 'domain', operator: 'contains', value: 'a' },
              { field: 'domain', operator: 'contains', value: 'b' },
            ],
          },
          { field: 'blocked', operator: 'equals', value: true },
        ],
      }),
    ).toBe(3);
  });
});

describe('applySavedFilter', () => {
  it('does not invent a condition from an empty stored filter', () => {
    store().applySavedFilter(3, 'legacy', {} as never);
    expect(store().advanced).toBeNull();
    expect(countEffectiveConditions(store().advanced)).toBe(0);
    expect(store().activeFilterNode()).toBeNull();
  });

  it('clears the advanced filter when the selection is cleared', () => {
    store().applySavedFilter(1, 'x', {
      op: 'and',
      children: [{ field: 'domain', operator: 'contains', value: 'a' }],
    });
    expect(store().advanced).not.toBeNull();

    store().applySavedFilter(null, '', null);
    expect(store().advanced).toBeNull();
    expect(store().savedFilterId).toBeNull();
  });
});

describe('pruneGroup', () => {
  it('keeps falsy-but-real values', () => {
    const pruned = pruneGroup({
      op: 'and',
      children: [
        { field: 'blocked', operator: 'equals', value: false },
        { field: 'response_time', operator: 'gt', value: 0 },
      ],
    });
    expect(pruned?.children).toHaveLength(2);
  });

  it('drops list conditions with no values', () => {
    expect(
      pruneGroup({ op: 'and', children: [{ field: 'tag', operator: 'in', values: [] }] }),
    ).toBeNull();
  });

  it('keeps operators that take no value', () => {
    const pruned = pruneGroup({
      op: 'and',
      children: [{ field: 'rule', operator: 'is_empty' }],
    });
    expect(pruned?.children).toHaveLength(1);
  });
});
