/** A dropdown that lets several options be picked at once. */

import { useEffect, useMemo, useRef, useState } from 'react';

export interface Option {
  value: string;
  label: string;
  hint?: string;
  color?: string;
}

export function MultiSelect({
  label,
  options,
  selected,
  onToggle,
  onClear,
  searchable = true,
  width = 260,
}: {
  label: string;
  options: Option[];
  selected: string[];
  onToggle: (value: string) => void;
  onClear: () => void;
  searchable?: boolean;
  width?: number;
}) {
  const [open, setOpen] = useState(false);
  const [needle, setNeedle] = useState('');
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (event: MouseEvent) => {
      if (!container.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const visible = useMemo(() => {
    const text = needle.trim().toLowerCase();
    if (!text) return options;
    return options.filter(
      (option) =>
        option.label.toLowerCase().includes(text) ||
        (option.hint ?? '').toLowerCase().includes(text),
    );
  }, [options, needle]);

  const summary =
    selected.length === 0
      ? label
      : selected.length === 1
        ? (options.find((option) => option.value === selected[0])?.label ?? selected[0])
        : `${label}: ${selected.length}`;

  return (
    <div ref={container} style={{ position: 'relative' }}>
      <button
        type="button"
        className="btn"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        style={selected.length ? { borderColor: 'var(--primary)', color: 'var(--primary-strong)' } : undefined}
      >
        <span className="truncate" style={{ maxWidth: 160 }}>
          {summary}
        </span>
        <span aria-hidden style={{ opacity: 0.6, fontSize: 10 }}>
          ▾
        </span>
      </button>

      {open ? (
        <div
          className="card"
          style={{
            position: 'absolute',
            top: 'calc(100% + 4px)',
            left: 0,
            width,
            maxHeight: 340,
            display: 'flex',
            flexDirection: 'column',
            zIndex: 40,
            boxShadow: 'var(--shadow-lg)',
          }}
        >
          {searchable && options.length > 8 ? (
            <div style={{ padding: 8, borderBottom: '1px solid var(--border)' }}>
              <input
                type="search"
                autoFocus
                placeholder="Filter…"
                value={needle}
                onChange={(event) => setNeedle(event.target.value)}
                style={{ width: '100%' }}
              />
            </div>
          ) : null}

          <div style={{ overflow: 'auto', padding: 4 }}>
            {visible.length === 0 ? (
              <div className="empty small" style={{ padding: 16 }}>
                Nothing matches
              </div>
            ) : (
              visible.map((option) => (
                <label
                  key={option.value}
                  className="row"
                  style={{
                    gap: 8,
                    padding: '5px 8px',
                    borderRadius: 'var(--radius-sm)',
                    cursor: 'pointer',
                  }}
                >
                  <input
                    type="checkbox"
                    checked={selected.includes(option.value)}
                    onChange={() => onToggle(option.value)}
                  />
                  {option.color ? (
                    <span
                      style={{
                        width: 8,
                        height: 8,
                        borderRadius: 4,
                        background: option.color,
                        flex: '0 0 auto',
                      }}
                    />
                  ) : null}
                  <span className="truncate" style={{ flex: '1 1 auto' }}>
                    {option.label}
                  </span>
                  {option.hint ? <span className="faint small nowrap">{option.hint}</span> : null}
                </label>
              ))
            )}
          </div>

          {selected.length ? (
            <div style={{ padding: 8, borderTop: '1px solid var(--border)' }}>
              <button type="button" className="btn sm ghost" onClick={onClear}>
                Clear {selected.length} selected
              </button>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
