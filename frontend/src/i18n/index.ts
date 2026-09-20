/**
 * Translation, and working out which language to use.
 *
 * The app is shown inside an iframe in the Home Assistant frontend, served
 * from the same origin as Home Assistant itself. That means the parent
 * document is readable, and its ``lang`` attribute is exactly the language
 * Home Assistant is rendering for this user — including a per-user choice made
 * in their profile, which no server-side signal would reveal.
 *
 * Everything else is a fallback: the browser's own language when the page is
 * opened directly, and English when nothing else says otherwise. An explicit
 * choice on the Settings page always wins.
 */

import { en } from './en';
import { hu } from './hu';

export type Language = 'en' | 'hu';
export type LanguagePreference = 'auto' | Language;
export type TranslationKey = keyof typeof en;

export const LANGUAGES: Language[] = ['en', 'hu'];

const DICTIONARIES: Record<Language, Record<TranslationKey, string>> = { en, hu };

/** Map anything BCP-47-ish onto a language we have. `hu-HU` -> `hu`. */
export function normalizeLanguage(value: string | null | undefined): Language | null {
  if (!value) return null;
  const base = value.trim().toLowerCase().split(/[-_]/)[0];
  return (LANGUAGES as string[]).includes(base) ? (base as Language) : null;
}

/** The language Home Assistant is showing, when we are embedded in it. */
export function hostLanguage(): Language | null {
  try {
    if (window.parent && window.parent !== window) {
      return normalizeLanguage(window.parent.document.documentElement.lang);
    }
  } catch {
    // A cross-origin parent throws on access. Nothing to do but move on.
  }
  return null;
}

export function detectLanguage(): Language {
  const browser = typeof navigator === 'undefined' ? null : navigator.language;
  return hostLanguage() ?? normalizeLanguage(browser) ?? 'en';
}

export function resolveLanguage(preference: LanguagePreference): Language {
  return preference === 'auto' ? detectLanguage() : preference;
}

/**
 * The language in effect, for code that runs outside React.
 *
 * Components read the language from the store and re-render when it changes;
 * the formatting helpers in `utils/format` are plain functions called during
 * that render, so they need somewhere to look it up. The store keeps this in
 * step — it is the same value, not a second source of truth.
 */
let active: Language = detectLanguage();

export function activeLanguage(): Language {
  return active;
}

export function setActiveLanguage(language: Language): void {
  active = language;
}

/**
 * The locale to format dates and numbers with.
 *
 * Prefer the browser's own locale when it speaks the active language, so a
 * Hungarian user keeps `hu-HU` conventions rather than a bare `hu`. When the
 * two disagree — someone reading the English UI on a Hungarian browser — the
 * chosen language wins, so the whole page reads as one language.
 */
export function activeLocale(): string {
  const browser = typeof navigator === 'undefined' ? null : navigator.language;
  if (browser && normalizeLanguage(browser) === active) return browser;
  return active;
}

/**
 * Look up *key* and substitute `{name}` placeholders.
 *
 * A missing key falls back to English and then to the key itself, so a gap in
 * a translation degrades to a readable string rather than a blank.
 */
export function translate(
  language: Language,
  key: TranslationKey,
  params?: Record<string, string | number>,
): string {
  const template = DICTIONARIES[language]?.[key] ?? en[key] ?? key;
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in params ? String(params[name]) : match,
  );
}

/**
 * A key built from data, or null when the dictionary has no such entry.
 *
 * Used where the key depends on a value that comes from the backend — a range
 * name, an operator — so an unknown value falls back to showing itself rather
 * than a missing-key placeholder.
 */
export function optionalKey(key: string): TranslationKey | null {
  return key in en ? (key as TranslationKey) : null;
}

export function rangeKey(range: string): TranslationKey | null {
  return optionalKey(`range.${range}`);
}

export function operatorKey(operator: string): TranslationKey | null {
  return optionalKey(`operator.${operator}`);
}

export function fieldKey(field: string): TranslationKey | null {
  return optionalKey(`field.${field}`);
}

export type Translator = (key: TranslationKey, params?: Record<string, string | number>) => string;

export { en, hu };
