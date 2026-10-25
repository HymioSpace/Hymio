import { useEffect, useState } from 'react';
import { Copy, Link2, LoaderCircle, X } from 'lucide-react';
import type { LoginState } from './useLogin';
import { DeviceRequestError, deviceRequest } from './deviceApi';

export function LinkPairing({ login }: { login: LoginState }) {
  const [pairing, setPairing] = useState<{ code: string; expires_at: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!pairing) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [pairing]);
  useEffect(() => {
    setPairing(null);
  }, [login.session?.user_id, login.backend]);
  async function create() {
    setBusy(true);
    setError('');
    setCopied(false);
    try {
      setPairing(await deviceRequest(login, '/link/pairings', {}));
      setNow(Date.now());
    } catch (error) {
      setError(
        error instanceof DeviceRequestError && error.status === 404
          ? '当前服务尚未启用设备配对，请更新服务后再试。'
          : error instanceof DeviceRequestError && error.status === 401
            ? '登录已过期，请重新登录后生成配对码。'
            : '暂时无法生成配对码，请稍后重试。',
      );
    } finally {
      setBusy(false);
    }
  }
  const remaining = pairing ? Math.max(0, Math.ceil(pairing.expires_at - now / 1000)) : 0;
  let sameMacAddress = '';
  try {
    const url = new URL(login.session?.backend || '');
    if (url.protocol === 'http:') {
      url.hostname = '127.0.0.1';
      sameMacAddress = url.origin;
    }
  } catch {
    /* The authenticated session normally supplies a valid service origin. */
  }
  return (
    <div className="link-pairing">
      {!pairing ? (
        <button className="text-button" disabled={busy} onClick={() => void create()}>
          {busy ? <LoaderCircle size={15} className="spin" /> : <Link2 size={15} />} 连接我的设备
        </button>
      ) : (
        <section className="link-pairing-card" aria-label="连接个人设备">
          <header>
            <strong>连接你的 Mac 或 Android 手机</strong>
            <button
              className="text-button"
              aria-label="收起配对码"
              onClick={() => setPairing(null)}
            >
              <X size={16} />
            </button>
          </header>
          <p>在设备上打开 HymioDevice，填写当前服务地址并输入配对码。仅连接你信任的设备。</p>
          <code>{login.session?.backend}</code>
          {sameMacAddress && (
            <p>
              若 Backend 就在运行 HymioDevice 的这台 Mac 上，请填写 <code>{sameMacAddress}</code>。
              Android 或其他设备连接需要 HTTPS；USB 开发调试可通过 ADB 转发使用本机地址。
            </p>
          )}
          <div className="link-pairing-code">
            <code>{remaining ? pairing.code : '配对码已过期'}</code>
            <button
              className="text-button"
              disabled={!remaining}
              onClick={() => {
                void navigator.clipboard
                  .writeText(pairing.code)
                  .then(() => setCopied(true))
                  .catch(() => setError('复制失败，请选择配对码手动复制。'));
              }}
            >
              <Copy size={14} /> {copied ? '已复制' : '复制'}
            </button>
          </div>
          <footer>
            <span>
              {remaining
                ? `${Math.floor(remaining / 60)}:${String(remaining % 60).padStart(2, '0')} 后失效 · 仅可使用一次`
                : '请重新生成配对码'}
            </span>
            {!remaining && (
              <button className="text-button" disabled={busy} onClick={() => void create()}>
                重新生成
              </button>
            )}
          </footer>
          <p>连接后仍需在 Mac 授予屏幕录制与辅助功能权限。Shell 默认关闭，可随时在本机断开。</p>
        </section>
      )}
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
