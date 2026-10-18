import { invoke, isTauri } from '@tauri-apps/api/core';
export const desktop = isTauri();
export async function bizGet<T>(
  base: string,
  path: string,
  credential: string,
  userId = '',
): Promise<T> {
  if (desktop) return invoke('biz_get', { base, path, credential, userId });
  const url = `${base.replace(/\/$/, '')}${path}`;
  const response = await fetch(url, {
    headers: { Authorization: `Bearer ${credential}`, 'X-Oath-User-Id': userId },
    signal: AbortSignal.timeout(10000),
  });
  if (!response.ok) throw new Error(`Biz HTTP ${response.status}`);
  return response.json();
}
