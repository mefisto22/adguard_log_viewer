/**
 * Guards for the layout rules that keep content inside its card.
 *
 * These assert on the stylesheet rather than on rendered geometry, because
 * jsdom has no layout engine — there is no way to measure an overflow in a unit
 * test. What they do protect is the part that is easy to lose: each of these
 * declarations looks redundant on its own, and removing one has no visible
 * effect until a long unbreakable string turns up in real data.
 *
 * The failure this prevents: a DoH upstream URL with no break opportunity
 * stretched its flex row, the row stretched its auto-sized grid track, and the
 * progress bar sized at 100% of that track ran 161px outside the card frame.
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

// Read from disk rather than imported: Vitest resolves a CSS import to an
// empty string unless CSS processing is turned on, which this one assertion
// does not justify.
const css = readFileSync(fileURLToPath(new URL('./global.css', import.meta.url)), 'utf8');

function rule(selector: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = css.match(new RegExp(`(^|[},])\\s*${escaped}\\s*\\{([^}]*)\\}`, 'm'));
  return match ? match[2] : '';
}

describe('shrinkable containers', () => {
  it('.truncate can shrink below its content width', () => {
    // A flex item defaults to min-width:auto, which refuses to shrink to the
    // point where text-overflow would apply. Without this the ellipsis never
    // appears and the row grows instead.
    expect(rule('.truncate')).toMatch(/min-width:\s*0/);
    expect(rule('.truncate')).toMatch(/text-overflow:\s*ellipsis/);
  });

  it('grid children can shrink below their content width', () => {
    // An auto-sized grid track is at least as wide as its item's min-content
    // size, so without this one long word widens the whole track past the
    // container.
    expect(rule('.grid > *')).toMatch(/min-width:\s*0/);
  });

  it('a card body scrolls rather than letting content escape the frame', () => {
    // Data tables are wider than a phone screen by nature.
    expect(rule('.card-body')).toMatch(/overflow-x:\s*auto/);
  });

  it('a card header wraps instead of overflowing', () => {
    expect(rule('.card-header')).toMatch(/flex-wrap:\s*wrap/);
  });
});

describe('control sizing', () => {
  it('buttons and native selects share one height', () => {
    // A native select sizes itself and ignores padding, so both have to be
    // given the height explicitly or they do not line up.
    expect(rule(':root')).toMatch(/--control-height:/);
    expect(rule('.btn')).toMatch(/height:\s*var\(--control-height\)/);
    expect(css).toMatch(/select\s*\{[^}]*height:\s*var\(--control-height\)/s);
  });
});
