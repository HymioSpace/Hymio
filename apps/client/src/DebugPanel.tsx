import { useEffect, useState } from 'react';
import {
  X,
  RefreshCw,
  ArrowRight,
  CircleCheck,
  TriangleAlert,
  Download,
  ChevronRight,
  LoaderCircle,
  Radio,
} from 'lucide-react';
import { type ClientState } from '@hymio/client';
import {
  obj,
  str,
  type Connection,
  type Trace,
  type TraceSummary,
  type Span,
} from '@hymio/protocol';
import { bizGet } from './platform';
import { JsonView as Json } from './JsonView';
const ms = (value: number | null | undefined) =>
  value == null ? '—' : value < 1000 ? `${Math.round(value)} ms` : `${(value / 1000).toFixed(2)} s`;
function SpanView({ span, total }: { span: Span; total: number }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="span-item">
      <button className="span-row" onClick={() => setOpen(!open)}>
        <ChevronRight size={14} className={open ? 'rotated' : ''} />
        <span className={`span-dot ${span.status}`} />
        <strong>{span.name}</strong>
        <small>{ms(span.duration_ms)}</small>
      </button>
      <div className="span-track">
        <i
          style={{
            width: `${Math.min(100, Math.max(2, ((span.duration_ms ?? 0) / Math.max(total, 1)) * 100))}%`,
          }}
        />
      </div>
      {open && <Json value={span} />}
    </div>
  );
}
export function DebugPanel({
  state,
  connection,
  onClose,
  onStatus,
  onCancel,
  onRetry,
}: {
  state: ClientState;
  connection: Connection;
  onClose: () => void;
  onStatus: () => void;
  onCancel: () => void;
  onRetry: () => void;
}) {
  const [tab, setTab] = useState('events'),
    [filter, setFilter] = useState(''),
    [traces, setTraces] = useState<TraceSummary[]>([]),
    [trace, setTrace] = useState<Trace>(),
    [error, setError] = useState(''),
    [loading, setLoading] = useState(false),
    [biz, setBiz] = useState<'idle' | 'alive' | 'failed'>('idle');
  async function refresh() {
    setLoading(true);
    setError('');
    onStatus();
    try {
      await bizGet(connection.bizUrl, '/heartbeat', connection.credential, connection.userId);
      setBiz('alive');
      if (tab === 'traces') {
        const data = await bizGet<{ trace_ids: TraceSummary[] }>(
          connection.bizUrl,
          '/list_traces?limit=30',
          connection.credential,
          connection.userId,
        );
        if (!Array.isArray(data.trace_ids)) throw new Error('Biz Trace 列表格式不兼容');
        setTraces(data.trace_ids);
      }
    } catch (e) {
      setBiz('failed');
      setError(
        `${String(e instanceof Error ? e.message : e)}。网页版跨域时，请配置同源代理或服务端 CORS。`,
      );
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void refresh();
  }, [tab]);
  async function select(id: string) {
    setLoading(true);
    setError('');
    try {
      const data = await bizGet<Trace>(
        connection.bizUrl,
        `/query_trace?trace_id=${encodeURIComponent(id)}`,
        connection.credential,
        connection.userId,
      );
      if (!Array.isArray(data.spans)) throw new Error('Biz Trace 详情格式不兼容');
      setTrace(data);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }
  function exportEvents() {
    const blob = new Blob([JSON.stringify(state.events, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'hymio-events.json';
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const steps = obj(state.runtime?.steps),
    calls = obj(state.runtime?.calls);
  return (
    <aside className="debug-panel" aria-label="工作观察">
      <div className="panel-head">
        <div>
          <span className="eyebrow">BEHIND THE SCENES</span>
          <h2>工作观察</h2>
        </div>
        <button className="icon-button" aria-label="关闭工作观察" onClick={onClose}>
          <X size={19} />
        </button>
      </div>
      <div className="flow-strip">
        <span className={state.phase === 'connected' ? 'live' : ''}>
          <Radio size={15} />
          客户端
        </span>
        <ArrowRight size={13} />
        <span className={state.phase === 'connected' ? 'live' : ''}>Oath</span>
        <ArrowRight size={13} />
        <span>工具</span>
      </div>
      <div className="panel-tabs">
        {[
          ['events', '事件'],
          ['traces', 'Trace'],
          ['status', '状态'],
        ].map(([value, label]) => (
          <button
            key={value}
            className={tab === value ? 'selected' : ''}
            onClick={() => setTab(value)}
          >
            {label}
          </button>
        ))}
        <button
          className="icon-button refresh"
          aria-label="刷新调试数据"
          onClick={() => void refresh()}
        >
          {loading ? <LoaderCircle size={15} className="spin" /> : <RefreshCw size={15} />}
        </button>
      </div>
      <div className="panel-content">
        {error && (
          <div className="debug-error" role="alert">
            <TriangleAlert size={15} />
            <p>{error}</p>
          </div>
        )}
        {tab === 'events' && (
          <>
            <div className="event-tools">
              <input
                aria-label="筛选事件"
                placeholder="筛选事件类型…"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
              />
              <button
                className="icon-button"
                aria-label="导出当前用户事件（包含对话内容）"
                title="导出包含对话内容的事件 JSON"
                onClick={exportEvents}
              >
                <Download size={16} />
              </button>
            </div>
            <p className="panel-caption">按服务端 event_seq 排序 · {state.events.length} 条</p>
            <div className="event-list">
              {[...state.events]
                .reverse()
                .filter((e) => e.event_type.includes(filter))
                .slice(0, 200)
                .map((e) => (
                  <details key={e.event_seq} className="event-row">
                    <summary>
                      <span className="event-seq">#{e.event_seq}</span>
                      <span>{e.event_type}</span>
                      <small>
                        {new Date(e.occur_dt).toLocaleTimeString('zh-CN', { hour12: false })}
                      </small>
                    </summary>
                    <Json value={e} />
                  </details>
                ))}
              {!state.events.length && (
                <div className="panel-empty">对话开始后，实际事件会出现在这里。</div>
              )}
            </div>
          </>
        )}
        {tab === 'traces' && (
          <>
            {trace ? (
              <>
                <button className="text-button trace-back" onClick={() => setTrace(undefined)}>
                  ← 全部 Trace
                </button>
                <div className="trace-heading">
                  <span className="eyebrow">TRACE</span>
                  <code>{trace.trace_id}</code>
                  <div className="trace-metrics">
                    <span>
                      <strong>{ms(trace.duration_ms)}</strong>总耗时
                    </span>
                    <span>
                      <strong>{trace.spans.length}</strong>Spans
                    </span>
                  </div>
                </div>
                {trace.spans.map((span) => (
                  <SpanView key={span.span_id} span={span} total={trace.duration_ms ?? 0} />
                ))}
                <p className="panel-caption">
                  展开 Span 查看原始模型输入、输出、性能属性与因果 links。
                </p>
              </>
            ) : (
              <>
                <p className="panel-caption">当前用户的实际执行记录</p>
                {traces.map((t) => (
                  <button
                    className="trace-card"
                    key={t.trace_id}
                    onClick={() => void select(t.trace_id)}
                  >
                    <div>
                      <code>{t.trace_id.slice(0, 12)}…</code>
                      <ChevronRight size={15} />
                    </div>
                    <p>
                      {t.step_count} steps<span>{ms(t.duration_ms)}</span>
                    </p>
                  </button>
                ))}
                {!traces.length && !loading && (
                  <div className="panel-empty">还没有 Trace。发送一条消息后刷新。</div>
                )}
              </>
            )}
          </>
        )}
        {tab === 'status' && (
          <>
            <div className="health-card">
              <h3>连接与交付</h3>
              <p>
                <span>WebSocket</span>
                <b>{state.phase === 'connected' ? '已连接' : state.phase}</b>
              </p>
              <p>
                <span>Biz HTTP</span>
                <b>
                  {biz === 'alive' ? (
                    <>
                      <CircleCheck size={13} />
                      在线
                    </>
                  ) : biz === 'failed' ? (
                    '不可达'
                  ) : (
                    '未检查'
                  )}
                </b>
              </p>
              <p>
                <span>用户</span>
                <code>{state.userId || '未认证'}</code>
              </p>
              <p>
                <span>最近事件</span>
                <code>#{state.events.at(-1)?.event_seq ?? 0}</code>
              </p>
              <p>
                <span>未确认命令</span>
                <b>{state.pending.length}</b>
              </p>
              <p>
                <span>WS 往返</span>
                <b>{ms(state.latency)}</b>
              </p>
            </div>
            <div className="health-card">
              <h3>执行概况</h3>
              <p>
                <span>Steps</span>
                <b>{Object.keys(steps).length}</b>
              </p>
              <p>
                <span>工具调用</span>
                <b>{Object.keys(calls).length}</b>
              </p>
              <p>
                <span>当前 Run</span>
                <code>{str(obj(state.runtime?.meta).run_id).slice(0, 12) || '—'}</code>
              </p>
              <div className="runtime-controls">
                <button
                  className="secondary-button"
                  disabled={state.phase !== 'connected'}
                  onClick={onRetry}
                >
                  重试失败步骤
                </button>
                <button
                  className="secondary-button"
                  disabled={state.phase !== 'connected'}
                  onClick={onCancel}
                >
                  停止当前任务
                </button>
              </div>
            </div>
            <details className="state-detail">
              <summary>运行状态原始数据</summary>
              <Json value={state.runtime ?? {}} />
            </details>
            <p className="panel-caption">
              仅观测 WS、Biz 与 Oath 返回的用户状态。内部服务健康由部署平台管理。
            </p>
          </>
        )}
      </div>
    </aside>
  );
}
