/** Minimal data-fetching hook: run an async function, expose its state. */

import { useCallback, useEffect, useRef, useState } from 'react';

export interface AsyncState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
}

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);
  const latest = useRef(0);
  const callback = useRef(fn);

  // Declared before the fetching effect, so it has already run by the time the
  // fetch below reads `callback.current`. Callers may pass an inline arrow
  // function; `deps` is what decides when a refetch happens.
  useEffect(() => {
    callback.current = fn;
  });

  useEffect(() => {
    const token = ++latest.current;
    setLoading(true);
    callback
      .current()
      .then((result) => {
        if (token !== latest.current) return;
        setData(result);
        setError(null);
      })
      .catch((err: unknown) => {
        if (token !== latest.current) return;
        setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (token === latest.current) setLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  const reload = useCallback(() => setNonce((value) => value + 1), []);
  return { data, error, loading, reload };
}
