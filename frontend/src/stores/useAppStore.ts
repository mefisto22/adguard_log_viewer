/** Global, long-lived state: metadata, reference data and the theme. */

import { create } from 'zustand';
import { endpoints } from '../api/endpoints';
import type { Device, Meta, Person, SavedFilter, Status, Tag } from '../types/api';
import type { LiveEvent, StreamMode } from './liveUpdates';
import type { Language, LanguagePreference } from '../i18n';
import { activeLanguage, resolveLanguage, setActiveLanguage, translate } from '../i18n';

type Theme = 'system' | 'light' | 'dark';
type Density = 'comfortable' | 'compact';

interface AppState {
  meta: Meta | null;
  status: Status | null;
  tags: Tag[];
  persons: Person[];
  devices: Device[];
  savedFilters: SavedFilter[];
  language: Language;
  languagePreference: LanguagePreference;
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
  setLanguage: (preference: LanguagePreference) => void;
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
  language: resolveLanguage('auto'),
  languagePreference: 'auto',
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
      // Settings first, and on its own: it carries the language, and every
      // request after it tells the backend which language to answer in. Folded
      // into the batch below, the status diagnostics would come back in
      // whatever language was current before the stored preference was read.
      const settings = await endpoints.settings();
      get().setPreferences(settings.app);

      const [meta, tags, persons, devices, savedFilters, status] = await Promise.all([
        endpoints.meta(),
        endpoints.tags(),
        endpoints.persons(),
        endpoints.devices(),
        endpoints.savedFilters(),
        endpoints.status(),
      ]);
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
        error:
          error instanceof Error
            ? error.message
            : translate(activeLanguage(), 'app.loadFailed'),
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

  setLanguage: (preference) => {
    const language = resolveLanguage(preference);
    setActiveLanguage(language);
    document.documentElement.lang = language;
    set({ languagePreference: preference, language });
    void endpoints.updateSettings({ 'ui.language': preference });
    // The status carries text the backend translated for the previous
    // language — the AdGuard diagnostics above all. Fetch it again.
    void get().refreshStatus();
  },

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
    const languagePreference = (values['ui.language'] as LanguagePreference) ?? 'auto';
    const language = resolveLanguage(languagePreference);
    setActiveLanguage(language);
    applyTheme(theme, density);
    document.documentElement.lang = language;
    set({
      language,
      languagePreference,
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
