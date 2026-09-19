/**
 * The single live-update connection, and the reference data it keeps fresh.
 *
 * Two things live here rather than in a component:
 *
 * * **One stream.** Every page that wanted live updates used to open its own
 *   EventSource, so moving between the log and the dashboard left several
 *   connections open against the add-on.
 * * **Reference data that does not go stale.** Devices, people and tags were
 *   loaded once at startup and never again. On a fresh install the UI comes up
 *   before ingest has seen its first query, so the Device and Tag dropdowns
 *   stayed empty until the page was reloaded by hand. Ingest tells us when a
 *   new client or domain appears; that is the moment to refetch.
 */

import { apiUrl } from '../api/api-core';
import { useAppStore } from './useAppStore';

export interface LiveEvent {
  type: string;
  inserted?: number;
  last_id?: number;
  new_domains?: number;
  new_clients?: number;
  at_ns?: number;
}

export type StreamMode = 'stream' | 'poll' | 'off';

/** Fall back to polling after this many failed connection attempts. */
const MAX_ATTEMPTS = 4;

/** How often the polling fallback pretends an event arrived. */
const POLL_INTERVAL_MS = 15_000;

/** Reference data is refetched at most this often, however busy the network. */
const REFRESH_COOLDOWN_MS = 15_000;

/** Backstop for anything the stream did not tell us about. */
const BACKSTOP_INTERVAL_MS = 5 * 60_000;

let source: EventSource | null = null;
let attempts = 0;
let retryTimer: number | undefined;
let pollTimer: number | undefined;
let backstopTimer: number | undefined;
let lastDeviceRefresh = 0;
let lastTagRefresh = 0;
let running = false;

function clearTimers() {
  if (retryTimer) window.clearTimeout(retryTimer);
  if (pollTimer) window.clearTimeout(pollTimer);
  if (backstopTimer) window.clearInterval(backstopTimer);
  retryTimer = undefined;
  pollTimer = undefined;
  backstopTimer = undefined;
}

function refreshReferenceData(event: LiveEvent) {
  const store = useAppStore.getState();
  const now = Date.now();

  // A new client IP means a device the Device filter does not know about yet.
  const devicesStale = (event.new_clients ?? 0) > 0 || event.type === 'backstop';
  if (devicesStale && now - lastDeviceRefresh > REFRESH_COOLDOWN_MS) {
    lastDeviceRefresh = now;
    void store.refreshDevices();
    void store.refreshPersons();
  }

  // A new domain may have been classified into a tag nothing has used before.
  const tagsStale = (event.new_domains ?? 0) > 0 || event.type === 'backstop';
  if (tagsStale && now - lastTagRefresh > REFRESH_COOLDOWN_MS) {
    lastTagRefresh = now;
    void store.refreshTags();
  }
}

function publish(event: LiveEvent) {
  useAppStore.setState({ lastEvent: event });
  refreshReferenceData(event);
}

function startPolling() {
  useAppStore.setState({ streamMode: 'poll', streamConnected: false });
  const tick = () => {
    // Without a stream we cannot know what changed, so assume everything might
    // have and let the cooldown keep it cheap.
    publish({ type: 'poll', at_ns: Date.now() * 1_000_000, new_clients: 1, new_domains: 1 });
    pollTimer = window.setTimeout(tick, POLL_INTERVAL_MS);
  };
  pollTimer = window.setTimeout(tick, POLL_INTERVAL_MS);
}

function connect() {
  if (!running) return;

  source = new EventSource(apiUrl('api/stream'));
  useAppStore.setState({ streamMode: 'stream' });

  const onMessage = (event: MessageEvent<string>) => {
    try {
      publish(JSON.parse(event.data) as LiveEvent);
    } catch {
      /* a malformed frame is not worth tearing the stream down for */
    }
  };

  source.onopen = () => {
    attempts = 0;
    useAppStore.setState({ streamConnected: true });
  };
  source.addEventListener('hello', () => useAppStore.setState({ streamConnected: true }));
  source.addEventListener('queries', onMessage as EventListener);
  source.addEventListener('cleanup', onMessage as EventListener);

  source.onerror = () => {
    useAppStore.setState({ streamConnected: false });
    source?.close();
    source = null;
    attempts += 1;
    if (attempts >= MAX_ATTEMPTS) {
      startPolling();
      return;
    }
    retryTimer = window.setTimeout(connect, Math.min(30_000, 2000 * attempts));
  };
}

export function startLiveUpdates(): void {
  if (running) return;
  running = true;
  attempts = 0;
  connect();

  backstopTimer = window.setInterval(() => {
    publish({ type: 'backstop', at_ns: Date.now() * 1_000_000 });
  }, BACKSTOP_INTERVAL_MS);

  // Coming back to a tab that was in the background for a while is the other
  // moment the lists are most likely to be out of date.
  document.addEventListener('visibilitychange', onVisibilityChange);
}

export function stopLiveUpdates(): void {
  running = false;
  source?.close();
  source = null;
  clearTimers();
  document.removeEventListener('visibilitychange', onVisibilityChange);
  useAppStore.setState({ streamConnected: false, streamMode: 'off' });
}

function onVisibilityChange() {
  if (document.visibilityState === 'visible' && running) {
    publish({ type: 'backstop', at_ns: Date.now() * 1_000_000 });
  }
}
