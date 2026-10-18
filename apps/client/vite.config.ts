import { defineConfig, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import { readFile } from 'node:fs/promises';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { parse } from 'smol-toml';

function localOath(): Plugin {
  return {
    name: 'hymio-local-oath',
    configureServer(server) {
      server.middlewares.use('/__hymio/local-profile', async (req, res) => {
        const host = req.headers.host;
        const origin = req.headers.origin;
        const local = ['127.0.0.1', '::1', '::ffff:127.0.0.1'].includes(
          req.socket.remoteAddress ?? '',
        );
        if (
          req.method !== 'POST' ||
          req.headers['x-hymio-local'] !== '1' ||
          !local ||
          !host ||
          !/^(127\.0\.0\.1|localhost):\d+$/.test(host) ||
          (origin && origin !== `http://${host}`)
        ) {
          res.statusCode = 403;
          res.end('Local request required');
          return;
        }
        res.setHeader('Cache-Control', 'no-store');
        res.setHeader('Content-Type', 'application/json');
        try {
          const raw = parse(await readFile(join(homedir(), '.oath/oath.toml'), 'utf8'));
          const services = raw.services as Record<string, unknown>;
          const users = services.users as Record<string, string>;
          const entry =
            Object.entries(users).find(([, id]) => id === 'local') ?? Object.entries(users)[0];
          if (!entry) throw new Error('No user credential');
          res.end(
            JSON.stringify({
              wsUrl: `ws://127.0.0.1:${services.gateway_port ?? 8765}`,
              bizUrl: `http://127.0.0.1:${services.biz_port ?? 8766}`,
              credential: entry[0],
              userId: entry[1],
            }),
          );
        } catch {
          res.statusCode = 404;
          res.end(JSON.stringify({ error: '未找到本机 Oath 用户配置，请先运行 oath 安装脚本。' }));
        }
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), localOath()],
  server: {
    port: 1420,
    strictPort: true,
    proxy: {
      '/oath-biz': {
        target: 'http://127.0.0.1:8766',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/oath-biz/, ''),
      },
    },
  },
  preview: { port: 1420, strictPort: true },
  clearScreen: false,
});
