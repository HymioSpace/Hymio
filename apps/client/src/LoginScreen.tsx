import { useEffect, useState } from 'react';
import { ArrowRight, LoaderCircle } from 'lucide-react';
import { Companion } from '@hymio/ui';
import type { LoginState } from './useLogin';

export function LoginScreen({ login }: { login: LoginState }) {
  const [method, setMethod] = useState<'account' | 'google'>('account');
  useEffect(() => {
    const controller = new AbortController();
    void fetch(`${login.backend}/auth/options`, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error('unavailable');
        return response.json();
      })
      .then((options) => setMethod(options.login_method === 'google' ? 'google' : 'account'))
      .catch(() => {});
    return () => controller.abort();
  }, [login.backend]);
  return (
    <main className="login-screen">
      <div className="login-wordmark" data-tauri-drag-region>
        hymio<span>in tune with you</span>
      </div>
      <section className="login-content" aria-labelledby="login-heading">
        <div className="login-companion">
          <Companion mood="idle" />
        </div>
        <p className="login-eyebrow">YOUR EVERYDAY COMPANION</p>
        <h1 id="login-heading">你好，我是 Hymio。</h1>
        <p className="login-description">
          从一句话开始，慢慢懂你。
          <br />
          你的日常，在这里接着聊。
        </p>
        <button className="login-continue" disabled={login.busy} onClick={() => void login.login()}>
          {login.busy ? (
            <LoaderCircle size={18} className="spin" />
          ) : method === 'google' ? (
            <GoogleMark />
          ) : null}
          {login.busy
            ? '等待浏览器确认…'
            : method === 'google'
              ? '使用 Google 继续'
              : '登录或创建账号'}
          {!login.busy && method !== 'google' && <ArrowRight size={17} />}
        </button>
        {login.busy ? (
          <div className="login-help">
            在打开的浏览器中完成登录。<button onClick={login.cancel}>取消</button>
          </div>
        ) : (
          <p className="login-help">
            {method === 'google'
              ? '首次登录会自动创建 Hymio 账号。'
              : '在安全登录页完成登录或注册。'}
          </p>
        )}
        {login.error && (
          <p className="login-error" role="alert">
            {login.error}
          </p>
        )}
      </section>
      <footer className="login-footer">属于你的对话，随时继续。</footer>
    </main>
  );
}
function GoogleMark() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="#4285F4"
        d="M21.6 12.2c0-.7-.1-1.4-.2-2.1H12v4h5.4a4.6 4.6 0 0 1-2 3v2.5h3.2c1.9-1.8 3-4.3 3-7.4Z"
      />
      <path
        fill="#34A853"
        d="M12 22c2.7 0 5-.9 6.6-2.4l-3.2-2.5c-.9.6-2 1-3.4 1-2.6 0-4.8-1.8-5.6-4.1H3.1v2.6A10 10 0 0 0 12 22Z"
      />
      <path fill="#FBBC05" d="M6.4 14a6 6 0 0 1 0-4V7.4H3.1a10 10 0 0 0 0 9.2L6.4 14Z" />
      <path
        fill="#EA4335"
        d="M12 5.9c1.5 0 2.8.5 3.9 1.5l2.9-2.9A9.6 9.6 0 0 0 12 2a10 10 0 0 0-8.9 5.4L6.4 10A6 6 0 0 1 12 5.9Z"
      />
    </svg>
  );
}
