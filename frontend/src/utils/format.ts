/**
 * Formatting helpers. All dates render in the browser's local zone.
 *
 * Dates, numbers and relative times follow the language the UI is in, so a
 * Hungarian page does not mix `hu` labels with `09/19/2026` stamps. The
 * formatters are built once per language and reused — constructing an `Intl`
 * formatter is expensive, and these run for every row of a virtualised table.
 */

import { activeLanguage, activeLocale, translate } from '../i18n';

const NS_PER_MS = 1_000_000;

function memo<T>(build: (locale: string) => T): () => T {
  let key: string | null = null;
  let value: T;
  return () => {
    const locale = activeLocale();
    if (locale !== key) {
      key = locale;
      value = build(locale);
    }
    return value;
  };
}

export function nsToDate(ns: number | null | undefined): Date | null {
  if (!ns) return null;
  return new Date(ns / NS_PER_MS);
}

const timeFormat = memo(
  (locale) =>
    new Intl.DateTimeFormat(locale, {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    }),
);

const dateTimeFormat = memo(
  (locale) =>
    new Intl.DateTimeFormat(locale, {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    }),
);

// `narrow` keeps table cells tight: "5m ago" in English, "5 perce" in
// Hungarian. `auto` turns the smallest offsets into words — "now", "most".
const relativeFormat = memo(
  (locale) => new Intl.RelativeTimeFormat(locale, { numeric: 'auto', style: 'narrow' }),
);

export function formatTime(ns: number | null | undefined): string {
  const date = nsToDate(ns);
  return date ? timeFormat().format(date) : '—';
}

export function formatDateTime(ns: number | null | undefined): string {
  const date = nsToDate(ns);
  return date ? dateTimeFormat().format(date) : '—';
}

/** Show the clock for today's entries and the full stamp for older ones. */
export function formatSmart(ns: number | null | undefined): string {
  const date = nsToDate(ns);
  if (!date) return '—';
  const now = new Date();
  const sameDay =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate();
  return sameDay ? timeFormat().format(date) : dateTimeFormat().format(date);
}

export function formatRelative(ns: number | null | undefined): string {
  const date = nsToDate(ns);
  if (!date) return translate(activeLanguage(), 'common.never');
  const format = relativeFormat();
  const seconds = Math.round((Date.now() - date.getTime()) / 1000);
  if (seconds < 5) return format.format(0, 'second');
  if (seconds < 60) return format.format(-seconds, 'second');
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return format.format(-minutes, 'minute');
  const hours = Math.round(minutes / 60);
  if (hours < 48) return format.format(-hours, 'hour');
  return format.format(-Math.round(hours / 24), 'day');
}

const numberFormat = memo((locale) => new Intl.NumberFormat(locale));

const compactFormat = memo(
  (locale) => new Intl.NumberFormat(locale, { notation: 'compact', maximumFractionDigits: 1 }),
);

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return numberFormat().format(value);
}

export function formatCompact(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  if (Math.abs(value) < 10_000) return numberFormat().format(value);
  return compactFormat().format(value);
}

export function formatBytes(bytes: number | null | undefined): string {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`;
}

export function formatMs(ms: number | null | undefined): string {
  if (!ms) return '—';
  if (ms < 1) return `${(ms * 1000).toFixed(0)} µs`;
  if (ms < 1000) return `${ms.toFixed(ms < 10 ? 1 : 0)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return `${value.toFixed(value < 10 ? 1 : 0)}%`;
}

/** Deterministic colour for a label that has none of its own. */
export function colorFor(text: string): string {
  let hash = 0;
  for (let index = 0; index < text.length; index += 1) {
    hash = (hash * 31 + text.charCodeAt(index)) | 0;
  }
  return `hsl(${Math.abs(hash) % 360} 58% 48%)`;
}
