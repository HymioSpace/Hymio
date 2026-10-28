import type { Approval } from '@hymio/client';
import type { LoginState } from './useLogin';

export interface AuthorizationRule {
  id: string;
  grant_key: string;
  tool: string;
  title: string;
  summary: string;
  target: string;
  created_at: number;
  last_used_at?: number;
}

export interface AuthorizationSettings {
  mode: 'read_only' | 'guided' | 'autonomous';
  modes: string[];
  rules: AuthorizationRule[];
}

async function request(
  login: LoginState,
  path: string,
  body?: Record<string, unknown>,
): Promise<AuthorizationSettings> {
  const session = login.session;
  if (!session) throw new Error('未登录');
  const response = await fetch(session.backend + path, {
    method: body ? 'POST' : 'GET',
    headers: {
      Authorization: 'Bearer ' + session.access_token,
      'Content-Type': 'application/json',
    },
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(15000),
    redirect: 'error',
  });
  if (!response.ok) throw new Error('授权设置暂时不可用');
  return response.json() as Promise<AuthorizationSettings>;
}

export function loadAuthorizationSettings(login: LoginState) {
  return request(login, '/settings/tool-authorization');
}

export function setAuthorizationMode(login: LoginState, mode: string) {
  return request(login, '/settings/tool-authorization', { mode });
}

export function rememberApproval(login: LoginState, approval: Approval) {
  return request(login, '/settings/tool-authorization/rules', {
    tool: approval.tool,
    arguments: approval.arguments,
  });
}

export function forgetApproval(login: LoginState, id: string) {
  return request(login, '/settings/tool-authorization/rules', {
    operation: 'delete',
    id,
  });
}
