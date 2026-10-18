import { useEffect, useRef, useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import type { Connection } from '@hymio/protocol';
import { desktop } from './platform';

interface Session {
  access_token: string;
  refresh_token: string;
  expires_at: number;
  user_id: string;
  name: string;
  oath_ws: string;
  oath_biz: string;
  backend: string;
}
const key = 'hymio.login';
function saved(): Session | undefined {
  try {
    const value = JSON.parse(sessionStorage.getItem(key) || 'null');
    return value?.backend === __HYMIO_BACKEND__ ? value : undefined;
  } catch {
    return undefined;
  }
}
export function useLogin(
  onConnection: (value: Connection, signedIn: boolean) => void,
  onLogout: () => void,
) {
  const [session, setSession] = useState<Session | undefined>(saved);
  const backend = __HYMIO_BACKEND__;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const generation = useRef(0);
  const cancelFlow = useRef(() => {});
  const callbacks = useRef({ onConnection, onLogout });
  callbacks.current = { onConnection, onLogout };
  const refreshing = useRef<Promise<void> | null>(null);
  async function request(base: string, path: string, body?: object, access?: string) {
    const response = await fetch(`${base.replace(/\/$/, '')}${path}`, {
      method: body ? 'POST' : 'GET',
      headers: {
        'Content-Type': 'application/json',
        ...(access ? { Authorization: `Bearer ${access}` } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
      signal: AbortSignal.timeout(15000),
    });
    if (!response.ok)
      throw new Error(
        response.status === 401
          ? '登录已失效，请重新登录。'
          : `登录服务暂不可用（${response.status}）`,
      );
    return response.json();
  }
  function apply(value: Session, signedIn = false) {
    if (
      !value.access_token ||
      !value.refresh_token ||
      !value.user_id ||
      !Number.isFinite(value.expires_at)
    )
      throw new Error('登录响应格式无效');
    sessionStorage.setItem(key, JSON.stringify(value));
    setSession(value);
    callbacks.current.onConnection(
      {
        wsUrl: value.oath_ws,
        bizUrl: value.oath_biz,
        credential: value.access_token,
        userId: value.user_id,
      },
      signedIn,
    );
  }
  async function login() {
    const popup = desktop ? null : window.open('about:blank', '_blank');
    const current = ++generation.current;
    setBusy(true);
    setError('');
    let cleanup = () => {};
    try {
      const url = new URL(backend);
      if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password)
        throw new Error('登录服务配置无效，请联系部署者。');
      if (desktop) {
        const result = await invoke<Session>('login_with_browser', { backend });
        if (current === generation.current) apply({ ...result, backend }, true);
        else await request(backend, '/auth/logout', {}, result.access_token);
        return;
      }
      if (!popup) throw new Error('请允许打开登录窗口后重试。');
      const flow = await request(backend, '/auth/start', { return_uri: location.origin });
      if (current !== generation.current) {
        popup.close();
        return;
      }
      const grant = new Promise<string>((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error('登录等待已过期，请重试。')), 300000);
        const closed = setInterval(() => {
          if (popup.closed) reject(new Error('登录窗口已关闭，请重试。'));
        }, 500);
        const listener = (event: MessageEvent) => {
          if (
            event.origin !== url.origin ||
            event.source !== popup ||
            event.data?.type !== 'hymio.login'
          )
            return;
          if (event.data.error) reject(new Error('登录未完成，请重试。'));
          else if (typeof event.data.login_code === 'string') resolve(event.data.login_code);
        };
        window.addEventListener('message', listener);
        cleanup = () => {
          clearTimeout(timer);
          clearInterval(closed);
          window.removeEventListener('message', listener);
        };
        cancelFlow.current = () => {
          cleanup();
          popup.close();
          reject(new Error('登录已取消'));
        };
      });
      popup.location.href = flow.authorization_url;
      const code = await grant;
      if (current !== generation.current) return;
      const result = await request(backend, '/auth/exchange', {
        flow_id: flow.flow_id,
        login_code: code,
      });
      if (current === generation.current) apply({ ...result, backend }, true);
      else await request(backend, '/auth/logout', {}, result.access_token);
    } catch (e) {
      if (current === generation.current)
        setError(
          e instanceof TypeError
            ? '暂时无法连接登录服务，请稍后重试。'
            : e instanceof Error
              ? e.message
              : String(e),
        );
    } finally {
      cleanup();
      popup?.close();
      if (current === generation.current) setBusy(false);
    }
  }
  async function logout() {
    if (!session) return;
    setBusy(true);
    setError('');
    try {
      await request(session.backend, '/auth/logout', {}, session.access_token);
      generation.current++;
      sessionStorage.removeItem(key);
      setSession(undefined);
      callbacks.current.onLogout();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  function refresh(value: Session) {
    if (refreshing.current) return refreshing.current;
    const current = generation.current;
    refreshing.current = request(value.backend, '/auth/refresh', {
      refresh_token: value.refresh_token,
    })
      .then((result) => {
        if (current === generation.current) apply({ ...result, backend: value.backend });
      })
      .catch((e) => {
        if (current !== generation.current) return;
        setError(String(e));
        callbacks.current.onLogout();
        // A failed response may have consumed the rotating token. Require login rather than replay it.
        sessionStorage.removeItem(key);
        setSession(undefined);
      })
      .finally(() => {
        refreshing.current = null;
      });
    return refreshing.current;
  }
  useEffect(() => {
    localStorage.removeItem('hymio.endpoints');
    localStorage.removeItem('hymio.backend');
    sessionStorage.removeItem('hymio.credential');
    const value = saved();
    if (!value) return;
    if (value.backend !== backend) {
      sessionStorage.removeItem(key);
      setSession(undefined);
      return;
    }
    if (value.expires_at * 1000 > Date.now()) apply(value);
  }, []);
  useEffect(() => {
    if (!session) return;
    const remaining = session.expires_at * 1000 - Date.now();
    if (remaining <= 0) {
      void refresh(session);
      return;
    }
    const timer = setTimeout(
      () => void refresh(session),
      Math.max(500, remaining - Math.min(30000, remaining * 0.2)),
    );
    const resume = () => {
      if (session.expires_at * 1000 <= Date.now() + 1000) void refresh(session);
    };
    window.addEventListener('focus', resume);
    return () => {
      clearTimeout(timer);
      window.removeEventListener('focus', resume);
    };
  }, [session]);
  useEffect(
    () => () => {
      generation.current++;
      cancelFlow.current();
      if (desktop) void invoke('cancel_login');
    },
    [],
  );
  return {
    session,
    backend,
    busy,
    error,
    login,
    logout,
    cancel: () => {
      generation.current++;
      cancelFlow.current();
      if (desktop) void invoke('cancel_login');
      setBusy(false);
    },
  };
}
export type LoginState = ReturnType<typeof useLogin>;
