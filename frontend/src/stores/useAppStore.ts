/** Global, long-lived state: metadata, reference data and the theme. */

import { create } from 'zustand';
import { endpoints } from '../api/endpoints';
import type { Device, Meta, Person, SavedFilter, Status, Tag } from '../types/api';
import type { LiveEvent, StreamMode } from './liveUpdates';

type Theme = 'system' | 'light' | 'dark';
type Density = 'comfortable' | 'compact';

interface AppState {
  meta: Meta | null;
  status: Status | null;
  tags: Tag[];
  persons: Person[];
  devices: Device[];
  savedFilters: SavedFilter[];
  theme: Theme;
  density: Density;
  liveUpdates: boolean;
  defaultRange: string;
  pageSize: number;
  loaded: boolean;
  error: string | null;

  // Owned by ./liveUpdates, which keeps a single connection for the whole app.
  lastEvent: LiveEvent | null;
  streamConnected: boolean;
  streamMode: StreamMode;

  bootstrap: () => Promise<void>;
  refreshStatus: () => Promise<void>;
  refreshTags: () => Promise<void>;
  refreshPersons: () => Promise<void>;
  refreshDevices: () => Promise<void>;
  refreshSavedFilters: () => Promise<void>;
  setTheme: (theme: Theme) => void;
  setDensity: (density: Density) => void;
  setLiveUpdates: (value: boolean) => void;
  setPreferences: (values: Record<string, unknown>) => void;
}

function applyTheme(theme: Theme, density: Density) {
  const resolved =
    theme === 'system'
      ? window.matchMedia('(prefers-color-scheme: dark)').matches
        ? 'dark'
        : 'light'
      : theme;
  document.documentElement.dataset.theme = resolved;
  document.documentElement.dataset.density = density;
}

export const useAppStore = create<AppState>((set, get) => ({
  meta: null,
  status: null,
  tags: [],
  persons: [],
  devices: [],
  savedFilters: [],
  theme: 'system',
  density: 'comfortable',
  liveUpdates: true,
  defaultRange: '24h',
  pageSize: 100,
  loaded: false,
  error: null,
  lastEvent: null,
  streamConnected: false,
  streamMode: 'off',

  bootstrap: async () => {
    try {
      const [meta, settings, tags, persons, devices, savedFilters, status] = await Promise.all([
        endpoints.meta(),
        endpoints.settings(),
        endpoints.tags(),
        endpoints.persons(),
        endpoints.devices(),
        endpoints.savedFilters(),
        endpoints.status(),
      ]);
      get().setPreferences(settings.app);
      set({
        meta,
        status,
        tags: tags.items,
        persons: persons.items,
        devices: devices.items,
        savedFilters: savedFilters.items,
        loaded: true,
        error: null,
      });
    } catch (error) {
      set({
        loaded: true,
        error: error instanceof Error ? error.message : 'Could not load the application',
      });
    }
  },

  refreshStatus: async () => {
    try {
      set({ status: await endpoints.status() });
    } catch {
      /* the status card shows the stale value; a transient failure is not fatal */
    }
  },
  refreshTags: async () => set({ tags: (await endpoints.tags()).items }),
  refreshPersons: async () => set({ persons: (await endpoints.persons()).items }),
  refreshDevices: async () => set({ devices: (await endpoints.devices()).items }),
  refreshSavedFilters: async () => set({ savedFilters: (await endpoints.savedFilters()).items }),

  setTheme: (theme) => {
    applyTheme(theme, get().density);
    set({ theme });
    void endpoints.updateSettings({ 'ui.theme': theme });
  },
  setDensity: (density) => {
    applyTheme(get().theme, density);
    set({ density });
    void endpoints.updateSettings({ 'ui.density': density });
  },
  setLiveUpdates: (liveUpdates) => {
    set({ liveUpdates });
    void endpoints.updateSettings({ 'ui.live_updates': liveUpdates });
  },

  setPreferences: (values) => {
    const theme = (values['ui.theme'] as Theme) ?? 'system';
    const density = (values['ui.density'] as Density) ?? 'comfortable';
    applyTheme(theme, density);
    set({
      theme,
      density,
      liveUpdates: values['ui.live_updates'] !== false,
      defaultRange: (values['ui.default_range'] as string) ?? '24h',
      pageSize: (values['ui.page_size'] as number) ?? 100,
    });
  },
}));

// Follow the OS when the user left the theme on "system".
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
  const { theme, density } = useAppStore.getState();
  if (theme === 'system') applyTheme(theme, density);
});
