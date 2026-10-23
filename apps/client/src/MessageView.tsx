import {
  Children,
  createContext,
  isValidElement,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { Check, Copy, BrainCircuit, ChevronRight } from 'lucide-react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Approval, Message, ToolActivity } from '@hymio/client';
import { ToolCalls } from './ToolActivityGroup';
import { IconButton } from '@hymio/ui';
import { MessageImage } from './MessageImage';
import { ProgressiveContent, useBufferedText, MotionText } from './ProgressiveContent';
import type { LoginState } from './useLogin';

const ImageLogin = createContext<LoginState | null>(null);
function MarkdownImage({ src, alt }: { src?: string; alt?: string }) {
  const login = useContext(ImageLogin);
  return login ? <MessageImage src={src} alt={alt} login={login} /> : null;
}
function UserMessageContent({ content, login }: { content: string; login: LoginState }) {
  const images: string[] = [];
  const text = content
    .replace(/!\[[^\]]*\]\((\/attachments\/[a-f0-9]{32})\)/g, (_, source: string) => {
      images.push(source);
      return '';
    })
    .trim();
  return (
    <ImageLogin.Provider value={login}>
      {images.length > 0 && (
        <div className="sent-attachment-tray">
          {images.map((source, index) => (
            <MessageImage key={source + index} src={source} alt="已发送的图片" login={login} />
          ))}
        </div>
      )}
      {text && (
        <Markdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
          {text}
        </Markdown>
      )}
    </ImageLogin.Provider>
  );
}
function AttachmentLink({ children, href, ...props }: React.ComponentProps<'a'>) {
  const login = useContext(ImageLogin);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const local = /^\/attachments\/[a-f0-9]{32}$/.test(href || '');
  async function download() {
    const session = login?.session;
    if (!session || !href || busy) return;
    setBusy(true);
    setError('');
    try {
      const response = await fetch(session.backend + href, {
        headers: { Authorization: 'Bearer ' + session.access_token },
        redirect: 'error',
        signal: AbortSignal.timeout(30000),
      });
      if (!response.ok) throw new Error('文件暂时无法下载');
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = typeof children === 'string' ? children : 'attachment';
      anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch {
      setError('文件下载失败，请重试');
    } finally {
      setBusy(false);
    }
  }
  if (local)
    return (
      <span>
        <button className="attachment-link" disabled={busy} onClick={() => void download()}>
          {busy ? '正在下载…' : children}
        </button>
        {error && <span role="alert">{error}</span>}
      </span>
    );
  return (
    <a {...props} href={href} target="_blank" rel="noreferrer">
      {children}
    </a>
  );
}
function useCopy(text: string) {
  const [state, setState] = useState('');
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);
  async function copy() {
    clearTimeout(timer.current);
    try {
      await navigator.clipboard.writeText(text);
      setState('已复制');
    } catch {
      setState('复制失败，请选择文字复制');
    }
    timer.current = setTimeout(() => setState(''), 2200);
  }
  return { state, copy };
}
function MessageCode({ children }: { children?: ReactNode }) {
  const child = Children.toArray(children)[0];
  const code = isValidElement<{ children?: ReactNode; className?: string }>(child)
    ? child
    : undefined;
  const text = String(code?.props.children ?? '').replace(/\n$/, '');
  const language = code?.props.className?.replace(/^language-/, '') || '代码';
  const { state, copy } = useCopy(text);
  return (
    <div className="message-code">
      <div className="code-toolbar">
        <span>{language}</span>
        <IconButton label={state || '复制代码'} onClick={() => void copy()}>
          {state === '已复制' ? <Check size={15} /> : <Copy size={15} />}
        </IconButton>
      </div>
      <pre tabIndex={0} aria-label={`${language}代码`}>
        {children}
      </pre>
      <span className="sr-only" role="status">
        {state}
      </span>
    </div>
  );
}
const markdownComponents = {
  p: ({ children }: { children?: ReactNode }) => (
    <p>
      <MotionText>{children}</MotionText>
    </p>
  ),
  li: ({ children }: { children?: ReactNode }) => (
    <li>
      <MotionText>{children}</MotionText>
    </li>
  ),
  h1: ({ children }: { children?: ReactNode }) => (
    <h1>
      <MotionText>{children}</MotionText>
    </h1>
  ),
  h2: ({ children }: { children?: ReactNode }) => (
    <h2>
      <MotionText>{children}</MotionText>
    </h2>
  ),
  h3: ({ children }: { children?: ReactNode }) => (
    <h3>
      <MotionText>{children}</MotionText>
    </h3>
  ),
  img: MarkdownImage,
  pre: MessageCode,
  a: AttachmentLink,
};

export function MessageMarkdown({ content, login }: { content: string; login: LoginState }) {
  return (
    <ImageLogin.Provider value={login}>
      <Markdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
        {content}
      </Markdown>
    </ImageLogin.Provider>
  );
}

export function MessageView({
  activity = false,
  message,
  tools,
  login,
  approvals,
  onAction,
}: {
  activity?: boolean;
  message: Message;
  tools: ToolActivity[];
  login: LoginState;
  approvals?: Approval[];
  onAction: (text: string) => Promise<void>;
}) {
  const { state: copied, copy } = useCopy(message.content);
  const reasoning = useBufferedText(message.reasoning || '', !!message.streaming);
  const reasoningOnly =
    message.role === 'assistant' &&
    !!message.reasoning &&
    !message.content &&
    !message.calls?.length;
  return (
    <article
      className={`message message-${message.role}${reasoningOnly ? ' message-reasoning-only' : ''}`}
      data-testid={`message-${message.role}`}
    >
      <div className="message-body">
        {message.reasoning && (
          <details className="reasoning-panel">
            <summary>
              <BrainCircuit size={13} />
              <span>{message.thinking ? '正在思考…' : '思考过程'}</span>
              <ChevronRight size={12} className="reasoning-chevron" />
            </summary>
            <div>{reasoning.text}</div>
          </details>
        )}
        <div className={`message-bubble ${message.streaming ? 'streaming' : ''}`}>
          {message.role === 'user' ? (
            <UserMessageContent content={message.content} login={login} />
          ) : (
            <ImageLogin.Provider value={login}>
              <ProgressiveContent
                key={message.attempt ?? 0}
                content={message.content}
                streaming={!!message.streaming}
                onAction={onAction}
                render={(text) => (
                  <Markdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                    {text}
                  </Markdown>
                )}
              />
            </ImageLogin.Provider>
          )}
          {!!message.calls?.length && (
            <ToolCalls message={message} tools={tools} approvals={approvals} />
          )}
          {message.role === 'user' && message.reactions?.assistant && (
            <span
              className="bubble-reaction"
              aria-label={`Hymio 的回应：${message.reactions.assistant}`}
            >
              {message.reactions.assistant}
            </span>
          )}
        </div>
        {!activity && (
          <div className="message-meta">
            <span>
              {message.role === 'assistant' ? 'Hymio' : '你'} ·{' '}
              {new Date(message.time).toLocaleTimeString('zh-CN', {
                hour: '2-digit',
                minute: '2-digit',
                hour12: false,
              })}
            </span>
            {message.delivery && (
              <span role="status">
                {
                  { queued: '正在发送…', accepted: '已送达', failed: '发送失败，可重试' }[
                    message.delivery
                  ]
                }
              </span>
            )}
            {message.role === 'assistant' && message.content && !message.streaming && (
              <IconButton
                className="copy-message"
                onClick={() => void copy()}
                label={copied || '复制回复'}
              >
                {copied === '已复制' ? <Check size={13} /> : <Copy size={13} />}
              </IconButton>
            )}
          </div>
        )}
        <span className="sr-only" role="status">
          {copied}
        </span>
      </div>
    </article>
  );
}
