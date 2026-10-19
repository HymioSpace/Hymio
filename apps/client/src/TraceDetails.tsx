import { useState } from 'react';
import { ChevronRight, Check, CircleAlert, Clock3 } from 'lucide-react';
import { Button } from '@hymio/ui';
import { type Span, type Trace } from '@hymio/protocol';
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
          <small>{model ? 'MODEL' : 'STEP'}</small>
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
      {model && (
        <div className="model-metrics">
          <span>首字 {duration(number(span.attributes['oath.llm.ttft_ms']))}</span>
          <span>每 token {duration(number(span.attributes['oath.llm.tpot_ms']))}</span>
        </div>
      )}
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
            <strong>{trace.spans.length}</strong>Spans
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
