/**
 * The filter the user is currently looking at.
 *
 * One store backs the log view and the dashboard, so switching between them
 * keeps the same question in view. Everything here is turned into the backend's
 * filter tree by `buildRequest` — the browser never filters rows itself.
 */

import { create } from 'zustand';
import type { FilterNode, Group, Predicate, ResultKind, SearchSpec } from '../types/api';
import type { QueryRequest } from '../api/endpoints';

export interface QuickFilters {
  personIds: number[];
  clientIds: number[];
  tags: string[];
  categories: string[];
  result: ResultKind | '';
  queryTypes: string[];
}

export const EMPTY_QUICK: QuickFilters = {
  personIds: [],
  clientIds: [],
  tags: [],
  categories: [],
  result: '',
  queryTypes: [],
};

export const DEFAULT_SEARCH_FIELDS = ['domain'];

interface FilterState {
  range: string;
  terms: string[];
  searchMode: 'any' | 'all';
  searchFields: string[];
  quick: QuickFilters;
  advanced: Group | null;
  savedFilterId: number | null;
  savedFilterName: string;
  sort: string;
  direction: 'asc' | 'desc';
  revision: number;

  setRange: (range: string) => void;
  setTerms: (terms: string[]) => void;
  addTerm: (term: string) => void;
  removeTerm: (term: string) => void;
  setSearchMode: (mode: 'any' | 'all') => void;
  setSearchFields: (fields: string[]) => void;
  setQuick: (patch: Partial<QuickFilters>) => void;
  toggleQuick: <K extends 'personIds' | 'clientIds' | 'tags' | 'categories' | 'queryTypes'>(
    key: K,
    value: QuickFilters[K][number],
  ) => void;
  setAdvanced: (group: Group | null) => void;
  applySavedFilter: (id: number | null, name: string, filter: FilterNode | null) => void;
  setSort: (sort: string, direction: 'asc' | 'desc') => void;
  reset: () => void;
  hasFilters: () => boolean;
  /** The quick-search terms as a filter tree, or null when there are none. */
  searchNode: () => FilterNode | null;
  /**
   * Everything the user can see narrowing the list, as one tree.
   *
   * This is what a saved filter has to contain. `activeFilterNode()` leaves
   * the search terms out because the backend receives them separately, but a
   * saved filter must stand on its own — otherwise saving "domain contains
   * youtube" stores nothing at all.
   */
  saveableFilterNode: () => FilterNode | null;
  /** Filter + search + range, with no paging or sorting. */
  buildFilterRequest: () => QueryRequest;
  buildRequest: () => QueryRequest;
  activeFilterNode: () => FilterNode | null;
}

function orOf(children: Predicate[]): FilterNode | null {
  if (children.length === 0) return null;
  if (children.length === 1) return children[0];
  return { op: 'or', children };
}

function quickToNodes(quick: QuickFilters): FilterNode[] {
  const nodes: FilterNode[] = [];

  const persons = orOf(
    quick.personIds.map((id) => ({ field: 'person_id', operator: 'equals', value: id })),
  );
  if (persons) nodes.push(persons);

  const clients = orOf(
    quick.clientIds.map((id) => ({ field: 'client_id', operator: 'equals', value: id })),
  );
  if (clients) nodes.push(clients);

  if (quick.tags.length) {
    nodes.push({ field: 'tag', operator: 'in', values: quick.tags });
  }
  if (quick.categories.length) {
    nodes.push({ field: 'category', operator: 'in', values: quick.categories });
  }
  if (quick.queryTypes.length) {
    nodes.push({ field: 'query_type', operator: 'in', values: quick.queryTypes });
  }
  if (quick.result) {
    nodes.push({ field: 'result', operator: 'equals', value: quick.result });
  }
  return nodes;
}

/**
 * Turn a stored filter into a group, or null when there is nothing usable.
 *
 * A filter saved before the search terms were included is an empty object.
 * Wrapping that in a group produced `{op:'and', children:[{}]}`: the condition
 * counter saw one child and showed "Advanced (1)", while the SQL builder
 * correctly dropped it and nothing was filtered.
 */
export function asGroup(filter: FilterNode | null | undefined): Group | null {
  if (!filter || typeof filter !== 'object') return null;
  if ('op' in filter && Array.isArray((filter as Group).children)) {
    return pruneGroup(filter as Group);
  }
  if ('field' in filter && (filter as Predicate).field) {
    return pruneGroup({ op: 'and', children: [filter] });
  }
  return null;
}

/** Number of conditions that will actually be sent to the backend. */
export function countEffectiveConditions(group: Group | null): number {
  const pruned = group ? pruneGroup(group) : null;
  const walk = (node: FilterNode): number =>
    'op' in node ? (node as Group).children.reduce((total, c) => total + walk(c), 0) : 1;
  return pruned ? walk(pruned) : 0;
}

/** True when the group has at least one usable condition. */
export function groupHasContent(group: Group | null): boolean {
  if (!group) return false;
  return group.children.some((child) => {
    if ('op' in child) return groupHasContent(child as Group);
    const predicate = child as Predicate;
    if (predicate.operator === 'is_empty' || predicate.operator === 'is_not_empty') return true;
    if (predicate.operator === 'in' || predicate.operator === 'not_in') {
      return (predicate.values ?? []).length > 0;
    }
    return predicate.value !== undefined && predicate.value !== null && predicate.value !== '';
  });
}

/** Drop half-finished conditions so the backend never sees an invalid tree. */
export function pruneGroup(group: Group): Group | null {
  const children: FilterNode[] = [];
  for (const child of group.children) {
    if ('op' in child) {
      const nested = pruneGroup(child as Group);
      if (nested) children.push(nested);
      continue;
    }
    const predicate = child as Predicate;
    if (predicate.operator === 'is_empty' || predicate.operator === 'is_not_empty') {
      children.push({ field: predicate.field, operator: predicate.operator });
      continue;
    }
    if (predicate.operator === 'in' || predicate.operator === 'not_in') {
      const values = (predicate.values ?? []).filter((value) => String(value).trim() !== '');
      if (values.length) children.push({ ...predicate, values });
      continue;
    }
    if (predicate.value !== undefined && predicate.value !== null && predicate.value !== '') {
      children.push({ field: predicate.field, operator: predicate.operator, value: predicate.value });
    }
  }
  if (!children.length) return null;
  return { op: group.op, children };
}

export const useFilterStore = create<FilterState>((set, get) => ({
  range: '24h',
  terms: [],
  searchMode: 'any',
  searchFields: DEFAULT_SEARCH_FIELDS,
  quick: EMPTY_QUICK,
  advanced: null,
  savedFilterId: null,
  savedFilterName: '',
  sort: 'time',
  direction: 'desc',
  revision: 0,

  setRange: (range) => set((state) => ({ range, revision: state.revision + 1 })),
  setTerms: (terms) => set((state) => ({ terms, revision: state.revision + 1 })),
  addTerm: (term) =>
    set((state) => {
      const value = term.trim();
      if (!value || state.terms.includes(value)) return state;
      return { terms: [...state.terms, value], revision: state.revision + 1 };
    }),
  removeTerm: (term) =>
    set((state) => ({
      terms: state.terms.filter((item) => item !== term),
      revision: state.revision + 1,
    })),
  setSearchMode: (searchMode) => set((state) => ({ searchMode, revision: state.revision + 1 })),
  setSearchFields: (searchFields) =>
    set((state) => ({
      searchFields: searchFields.length ? searchFields : DEFAULT_SEARCH_FIELDS,
      revision: state.revision + 1,
    })),

  setQuick: (patch) =>
    set((state) => ({ quick: { ...state.quick, ...patch }, revision: state.revision + 1 })),

  toggleQuick: (key, value) =>
    set((state) => {
      const current = state.quick[key] as (string | number)[];
      const next = current.includes(value)
        ? current.filter((item) => item !== value)
        : [...current, value];
      return {
        quick: { ...state.quick, [key]: next } as QuickFilters,
        revision: state.revision + 1,
      };
    }),

  setAdvanced: (advanced) => set((state) => ({ advanced, revision: state.revision + 1 })),

  applySavedFilter: (id, name, filter) =>
    set((state) => ({
      savedFilterId: id,
      savedFilterName: name,
      advanced: id === null ? null : (asGroup(filter) ?? state.advanced),
      revision: state.revision + 1,
    })),

  setSort: (sort, direction) => set((state) => ({ sort, direction, revision: state.revision + 1 })),

  reset: () =>
    set((state) => ({
      terms: [],
      quick: EMPTY_QUICK,
      advanced: null,
      savedFilterId: null,
      savedFilterName: '',
      revision: state.revision + 1,
    })),

  hasFilters: () => {
    const state = get();
    return (
      state.terms.length > 0 ||
      quickToNodes(state.quick).length > 0 ||
      groupHasContent(state.advanced) ||
      state.savedFilterId !== null
    );
  },

  activeFilterNode: () => {
    const state = get();
    const nodes: FilterNode[] = quickToNodes(state.quick);
    if (state.advanced) {
      const pruned = pruneGroup(state.advanced);
      if (pruned) nodes.push(pruned);
    }
    if (!nodes.length) return null;
    if (nodes.length === 1) return nodes[0];
    return { op: 'and', children: nodes };
  },

  searchNode: () => {
    const state = get();
    const terms = state.terms.map((term) => term.trim()).filter(Boolean);
    if (!terms.length) return null;
    const fields = state.searchFields.length ? state.searchFields : DEFAULT_SEARCH_FIELDS;

    // Mirrors the backend's quick_search_filter: each term matches across the
    // selected fields, and the terms combine with OR (any) or AND (all).
    const perTerm: FilterNode[] = terms.map((term) => {
      const alternatives: FilterNode[] = fields.map((field) => ({
        field,
        operator: 'contains',
        value: term,
      }));
      return alternatives.length > 1 ? { op: 'or', children: alternatives } : alternatives[0];
    });

    if (perTerm.length === 1) return perTerm[0];
    return { op: state.searchMode === 'any' ? 'or' : 'and', children: perTerm };
  },

  saveableFilterNode: () => {
    const state = get();
    const parts = [state.activeFilterNode(), state.searchNode()].filter(
      (node): node is FilterNode => node !== null,
    );
    if (!parts.length) return null;
    if (parts.length === 1) return parts[0];
    return { op: 'and', children: parts };
  },

  buildFilterRequest: () => {
    const state = get();
    const search: SearchSpec | null = state.terms.length
      ? {
          terms: state.terms,
          mode: state.searchMode,
          fields: state.searchFields,
          operator: 'contains',
        }
      : null;
    return {
      filter: state.activeFilterNode(),
      search,
      range: state.range,
    };
  },

  buildRequest: () => {
    const state = get();
    return {
      ...state.buildFilterRequest(),
      sort: state.sort,
      direction: state.direction,
    };
  },
}));
