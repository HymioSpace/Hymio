import { useEffect, useMemo, useState } from 'react';
import { Sheet, IconButton } from '@hymio/ui';
import {
  AlertCircle,
  CheckCircle2,
  ChevronLeft,
  Cpu,
  GitBranch,
  HelpCircle,
  UserRound,
  Users,
  X,
  Zap,
} from 'lucide-react';
import type { LoginState } from './useLogin';
import {
  taskExecutionMode,
  taskModeDescription,
  taskModeLabel,
  taskNeedsAttention,
  taskPortfolioScope,
  taskStatusLabel,
  taskTemporalScope,
  type ExecutionAgent,
  type TaskPortfolioScope,
  type TeamMessage,
  type Work,
  type WorkflowNode,
} from './taskModels';
import './tasks.css';

const scopeDefinitions: { scope: TaskPortfolioScope; title: string }[] = [
  { scope: 'ongoing', title: '长期任务' },
  { scope: 'temporary', title: '临时任务' },
  { scope: 'completed', title: '已完成' },
];

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
        .then((value) => {
          if (active) {
            setTasks(value.tasks);
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
        .then((value: Work) => {
          if (active) {
            setDetail(value);
            setError('');
          }
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
      const updated = await request({
        action,
        task_id: task.id,
        expected_revision: task.revision,
      });
      setDetail(updated);
      await load();
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const chosen = detail?.id === selected ? detail : tasks.find((task) => task.id === selected);
  const grouped = useMemo(
    () =>
      scopeDefinitions
        .map((definition) => ({
          ...definition,
          tasks: tasks.filter((task) => taskPortfolioScope(task) === definition.scope),
        }))
        .filter((group) => group.tasks.length),
    [tasks],
  );

  return (
    <Sheet className="tasks-dialog" labelledBy="tasks-title" onClose={onClose}>
      <header className="tasks-header">
        <div>
          <h2 id="tasks-title">任务</h2>
          <p>{tasks.length} 项任务</p>
        </div>
        <IconButton label="关闭任务" onClick={onClose}>
          <X size={20} />
        </IconButton>
      </header>

      {error && (
        <div className="tasks-error" role="alert">
          <span>{error}</span>
          <button onClick={() => void load().catch((cause) => setError(cause.message))}>
            重试
          </button>
        </div>
      )}

      <div className={'tasks-layout' + (selected ? ' has-selection' : '')}>
        <section className="tasks-list" aria-label="任务列表">
          {!tasks.length && (
            <div className="tasks-empty">
              <CheckCircle2 size={28} />
              <strong>暂无任务</strong>
            </div>
          )}
          {grouped.map((group) => (
            <div className="task-group" key={group.scope}>
              <h3>
                {group.title}
                <span>{group.tasks.length}</span>
              </h3>
              <div className="task-cards">
                {group.tasks.map((task) => (
                  <TaskCard
                    key={task.id}
                    task={task}
                    selected={selected === task.id}
                    onSelect={() => setSelected(task.id)}
                  />
                ))}
              </div>
            </div>
          ))}
        </section>

        {chosen && (
          <TaskDetail
            task={chosen}
            busy={busy}
            onBack={() => setSelected('')}
            onControl={(action) => void control(chosen, action)}
          />
        )}
      </div>
    </Sheet>
  );
}

function TaskCard({
  task,
  selected,
  onSelect,
}: {
  task: Work;
  selected: boolean;
  onSelect: () => void;
}) {
  const run = task.runs[0];
  return (
    <button
      className={`task-card${selected ? ' selected' : ''}${taskNeedsAttention(task) ? ' attention' : ''}`}
      onClick={onSelect}
      aria-pressed={selected}
    >
      <div className="task-card-copy">
        <div className="task-card-meta">
          <span className={`task-state ${run?.status || task.state}`}>{taskStatusLabel(task)}</span>
          <span>{taskModeLabel(task)}</span>
          {taskNeedsAttention(task) && <AlertCircle size={13} aria-label="需要关注" />}
        </div>
        <strong className="task-card-title">{task.title}</strong>
        <span className="task-card-preview">
          {run?.progress || run?.next_step || task.objective}
        </span>
      </div>
    </button>
  );
}

function TaskDetail({
  task,
  busy,
  onBack,
  onControl,
}: {
  task: Work;
  busy: boolean;
  onBack: () => void;
  onControl: (action: string) => void;
}) {
  const run = task.runs[0];
  const mode = taskExecutionMode(task);
  const waitingForBudget = run?.error_code === 'BUDGET_EXHAUSTED';
  const nodes = task.execution?.workflow?.nodes || [];
  const children = task.execution?.subagents || [];
  return (
    <section className="task-detail" aria-label="任务详情">
      <button className="task-back" onClick={onBack}>
        <ChevronLeft size={16} />
        返回任务列表
      </button>

      <header className="task-detail-hero">
        <div className="task-detail-heading">
          <span className={`task-state ${run?.status || task.state}`}>{taskStatusLabel(task)}</span>
          <span className="task-scope">
            {taskTemporalScope(task) === 'ongoing' ? '长期任务' : '临时任务'}
          </span>
          <ModeBadge task={task} />
        </div>
        <h3>{task.title}</h3>
        <p className="task-objective-preview">{task.objective}</p>
      </header>

      {taskNeedsAttention(task) && (
        <div className="task-attention-card">
          <AlertCircle size={18} />
          <div>
            <strong>{waitingForBudget ? '本轮预算已用尽' : taskStatusLabel(task)}</strong>
            <p>{run?.wait_reason || run?.progress || task.objective}</p>
          </div>
        </div>
      )}

      {run && (
        <section className="task-run-card" aria-label="本次运行">
          <header>
            <strong>本次运行</strong>
            <span>{taskStatusLabel(task)}</span>
          </header>
          {(run.progress || run.next_step) && <p>{run.progress || run.next_step}</p>}
          {mode === 'program' ? (
            <small>由任务系统按时执行，不需要 Agent</small>
          ) : (
            task.execution?.usage && (
              <div className="task-run-metrics">
                <span>{compact(task.execution.usage.tokens)} tokens</span>
                <span>{task.execution.usage.steps} 步</span>
                <span>{duration(task.execution.usage.active_seconds)}</span>
              </div>
            )
          )}
        </section>
      )}

      {mode === 'dynamic_workflow' && nodes.length > 0 && <WorkflowPanel nodes={nodes} />}
      {mode !== 'program' && !!task.plan?.length && <PlanPanel plan={task.plan} />}

      <section className="task-execution" aria-label="执行团队">
        <header>
          <strong>{mode === 'program' ? '执行方式' : '执行团队'}</strong>
          <span>
            {mode === 'program'
              ? '自动执行'
              : children.length
                ? `${children.length + 1} 个 Agent`
                : '等待委派'}
          </span>
        </header>
        {mode === 'program' ? (
          <div className="task-program-note">
            <Zap size={18} />
            <span>不启动 Agent</span>
          </div>
        ) : task.execution?.task_agent ? (
          <>
            <AgentDetail
              agent={task.execution.task_agent}
              lead
              label={
                mode === 'agent_team'
                  ? 'Leader'
                  : mode === 'dynamic_workflow'
                    ? '主流程 Agent'
                    : '主执行 Agent'
              }
            />
            <div className="task-leaves">
              {children.map((agent) => (
                <AgentDetail
                  key={agent.agent_id}
                  agent={agent}
                  label={
                    agent.delegation_role === 'teammate'
                      ? 'Team 成员'
                      : agent.delegation_role === 'workflow_node'
                        ? '工作流节点'
                        : '绑定子 Agent'
                  }
                />
              ))}
            </div>
          </>
        ) : (
          <p className="task-muted">正在准备执行 Agent。</p>
        )}
      </section>

      {run?.result && (
        <section className="task-result complete">
          <div>
            <CheckCircle2 size={17} />
            <strong>任务结果</strong>
          </div>
          <p>{run.result}</p>
        </section>
      )}

      <details className="task-definition">
        <summary>任务定义</summary>
        <p>{task.objective}</p>
        <p>完成标准：{task.success_criteria}</p>
        {task.schedule?.mode && <p>时间：{scheduleLabel(task)}</p>}
      </details>

      <div className="task-detail-actions">
        {task.state !== 'closed' && (
          <>
            {waitingForBudget ? (
              <span>在对话中调整本轮预算后继续。</span>
            ) : (
              <button
                disabled={busy}
                onClick={() => onControl(task.state === 'paused' ? 'resume' : 'pause')}
              >
                {task.state === 'paused' ? '恢复' : '暂停'}
              </button>
            )}
            <button disabled={busy} onClick={() => onControl('cancel')}>
              取消任务
            </button>
          </>
        )}
        <small>补充要求或调整计划，请在对话中说明。</small>
      </div>
    </section>
  );
}

function ModeBadge({ task }: { task: Work }) {
  const mode = taskExecutionMode(task);
  const Icon =
    mode === 'program'
      ? Zap
      : mode === 'agent_team'
        ? Users
        : mode === 'dynamic_workflow'
          ? GitBranch
          : UserRound;
  return (
    <span className="task-mode-badge">
      <Icon size={14} aria-hidden="true" />
      {taskModeLabel(task)}
      <details className="task-mode-help">
        <summary aria-label={`${taskModeLabel(task)}说明`}>
          <HelpCircle size={14} />
        </summary>
        <div role="note">{taskModeDescription(task)}</div>
      </details>
    </span>
  );
}

function WorkflowPanel({ nodes }: { nodes: WorkflowNode[] }) {
  const names = Object.fromEntries(nodes.map((node) => [node.id, node.title]));
  return (
    <section className="task-workflow" aria-label="执行依赖">
      <header>
        <strong>执行依赖</strong>
        <span>
          {nodes.filter((node) => node.status === 'succeeded').length}/{nodes.length}
        </span>
      </header>
      <ol>
        {nodes.map((node) => (
          <li key={node.id} className={`workflow-${node.status}`}>
            <span className="workflow-node-dot" />
            <div>
              <header>
                <strong>{node.title}</strong>
                <small>{statusLabel(node.status)}</small>
              </header>
              {!!node.depends_on.length && (
                <p>依赖 {node.depends_on.map((id) => names[id] || id).join('、')}</p>
              )}
              {node.result && <p>{node.result}</p>}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

function PlanPanel({ plan }: { plan: unknown[] }) {
  return (
    <section className="task-plan">
      <strong>计划</strong>
      <ol>
        {plan.map((step, index) => {
          const value = step as { title?: string; description?: string; state?: string };
          return (
            <li key={index}>
              <span className={`plan-${value.state || 'todo'}`} />
              {value.title || value.description || `步骤 ${index + 1}`}
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function AgentDetail({
  agent,
  lead = false,
  label,
}: {
  agent: ExecutionAgent;
  lead?: boolean;
  label: string;
}) {
  const status = agent.execution_status || agent.status;
  const Icon = status === 'succeeded' ? CheckCircle2 : lead ? Cpu : UserRound;
  const activities = semanticActivities(agent);
  return (
    <details className="task-agent-node">
      <summary>
        <Icon size={20} aria-hidden="true" />
        <strong>
          {agent.title}
          <small>{label}</small>
        </strong>
        <span>{statusLabel(status)}</span>
      </summary>
      {agent.result && <p className="task-agent-result">{agent.result}</p>}
      <section>
        <h4>上下文与职责</h4>
        <p>{agent.objective}</p>
        <p>完成标准：{agent.success_criteria}</p>
      </section>
      {!!agent.communications?.length && (
        <section>
          <h4>Agent 间通信</h4>
          {agent.communications.map((message) => (
            <Communication key={message.id} message={message} agentID={agent.agent_id} />
          ))}
        </section>
      )}
      {!!activities.length && (
        <section>
          <h4>执行记录</h4>
          {activities.map((activity) => (
            <p className="task-agent-activity-line" key={activity.id}>
              {activity.title}
            </p>
          ))}
        </section>
      )}
      {!!activities.some((activity) => activity.tool) && (
        <details className="task-agent-tools">
          <summary>工具调用</summary>
          {activities
            .filter((activity) => activity.tool)
            .map((activity) => (
              <p key={activity.id}>
                {activity.title}
                <small>{activity.tool}</small>
              </p>
            ))}
        </details>
      )}
    </details>
  );
}

function Communication({ message, agentID }: { message: TeamMessage; agentID: string }) {
  const outgoing = message.sender_agent_id === agentID;
  return (
    <div className="task-communication">
      <small>{outgoing ? `发给 ${message.recipient_title}` : `来自 ${message.sender_title}`}</small>
      <p>{message.content}</p>
    </div>
  );
}

function semanticActivities(agent: ExecutionAgent) {
  const result: { id: string; title: string; tool: string }[] = [];
  const seen = new Set<string>();
  for (const entry of agent.activity?.entries || []) {
    const values = [
      ...(entry.tool_description
        ? [{ title: entry.tool_description, tool: entry.tool || '工具' }]
        : []),
      ...(entry.tool_calls || []).map((call) => ({
        title: call.description || call.name,
        tool: call.name,
      })),
    ];
    for (const value of values) {
      const key = `${value.title}|${value.tool}`;
      if (!value.title || seen.has(key)) continue;
      seen.add(key);
      result.push({ id: `${entry.id}-${result.length}`, ...value });
    }
    if (entry.kind === 'assistant.message' && entry.content) {
      const title = entry.content.slice(0, 220);
      if (!seen.has(title)) result.push({ id: String(entry.id), title, tool: '' });
    }
  }
  return result.slice(-20);
}

function statusLabel(status: string) {
  return (
    {
      queued: '准备中',
      pending: '等待依赖',
      ready: '准备执行',
      running: '进行中',
      waiting: '等待完成',
      paused: '已暂停',
      succeeded: '已完成',
      failed: '未完成',
      blocked: '需要处理',
      cancelled: '已取消',
      expired: '已过期',
    }[status] || status
  );
}

function compact(value = 0) {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1).replace('.0', '')}m`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1).replace('.0', '')}k`;
  return String(value);
}

function duration(seconds = 0) {
  return seconds < 60 ? `${Math.round(seconds)}s` : `${Math.round(seconds / 60)}m`;
}

function scheduleLabel(task: Work) {
  const schedule = task.schedule;
  if (schedule.mode === 'daily') return `每天 ${schedule.time}`;
  if (schedule.mode === 'weekly') return `每周 ${schedule.time}`;
  if (schedule.mode === 'once' && schedule.at) return new Date(schedule.at).toLocaleString();
  if (schedule.mode === 'event') return '等待条件';
  return '随时';
}
