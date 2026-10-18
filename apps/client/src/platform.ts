import { invoke, isTauri } from '@tauri-apps/api/core';
import type { Connection } from '@hymio/protocol';
export const desktop = isTauri();
export async function localProfile(): Promise<Connection> {
  if (desktop) return invoke('local_oath_profile');
  if (!import.meta.env.DEV)
    throw new Error('网页版请手动填写 Oath 用户凭据；本机读取仅在开发模式可用。');
  const response = await fetch('/__hymio/local-profile', {
    method: 'POST',
    headers: { 'X-Hymio-Local': '1' },
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '未能读取本机配置');
  return data;
}
export async function bizGet<T>(base: string, path: string, credential: string): Promise<T> {
  if (desktop) return invoke('biz_get', { base, path, credential });
  const root = base.replace(/\/$/, '');
  // The local development proxy targets Oath's default Biz port.
  const url =
    import.meta.env.DEV && root === 'http://127.0.0.1:8766' ? `/oath-biz${path}` : `${root}${path}`;
  const response = await fetch(url, {
    headers: { Authorization: `Bearer ${credential}` },
    signal: AbortSignal.timeout(10000),
  });
  if (!response.ok) throw new Error(`Biz HTTP ${response.status}`);
  return response.json();
}
export function readConnection(): Connection {
  try {
    const saved = JSON.parse(localStorage.getItem('hymio.endpoints') || '{}');
    return {
      credential: sessionStorage.getItem('hymio.credential') || '',
      wsUrl: typeof saved.wsUrl === 'string' ? saved.wsUrl : 'ws://127.0.0.1:8765',
      bizUrl: typeof saved.bizUrl === 'string' ? saved.bizUrl : 'http://127.0.0.1:8766',
    };
  } catch {
    return { wsUrl: 'ws://127.0.0.1:8765', bizUrl: 'http://127.0.0.1:8766', credential: '' };
  }
}
export function saveConnection(connection: Connection) {
  localStorage.setItem(
    'hymio.endpoints',
    JSON.stringify({ wsUrl: connection.wsUrl, bizUrl: connection.bizUrl }),
  );
  sessionStorage.setItem('hymio.credential', connection.credential);
}
