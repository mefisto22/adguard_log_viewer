/**
 * Subscribes to the backend's SSE stream and reports when new rows land.
 *
 * The stream carries notifications only. Callers decide what to fetch, which
 * keeps the browser from ever pulling the whole query log. If the stream cannot
 * be established — a proxy that buffers, an old browser — the hook falls back
 * to polling the status endpoint, so live updates degrade instead of breaking.
 */

import { useEffect, useRef, useState } from 'react';
import { apiUrl } from '../api/api-core';

export interface LiveEvent {
  type: string;
  inserted?: number;
  last_id?: number;
  at_ns?: number;
}

const FALLBACK_POLL_MS = 15_000;

export function useLiveUpdates(enabled: boolean): {
  lastEvent: LiveEvent | null;
  connected: boolean;
  mode: 'stream' | 'poll' | 'off';
} {
  const [lastEvent, setLastEvent] = useState<LiveEvent | null>(null);
  const [connected, setConnected] = useState(false);
  const [mode, setMode] = useState<'stream' | 'poll' | 'off'>('off');
  const failures = useRef(0);

  useEffect(() => {
    if (!enabled) {
      setMode('off');
      setConnected(false);
      return;
    }

    let source: EventSource | null = null;
    let pollTimer: number | undefined;
    let retryTimer: number | undefined;
    let cancelled = false;

    const startPolling = () => {
      setMode('poll');
      setConnected(false);
      const tick = () => {
        setLastEvent({ type: 'poll', at_ns: Date.now() * 1_000_000 });
        pollTimer = window.setTimeout(tick, FALLBACK_POLL_MS);
      };
      pollTimer = window.setTimeout(tick, FALLBACK_POLL_MS);
    };

    const connect = () => {
      if (cancelled) return;
      source = new EventSource(apiUrl('api/stream'));
      setMode('stream');

      source.onopen = () => {
        failures.current = 0;
        setConnected(true);
      };
      const handle = (event: MessageEvent<string>) => {
        try {
          setLastEvent(JSON.parse(event.data) as LiveEvent);
        } catch {
          /* a malformed frame is not worth tearing the stream down for */
        }
      };
      source.addEventListener('queries', handle as EventListener);
      source.addEventListener('cleanup', handle as EventListener);
      source.addEventListener('hello', () => setConnected(true));

      source.onerror = () => {
        setConnected(false);
        source?.close();
        source = null;
        failures.current += 1;
        if (failures.current >= 4) {
          startPolling();
          return;
        }
        retryTimer = window.setTimeout(connect, Math.min(30_000, 2000 * failures.current));
      };
    };

    connect();

    return () => {
      cancelled = true;
      source?.close();
      if (pollTimer) window.clearTimeout(pollTimer);
      if (retryTimer) window.clearTimeout(retryTimer);
      setConnected(false);
    };
  }, [enabled]);

  return { lastEvent, connected, mode };
}
