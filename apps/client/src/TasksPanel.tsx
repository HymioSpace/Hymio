import { useEffect, useState } from 'react';
import {
  ArrowLeft,
  ArrowUpRight,
  CalendarDays,
  MessageSquare,
  Check,
  CheckCheck,
  ChevronRight,
  Clock3,
  Flag,
  LoaderCircle,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react';
import { Sheet, IconButton, Button } from '@hymio/ui';
import type { LoginState } from './useLogin';
import './tasks.css';
import type { Work, Schedule } from './taskModels';
import { TaskForm } from './TaskForm';
import { MessageMarkdown } from './MessageView';
const labels: Record<string, string> = {
  scheduled: '已安排',
  delivering: '正在送达',
  ready: '等待开始',
  running: '进行中',
  blocked: '需要关注',
  succeeded: '已完成',
  failed: '未完成',
  expired: '已过期',
  cancelled: '已取消',
  paused: '已暂停',
  active: '已安排',
};
const date = (value: number) =>
  new Date(value * 1000).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
function status(task: Work) {
  return task.state === 'active' ? task.runs[0]?.status || 'scheduled' : task.state;
}
function scheduleLabel(s: Schedule) {
  return s.mode === 'now'
    ? '即刻开始'
    : s.mode === 'once'
      ? new Date(s.at!).toLocaleString()
      : `${s.mode === 'daily' ? '每天' : ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][s.weekday || 0]} ${s.time} · ${s.timezone}`;
}
function TaskNoteContent({ content }: { content: string }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="task-note-content">
      <p className={expanded ? '' : 'task-note-preview'}>{content}</p>
      {(content.length > 180 || content.split('\n').length > 3) && (
        <button type="button" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>
          {expanded ? '收起' : '展开'}
        </button>
      )}
    </div>
  );
}

export function TasksPanel({
  login,
  onClose,
  initialSelected = '',
}: {
  login: LoginState;
  onClose: () => void;
  initialSelected?: string;
}) {
  const [tasks, setTasks] = useState<Work[]>([]),
    [selected, setSelected] = useState(initialSelected),
    [filter, setFilter] = useState('active');
  const [editing, setEditing] = useState<Work | 'new' | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [loaded, setLoaded] = useState(false);
  async function request(data?: object) {
    const session = login.session;
    if (!session) throw new Error('请先登录');
    const response = await fetch(session.backend + '/tasks', {
      method: data ? 'POST' : 'GET',
      headers: {
        Authorization: 'Bearer ' + session.access_token,
        'Content-Type': 'application/json',
      },
      body: data ? JSON.stringify(data) : undefined,
      redirect: 'error',
      signal: AbortSignal.timeout(15000),
    });
    if (!response.ok) {
      const value = await response.json().catch(() => ({}));
      throw new Error(value.message || '暂时无法更新任务，请稍后重试');
    }
    return response.json();
  }
  async function load() {
    try {
      const v = await request();
      setTasks(v.tasks);
      setError('');
      setLoaded(true);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    let active = true;
    const refresh = async () => {
      try {
        const v = await request();
        if (active) {
          setTasks(v.tasks);
          setLoaded(true);
        }
      } catch {
        if (active) setError('暂时无法读取任务');
      }
    };
    void refresh();
    const timer = setInterval(() => void refresh(), 5000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [login.session?.access_token]);
  async function change(data: object) {
    setBusy(true);
    setError('');
    try {
      const updated = await request(data);
      if (updated.id === selected) setDetail(updated);
      await load();
      setEditing(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const [detail, setDetail] = useState<Work | null>(null);
  const [continuation, setContinuation] = useState('');
  const [activity, setActivity] = useState<
    {
      id: number;
      kind: string;
      content: string;
      tool: string;
      status: string;
      created_at: string;
    }[]
  >([]);
  const agentID = detail?.runs.find((r) => r.agent_id && r.agent_id !== 'pending')?.agent_id;
  useEffect(() => {
    setActivity([]);
    if (!agentID) return;
    const controller = new AbortController();
    let running = false;
    async function refresh() {
      if (running || document.hidden) return;
      running = true;
      try {
        const response = await fetch(login.backend + '/agents/' + agentID + '/activity', {
          headers: { Authorization: 'Bearer ' + login.session!.access_token },
          signal: controller.signal,
          redirect: 'error',
        });
        if (response.ok) {
          const value = await response.json();
          if (!controller.signal.aborted) setActivity(value.entries);
        }
      } finally {
        running = false;
      }
    }
    void refresh().catch(() => {});
    const timer = setInterval(() => void refresh().catch(() => {}), 5000);
    return () => {
      controller.abort();
      clearInterval(timer);
    };
  }, [agentID, login.backend, login.session?.access_token]);
  useEffect(() => {
    if (!selected) {
      setDetail(null);
      setContinuation('');
      return;
    }
    let active = true;
    const refresh = async () => {
      try {
        const value = await request({ action: 'get', task_id: selected });
        if (active) setDetail(value);
      } catch {
        if (active) setError('暂时无法读取任务详情');
      }
    };
    void refresh();
    const timer = setInterval(() => void refresh(), 5000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [selected, login.session?.access_token]);
  const task = detail?.id === selected ? detail : tasks.find((t) => t.id === selected),
    run = task?.runs[0];
  const visible = tasks.filter(
    (t) =>
      filter === 'all' ||
      (filter === 'scheduled' && ['scheduled', 'paused'].includes(status(t))) ||
      (filter === 'done'
        ? ['succeeded', 'expired', 'cancelled'].includes(status(t))
        : filter === 'active' && !['succeeded', 'expired', 'cancelled'].includes(status(t))),
  );
  return (
    <Sheet className="tasks-dialog" labelledBy="tasks-title" onClose={onClose}>
      <header className="tasks-header">
        <div>
          <h2 id="tasks-title">
            交给 Hymio 的事<span className="tasks-count">{tasks.length}</span>
          </h2>
          <p>进展、下一步，还有带回来的结果。</p>
        </div>
        <IconButton label="关闭任务" onClick={onClose}>
          <X size={20} />
        </IconButton>
      </header>
      {error && (
        <p className="tasks-error" role="alert">
          {error}
          <button onClick={() => void load()}>重新读取</button>
        </p>
      )}
      {editing ? (
        <TaskForm
          key={editing === 'new' ? 'new' : editing.id}
          task={editing === 'new' ? undefined : editing}
          busy={busy}
          onCancel={() => setEditing(null)}
          onSave={(data) => void change(data)}
        />
      ) : (
        <div className={`tasks-layout ${task ? 'has-selection' : ''}`}>
          <section className="tasks-list">
            <div className="tasks-list-toolbar">
              <div className="tasks-filters" aria-label="筛选任务">
                {[
                  ['active', '未完成'],
                  ['scheduled', '日程'],
                  ['done', '已结束'],
                ].map(([key, label]) => (
                  <button key={key} aria-pressed={filter === key} onClick={() => setFilter(key)}>
                    {label}
                  </button>
                ))}
              </div>
              <IconButton label="新建任务" onClick={() => setEditing('new')}>
                <Plus size={19} />
              </IconButton>
            </div>
            {!loaded && !error && (
              <div className="tasks-empty">
                <LoaderCircle size={24} />
                <p>正在读取任务…</p>
              </div>
            )}
            {loaded && !visible.length && (
              <div className="tasks-empty">
                <div className="tasks-empty-orbit">
                  <Flag size={27} strokeWidth={1.4} />
                </div>
                <h3>{filter === 'done' ? '好结果，会留在这里。' : '把想做的事，留给我。'}</h3>
                <p>
                  聊一句你想完成的事，进展会留在这里。
                  <br />
                  你离开后，工作仍会继续。
                </p>
                <Button onClick={() => setEditing('new')}>
                  <Plus size={15} />
                  安排第一件事
                </Button>
              </div>
            )}
            <div className="task-cards">
              {[...visible]
                .sort((a, b) => {
                  if (filter === 'scheduled')
                    return (a.runs[0]?.due_at || 0) - (b.runs[0]?.due_at || 0);
                  const rank = (v: Work) =>
                    ['blocked', 'failed'].includes(status(v))
                      ? 0
                      : ['running', 'ready', 'delivering'].includes(status(v))
                        ? 1
                        : 2;
                  return rank(a) - rank(b);
                })
                .map((t) => {
                  const state = status(t);
                  return (
                    <button
                      className={`task-card ${selected === t.id ? 'selected' : ''}`}
                      key={t.id}
                      onClick={() => setSelected(t.id)}
                    >
                      <span className={`task-state-icon ${state}`}>
                        {state === 'succeeded' ? (
                          <Check size={16} />
                        ) : state === 'running' ? (
                          <Sparkles size={16} />
                        ) : (
                          <Clock3 size={16} />
                        )}
                      </span>
                      <span className="task-card-copy">
                        <span className="task-card-title">{t.title}</span>
                        <span className="task-card-preview">
                          {t.runs[0]?.result || t.runs[0]?.progress || t.objective}
                        </span>
                        <span className="task-card-meta">
                          <span className={`task-state ${state}`}>{labels[state] || state}</span>
                          <span>
                            {t.source === 'conversation' ? '来自对话' : scheduleLabel(t.schedule)}
                          </span>
                        </span>
                      </span>
                      <ChevronRight size={14} />
                    </button>
                  );
                })}
            </div>
          </section>
          <section className="task-detail" aria-label="任务详情">
            {task ? (
              <>
                <button className="task-back" onClick={() => setSelected('')}>
                  <ArrowLeft size={15} />
                  任务列表
                </button>
                <div className="task-detail-heading">
                  <span className={`task-state ${status(task)}`}>
                    {labels[status(task)] || status(task)}
                  </span>
                  <span className="task-detail-schedule">
                    {task.source === 'conversation' ? (
                      <MessageSquare size={14} />
                    ) : (
                      <CalendarDays size={14} />
                    )}
                    {task.source === 'conversation' ? '来自对话' : scheduleLabel(task.schedule)}
                  </span>
                </div>
                <h3>{task.title}</h3>
                <p className="task-objective">{task.objective}</p>
                <div className="task-criteria">
                  <Flag size={15} />
                  <div>
                    <span>怎样算完成</span>
                    <p>{task.success_criteria}</p>
                  </div>
                </div>
                {run &&
                  ['running', 'blocked'].includes(run.status) &&
                  (run.phase || run.next_step || run.progress) && (
                    <section className={`task-milestone ${run.status}`} aria-label="当前进展">
                      <span className="task-milestone-label">
                        {run.status === 'blocked' ? '等待解决' : '推进到这里'}
                      </span>
                      {run.status === 'blocked' && (
                        <div>
                          <input
                            aria-label="补充决定或新的要求"
                            placeholder="补充决定或新的要求"
                            value={continuation}
                            onChange={(e) => setContinuation(e.target.value)}
                          />
                          <button
                            disabled={busy}
                            onClick={() =>
                              void change({
                                action: 'continue',
                                task_id: task.id,
                                content: continuation,
                              })
                            }
                          >
                            <Play size={13} />
                            继续推进
                          </button>
                        </div>
                      )}
                      {run.phase && <h4>{run.phase}</h4>}
                      {run.progress && <p>{run.progress}</p>}
                      {run.next_step && (
                        <div>
                          <ArrowUpRight size={14} />
                          <span>下一步 · {run.next_step}</span>
                        </div>
                      )}
                    </section>
                  )}
                <div className="task-actions">
                  {['paused', 'cancelled'].includes(task.state) ? (
                    <button
                      disabled={busy}
                      onClick={() => void change({ action: 'resume', task_id: task.id })}
                    >
                      <Play size={14} />
                      重新安排
                    </button>
                  ) : (
                    <>
                      {task.source !== 'conversation' &&
                        !['succeeded', 'failed', 'expired', 'cancelled'].includes(
                          run?.status || '',
                        ) && (
                          <button
                            disabled={busy}
                            onClick={() => void change({ action: 'pause', task_id: task.id })}
                          >
                            <Pause size={14} />
                            暂停日程
                          </button>
                        )}
                      <button
                        disabled={busy}
                        onClick={() => void change({ action: 'cancel', task_id: task.id })}
                      >
                        取消任务
                      </button>
                    </>
                  )}
                  <button
                    disabled={busy || run?.status === 'running' || run?.status === 'blocked'}
                    onClick={() => setEditing(task)}
                  >
                    编辑
                  </button>
                  <button
                    aria-label="删除任务"
                    disabled={busy}
                    onClick={() => {
                      if (window.confirm('删除任务并取消尚未完成的工作？')) {
                        void change({ action: 'delete', task_id: task.id });
                        setSelected('');
                      }
                    }}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
                {run?.result && (
                  <div className={`task-result ${run.status === 'succeeded' ? 'complete' : ''}`}>
                    <div>
                      <CheckCheck size={17} />
                      <span>{run.status === 'succeeded' ? '这次的成果' : '最新进展'}</span>
                    </div>
                    <div className="markdown task-result-body">
                      <MessageMarkdown content={run.result} login={login} />
                    </div>
                  </div>
                )}
                {activity.length > 0 && (
                  <section className="task-agent-activity">
                    <h4>执行过程</h4>
                    {activity.map((entry) => (
                      <details key={entry.id}>
                        <summary>
                          <span>
                            {entry.tool ||
                              (entry.kind === 'assistant.message' ? '进展' : '执行步骤')}
                          </span>
                          <span>{labels[entry.status] || entry.status}</span>
                          <time>
                            {new Date(entry.created_at).toLocaleTimeString(undefined, {
                              hour: '2-digit',
                              minute: '2-digit',
                            })}
                          </time>
                        </summary>
                        {entry.content && <p>{entry.content}</p>}
                      </details>
                    ))}
                  </section>
                )}
                <div className="task-timeline">
                  <h4>
                    工作记录<span>{task.runs.length} 次执行</span>
                  </h4>
                  {task.runs.map((r) => (
                    <div className="task-run" key={r.id}>
                      <div className="task-run-title">
                        <span className={`task-state ${r.status}`}>
                          {labels[r.status] || r.status}
                        </span>
                        <time>{date(r.started_at || r.due_at)}</time>
                      </div>
                      {r.agent_id && (
                        <span className="task-delegated">
                          <Sparkles size={12} />
                          独立专家协作
                        </span>
                      )}
                      {r.updates.map((n) => (
                        <div className="task-note" key={n.note_id}>
                          <span className="task-note-dot" />
                          <div>
                            <div className="task-note-heading">
                              <time>{date(n.created_at)}</time>
                              {n.status && (
                                <span className={`task-state ${n.status}`}>
                                  {labels[n.status] || n.status}
                                </span>
                              )}
                            </div>
                            {n.phase && <strong>{n.phase}</strong>}
                            <TaskNoteContent content={n.content} />
                          </div>
                        </div>
                      ))}
                      {!r.updates.length && (
                        <p className="task-waiting">
                          {r.status === 'scheduled'
                            ? '到时间后，Hymio 会收到提醒。'
                            : r.status === 'cancelled'
                              ? '已停止后续安排。'
                              : '进展和成果会记录在这里。'}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <div className="task-detail-placeholder">
                <span className="task-placeholder-line" />
                <ArrowUpRight size={25} strokeWidth={1} />
                <h3>让事情，慢慢有着落。</h3>
                <p>选一件事，看看它走到了哪里。</p>
              </div>
            )}
          </section>
        </div>
      )}
      <footer className="tasks-footer">
        <span>
          <RefreshCw size={12} />
          {tasks.length === 100 ? '最近 100 件事 · 进展自动同步' : '进展自动同步'}
        </span>
        <span>一个 Hymio，持续为你推进。</span>
      </footer>
    </Sheet>
  );
}
