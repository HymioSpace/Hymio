import { useEffect, useState } from 'react';
import { ArrowRight, Eye, EyeOff } from 'lucide-react';
import { Companion, Button } from '@hymio/ui';
import type { LoginState } from './useLogin';

export function LoginScreen({ login }: { login: LoginState }) {
  const [mode, setMode] = useState<'login' | 'signup'>('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [reveal, setReveal] = useState(false);
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
        <h1 id="login-heading">你好，我是 Hymio。</h1>
        <p className="login-description">一个 Hymio，随时接着聊。</p>
        {method === 'account' ? (
          <form
            className="account-form"
            onSubmit={(event) => {
              event.preventDefault();
              void login.account(mode, username.trim(), password).finally(() => setPassword(''));
            }}
          >
            <label htmlFor="account-username">用户名</label>
            <input
              id="account-username"
              name="username"
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              placeholder="你的用户名"
              required
              pattern={'[A-Za-z0-9_\\-]{3,32}'}
              title="3–32 位字母、数字、下划线或连字符"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              disabled={login.busy}
            />
            <label htmlFor="account-password">密码</label>
            <div className="account-password">
              <input
                id="account-password"
                name="password"
                type={reveal ? 'text' : 'password'}
                autoComplete={mode === 'signup' ? 'new-password' : 'current-password'}
                placeholder={mode === 'signup' ? '至少 8 个字符' : '输入密码'}
                required
                minLength={mode === 'signup' ? 8 : 1}
                maxLength={128}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                disabled={login.busy}
              />
              <button
                type="button"
                aria-label={reveal ? '隐藏密码' : '显示密码'}
                onClick={() => setReveal(!reveal)}
              >
                {reveal ? <EyeOff size={17} /> : <Eye size={17} />}
              </button>
            </div>
            {mode === 'signup' && (
              <p className="account-hint">用户名为 3–32 位字母、数字、下划线或连字符。</p>
            )}
            <Button className="login-continue" variant="primary" type="submit" busy={login.busy}>
              {login.busy ? '正在处理…' : mode === 'signup' ? '创建账号' : '登录'}
              {!login.busy && <ArrowRight size={17} />}
            </Button>
            <p className="login-help">
              {mode === 'signup' ? '已有账号？' : '第一次来？'}
              <button
                type="button"
                disabled={login.busy}
                onClick={() => {
                  setMode(mode === 'signup' ? 'login' : 'signup');
                  setPassword('');
                  setReveal(false);
                }}
              >
                {mode === 'signup' ? '登录' : '创建账号'}
              </button>
            </p>
          </form>
        ) : (
          <>
            <Button className="login-continue" busy={login.busy} onClick={() => void login.login()}>
              {!login.busy && <GoogleMark />}
              {login.busy ? '等待浏览器确认…' : '使用 Google 继续'}
            </Button>
            {login.busy ? (
              <div className="login-help">
                在浏览器中完成登录。<button onClick={login.cancel}>取消</button>
              </div>
            ) : (
              <p className="login-help">首次登录会自动创建 Hymio 账号。</p>
            )}
          </>
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
