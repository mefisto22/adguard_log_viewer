import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The app is served both from the add-on's own root and from behind Home
// Assistant ingress, where the path prefix is generated per session. Relative
// asset URLs plus hash routing keep the same build working in both places.
export default defineConfig({
  base: './',
  plugins: [react()],
  build: {
    // The backend serves whatever ends up here.
    outDir: '../adguard_log_viewer/app/static',
    emptyOutDir: true,
    sourcemap: false,
    chunkSizeWarningLimit: 700,
  },
  server: {
    port: 5173,
    proxy: {
      // `npm run dev` talks to a backend started with `python -m app.main`.
      '/api': { target: 'http://127.0.0.1:8099', changeOrigin: true },
    },
  },
});
