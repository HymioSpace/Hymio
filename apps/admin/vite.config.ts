import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  base: '/admin/',
  server: {
    host: '127.0.0.1',
    port: 1421,
    strictPort: true,
    proxy: {
      '/admin/api': 'http://127.0.0.1:8080',
      '/auth': 'http://127.0.0.1:8080',
    },
  },
  preview: { host: '127.0.0.1', port: 1421, strictPort: true },
  clearScreen: false,
});
