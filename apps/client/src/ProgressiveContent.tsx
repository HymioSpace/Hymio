import {
  Children,
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { TextBuffer, contentParts, parseSurface, actionPrompt } from '@hymio/client';
import { ArrowUpRight, Sparkles, CircleAlert } from 'lucide-react';

export function useBufferedText(target: string, streaming: boolean) {
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const buffer = useRef<TextBuffer | null>(null);
  if (!buffer.current) {
    buffer.current = new TextBuffer();
    buffer.current.set(target, performance.now(), !streaming || reduced);
  }
  const [visible, setVisible] = useState(buffer.current.value);
  useEffect(() => {
    const b = buffer.current!;
    const next = b.set(target, performance.now(), reduced || document.hidden);
    setVisible((current) => (current === next ? current : next));
    const resume = () => {
      if (!document.hidden) {
        const next = b.set(target, performance.now(), true);
        setVisible((current) => (current === next ? current : next));
      }
    };
    document.addEventListener('visibilitychange', resume);
    return () => {
      document.removeEventListener('visibilitychange', resume);
    };
  }, [target, reduced]);
  useEffect(() => {
    const b = buffer.current!;
    const timer = window.setInterval(() => {
      if (document.hidden) return;
      const next = b.tick(performance.now());
      setVisible((current) => (current === next ? current : next));
    }, 32);
    return () => clearInterval(timer);
  }, []);
  return { text: visible, pending: visible !== target };
}
const TextMotion = createContext(false);
export function MotionText({ children }: { children: ReactNode }) {
  const animate = useContext(TextMotion);
  if (!animate) return <>{children}</>;
  return (
    <>
      {Children.map(children, (child, index) =>
        typeof child === 'string'
          ? Array.from(
              new Intl.Segmenter(undefined, { granularity: 'grapheme' }).segment(child),
              (s) => s.segment,
            )
              .reduce<string[]>((out, g, i) => {
                if (i % 4 === 0) out.push(g);
                else out[out.length - 1] += g;
                return out;
              }, [])
              .map((text, i) => (
                <span className="text-resolve" key={`${index}-${i}`}>
                  {text}
                </span>
              ))
          : child,
      )}
    </>
  );
}
function Prose({
  source,
  streaming,
  render,
}: {
  source: string;
  streaming: boolean;
  render: (text: string) => ReactNode;
}) {
  const display = useBufferedText(source, streaming);
  return (
    <TextMotion.Provider value={display.pending || streaming}>
      <div className={display.pending ? 'prose-release' : 'prose-settled'}>
        {render(display.text)}
      </div>
    </TextMotion.Provider>
  );
}
export function ProgressiveContent({
  content,
  streaming,
  render,
  onAction,
}: {
  content: string;
  streaming: boolean;
  render: (text: string) => ReactNode;
  onAction: (text: string) => Promise<void>;
}) {
  return (
    <>
      {contentParts(content, streaming).map((p) =>
        p.kind === 'ui' ? (
          <AgentSurface key={p.id} source={p.source} complete={p.complete} onAction={onAction} />
        ) : (
          <Prose key={p.id} source={p.source} streaming={streaming} render={render} />
        ),
      )}
    </>
  );
}
function SurfaceFrame({ children }: { children: ReactNode }) {
  const body = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState<number>();
  useEffect(() => {
    const node = body.current;
    if (!node) return;
    const observer = new ResizeObserver(() => {
      if (node.getClientRects().length) setHeight(node.getBoundingClientRect().height);
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  return (
    <div className="surface-frame" style={{ height: height === undefined ? 'auto' : height }}>
      <div ref={body}>{children}</div>
    </div>
  );
}
export function AgentSurface({
  source,
  complete,
  onAction,
}: {
  source: string;
  complete: boolean;
  onAction: (text: string) => Promise<void>;
}) {
  const parsed = parseSurface(source, complete);
  const animate = useRef(!complete).current;
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false),
    [failure, setFailure] = useState('');
  const spec = parsed.spec;
  const currentValues = Object.fromEntries(
    Object.entries(spec?.elements || {})
      .filter(([, n]) => n.type === 'Input' || n.type === 'Choice')
      .map(([id, n]) => [id, values[id] ?? String(n.props.value || '')]),
  );
  const resolvable = (template: string) =>
    [...template.matchAll(/\{\{([A-Za-z0-9_-]{1,64})\}\}/g)].every((match) =>
      Object.hasOwn(currentValues, match[1]),
    );
  async function submit(template: string) {
    const text = actionPrompt(template, currentValues);
    if (!text || busy || !resolvable(template)) return;
    setBusy(true);
    setFailure('');
    try {
      await onAction(text);
    } catch {
      setFailure('未能发送，请重试。');
    } finally {
      setBusy(false);
    }
  }
  function element(id: string, depth = 0): ReactNode {
    if (!spec || depth > 12) return null;
    const n = spec.elements[id];
    if (!n)
      return complete ? null : <div key={id} className="surface-slot" aria-label="正在生成内容" />;
    const p = n.props,
      text = (key: string) => (typeof p[key] === 'string' ? (p[key] as string) : '');
    const children = () =>
      n.children?.map((c) => (
        <div className="surface-node" key={c}>
          {element(c, depth + 1)}
        </div>
      ));
    switch (n.type) {
      case 'Card':
        return (
          <section className="surface-card">
            {text('title') && <h3>{text('title')}</h3>}
            {text('subtitle') && <p className="surface-muted">{text('subtitle')}</p>}
            <div className="surface-column">{children()}</div>
          </section>
        );
      case 'Column':
        return <div className="surface-column">{children()}</div>;
      case 'Row':
        return <div className="surface-row">{children()}</div>;
      case 'Text':
        return <p className={text('tone') === 'muted' ? 'surface-muted' : ''}>{text('text')}</p>;
      case 'Metric':
        return (
          <div className="surface-metric">
            <span>{text('label')}</span>
            <strong>{text('value')}</strong>
            {text('detail') && <small>{text('detail')}</small>}
          </div>
        );
      case 'Badge':
        return <span className="surface-badge">{text('text')}</span>;
      case 'Input':
        return (
          <label className="surface-field">
            {text('label')}
            <input
              maxLength={2000}
              placeholder={text('placeholder')}
              value={currentValues[id] ?? ''}
              onChange={(e) => setValues((v) => ({ ...v, [id]: e.target.value }))}
            />
          </label>
        );
      case 'Choice':
        return (
          <fieldset className="surface-choice">
            <legend>{text('label')}</legend>
            {(Array.isArray(p.options) ? p.options : []).map((option) => (
              <button
                key={option}
                type="button"
                aria-pressed={currentValues[id] === option}
                onClick={() => setValues((v) => ({ ...v, [id]: option }))}
              >
                {option}
              </button>
            ))}
          </fieldset>
        );
      case 'Button':
        return (
          <button
            type="button"
            className="surface-action"
            disabled={busy || !text('prompt') || !resolvable(text('prompt'))}
            onClick={() => void submit(text('prompt'))}
          >
            {text('label') || '继续'}
            <ArrowUpRight size={15} />
          </button>
        );
    }
  }
  return (
    <div
      className={`agent-surface ${animate ? 'surface-live' : ''}`}
      aria-label="交互卡片"
      aria-busy={!complete}
    >
      <div className="surface-caption">
        <Sparkles size={12} />
        <span>{complete ? '为你整理' : '正在构建'}</span>
        {!complete && <i className="surface-pulse" />}
      </div>
      <SurfaceFrame>
        {spec ? element(spec.root) : !complete ? <div className="surface-slot" /> : null}
      </SurfaceFrame>
      {(parsed.error || (!spec && complete)) && (
        <p className="surface-error">
          <CircleAlert size={13} />
          部分内容未能展示，你可以继续提问。
        </p>
      )}
      {failure && (
        <p role="alert" className="surface-error">
          {failure}
        </p>
      )}
    </div>
  );
}
