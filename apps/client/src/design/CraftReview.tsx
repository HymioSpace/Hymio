import { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import '@hymio/ui';
import '../styles.css';
import '../craft.css';
import craftSource from '../craft.css?raw';
import tokenSource from '../../../../packages/ui/src/tokens.css?raw';
import { Disclosure } from '../Disclosure';
import { ProgressiveContent, MotionText } from '../ProgressiveContent';
import { MessageView } from '../MessageView';
import { MessageImage } from '../MessageImage';
import type { LoginState } from '../useLogin';

function Review() {
  const [target, setTarget] = useState('');
  const [start, setStart] = useState(0);
  const text = '小海獭正在核对订单。时间、地点和价格会逐项保留。Streaming words stay together.';
  useEffect(() => {
    if (!start) return;
    setTarget('');
    let index = 0;
    const timer = setInterval(() => {
      index += 2;
      setTarget(text.slice(0, index));
      if (index >= text.length) clearInterval(timer);
    }, 90);
    return () => clearInterval(timer);
  }, [start]);
  const previewDark = new URLSearchParams(location.search).get('theme') === 'dark';
  const darkVariables = [tokenSource, craftSource]
    .map(
      (source) =>
        source.match(/@media \(prefers-color-scheme: dark\)\s*\{\s*:root\s*\{([^}]+)/)?.[1] || '',
    )
    .join('\n');
  return (
    <>
      <style>{previewDark ? `:root { color-scheme: dark; ${darkVariables} }` : ''}</style>
      <main
        style={{ maxWidth: 720, margin: '32px auto', padding: 24, background: 'var(--layer-2)' }}
      >
        <h1 style={{ fontSize: 24 }}>展示层验证</h1>
        <p>合成内容 · 使用实际消息、折叠与流式组件</p>
        <section aria-label="窄屏附件与暂停验证" style={{ maxWidth: 280 }}>
          <div className="sent-attachment-tray">
            {Array.from({ length: 7 }, (_, index) => (
              <MessageImage
                key={index}
                src={`unsupported:fixture-${index}`}
                thumbnail
                login={{ backend: 'http://127.0.0.1' } as LoginState}
              />
            ))}
          </div>
          <div className="pause-notice">
            <p role="status">本轮自动处理额度已用完，进展已保留。</p>
            <button className="pause-continue" disabled>
              继续处理
            </button>
          </div>
        </section>
        <div className="composer">
          <textarea aria-label="聚焦示例" placeholder="点击后检查双环阴影" />
        </div>
        <div style={{ marginTop: 24 }}>
          <Disclosure
            className="trace-fold"
            data-testid="craft-fold"
            summary={<span>已探索 39 秒</span>}
          >
            <div className="trace-fold-body">
              <p>已核对车次与住宿。</p>
              <button type="button">过程中的操作</button>
            </div>
          </Disclosure>
        </div>
        <button
          type="button"
          onClick={() => setStart((value) => value + 1)}
          style={{ padding: 12 }}
        >
          开始流式显示
        </button>
        <ProgressiveContent
          content={target}
          streaming={target.length < text.length}
          onAction={async () => {}}
          render={(value) => (
            <p>
              <MotionText>{value}</MotionText>
            </p>
          )}
        />
        <MessageView
          message={{
            id: 'synthetic-copy',
            role: 'assistant',
            content: '```text\n只复制这段合成文字\n```',
            time: '2026-10-27T14:00:00Z',
          }}
          tools={[]}
          login={{ backend: 'http://127.0.0.1', session: undefined } as LoginState}
          onAction={async () => {}}
        />
      </main>
    </>
  );
}
createRoot(document.getElementById('root')!).render(<Review />);
