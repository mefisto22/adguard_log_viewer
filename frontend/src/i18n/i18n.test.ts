/**
 * The translation layer, and how the language is chosen.
 *
 * Key parity between the dictionaries is already a compile error — `hu` is
 * typed as `Record<keyof typeof en, string>` — so what is worth testing here is
 * what the type system cannot see: placeholders that do not survive
 * translation, entries left untranslated, and the fallbacks that decide which
 * language the page starts in.
 */

import { describe, expect, it, afterEach } from 'vitest';
import {
  activeLanguage,
  detectLanguage,
  en,
  hostLanguage,
  hu,
  normalizeLanguage,
  resolveLanguage,
  setActiveLanguage,
  translate,
  type TranslationKey,
} from './index';

const placeholders = (text: string) => new Set(text.match(/\{(\w+)\}/g) ?? []);

afterEach(() => {
  setActiveLanguage('en');
});

describe('the dictionaries', () => {
  it('cover exactly the same keys', () => {
    expect(Object.keys(hu).sort()).toEqual(Object.keys(en).sort());
  });

  it('use the same placeholders in both languages', () => {
    for (const key of Object.keys(en) as TranslationKey[]) {
      expect(placeholders(hu[key]), `placeholders differ for ${key}`).toEqual(
        placeholders(en[key]),
      );
    }
  });

  it('has no blank entries', () => {
    for (const key of Object.keys(en) as TranslationKey[]) {
      expect(en[key].trim(), `empty English entry for ${key}`).not.toBe('');
      expect(hu[key].trim(), `empty Hungarian entry for ${key}`).not.toBe('');
    }
  });

  it('actually translates — the two are not the same text', () => {
    // Some entries are legitimately identical (proper nouns, "OK"), but a whole
    // dictionary copied across would be a mistake worth catching.
    const identical = (Object.keys(en) as TranslationKey[]).filter((key) => hu[key] === en[key]);
    expect(identical.length).toBeLessThan(Object.keys(en).length * 0.2);
  });
});

describe('translate', () => {
  it('returns the entry for the language asked for', () => {
    expect(translate('en', 'common.save')).toBe('Save');
    expect(translate('hu', 'common.save')).toBe('Mentés');
  });

  it('substitutes named parameters', () => {
    expect(translate('en', 'settings.foundAs', { slug: 'core_adguard' })).toContain(
      'core_adguard',
    );
  });

  it('leaves a placeholder alone when no value is given for it', () => {
    expect(translate('en', 'settings.foundAs', { other: 'x' })).toContain('{slug}');
  });

  it('falls back to the key itself when no dictionary has it', () => {
    // The types stop this happening in the app; a key built from backend data
    // could still slip through, and a visible key beats a blank.
    expect(translate('hu', 'nope.missing' as TranslationKey)).toBe('nope.missing');
  });

  it('accepts numbers as parameters', () => {
    expect(translate('hu', 'settings.subscribers', { count: 3 })).toContain('3');
  });
});

describe('choosing a language', () => {
  it('maps regional tags onto a language we have', () => {
    expect(normalizeLanguage('hu-HU')).toBe('hu');
    expect(normalizeLanguage('HU')).toBe('hu');
    expect(normalizeLanguage('en_GB')).toBe('en');
    expect(normalizeLanguage('de')).toBeNull();
    expect(normalizeLanguage('')).toBeNull();
    expect(normalizeLanguage(null)).toBeNull();
  });

  it('reports no host language when there is no Home Assistant around it', () => {
    // No window here, which is exactly what a cross-origin parent looks like
    // from inside the ingress iframe: unreadable, so fall through.
    expect(hostLanguage()).toBeNull();
  });

  it('falls back to English when nothing says otherwise', () => {
    expect(detectLanguage()).toBe('en');
  });

  it('respects an explicit choice over detection', () => {
    expect(resolveLanguage('hu')).toBe('hu');
    expect(resolveLanguage('en')).toBe('en');
    expect(resolveLanguage('auto')).toBe(detectLanguage());
  });

  it('keeps the active language for code outside React', () => {
    setActiveLanguage('hu');
    expect(activeLanguage()).toBe('hu');
  });
});
