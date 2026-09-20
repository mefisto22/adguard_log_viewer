/**
 * Column widths the reader has dragged, remembered per browser.
 *
 * These live in `localStorage` rather than in the application settings on
 * purpose: a width that suits a 27" monitor is wrong on a laptop, and the
 * settings are shared by everyone using the same install. The visible-columns
 * list next to it is stored the same way, for the same reason.
 *
 * Every access is wrapped: in a private window, or with site data blocked,
 * reading and writing both throw, and a table that cannot remember its widths
 * is still a working table.
 */

import { useCallback, useEffect, useState } from 'react';

const STORAGE_KEY = 'aglv.columnWidths';

export type ColumnWidths = Record<string, number>;

function persist(widths: ColumnWidths): ColumnWidths {
  try {
    if (Object.keys(widths).length === 0) localStorage.removeItem(STORAGE_KEY);
    else localStorage.setItem(STORAGE_KEY, JSON.stringify(widths));
  } catch {
    /* storage unavailable — the widths still apply for this session */
  }
  return widths;
}

export function useColumnWidths() {
  const [widths, setWidths] = useState<ColumnWidths>({});

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const parsed: unknown = JSON.parse(raw);
      if (parsed && typeof parsed === 'object') {
        const clean: ColumnWidths = {};
        for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
          if (typeof value === 'number' && Number.isFinite(value) && value > 0) {
            clean[key] = value;
          }
        }
        setWidths(clean);
      }
    } catch {
      /* unreadable or not ours — start from the defaults */
    }
  }, []);

  const setWidth = useCallback((key: string, width: number) => {
    setWidths((previous) => persist({ ...previous, [key]: Math.round(width) }));
  }, []);

  /** Drop one column's width, putting it back on its default sizing. */
  const clearWidth = useCallback((key: string) => {
    setWidths((previous) => {
      if (!(key in previous)) return previous;
      const next = { ...previous };
      delete next[key];
      return persist(next);
    });
  }, []);

  const resetWidths = useCallback(() => setWidths(persist({})), []);

  return { widths, setWidth, clearWidth, resetWidths };
}
