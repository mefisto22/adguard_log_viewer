/**
 * Read the shared live-update state.
 *
 * The connection itself lives in ../stores/liveUpdates so that the whole app
 * uses one EventSource, and so that reference data can be refreshed from the
 * same events without every page having to know about it.
 */

import { useAppStore } from '../stores/useAppStore';
import type { LiveEvent, StreamMode } from '../stores/liveUpdates';

export type { LiveEvent } from '../stores/liveUpdates';

export function useLiveUpdates(): {
  lastEvent: LiveEvent | null;
  connected: boolean;
  mode: StreamMode;
} {
  // Selected one field at a time: a selector returning a fresh object would
  // re-render on every store change.
  const lastEvent = useAppStore((state) => state.lastEvent);
  const connected = useAppStore((state) => state.streamConnected);
  const mode = useAppStore((state) => state.streamMode);
  return { lastEvent, connected, mode };
}
