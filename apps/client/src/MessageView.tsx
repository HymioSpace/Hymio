import { useState } from 'react';
import { Check, Copy, Terminal } from 'lucide-react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Message, ToolActivity } from '@hymio/client';
import { obj, str } from '@hymio/protocol';
import { JsonView } from './JsonView';
import { Companion } from '@hymio/ui';

export function MessageView({ message, tools }: { message: Message; tools: ToolActivity[] }) {
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
              {message.calls.map((call, i) => {
                const args = obj(call.arguments);
                const result = tools.find((t) => t.id === `${message.stepId}-${i}`);
                const title =
                  call.name === 'skill'
                    ? args.action === 'search'
                      ? '查找技能'
                      : args.action === 'read'
                        ? '读取技能'
                        : '技能工具'
                    : call.name === 'bash'
                      ? '执行命令'
                      : String(call.name);
                const hint = call.name === 'skill' ? str(args.query) || str(args.name) : '';
                return (
                  <details key={i} className="tool-call-detail">
                    <summary>
                      <Terminal size={14} />
                      <strong>{title}</strong>
                      {hint && <span className="tool-call-hint">{hint}</span>}
                      <span>
                        {result?.outcome === 'succeeded'
                          ? '已完成'
                          : result?.outcome === 'running'
                            ? '处理中'
                            : result?.outcome || '已请求'}
                      </span>
                    </summary>
                    <div className="tool-call-content">
                      <p>工具：{String(call.name)}</p>
                      <JsonView value={args} />
                      {result?.result && (
                        <>
                          <p>返回结果</p>
                          <pre>{result.result}</pre>
                        </>
                      )}
                    </div>
                  </details>
                );
              })}
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
