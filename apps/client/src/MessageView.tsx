import { useState } from 'react';
import { Check, Copy, Terminal } from 'lucide-react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Message } from '@hymio/client';
import { Companion } from '@hymio/ui';

export function MessageView({ message }: { message: Message }) {
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
            <Markdown
              remarkPlugins={[remarkGfm]}
              components={{
                a: ({ children, ...props }) => (
                  <a {...props} target="_blank" rel="noreferrer">
                    {children}
                  </a>
                ),
              }}
            >
              {message.content || (message.streaming ? '…' : '')}
            </Markdown>
          )}
          {!!message.calls?.length && (
            <div className="tool-pills">
              {message.calls.map((call, i) => (
                <span key={i}>
                  <Terminal size={12} />
                  {String(call.name)}
                </span>
              ))}
            </div>
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
