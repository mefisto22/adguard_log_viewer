import { defineConfig } from 'vitest/config';

// The logic worth testing here — the filter tree the UI builds and reads back —
// is pure, so no DOM environment is needed.
export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
});
