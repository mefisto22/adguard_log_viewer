/** Shapes returned by the backend. Kept in one place so a schema change
 *  surfaces as a type error rather than as an undefined at runtime. */

export type TagKind = 'tag' | 'category';

export interface TagRef {
  name: string;
  color: string;
}

export interface Tag {
  id: number;
  name: string;
  kind: TagKind;
  color: string;
  description: string;
  builtin: boolean;
  domain_count: number;
}

export type ResultKind = 'allowed' | 'blocked' | 'rewritten' | 'allowlisted' | 'error';

export interface DnsAnswer {
  type: string;
  value: string;
  ttl: number;
}

export interface QueryRow {
  id: number;
  ts_ns: number;
  time: string;
  domain: string;
  domain_id: number;
  registrable_domain: string;
  client_ip: string;
  client_id: number;
  client_name: string;
  adguard_name: string;
  alias: string;
  person: string | null;
  person_id: number | null;
  query_type: string;
  query_class: string;
  response_status: string;
  reason: string;
  result: ResultKind;
  blocked: boolean;
  rule: string;
  filter_list_id: number;
  response_time_ms: number;
  upstream: string;
  cached: boolean;
  answer: string;
  answers: DnsAnswer[];
  client_proto: string;
  tags: TagRef[];
  categories: TagRef[];
}

export interface QueryPage {
  items: QueryRow[];
  limit: number;
  offset: number;
  total: number | null;
  total_capped: boolean;
  has_more: boolean;
  newest_id: number;
}

/* -- filters ------------------------------------------------------------- */

export type FieldKind = 'text' | 'number' | 'bool' | 'time' | 'enum';

export interface FieldSpec {
  name: string;
  kind: FieldKind;
  label: string;
  operators: string[];
  choices: string[];
  description: string;
}

export interface Predicate {
  field: string;
  operator: string;
  value?: string | number | boolean | null;
  values?: (string | number)[];
}

export interface Group {
  op: 'and' | 'or' | 'not';
  children: FilterNode[];
}

export type FilterNode = Group | Predicate;

export const isGroup = (node: FilterNode): node is Group =>
  typeof (node as Group).op === 'string';

export interface SearchSpec {
  terms: string[];
  mode: 'any' | 'all';
  fields: string[];
  operator: string;
}

export interface SavedFilter {
  id: number;
  name: string;
  description: string;
  filter: FilterNode | null;
  created_at: number;
  updated_at: number;
}

/* -- entities ------------------------------------------------------------ */

export interface Device {
  id: number;
  ip: string;
  adguard_name: string;
  alias: string;
  name: string;
  person_id: number | null;
  person: string | null;
  person_color: string | null;
  first_seen_ns: number;
  last_seen_ns: number;
  query_count: number;
  blocked_count: number;
}

export interface Person {
  id: number;
  name: string;
  color: string;
  note: string;
  device_count: number;
  query_count: number;
  blocked_count: number;
  last_seen_ns: number;
  devices: Device[];
}

export interface DomainRow {
  id: number;
  name: string;
  registrable_domain: string;
  first_seen_ns: number;
  last_seen_ns: number;
  query_count: number;
  blocked_count: number;
  tags: (TagRef & { id: number; source: string })[];
  categories: (TagRef & { id: number; source: string })[];
}

/* -- dashboard ----------------------------------------------------------- */

export interface Summary {
  total: number;
  blocked: number;
  allowed: number;
  blocked_percent: number;
  unique_domains: number;
  active_clients: number;
  active_persons: number;
  cached: number;
  avg_response_time_ms: number;
}

export interface TimelinePoint {
  t: number;
  total: number;
  blocked: number;
  allowed: number;
}

export interface Timeline {
  bucket_seconds: number;
  from_ns: number;
  to_ns: number;
  source: string;
  points: TimelinePoint[];
}

export interface TopRow {
  count: number;
  blocked: number;
  domain?: string;
  domain_id?: number;
  registrable?: string;
  client_id?: number;
  client_ip?: string;
  client_name?: string;
  person?: string | null;
  person_id?: number;
  query_type?: string;
  upstream?: string;
  tag_id?: number;
  name?: string;
  color?: string;
}

export interface Dashboard {
  summary: Summary;
  timeline: Timeline;
  top_domains: TopRow[];
  top_blocked_domains: TopRow[];
  top_clients: TopRow[];
  top_persons: TopRow[];
  top_categories: TopRow[];
  top_tags: TopRow[];
  top_query_types: TopRow[];
  top_upstreams: TopRow[];
}

/* -- rules, status, settings --------------------------------------------- */

export interface RuleCondition {
  field: string;
  operator: string;
  value: string;
}

export interface RuleTag {
  name: string;
  kind: TagKind;
}

export interface Rule {
  id: number;
  name: string;
  enabled: boolean;
  priority: number;
  match_mode: 'any' | 'all';
  conditions: RuleCondition[];
  tags: RuleTag[];
  builtin: boolean;
}

export interface ProviderStatus {
  name: string;
  available: boolean;
  source: string;
  detail: string;
  warnings: string[];
  extra: Record<string, unknown>;
}

export interface Status {
  version: string;
  schema_target: number;
  started_at_ns: number;
  database: {
    path: string;
    size_bytes: number;
    queries: number;
    oldest_ns: number | null;
    newest_ns: number | null;
    domains: number;
    clients: number;
    persons: number;
    tags: number;
    rules: number;
    pending_reclassification: number;
    schema_version: number;
    retention_days: number;
    ingest_enabled: boolean;
  };
  provider: ProviderStatus | null;
  discovery: {
    url: string;
    source: string;
    slug: string;
    addon_name: string;
    version: string;
    confident: boolean;
    warnings: string[];
  } | null;
  ingest: {
    last: Record<string, unknown>;
    error: string;
    engine_rules: number;
    ruleset_rev: number;
  };
  stream: { subscribers: number };
}

export interface AppSettings {
  app: Record<string, unknown>;
  addon_options: Record<string, unknown>;
  effective: {
    retention_days: number;
    ingest_enabled: boolean;
    poll_interval: number;
    timezone: string;
  };
  choices: {
    themes: string[];
    densities: string[];
    retention_days: number[];
  };
  editable_keys: string[];
}

export interface Meta {
  fields: FieldSpec[];
  ranges: string[];
  result_kinds: ResultKind[];
  rule_operators: string[];
  version: string;
}
