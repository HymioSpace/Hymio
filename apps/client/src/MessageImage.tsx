import { useEffect, useState } from 'react';
import type { LoginState } from './useLogin';
import { DesktopSnapshot } from './DesktopSnapshot';
import { deviceImage } from './deviceApi';

export function MessageImage({
  src,
  alt,
  login,
}: {
  src?: string;
  alt?: string;
  login: LoginState;
}) {
  const [image, setImage] = useState('');
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [zoomed, setZoomed] = useState(false);
  const session = login.session;
  useEffect(() => {
    const controller = new AbortController();
    let objectUrl = '';
    setImage('');
    setError('');
    setZoomed(false);
    async function load() {
      if (!src) throw new Error('图片地址为空');
      const base = session?.backend || login.backend;
      const url = new URL(src, base + '/');
      const media = /^\/devices\/media\/[a-f0-9]{32}$/.test(url.pathname);
      if (media) {
        objectUrl = URL.createObjectURL(await deviceImage(login, src, controller.signal));
        if (controller.signal.aborted) {
          URL.revokeObjectURL(objectUrl);
          return;
        }
        setImage(objectUrl);
      } else {
        if (!['https:', 'http:'].includes(url.protocol))
          throw new Error('此图片路径无法在客户端打开，请让 Hymio 使用截图工具重新截图');
        setImage(url.href);
      }
    }
    void load().catch((e) => {
      if (!controller.signal.aborted) setError(e instanceof Error ? e.message : '图片加载失败');
    });
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [src, session?.access_token, session?.backend, login.backend, attempt]);
  if (error)
    return (
      <span className="message-image-error" role="status">
        {error} <button onClick={() => setAttempt((a) => a + 1)}>重试</button>
      </span>
    );
  if (!image) return <span className="message-image-loading">正在加载图片…</span>;
  return (
    <>
      <img
        className="message-image"
        src={image}
        alt={alt || '截图'}
        onClick={() => setZoomed(true)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            setZoomed(true);
          }
        }}
        role="button"
        tabIndex={0}
        aria-label="放大图片"
        onError={() => setError('图片无法加载，请重试或让 Hymio 重新截图')}
      />
      {zoomed && <DesktopSnapshot src={image} onClose={() => setZoomed(false)} />}
    </>
  );
}
