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
import { Check, Copy } from 'lucide-react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Approval, Message, ToolActivity } from '@hymio/client';
import { ToolCalls } from './ToolActivityGroup';
import { Companion, IconButton } from '@hymio/ui';
import { MessageImage } from './MessageImage';
import type { LoginState } from './useLogin';

const ImageLogin = createContext<LoginState | null>(null);
function MarkdownImage({ src, alt }: { src?: string; alt?: string }) {
  const login = useContext(ImageLogin);
  return login ? <MessageImage src={src} alt={alt} login={login} /> : null;
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
  img: MarkdownImage,
  pre: MessageCode,
  a: ({ children, ...props }: React.ComponentProps<'a'>) => (
    <a {...props} target="_blank" rel="noreferrer">
      {children}
    </a>
  ),
};

export function MessageView({
  message,
  tools,
  login,
  approvals,
}: {
  message: Message;
  tools: ToolActivity[];
  login: LoginState;
  approvals?: Approval[];
}) {
  const { state: copied, copy } = useCopy(message.content);
  return (
    <article className={`message message-${message.role}`} data-testid={`message-${message.role}`}>
      {message.role === 'assistant' && (
        <div className="message-avatar">
          <Companion compact mood={message.streaming ? 'replying' : 'idle'} />
        </div>
      )}
      <div className="message-body">
        <div className={`message-bubble ${message.streaming ? 'streaming' : ''}`}>
          {message.role === 'user' ? (
            <p>{message.content}</p>
          ) : (
            <ImageLogin.Provider value={login}>
              <Markdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                {message.content || (message.streaming ? '…' : '')}
              </Markdown>
            </ImageLogin.Provider>
          )}
          {!!message.calls?.length && (
            <ToolCalls message={message} tools={tools} approvals={approvals} />
          )}
        </div>
        <div className="message-meta">
          <span>
            {message.role === 'assistant' ? 'Hymio' : '你'} ·{' '}
            {new Date(message.time).toLocaleTimeString('zh-CN', {
              hour: '2-digit',
              minute: '2-digit',
              hour12: false,
            })}
          </span>
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
        <span className="sr-only" role="status">
          {copied}
        </span>
      </div>
    </article>
  );
}
