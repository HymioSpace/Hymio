import { spawn } from 'node:child_process';
let reuse = false;
try {
  const response = await fetch('http://127.0.0.1:1420/', { signal: AbortSignal.timeout(1000) });
  if (!(await response.text()).includes('<title>Hymio')) {
    throw new Error('Port 1420 is already used by another app. Stop it before starting Hymio.');
  }
  reuse = true;
} catch (error) {
  if (error.message.includes('Port 1420')) throw error;
}
const args = ['exec', 'tauri', 'dev'];
if (reuse) args.push('--config', JSON.stringify({ build: { beforeDevCommand: null } }));
const child = spawn('pnpm', args, { stdio: 'inherit', shell: process.platform === 'win32' });
child.on('exit', (code) => process.exit(code ?? 1));
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => child.kill(signal));
