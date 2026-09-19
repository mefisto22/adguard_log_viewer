/**
 * Tiny fetch wrapper.
 *
 * Under Home Assistant ingress the app lives at a generated prefix such as
 * `/api/hassio_ingress/<token>/`. Every request is therefore made relative to
 * the directory the document was loaded from, never from the site root.
 *
 * Every request also carries the language the UI is rendering in. A few
 * messages come from the backend — validation errors, and the diagnostics about
 * reaching AdGuard Home — and they are shown in the same banners as everything
 * else, so they have to speak the same language.
 */

import { activeLanguage, translate } from '../i18n';

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/** Directory of the current document, always ending in a slash. */
export function baseUrl(): string {
  const path = window.location.pathname;
  return path.endsWith('/') ? path : `${path.slice(0, path.lastIndexOf('/') + 1)}`;
}

export function apiUrl(path: string): string {
  const clean = path.replace(/^\/+/, '');
  return `${baseUrl()}${clean}`;
}

async function parse(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const language = activeLanguage();
  const headers: Record<string, string> = { 'Accept-Language': language };
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  let response: Response;
  try {
    response = await fetch(apiUrl(path), {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: 'same-origin',
    });
  } catch (error) {
    throw new ApiError(
      error instanceof Error ? error.message : translate(language, 'error.unreachable'),
      0,
    );
  }

  const payload = await parse(response);
  if (!response.ok) {
    const detail =
      payload && typeof payload === 'object' && 'detail' in payload
        ? String((payload as { detail: unknown }).detail)
        : translate(language, 'error.http', { status: response.status });
    throw new ApiError(detail, response.status);
  }
  return payload as T;
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body ?? {}),
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, body ?? {}),
  patch: <T>(path: string, body?: unknown) => request<T>('PATCH', path, body ?? {}),
  delete: <T>(path: string) => request<T>('DELETE', path),
};

/** Build a query string, skipping empty values. */
export function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : '';
}
