import type { LoginState } from './useLogin';
export interface Device {
  device_id: string;
  name: string;
  kind: string;
  provider: string;
  state: string;
  online: boolean;
  capabilities: string[];
  preserves_files_on_revoke: boolean;
  replaces_device_id?: string | null;
}
export async function deviceRequest(login: LoginState, path = '', data?: object) {
  const session = login.session;
  if (!session) throw new Error('请先登录');
  const response = await fetch(`${session.backend}/devices${path}`, {
    method: data ? 'POST' : 'GET',
    headers: {
      Authorization: `Bearer ${session.access_token}`,
      'Content-Type': 'application/json',
    },
    body: data ? JSON.stringify(data) : undefined,
    signal: AbortSignal.timeout(
      ['/provision', '/ensure'].includes(path)
        ? 130000
        : /\/(pause|resume)$/.test(path)
          ? 90000
          : 15000,
    ),
  });
  if (!response.ok)
    throw new Error(
      response.status === 409
        ? '设备正在执行操作，请稍后再试'
        : `设备服务暂不可用（${response.status}）`,
    );
  return response.json();
}

export async function deviceImage(login: LoginState, path: string, signal?: AbortSignal) {
  const session = login.session;
  if (!session) throw new Error('请先登录以查看截图');
  const url = new URL(path, session.backend + '/');
  if (
    url.origin !== new URL(session.backend).origin ||
    !/^\/devices\/media\/[a-f0-9]{32}$/.test(url.pathname)
  )
    throw new Error('截图地址与当前服务不一致');
  const response = await fetch(url.href, {
    headers: { Authorization: `Bearer ${session.access_token}` },
    redirect: 'error',
    signal: signal || AbortSignal.timeout(15000),
  });
  if (!response.ok)
    throw new Error(response.status === 404 ? '截图不存在或无权查看' : '截图加载失败，请重试');
  if (!response.headers.get('content-type')?.startsWith('image/'))
    throw new Error('返回内容不是图片');
  return response.blob();
}
