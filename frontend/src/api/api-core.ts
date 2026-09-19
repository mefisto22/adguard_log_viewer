/**
 * Tiny fetch wrapper.
 *
 * Under Home Assistant ingress the app lives at a generated prefix such as
 * `/api/hassio_ingress/<token>/`. Every request is therefore made relative to
 * the directory the document was loaded from, never from the site root.
 */

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
  let response: Response;
  try {
    response = await fetch(apiUrl(path), {
      method,
      headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: 'same-origin',
    });
  } catch (error) {
    throw new ApiError(
      error instanceof Error ? error.message : 'The add-on could not be reached',
      0,
    );
  }

  const payload = await parse(response);
  if (!response.ok) {
    const detail =
      payload && typeof payload === 'object' && 'detail' in payload
        ? String((payload as { detail: unknown }).detail)
        : `Request failed with HTTP ${response.status}`;
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
