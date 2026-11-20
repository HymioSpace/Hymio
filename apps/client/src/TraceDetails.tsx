import { useState } from 'react';
import {
  Bot,
  Check,
  ChevronRight,
  CircleAlert,
  Clock3,
  MessageSquare,
  Sparkles,
  Wrench,
} from 'lucide-react';
import { Button } from '@hymio/ui';
import { obj, str, list, type Span, type Trace } from '@hymio/protocol';
import { JsonView } from './JsonView';
import { orderedTraceEntries, type TimelineEntry } from './traceTimeline';

export const duration = (value: number | null | undefined) =>
  value == null || !Number.isFinite(value)
    ? '—'
    : value < 1000
      ? `${Math.round(value)} ms`
      : `${(value / 1000).toFixed(2)} s`;

function body(value: unknown) {
  if (typeof value !== 'string') return obj(value);
  try {
    return obj(JSON.parse(value));
  } catch {
    return { content: value };
  }
}

function eventBody(event: Span['events'][number]) {
  return body(event.attributes.body);
}

function messageText(value: unknown): string {
  if (typeof value === 'string') return value;
  return list(value)
    .map((part) => str(obj(part).text) || (obj(part).type === 'image_url' ? '[图片]' : ''))
    .filter(Boolean)
    .join('\n');
}

function contentText(value: unknown) {
  const text = messageText(value);
  if (text) return text;
  if (value == null) return '';
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function payload(span: Span, name: string) {
  return body(span.events.find((event) => event.name === name)?.attributes.body);
}

function kindOf(entry: TimelineEntry) {
  if (entry.name === 'gen_ai.request') return 'request';
  if (entry.name === 'gen_ai.response') return 'response';
  if (entry.name === 'oath.tool.request') return 'tool-request';
  if (entry.name === 'oath.tool.response') return 'tool-response';
  if (entry.name.startsWith('oath.input.')) return 'input';
  if (entry.name.startsWith('oath.stage.')) return 'stage';
  if (entry.name === 'span') return 'span';
  return 'event';
}

function kindLabel(kind: string) {
  return (
    {
      input: '用户事件',
      request: 'LLM 请求',
      response: 'LLM 响应',
      'tool-request': 'Tool 调用',
      'tool-response': 'Tool 结果',
      stage: '执行阶段',
      span: '执行步骤',
      event: '事件',
    }[kind] || '事件'
  );
}

function entryIcon(kind: string) {
  if (kind === 'request' || kind === 'response') return Bot;
  if (kind === 'tool-request' || kind === 'tool-response') return Wrench;
  if (kind === 'input') return MessageSquare;
  if (kind === 'stage') return Sparkles;
  return Clock3;
}

function entryTitle(entry: TimelineEntry) {
  const tool = str(entry.span.attributes['oath.tool.name']);
  if (entry.name === 'span' && tool) return `执行 ${tool}`;
  if (entry.name === 'gen_ai.request') {
    return `${str(entry.span.attributes['gen_ai.request.model']) || '模型'} 请求`;
  }
  if (entry.name === 'gen_ai.response') return '模型响应';
  if (entry.name === 'oath.tool.request') return `${tool || 'Tool'} 调用`;
  if (entry.name === 'oath.tool.response') return `${tool || 'Tool'} 结果`;
  if (entry.name.startsWith('oath.input.')) return `收到 ${entry.name.split('.').at(-1)} 输入`;
  if (entry.name.startsWith('oath.stage.')) return entry.name.replace('oath.stage.', '');
  return entry.name;
}

function entrySummary(entry: TimelineEntry) {
  if (entry.name === 'gen_ai.request') {
    const messages = list(payload(entry.span, 'gen_ai.request').messages);
    const lastUser = [...messages].reverse().find((message) => obj(message).role === 'user');
    return messageText(obj(lastUser).content).slice(0, 220) || `${messages.length} 条输入消息`;
  }
  if (entry.name === 'gen_ai.response') {
    const response = payload(entry.span, 'gen_ai.response');
    const content = str(response.content);
    const calls = list(response.tool_calls);
    return (
      content?.slice(0, 220) ||
      (calls.length ? `返回 ${calls.length} 个工具调用` : duration(entry.span.duration_ms))
    );
  }
  const value = entry.event ? eventBody(entry.event) : {};
  if (entry.name === 'oath.tool.request') {
    return (
      str(value.description) ||
      str(obj(value.arguments).description) ||
      `调用 ${str(entry.span.attributes['oath.tool.name']) || '工具'}`
    );
  }
  if (entry.name === 'oath.tool.response') {
    return contentText(value.content).slice(0, 220) || str(value.error) || '工具已返回结果';
  }
  if (entry.event) return str(value.content) || str(value.preview) || '查看事件详情';
  if (str(entry.span.attributes['oath.tool.name'])) {
    return `结果：${str(entry.span.attributes['oath.tool.outcome']) || entry.span.status}`;
  }
  return '执行步骤';
}

function MessageInspector({ messages }: { messages: unknown[] }) {
  return (
    <ol className="trace-sequence-messages">
      {messages.map((value, index) => {
        const message = obj(value);
        return (
          <li key={index}>
            <strong>{str(message.role) || 'message'}</strong>
            <p>
              {messageText(message.content) || `工具调用 ${list(message.tool_calls).length} 项`}
            </p>
            {!!list(message.tool_calls).length && <JsonView value={message.tool_calls} />}
          </li>
        );
      })}
    </ol>
  );
}

function TimelineCard({
  entry,
  index,
  start,
}: {
  entry: TimelineEntry;
  index: number;
  start: number;
}) {
  const kind = kindOf(entry);
  const Icon = entryIcon(kind);
  const request =
    entry.name === 'gen_ai.request' ? payload(entry.span, 'gen_ai.request') : undefined;
  const response =
    entry.name === 'gen_ai.response' ? payload(entry.span, 'gen_ai.response') : undefined;
  return (
    <article className={`trace-sequence-card trace-kind-${kind}`}>
      <span className="trace-sequence-index">{String(index + 1).padStart(2, '0')}</span>
      <span className="trace-sequence-rail" aria-hidden="true" />
      <div className="trace-sequence-body">
        <header>
          <span className="trace-sequence-kind">
            <Icon size={14} aria-hidden="true" />
            {kindLabel(kind)}
          </span>
          <time>+{duration(Math.max(0, (entry.at - start) / 1_000_000))}</time>
        </header>
        <strong>{entryTitle(entry)}</strong>
        <p>{entrySummary(entry)}</p>
        <details>
          <summary>
            <ChevronRight size={14} />
            查看 {kindLabel(kind)} 详情
          </summary>
          {request && <MessageInspector messages={list(request.messages)} />}
          {response && (
            <>
              <pre>{messageText(response.content) || '无正文'}</pre>
              {!!list(response.tool_calls).length && <JsonView value={response.tool_calls} />}
            </>
          )}
          {!request && !response && !!entry.event && <JsonView value={entry.event} />}
          <JsonView value={entry.span.attributes} />
        </details>
      </div>
    </article>
  );
}

function RawSpanTree({ span }: { span: Span }) {
  return (
    <details className="trace-raw-span">
      <summary>
        <span>{span.status === 'error' ? <CircleAlert size={13} /> : <Check size={13} />}</span>
        <strong>{span.name}</strong>
        <small>{duration(span.duration_ms)}</small>
      </summary>
      <JsonView value={span} />
    </details>
  );
}

export function TraceDetails({ trace, onBack }: { trace: Trace; onBack: () => void }) {
  const [rawOpen, setRawOpen] = useState(false);
  const entries = orderedTraceEntries(trace);
  const start = entries[0]?.at ?? 0;
  const models = entries.filter((entry) => entry.name === 'gen_ai.request').length;
  const toolCalls =
    entries.filter((entry) => entry.name === 'oath.tool.request').length ||
    trace.spans.filter((span) => str(span.attributes['oath.tool.name'])).length;
  return (
    <div className="trace-detail">
      <Button variant="quiet" onClick={onBack}>
        ← 全部执行
      </Button>
      <div className="trace-heading">
        <p className="eyebrow">EVENT-ORDERED TRACE</p>
        <code>{trace.trace_id}</code>
        <div className="trace-metrics">
          <span>
            <strong>{duration(trace.duration_ms)}</strong>总耗时
          </span>
          <span>
            <strong>{models}</strong>LLM 请求
          </span>
          <span>
            <strong>{toolCalls}</strong>Tool 调用
          </span>
          <span>
            <strong>{entries.length}</strong>事件
          </span>
        </div>
      </div>
      <p className="trace-sequence-caption">
        按真实发生时间排序。先看用户输入、模型请求、工具调用和工具结果。
      </p>
      <ol className="trace-sequence">
        {entries.map((entry, index) => (
          <li key={entry.id}>
            <TimelineCard entry={entry} index={index} start={start} />
          </li>
        ))}
      </ol>
      <section className="trace-raw">
        <button onClick={() => setRawOpen(!rawOpen)} aria-expanded={rawOpen}>
          <ChevronRight size={15} className={rawOpen ? 'rotated' : ''} />
          原始 Span 树 · {trace.spans.length}
        </button>
        {rawOpen && (
          <div>
            {trace.spans.map((span) => (
              <RawSpanTree key={span.span_id} span={span} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
