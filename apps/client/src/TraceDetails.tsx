import { useState } from 'react';
import { ChevronRight, Check, CircleAlert, Clock3 } from 'lucide-react';
import { Button } from '@hymio/ui';
import { obj, str, list, type Span, type Trace } from '@hymio/protocol';
import { JsonView } from './JsonView';
export const duration = (value: number | null | undefined) =>
  value == null || !Number.isFinite(value)
    ? '—'
    : value < 1000
      ? `${Math.round(value)} ms`
      : `${(value / 1000).toFixed(2)} s`;
function number(value: unknown) {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}
function payload(span: Span, name: string) {
  const raw = span.events.find((e) => e.name === name)?.attributes.body;
  if (typeof raw !== 'string') return obj(raw);
  try {
    return obj(JSON.parse(raw));
  } catch {
    return {};
  }
}
function messageText(value: unknown): string {
  if (typeof value === 'string') return value;
  return list(value)
    .map((part) => str(obj(part).text) || (obj(part).type === 'image_url' ? '[图片]' : ''))
    .filter(Boolean)
    .join('\n');
}
function MessageInspector({ messages }: { messages: unknown[] }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <section className="trace-messages">
      <button
        className="trace-message-toggle"
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
      >
        <ChevronRight size={14} className={expanded ? 'rotated' : ''} />
        输入消息 · {messages.length}
      </button>
      {expanded && (
        <ol>
          {messages.map((value, i) => {
            const m = obj(value);
            return (
              <li key={i}>
                <details>
                  <summary>
                    <code>{str(m.role) || 'message'}</code>
                    <span>
                      {messageText(m.content).slice(0, 100) ||
                        `工具调用 ${list(m.tool_calls).length} 项`}
                    </span>
                  </summary>
                  <pre>{messageText(m.content)}</pre>
                  {!!list(m.tool_calls).length && <JsonView value={m.tool_calls} />}
                </details>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
function ModelReport({ span }: { span: Span }) {
  const request = payload(span, 'gen_ai.request');
  const response = payload(span, 'gen_ai.response');
  const messages = list(request.messages);
  const lastUser = [...messages].reverse().find((m) => obj(m).role === 'user');
  const usage = obj(response.usage);
  const input = number(span.attributes['gen_ai.usage.input_tokens']) ?? number(usage.prompt_tokens);
  const output =
    number(span.attributes['gen_ai.usage.output_tokens']) ?? number(usage.completion_tokens);
  const cached =
    number(span.attributes['gen_ai.usage.cache_read.input_tokens']) ??
    number(obj(usage.prompt_tokens_details).cached_tokens);
  return (
    <section className="trace-model-report">
      <dl className="trace-performance">
        <div>
          <dt>TTFT · 首包</dt>
          <dd>{duration(number(span.attributes['oath.llm.ttft_ms']))}</dd>
        </div>
        <div>
          <dt>首段正文</dt>
          <dd>{duration(number(span.attributes['oath.llm.first_content_ms']))}</dd>
        </div>
        <div>
          <dt>模型总耗时</dt>
          <dd>{duration(span.duration_ms)}</dd>
        </div>
        <div>
          <dt>输入 / 输出 token</dt>
          <dd>
            {input ?? '—'} / {output ?? '—'}
          </dd>
        </div>
        <div>
          <dt>缓存读取</dt>
          <dd>
            {cached == null
              ? '未上报'
              : `${cached} token${input ? ` · ${Math.round((cached / input) * 100)}%` : ''}`}
          </dd>
        </div>
        <div>
          <dt>输入消息 / 工具</dt>
          <dd>
            {messages.length} / {list(request.tools).length}
          </dd>
        </div>
      </dl>
      <div className="trace-exchange">
        <section>
          <small>本轮输入</small>
          <p>{messageText(obj(lastUser).content) || '本轮没有用户消息'}</p>
        </section>
        <section>
          <small>助手回复</small>
          <p>
            {str(response.content) ||
              (list(response.tool_calls).length
                ? `发起 ${list(response.tool_calls).length} 项工具调用`
                : span.duration_ms == null
                  ? '正在生成…'
                  : '无正文')}
          </p>
        </section>
      </div>
      <MessageInspector messages={messages} />
      {!!list(response.tool_calls).length && (
        <details>
          <summary>输出工具调用 · {list(response.tool_calls).length}</summary>
          <JsonView value={response.tool_calls} />
        </details>
      )}
      <p className="panel-caption">
        TTFT 包含思考首增量；首段正文是用户可读回复开始的时间。缺失指标表示未上报。
      </p>
    </section>
  );
}
function TraceSpan({ span, total, depth }: { span: Span; total: number | null; depth: number }) {
  const [open, setOpen] = useState(false);
  const model = span.attributes['gen_ai.operation.name'] === 'chat' || span.name.startsWith('chat');
  const failed = span.status === 'error';
  const pending = span.duration_ms == null;
  const inputs = span.events.filter((e) => e.name.startsWith('oath.input.'));
  const request = span.events.filter((e) => e.name === 'gen_ai.request');
  const response = span.events.filter((e) => e.name === 'gen_ai.response');
  return (
    <article
      className={`trace-span ${failed ? 'trace-span-error' : ''}`}
      style={{ marginLeft: depth * 12 }}
    >
      <button className="trace-span-heading" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className="trace-node">
          {failed ? (
            <CircleAlert size={14} />
          ) : pending ? (
            <Clock3 size={14} />
          ) : (
            <Check size={14} />
          )}
        </span>
        <span className="trace-span-title">
          <small>{model ? '模型调用' : '执行步骤'}</small>
          <strong>{span.name}</strong>
        </span>
        <span className="trace-span-duration">{duration(span.duration_ms)}</span>
        <ChevronRight size={14} className={open ? 'rotated' : ''} />
      </button>
      <div
        className="trace-duration-track"
        title="此 Span 耗时占 Trace 总耗时的比例；不是开始时间轴"
      >
        <i
          style={{
            width: `${total && span.duration_ms != null ? Math.min(100, Math.max(0, (span.duration_ms / total) * 100)) : 0}%`,
          }}
        />
      </div>
      {model && <ModelReport span={span} />}
      {open && (
        <div className="trace-span-detail">
          {inputs.length > 0 && (
            <details>
              <summary>输入事件 · {inputs.length}</summary>
              <JsonView value={inputs} />
            </details>
          )}
          {request.length > 0 && (
            <details>
              <summary>模型原始请求</summary>
              <JsonView value={request} />
            </details>
          )}
          {response.length > 0 && (
            <details>
              <summary>模型原始响应</summary>
              <JsonView value={response} />
            </details>
          )}
          <details>
            <summary>Span 属性、阶段与关联</summary>
            <JsonView value={span} />
          </details>
        </div>
      )}
    </article>
  );
}
export function TraceDetails({ trace, onBack }: { trace: Trace; onBack: () => void }) {
  const spans = new Map(trace.spans.map((s) => [s.span_id, s]));
  function depth(s: Span) {
    let n = 0;
    let parent = s.parent_span_id;
    const seen = new Set([s.span_id]);
    while (parent && spans.has(parent) && !seen.has(parent) && n < 4) {
      seen.add(parent);
      n++;
      parent = spans.get(parent)!.parent_span_id;
    }
    return n;
  }
  const models = trace.spans.filter(
    (s) => s.attributes['gen_ai.operation.name'] === 'chat' || s.name.startsWith('chat'),
  );
  return (
    <div className="trace-detail">
      <Button variant="quiet" onClick={onBack}>
        ← 全部执行
      </Button>
      <div className="trace-heading">
        <p className="eyebrow">EXECUTION TRACE</p>
        <code>{trace.trace_id}</code>
        <div className="trace-metrics">
          <span>
            <strong>{duration(trace.duration_ms)}</strong>累计耗时
          </span>
          <span>
            <strong>{models.length}</strong>模型调用
          </span>
          <span>
            <strong>
              {models.reduce(
                (sum, s) => sum + list(payload(s, 'gen_ai.request').messages).length,
                0,
              )}
            </strong>
            输入消息总数
          </span>
        </div>
      </div>
      <div className="trace-spans">
        {trace.spans.map((span) => (
          <TraceSpan key={span.span_id} span={span} total={trace.duration_ms} depth={depth(span)} />
        ))}
      </div>
      <p className="panel-caption">
        耗时条为占比，嵌套 Span 不可相加。展开可查看真实输入、模型报文和阶段事件。
      </p>
    </div>
  );
}
