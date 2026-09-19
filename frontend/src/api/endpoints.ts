/** Every backend call the UI makes, in one place. */

import { api, qs } from './api-core';
import type {
  AppSettings,
  Dashboard,
  Device,
  DomainRow,
  FilterNode,
  Meta,
  Person,
  QueryPage,
  QueryRow,
  Rule,
  SavedFilter,
  SearchSpec,
  Status,
  Tag,
  TagKind,
  Timeline,
  TopRow,
} from '../types/api';

export interface QueryRequest {
  filter?: FilterNode | null;
  search?: SearchSpec | null;
  range?: string;
  from?: string | number;
  to?: string | number;
  saved_filter_id?: number | null;
  limit?: number;
  offset?: number;
  sort?: string;
  direction?: 'asc' | 'desc';
  include_total?: boolean;
  before_id?: number | null;
  after_id?: number | null;
}

/** Strip keys the backend's strict schemas would reject. */
function clean<T extends object>(payload: T): T {
  const result: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(payload)) {
    if (value === undefined || value === null) continue;
    result[key] = value;
  }
  return result as T;
}

export const endpoints = {
  meta: () => api.get<Meta>('api/meta'),
  status: () => api.get<Status>('api/status'),

  searchQueries: (request: QueryRequest) =>
    api.post<QueryPage>('api/queries/search', clean(request)),
  getQuery: (id: number) => api.get<QueryRow>(`api/queries/${id}`),

  dashboard: (request: QueryRequest & { top_limit?: number; buckets?: number; parts?: string[] }) =>
    api.post<Dashboard>('api/dashboard', clean(request)),
  timeline: (request: QueryRequest & { buckets?: number }) =>
    api.post<Timeline>('api/dashboard/timeline', clean(request)),

  devices: (params: { search?: string; person_id?: number; sort?: string } = {}) =>
    api.get<{ items: Device[]; total: number }>(`api/devices${qs(params)}`),
  device: (id: number) => api.get<Device>(`api/devices/${id}`),
  deviceDetail: (id: number, range: string) =>
    api.get<DetailPayload & { device: Device }>(`api/devices/${id}/detail${qs({ range })}`),
  updateDevice: (id: number, body: { alias?: string; person_id?: number | null; clear_person?: boolean }) =>
    api.patch<{ ok: true; device: Device }>(`api/devices/${id}`, body),
  deleteDevice: (id: number) => api.delete<{ ok: true }>(`api/devices/${id}`),
  assignDevices: (person_id: number | null, client_ids: number[]) =>
    api.post<{ ok: true; changed: number }>('api/devices/assign', { person_id, client_ids }),

  persons: () => api.get<{ items: Person[]; total: number }>('api/persons'),
  createPerson: (body: { name: string; color?: string; note?: string }) =>
    api.post<{ ok: true; id: number }>('api/persons', body),
  updatePerson: (id: number, body: { name?: string; color?: string; note?: string }) =>
    api.patch<{ ok: true }>(`api/persons/${id}`, body),
  deletePerson: (id: number) => api.delete<{ ok: true }>(`api/persons/${id}`),
  personDetail: (id: number, range: string) =>
    api.get<DetailPayload & { person: Person }>(`api/persons/${id}/detail${qs({ range })}`),

  domains: (params: { search?: string; sort?: string; limit?: number; offset?: number } = {}) =>
    api.get<{ items: DomainRow[]; total: number }>(`api/domains${qs(params)}`),
  domainDetail: (id: number, range: string) =>
    api.get<DetailPayload & { domain: DomainRow; related_domains: DomainRow[] }>(
      `api/domains/${id}${qs({ range })}`,
    ),
  lookupDomain: (name: string, range: string) =>
    api.get<DetailPayload & { domain: DomainRow; related_domains: DomainRow[] }>(
      `api/domains/lookup${qs({ name, range })}`,
    ),
  setDomainTags: (id: number, tag_ids: number[]) =>
    api.put<{ ok: true }>(`api/domains/${id}/tags`, { tag_ids }),

  tags: (kind?: TagKind) => api.get<{ items: Tag[] }>(`api/tags${qs({ kind })}`),
  createTag: (body: { name: string; kind: TagKind; color?: string; description?: string }) =>
    api.post<{ ok: true; id: number }>('api/tags', body),
  updateTag: (id: number, body: { name?: string; color?: string; description?: string }) =>
    api.patch<{ ok: true }>(`api/tags/${id}`, body),
  deleteTag: (id: number) => api.delete<{ ok: true }>(`api/tags/${id}`),

  rules: () =>
    api.get<{ items: Rule[]; builtin: Rule[]; total: number; pending_reclassification: number }>(
      'api/rules',
    ),
  createRule: (body: Omit<Rule, 'id' | 'builtin'>) =>
    api.post<{ ok: true; id: number }>('api/rules', body),
  updateRule: (id: number, body: Omit<Rule, 'id' | 'builtin'>) =>
    api.put<{ ok: true }>(`api/rules/${id}`, body),
  deleteRule: (id: number) => api.delete<{ ok: true }>(`api/rules/${id}`),
  testRule: (domain: string, rule?: Omit<Rule, 'id' | 'builtin'>) =>
    api.post<{ domain: string; matched: boolean; tags: RuleTagResult[]; matches: RuleMatch[] }>(
      'api/rules/test',
      rule ? { domain, rule } : { domain },
    ),

  savedFilters: () => api.get<{ items: SavedFilter[] }>('api/saved-filters'),
  createSavedFilter: (body: { name: string; description?: string; filter: FilterNode | null }) =>
    api.post<{ ok: true; id: number }>('api/saved-filters', body),
  updateSavedFilter: (
    id: number,
    body: { name?: string; description?: string; filter?: FilterNode | null },
  ) => api.put<{ ok: true }>(`api/saved-filters/${id}`, body),
  deleteSavedFilter: (id: number) => api.delete<{ ok: true }>(`api/saved-filters/${id}`),

  settings: () => api.get<AppSettings>('api/settings'),
  updateSettings: (values: Record<string, unknown>) =>
    api.patch<AppSettings & { ok: true }>('api/settings', { values }),

  runIngest: () => api.post<{ ok: true }>('api/ingest/run'),
  runCleanup: () => api.post<{ ok: true; deleted_queries: number }>('api/maintenance/cleanup'),
  reclassify: () => api.post<{ ok: true; marked: number }>('api/maintenance/reclassify'),
  reconnect: () => api.post<{ ok: true }>('api/maintenance/reconnect'),
};

export interface RuleTagResult {
  name: string;
  kind: TagKind;
}

export interface RuleMatch {
  rule: string;
  rule_id: number;
  builtin: boolean;
  tags: RuleTagResult[];
}

export interface DetailPayload {
  summary: Dashboard['summary'];
  timeline: Timeline;
  top_domains?: TopRow[];
  top_blocked_domains?: TopRow[];
  top_categories?: TopRow[];
  top_tags?: TopRow[];
  top_query_types?: TopRow[];
  top_clients?: TopRow[];
  top_persons?: TopRow[];
  top_upstreams?: TopRow[];
}
