import { useEffect, useRef, useState } from 'react';
import { X, Plug, ArrowRight, Eye, EyeOff, Laptop, LoaderCircle } from 'lucide-react';
import type { Connection } from '@hymio/protocol';
import { localProfile, desktop } from './platform';
export function Settings({
  connection,
  onConnect,
  onClose,
  connected,
  onDisconnect,
}: {
  connection: Connection;
  onConnect: (c: Connection) => void;
  onClose: () => void;
  connected: boolean;
  onDisconnect: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [form, setForm] = useState(connection),
    [error, setError] = useState(''),
    [loading, setLoading] = useState(false),
    [reveal, setReveal] = useState(false);
  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  async function local() {
    setLoading(true);
    setError('');
    try {
      setForm(await localProfile());
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    } finally {
      setLoading(false);
    }
  }
  function submit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    try {
      const biz = new URL(form.bizUrl, location.origin);
      if (!['http:', 'https:'].includes(biz.protocol) || biz.username || biz.password)
        throw new Error('Biz 地址需要使用 HTTP 或 HTTPS');
      onConnect({ ...form, credential: form.credential.trim() });
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e));
    }
  }
  return (
    <dialog
      className="settings-dialog"
      ref={dialog}
      onCancel={onClose}
      onClick={(e) => {
        if (e.target === dialog.current) onClose();
      }}
      aria-labelledby="settings-title"
    >
      <div className="dialog-head">
        <span className="dialog-symbol">
          <Plug size={22} />
        </span>
        <button className="icon-button" aria-label="关闭连接设置" onClick={onClose}>
          <X size={19} />
        </button>
      </div>
      <h2 id="settings-title">让 Hymio 连上线</h2>
      <p className="dialog-intro">连接你的 Oath，接着同一段对话。</p>
      {(desktop || import.meta.env.DEV) && (
        <button className="local-button" onClick={local} disabled={loading}>
          {loading ? <LoaderCircle className="spin" size={17} /> : <Laptop size={17} />}使用本机
          Oath 配置<span>~/.oath/oath.toml</span>
        </button>
      )}
      <form onSubmit={submit}>
        <label>
          对话服务<span>WebSocket</span>
          <input
            value={form.wsUrl}
            onChange={(e) => setForm({ ...form, wsUrl: e.target.value })}
            required
            spellCheck={false}
            placeholder="ws://127.0.0.1:8765"
          />
        </label>
        <label>
          观察服务<span>Biz HTTP</span>
          <input
            value={form.bizUrl}
            onChange={(e) => setForm({ ...form, bizUrl: e.target.value })}
            required
            spellCheck={false}
            placeholder="http://127.0.0.1:8766"
          />
        </label>
        <label>
          用户凭据<span>当前窗口内保存</span>
          <div className="password-field">
            <input
              aria-label="用户凭据"
              value={form.credential}
              type={reveal ? 'text' : 'password'}
              autoComplete="off"
              onChange={(e) => setForm({ ...form, credential: e.target.value })}
              required
              placeholder="Oath services.users 中的用户 token"
            />
            <button
              type="button"
              className="icon-button"
              onClick={() => setReveal(!reveal)}
              aria-label={reveal ? '隐藏凭据' : '显示凭据'}
            >
              {reveal ? <EyeOff size={17} /> : <Eye size={17} />}
            </button>
          </div>
        </label>
        {error && (
          <p role="alert" className="form-error">
            {error}
          </p>
        )}
        <button className="primary-button connect-button" type="submit">
          连接 Hymio
          <ArrowRight size={17} />
        </button>
      </form>
      {connected && (
        <button className="text-button disconnect" onClick={onDisconnect}>
          断开客户端连接
        </button>
      )}
      <p className="dialog-note">客户端离开后，已接纳的任务仍由 Oath 继续执行。</p>
    </dialog>
  );
}
