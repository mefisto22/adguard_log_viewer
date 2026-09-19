/** Hook for translating in a component. */

import { useCallback } from 'react';

import { useAppStore } from '../stores/useAppStore';
import { translate } from './index';
import type { TranslationKey, Translator } from './index';

export function useT(): Translator {
  const language = useAppStore((state) => state.language);
  return useCallback(
    (key: TranslationKey, params?: Record<string, string | number>) =>
      translate(language, key, params),
    [language],
  );
}

/** The active language, for anything that formats rather than translates. */
export function useLanguage() {
  return useAppStore((state) => state.language);
}
