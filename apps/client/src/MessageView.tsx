import { createContext, useContext, useState } from 'react';
import { Check, Copy } from 'lucide-react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Message, ToolActivity } from '@hymio/client';
import { ToolCalls } from './ToolActivityGroup';
import { Companion } from '@hymio/ui';
import { MessageImage } from './MessageImage';
import type { LoginState } from './useLogin';

const ImageLogin = createContext<LoginState | null>(null);
function MarkdownImage({ src, alt }: { src?: string; alt?: string }) {
  const login = useContext(ImageLogin);
  return login ? <MessageImage src={src} alt={alt} login={login} /> : null;
}
const markdownComponents = {
  img: MarkdownImage,
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
}: {
  message: Message;
  tools: ToolActivity[];
  login: LoginState;
}) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }
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
          {!!message.calls?.length && <ToolCalls message={message} tools={tools} />}
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
            <button
              className="icon-button copy-message"
              onClick={() => void copy()}
              aria-label="复制回复"
            >
              {copied ? <Check size={13} /> : <Copy size={13} />}
            </button>
          )}
        </div>
      </div>
    </article>
  );
}
