/**
 * Formatting follows the language the UI is in.
 *
 * These helpers are plain functions, not components, so they read the active
 * language rather than receiving it — the test pins that they really do.
 */

import { afterEach, describe, expect, it } from 'vitest';
import { setActiveLanguage } from '../i18n';
import { formatBytes, formatMs, formatNumber, formatRelative } from './format';

const MS = 1_000_000;
const ago = (seconds: number) => (Date.now() - seconds * 1000) * MS;

afterEach(() => {
  setActiveLanguage('en');
});

describe('formatRelative', () => {
  it('reads as English by default', () => {
    expect(formatRelative(ago(90 * 60))).toBe('2h ago');
    expect(formatRelative(ago(5 * 60))).toBe('5m ago');
  });

  it('switches to Hungarian with the language', () => {
    setActiveLanguage('hu');
    expect(formatRelative(ago(5 * 60))).toBe('5 perce');
    expect(formatRelative(ago(3 * 3600))).toBe('3 órája');
  });

  it('says "never" in the right language when there is no timestamp', () => {
    expect(formatRelative(0)).toBe('never');
    setActiveLanguage('hu');
    expect(formatRelative(null)).toBe('soha');
  });

  it('stays narrow, so table cells do not grow', () => {
    // "5m ago", not "5 minutes ago" — these render in a nowrap column.
    expect(formatRelative(ago(300)).length).toBeLessThan(10);
  });
});

describe('numbers', () => {
  it('group digits the way the language does', () => {
    setActiveLanguage('en');
    expect(formatNumber(1234567)).toBe('1,234,567');
    setActiveLanguage('hu');
    // Hungarian groups with spaces (a non-breaking one, hence the loose check).
    expect(formatNumber(1234567)).not.toBe('1,234,567');
    expect(formatNumber(1234567).replace(/\D/g, '')).toBe('1234567');
  });

  it('formats sizes and durations independently of language', () => {
    expect(formatBytes(1536)).toBe('1.5 KB');
    expect(formatMs(0.5)).toBe('500 µs');
  });
});
