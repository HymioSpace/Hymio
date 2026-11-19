import { useEffect, useState } from 'react';
import { Sheet, IconButton } from '@hymio/ui';
import { X, Cpu, UserRound, CheckCircle2 } from 'lucide-react';
import type { LoginState } from './useLogin';
import type { ExecutionAgent, Work } from './taskModels';
import './tasks.css';

const labels: Record<string, string> = {
  queued: '等待执行',
  running: '执行中',
  waiting: '等待条件',
  paused: '已暂停',
  succeeded: '已完成',
  failed: '执行失败',
  cancelled: '已取消',
  closed: '已结束',
  active: '已安排',
};

export function TasksPanel({
  login,
  onClose,
  initialSelected = '',
}: {
  login: LoginState;
  onClose: () => void;
  initialSelected?: string;
}) {
  const [tasks, setTasks] = useState<Work[]>([]);
  const [selected, setSelected] = useState(initialSelected);
  const [detail, setDetail] = useState<Work | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function request(data?: object) {
    if (!login.session) throw new Error('请先登录');
    const response = await fetch(login.session.backend + '/tasks', {
      method: data ? 'POST' : 'GET',
      headers: {
        Authorization: 'Bearer ' + login.session.access_token,
        'Content-Type': 'application/json',
      },
      body: data ? JSON.stringify(data) : undefined,
      signal: AbortSignal.timeout(15000),
      redirect: 'error',
    });
    if (!response.ok) throw new Error('暂时无法读取或更新任务');
    return response.json();
  }
  async function load() {
    const value = await request();
    setTasks(value.tasks);
    setError('');
  }
  useEffect(() => {
    let active = true;
    const refresh = () =>
      request()
        .then((v) => {
          if (active) {
            setTasks(v.tasks);
            setError('');
          }
        })
        .catch(() => {
          if (active) setError('暂时无法读取任务');
        });
    void refresh();
    const timer = setInterval(refresh, 5000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [login.session?.access_token]);
  useEffect(() => {
    if (!selected) {
      setDetail(null);
      return;
    }
    let active = true;
    const refresh = () =>
      request({ action: 'get', task_id: selected })
        .then((v: Work) => {
          if (active) setDetail(v);
        })
        .catch(() => {
          if (active) setError('暂时无法读取任务详情');
        });
    void refresh();
    const timer = setInterval(refresh, 5000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [selected, login.session?.access_token]);
  async function control(task: Work, action: string) {
    setBusy(true);
    try {
      const updated = await request({ action, task_id: task.id, expected_revision: task.revision });
      setDetail(updated);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const chosen = detail?.id === selected ? detail : tasks.find((t) => t.id === selected);
  return (
    <Sheet className="tasks-dialog" labelledBy="tasks-title" onClose={onClose}>
      <header className="tasks-header">
        <div>
          <h2 id="tasks-title">任务</h2>
          <p>在对话中交代工作，这里查看进展。</p>
        </div>
        <IconButton label="关闭任务" onClick={onClose}>
          <X size={20} />
        </IconButton>
      </header>
      {error && (
        <p role="alert">
          {error}
          <button onClick={() => void load().catch((e) => setError(e.message))}>重试</button>
        </p>
      )}
      <div className={'tasks-layout' + (selected ? ' has-selection' : '')}>
        <section className="tasks-list" aria-label="任务列表">
          {!tasks.length && <p>暂无任务。可以在对话中提出提醒、分析或持续跟进的要求。</p>}
          {tasks.map((task) => (
            <button
              key={task.id}
              onClick={() => setSelected(task.id)}
              aria-pressed={selected === task.id}
            >
              <strong>{task.title}</strong>
              <span>{taskStatusLabel(task)}</span>
            </button>
          ))}
        </section>
        {chosen && (
          <section className="task-detail" aria-label="任务详情">
            <button className="task-back" onClick={() => setSelected('')}>
              返回任务列表
            </button>
            <h3>{chosen.title}</h3>
            <p className="task-objective-preview">{chosen.objective}</p>
            <details>
              <summary>任务要求</summary>
              <p>{chosen.objective}</p>
              <p>完成条件：{chosen.success_criteria}</p>
            </details>
            {chosen.runs.map((run) => (
              <div key={run.id}>
                {run.status !== 'succeeded' && run.progress && <p>{run.progress}</p>}
                {run.status !== 'succeeded' && run.next_step && <p>{run.next_step}</p>}
                {run.wait_reason && <p className="task-waiting">◷ {run.wait_reason}</p>}
                {run.result && (
                  <details>
                    <summary>查看成果</summary>
                    <div style={{ whiteSpace: 'pre-wrap' }}>{run.result}</div>
                  </details>
                )}
              </div>
            ))}
            {chosen.execution?.task_agent && (
              <section className="task-execution" aria-label="执行协作">
                <h4>执行协作 · {1 + chosen.execution.subagents.length} 个 Agent</h4>
                <AgentDetail agent={chosen.execution.task_agent} />
                <div className="task-leaves">
                  {chosen.execution.subagents.map((agent) => (
                    <AgentDetail key={agent.agent_id} agent={agent} />
                  ))}
                </div>
              </section>
            )}
            <details className="task-technical">
              <summary>执行细节</summary>
              {!!chosen.evidence?.length && (
                <section>
                  <h4>完成依据</h4>
                  {chosen.evidence.map((e, i) => (
                    <p key={i}>
                      {e.summary}
                      <small> · {e.ref}</small>
                    </p>
                  ))}
                </section>
              )}
              <dl className="task-facts">
                {(chosen.executor_kind || chosen.execution?.executor) && (
                  <div>
                    <dt>执行方式</dt>
                    <dd>
                      {(chosen.executor_kind || chosen.execution?.executor) === 'program'
                        ? '程序规则'
                        : '专属 Agent'}
                    </dd>
                  </div>
                )}
                {chosen.execution?.usage && (
                  <div>
                    <dt>模型用量</dt>
                    <dd>
                      {chosen.execution.usage.steps} 步 · {chosen.execution.usage.tokens} tokens
                    </dd>
                  </div>
                )}
                {chosen.runs[0]?.notification_status &&
                  chosen.runs[0].notification_status !== 'none' && (
                    <div>
                      <dt>结果通知</dt>
                      <dd>{notificationLabel(chosen.runs[0].notification_status)}</dd>
                    </div>
                  )}
              </dl>
              {chosen.context?.brief && (
                <details>
                  <summary>初始上下文</summary>
                  <p>{chosen.context.brief}</p>
                </details>
              )}
              {!!chosen.plan?.length && (
                <details>
                  <summary>执行计划</summary>
                  <pre>{JSON.stringify(chosen.plan, null, 2)}</pre>
                </details>
              )}
              {!!chosen.execution?.events?.length && (
                <details className="task-journal">
                  <summary>事件记录 · {chosen.execution.events.length} 条</summary>
                  {chosen.execution.events.map((event) => (
                    <details key={event.id}>
                      <summary>
                        <time>{new Date(event.created_at * 1000).toLocaleString()}</time> ·{' '}
                        {event.type}
                      </summary>
                      <pre>{JSON.stringify(event.data, null, 2)}</pre>
                    </details>
                  ))}
                </details>
              )}
            </details>
            {chosen.state !== 'closed' && (
              <div>
                <button
                  disabled={busy}
                  onClick={() =>
                    void control(chosen, chosen.state === 'paused' ? 'resume' : 'pause')
                  }
                >
                  {chosen.state === 'paused' ? '恢复' : '暂停'}
                </button>
                <button disabled={busy} onClick={() => void control(chosen, 'cancel')}>
                  取消任务
                </button>
              </div>
            )}
            <p>补充要求、回答问题或调整计划，请回到对话中说明。</p>
          </section>
        )}
      </div>
    </Sheet>
  );
}

function AgentDetail({ agent }: { agent: ExecutionAgent }) {
  const status = agent.execution_status || agent.status;
  const Icon =
    status === 'succeeded' ? CheckCircle2 : agent.role === 'task_agent' ? Cpu : UserRound;
  return (
    <details className="task-agent-node">
      <summary>
        <Icon size={22} aria-hidden="true" />
        <strong>
          {agent.title}
          <small>{agent.role === 'task_agent' ? '任务 Agent' : '协作者'}</small>
        </strong>
        <span>{labels[status] || status}</span>
      </summary>
      {agent.result && <p className="task-agent-result">{agent.result}</p>}
      <details>
        <summary>过程与要求</summary>
        <p>{agent.objective}</p>
        <p>完成条件：{agent.success_criteria}</p>
        {agent.notes?.map((note) => (
          <p key={note.note_id}>{note.content}</p>
        ))}
        {agent.activity?.entries?.map((entry) => (
          <div key={entry.id} className="task-agent-event">
            <small>
              {new Date(entry.created_at * 1000).toLocaleTimeString()} · {entry.tool || entry.kind}{' '}
              · {entry.status}
            </small>
            {entry.content && <p>{entry.content}</p>}
          </div>
        ))}
      </details>
    </details>
  );
}

function notificationLabel(status: string) {
  return (
    (
      {
        pending: '等待发送',
        inflight: '正在发送',
        accepted: '系统已接收',
        unknown: '回执未知',
        failed: '发送失败',
        cancelled: '已取消',
      } as Record<string, string>
    )[status] || status
  );
}

function taskStatusLabel(task: Work) {
  if (task.state === 'closed')
    return task.close_reason === 'achieved'
      ? '已完成'
      : task.close_reason === 'cancelled'
        ? '已取消'
        : '已结束';
  if (task.state !== 'active') return labels[task.state] || task.state;
  const run = task.runs[0];
  if (run?.status === 'succeeded' && task.next_due_at) return '已安排';
  return labels[run?.status || 'active'] || run?.status || task.state;
}
