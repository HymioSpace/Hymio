import type { LoginState } from './useLogin';
export interface Device {
  device_id: string;
  name: string;
  kind: string;
  provider: string;
  state: string;
  online: boolean;
  capabilities: string[];
  permissions?: {
    screen_recording?: boolean;
    accessibility?: boolean;
    shell?: boolean;
    unlocked?: boolean;
    screen_awake?: boolean;
  };
  preserves_files_on_revoke: boolean;
  replaces_device_id?: string | null;
}
const errorMessages: Record<string, string> = {
  device_busy_or_requires_recovery:
    '上一次云端操作尚未结束。系统正在保留原环境并核对结果，请稍后重试；原操作不会重复执行。',
  device_busy_or_outcome_unknown:
    '上一次云端操作结果未知。系统会先确认远端状态，不会直接重复执行；请稍后重试。',
  device_running_or_requires_recovery: '云电脑仍有一条执行记录。过期记录会自动核对，请稍后再试。',
  device_unavailable: '云电脑暂时无法连接，原环境和文件仍会保留，请稍后重试。',
  provision_requires_recovery: '云电脑的创建结果还在核对中，请稍后重试，不要重复创建。',
};
export class DeviceRequestError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
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
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const code =
      payload && typeof payload === 'object' && 'error' in payload ? String(payload.error) : '';
    throw new DeviceRequestError(
      errorMessages[code] ||
        (response.status === 409
          ? '设备状态正在变化，请稍后重试。'
          : `设备服务暂不可用（${response.status}）`),
      response.status,
    );
  }
  return payload;
}

export async function deviceImage(login: LoginState, path: string, signal?: AbortSignal) {
  const session = login.session;
  if (!session) throw new Error('请先登录以查看截图');
  const url = new URL(path, session.backend + '/');
  if (
    url.origin !== new URL(session.backend).origin ||
    !/^\/(?:devices\/media|attachments)\/[a-f0-9]{32}$/.test(url.pathname)
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
