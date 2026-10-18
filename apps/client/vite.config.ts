import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { readFileSync } from 'node:fs';
import { parse } from 'smol-toml';

const settings = parse(readFileSync(new URL('./client.toml', import.meta.url), 'utf8'));
const backend = new URL(String(settings.backend_url));
if (
  !['http:', 'https:'].includes(backend.protocol) ||
  backend.username ||
  backend.password ||
  backend.search ||
  backend.hash
) {
  throw new Error('client.toml backend_url must be an HTTP(S) service URL');
}
export default defineConfig({
  plugins: [react()],
  define: { __HYMIO_BACKEND__: JSON.stringify(backend.href.replace(/\/$/, '')) },
  server: { port: 1420, strictPort: true },
  preview: { port: 1420, strictPort: true },
  clearScreen: false,
});
