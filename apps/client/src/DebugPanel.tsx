import { useEffect, useMemo, useRef, useState } from 'react';
import {
  X,
  RefreshCw,
  CircleCheck,
  TriangleAlert,
  Download,
  ChevronRight,
  LoaderCircle,
  Radio,
} from 'lucide-react';
import { type ClientState } from '@hymio/client';
import { obj, str, type Connection, type Trace, type TraceSummary } from '@hymio/protocol';
import { conversation } from '@hymio/client';
import { Button, IconButton, StatusBadge } from '@hymio/ui';
import { TraceDetails, duration as ms } from './TraceDetails';
import { bizGet } from './platform';
import { JsonView as Json } from './JsonView';
export function DebugPanel({
  state,
  modal,
  connection,
  onClose,
  onStatus,
  onCancel,
  onRetry,
}: {
  state: ClientState;
  modal: boolean;
  connection: Connection;
  onClose: () => void;
  onStatus: () => void;
  onCancel: () => void;
  onRetry: () => void;
}) {
  const [tab, setTab] = useState('traces'),
    [filter, setFilter] = useState(''),
    [traces, setTraces] = useState<TraceSummary[]>([]),
    [trace, setTrace] = useState<Trace>(),
    [error, setError] = useState(''),
    [loading, setLoading] = useState(false),
    [biz, setBiz] = useState<'idle' | 'alive' | 'failed'>('idle');
  const panel = useRef<HTMLElement>(null);
  useEffect(() => {
    const previous = document.activeElement;
    panel.current?.querySelector<HTMLButtonElement>('button')?.focus();
    return () => {
      if (previous instanceof HTMLElement && previous.isConnected) previous.focus();
    };
  }, []);
  const generation = useRef(0);
  const projection = useMemo(() => conversation(state.events), [state.events]);
  const [updated, setUpdated] = useState('');
  async function refresh() {
    const current = ++generation.current;
    setLoading(true);
    setError('');
    onStatus();
    const [health, records] = await Promise.allSettled([
      bizGet(connection.bizUrl, '/heartbeat', connection.credential, connection.userId),
      tab === 'traces'
        ? bizGet<{ trace_ids: TraceSummary[] }>(
            connection.bizUrl,
            '/list_traces?limit=30',
            connection.credential,
            connection.userId,
          )
        : Promise.resolve(undefined),
    ]);
    if (current !== generation.current) return;
    setBiz(health.status === 'fulfilled' ? 'alive' : 'failed');
    const errors: string[] = [];
    if (health.status === 'rejected') errors.push('业务接口暂不可达，请检查连接后重试。');
    if (records.status === 'rejected') errors.push('执行记录读取失败，请重试。');
    else if (records.value) {
      if (Array.isArray(records.value.trace_ids)) setTraces(records.value.trace_ids);
      else errors.push('执行记录格式不兼容。');
    }
    setError(errors.join(' '));
    setLoading(false);
    setUpdated(
      new Date().toLocaleTimeString('zh-CN', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
      }),
    );
  }
  useEffect(() => {
    void refresh();
    return () => {
      generation.current++;
    };
  }, [tab]);
  async function select(id: string) {
    const current = ++generation.current;
    setLoading(true);
    setError('');
    try {
      const data = await bizGet<Trace>(
        connection.bizUrl,
        `/query_trace?trace_id=${encodeURIComponent(id)}`,
        connection.credential,
        connection.userId,
      );
      if (current !== generation.current) return;
      if (!Array.isArray(data.spans)) throw new Error('执行详情格式不兼容');
      setTrace(data);
    } catch (e) {
      if (current === generation.current) setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (current === generation.current) setLoading(false);
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
    <aside
      ref={panel}
      id="work-observer"
      className="debug-panel"
      aria-label="工作观察"
      role={modal ? 'dialog' : undefined}
      aria-modal={modal || undefined}
      onKeyDown={(e) => {
        if (!modal || e.key !== 'Tab') return;
        const items = Array.from(
          panel.current?.querySelectorAll<HTMLElement>(
            'button:not(:disabled), input, summary, a[href], [tabindex="0"]',
          ) ?? [],
        ).filter((el) => el.getClientRects().length);
        const first = items[0],
          last = items.at(-1);
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }}
    >
      <div className="panel-head">
        <div>
          <span className="eyebrow">BEHIND THE SCENES</span>
          <h2>工作观察</h2>
        </div>
        <IconButton label="关闭工作观察" onClick={onClose}>
          <X size={19} />
        </IconButton>
      </div>
      <div className="execution-flow" aria-label="可观测链路">
        <div>
          <Radio size={17} />
          <strong>消息</strong>
          <StatusBadge tone={state.phase === 'connected' ? 'active' : 'neutral'}>
            {state.phase === 'connected' ? '已连接' : '未连接'}
          </StatusBadge>
        </div>
        <span
          className={state.phase === 'connected' ? 'flow-link connected' : 'flow-link'}
          aria-hidden="true"
        />
        <div>
          <CircleCheck size={17} />
          <strong>Agent</strong>
          <small>
            {{
              running: '工作中',
              prepared: '准备中',
              failed: '需要查看',
              paused: '已暂停',
              completed: '已完成',
            }[projection.latestStep?.status || ''] || '查看执行记录'}
          </small>
        </div>
        <span className="flow-link" aria-hidden="true" />
        <div>
          <ChevronRight size={17} />
          <strong>工具</strong>
          <small>{projection.tools.length} 项记录</small>
        </div>
      </div>
      <div className="panel-tabs">
        {[
          ['traces', '执行'],
          ['events', '事件'],
          ['status', '连接'],
        ].map(([value, label]) => (
          <button
            key={value}
            className={tab === value ? 'selected' : ''}
            aria-pressed={tab === value}
            onClick={() => setTab(value)}
          >
            {label}
          </button>
        ))}
        <button
          className="icon-button refresh"
          aria-label="刷新调试数据"
          disabled={loading}
          onClick={() => {
            setTrace(undefined);
            void refresh();
          }}
        >
          {loading ? <LoaderCircle size={15} className="spin" /> : <RefreshCw size={15} />}
        </button>
      </div>
      <div className="panel-updated">{updated ? `接口最近检查于 ${updated}` : '正在检查连接…'}</div>
      <div className="panel-content" aria-busy={loading}>
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
            <p className="panel-caption">最近事件 · 按序号倒序 · 最多显示 200 条</p>
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
              {!state.events.some((e) => e.event_type.includes(filter)) && (
                <div className="panel-empty">
                  {filter
                    ? '没有匹配的事件，试试其他关键词。'
                    : '对话开始后，实际事件会出现在这里。'}
                </div>
              )}
            </div>
          </>
        )}
        {tab === 'traces' && (
          <>
            {trace ? (
              <TraceDetails trace={trace} onBack={() => setTrace(undefined)} />
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
                {loading && !traces.length && (
                  <div className="panel-empty" role="status">
                    <LoaderCircle size={20} className="spin" />
                    <p>正在读取执行记录…</p>
                  </div>
                )}
                {!traces.length && !loading && !error && (
                  <div className="panel-empty">
                    这里记录 Hymio 如何完成工作。
                    <br />
                    聊一句，再回来看看。
                  </div>
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
                <Button disabled={state.phase !== 'connected'} onClick={onRetry}>
                  重试失败步骤
                </Button>
                <Button disabled={state.phase !== 'connected'} onClick={onCancel}>
                  停止当前任务
                </Button>
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
