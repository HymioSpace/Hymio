import { useEffect, useMemo, useState } from 'react';
import { Sheet, IconButton } from '@hymio/ui';
import {
  AlertCircle,
  Archive,
  CheckCircle2,
  ChevronLeft,
  Cpu,
  GitBranch,
  HelpCircle,
  ListTodo,
  LoaderCircle,
  Trash2,
  UserRound,
  Users,
  X,
  Zap,
} from 'lucide-react';
import type { LoginState } from './useLogin';
import { MessageMarkdown } from './MessageView';
import {
  taskExecutionMode,
  taskIsCancelled,
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
import { workflowLayers } from './workflowLayout';
import './tasks.css';

const scopeDefinitions: { scope: TaskPortfolioScope; title: string }[] = [
  { scope: 'ongoing', title: '长期任务' },
  { scope: 'temporary', title: '临时任务' },
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
  const [archiveOpen, setArchiveOpen] = useState(false);
  const [archive, setArchive] = useState<Work[]>([]);
  const [archiveError, setArchiveError] = useState('');

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
    setTasks(value.tasks.filter((task: Work) => !taskIsCancelled(task)));
    setError('');
  }

  async function loadArchive() {
    try {
      const value = await request({ action: 'archive_list' });
      setArchive(value.tasks || []);
      setArchiveError('');
    } catch {
      setArchiveError('暂时无法读取归档');
    }
  }

  useEffect(() => {
    let active = true;
    const refresh = () =>
      request()
        .then((value) => {
          if (active) {
            setTasks(value.tasks.filter((task: Work) => !taskIsCancelled(task)));
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

  async function control(task: Work, action: string, extra: Record<string, unknown> = {}) {
    setBusy(true);
    try {
      const updated = await request({
        action,
        task_id: task.id,
        expected_revision: task.revision,
        request_id: crypto.randomUUID(),
        ...extra,
      });
      setDetail(updated);
      if (taskIsCancelled(updated)) setSelected('');
      await load();
      return true;
    } catch (cause) {
      setError((cause as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function hideArchived(task: Work) {
    if (!window.confirm('从归档中移除这个任务？原始任务与执行记录会保留，只是不再展示。')) return;
    const previous = archive;
    setArchive((items) => items.filter((item) => item.id !== task.id));
    if (selected === task.id) setSelected('');
    try {
      await request({ action: 'archive_hide', task_id: task.id });
      setArchiveError('');
    } catch {
      setArchive(previous);
      setArchiveError('移除失败，归档内容已恢复。');
    }
  }

  const list = archiveOpen ? archive : tasks;
  const chosen = detail?.id === selected ? detail : list.find((task) => task.id === selected);
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
          <h2 id="tasks-title">{archiveOpen ? '归档' : '任务'}</h2>
          <p>{archiveOpen ? `${archive.length} 项已结束任务` : `${tasks.length} 项当前任务`}</p>
        </div>
        <div className="tasks-header-actions">
          <button
            className={`tasks-archive${archiveOpen ? ' selected' : ''}`}
            aria-label={archiveOpen ? '返回当前任务' : '查看归档'}
            onClick={() => {
              setSelected('');
              setDetail(null);
              if (!archiveOpen) void loadArchive();
              setArchiveOpen(!archiveOpen);
            }}
          >
            {archiveOpen ? <ChevronLeft size={18} /> : <Archive size={18} />}
            <span>{archiveOpen ? '当前任务' : '归档'}</span>
          </button>
          <IconButton label="关闭任务" onClick={onClose}>
            <X size={20} />
          </IconButton>
        </div>
      </header>

      {error && (
        <div className="tasks-error" role="alert">
          <span>{error}</span>
          <button onClick={() => void load().catch((cause) => setError(cause.message))}>
            重试
          </button>
        </div>
      )}

      {archiveError && (
        <div className="tasks-error" role="alert">
          <span>{archiveError}</span>
          <button onClick={() => void loadArchive()}>重试</button>
        </div>
      )}

      <div className={'tasks-layout' + (selected ? ' has-selection' : '')}>
        <section className="tasks-list" aria-label={archiveOpen ? '任务归档' : '当前任务列表'}>
          {!list.length && (
            <div className="tasks-empty">
              {archiveOpen ? <Archive size={28} /> : <ListTodo size={28} />}
              <strong>{archiveOpen ? '归档还是空的' : '暂无任务'}</strong>
              {archiveOpen && <span>已完成和已取消的任务会保留在这里。</span>}
            </div>
          )}
          {archiveOpen ? (
            <div className="task-cards archive-cards">
              {archive.map((task) => (
                <div className="archive-row" key={task.id}>
                  <TaskCard
                    task={task}
                    selected={selected === task.id}
                    onSelect={() => setSelected(task.id)}
                  />
                  <button
                    className="archive-remove"
                    aria-label={`从归档移除 ${task.title}`}
                    title="从归档移除"
                    onClick={() => void hideArchived(task)}
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              ))}
            </div>
          ) : (
            grouped.map((group) => (
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
            ))
          )}
        </section>

        {chosen && (
          <TaskDetail
            task={chosen}
            login={login}
            busy={busy}
            archived={archiveOpen}
            onBack={() => setSelected('')}
            onControl={(action, extra) => control(chosen, action, extra)}
            onDeleteArchived={() => hideArchived(chosen)}
          />
        )}
        {!chosen && (
          <section className="task-detail-placeholder" aria-label="未选择任务">
            {archiveOpen ? <Archive size={24} /> : <ListTodo size={24} />}
            <p>{archiveOpen ? '选择一个归档任务' : '选择一个任务'}</p>
          </section>
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
  login,
  busy,
  archived,
  onBack,
  onControl,
  onDeleteArchived,
}: {
  task: Work;
  login: LoginState;
  busy: boolean;
  archived: boolean;
  onBack: () => void;
  onControl: (action: string, extra?: Record<string, unknown>) => Promise<boolean>;
  onDeleteArchived: () => void;
}) {
  const run = task.runs[0];
  const mode = taskExecutionMode(task);
  const waitingForBudget = task.state === 'active' && run?.error_code === 'BUDGET_EXHAUSTED';
  const nodes = task.execution?.workflow?.nodes || [];
  const edges = task.execution?.workflow?.edges || [];
  const children = task.execution?.subagents || [];
  const TaskModeIcon =
    mode === 'program'
      ? Zap
      : mode === 'agent_team'
        ? Users
        : mode === 'dynamic_workflow'
          ? GitBranch
          : taskModeLabel(task) === 'Agent 并行'
            ? Users
            : UserRound;
  return (
    <section className="task-detail" aria-label="任务详情">
      <button className="task-back" onClick={onBack}>
        <ChevronLeft size={16} />
        {archived ? '返回归档' : '返回任务列表'}
      </button>

      <header className="task-detail-hero">
        <div className="task-detail-heading">
          <span className="task-detail-mode-icon" aria-hidden="true">
            <TaskModeIcon size={20} />
          </span>
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
            <p>
              {waitingForBudget
                ? '在对话中让我调整预算后继续。'
                : run?.wait_reason || run?.progress || task.objective}
            </p>
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

      {mode === 'dynamic_workflow' &&
        (nodes.length > 0 ? (
          <WorkflowPanel nodes={nodes} edges={edges} agents={children} login={login} />
        ) : (
          <section className="task-workflow task-workflow-pending" aria-label="工作流准备中">
            <div className="workflow-pending-heading">
              <LoaderCircle size={18} className="spin" />
              <strong>工作流准备中</strong>
            </div>
            <p>任务 Agent 正在确定工作节点和依赖关系，定义完成后会自动显示 DAG。</p>
          </section>
        ))}
      {mode !== 'program' && mode !== 'dynamic_workflow' && !!task.plan?.length && (
        <PlanPanel plan={task.plan} />
      )}

      {mode !== 'dynamic_workflow' && (
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
                login={login}
                lead
                label={mode === 'agent_team' ? 'Leader' : '主执行 Agent'}
                showCommunications={mode === 'agent_team'}
              />
              <div className="task-leaves">
                {children.map((agent) => (
                  <AgentDetail
                    key={agent.agent_id}
                    agent={agent}
                    login={login}
                    label={agent.delegation_role === 'teammate' ? 'Team 成员' : '绑定子 Agent'}
                    showCommunications={mode === 'agent_team'}
                  />
                ))}
              </div>
            </>
          ) : (
            <p className="task-muted">正在准备执行 Agent。</p>
          )}
        </section>
      )}

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
        <div className="task-agent-success">
          <strong>完成标准</strong>
          <span>{task.success_criteria}</span>
        </div>
        {task.schedule?.mode && <p>时间：{scheduleLabel(task)}</p>}
      </details>

      <div className="task-detail-actions">
        {archived ? (
          <button className="archive-delete" disabled={busy} onClick={onDeleteArchived}>
            <Trash2 size={15} />
            从归档移除
          </button>
        ) : task.state !== 'closed' ? (
          <>
            {waitingForBudget ? (
              <span>在对话中让我调整预算后继续。</span>
            ) : (
              <button
                disabled={busy}
                onClick={() => void onControl(task.state === 'paused' ? 'resume' : 'pause')}
              >
                {task.state === 'paused' ? '恢复' : '暂停'}
              </button>
            )}
            <button disabled={busy} onClick={() => void onControl('cancel')}>
              取消任务
            </button>
          </>
        ) : null}
        <small>
          {archived
            ? '从归档移除只影响这个视图，不删除任务与执行记录。'
            : '补充要求或调整计划，请在对话中说明。'}
        </small>
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

function WorkflowPanel({
  nodes,
  edges,
  agents,
  login,
}: {
  nodes: WorkflowNode[];
  edges: { from: string; to: string }[];
  agents: ExecutionAgent[];
  login: LoginState;
}) {
  const names = Object.fromEntries(nodes.map((node) => [node.id, node.title]));
  const nodeByID = Object.fromEntries(nodes.map((node) => [node.id, node]));
  const layers = workflowLayers(nodes, edges) as WorkflowNode[][];
  const [selectedID, setSelectedID] = useState(
    nodes.find((node) => node.status === 'running')?.id || nodes[0]?.id || '',
  );
  const nodeWidth = 196;
  const nodeHeight = 94;
  const gapX = 56;
  const gapY = 68;
  const padding = 26;
  const maxPerLayer = Math.max(1, ...layers.map((layer) => layer.length));
  const canvasWidth = Math.max(
    620,
    padding * 2 + maxPerLayer * nodeWidth + (maxPerLayer - 1) * gapX,
  );
  const positions = new Map<
    string,
    { x: number; y: number; width: number; height: number; layer: number }
  >();
  layers.forEach((layer, layerIndex) => {
    const width = layer.length * nodeWidth + Math.max(0, layer.length - 1) * gapX;
    const start = (canvasWidth - width) / 2;
    layer.forEach((node, index) => {
      positions.set(node.id, {
        x: start + index * (nodeWidth + gapX),
        y: padding + layerIndex * (nodeHeight + gapY),
        width: nodeWidth,
        height: nodeHeight,
        layer: layerIndex,
      });
    });
  });
  const canvasHeight =
    padding * 2 + Math.max(1, layers.length) * nodeHeight + Math.max(0, layers.length - 1) * gapY;
  const selected = nodes.find((node) => node.id === selectedID) || nodes[0];
  const selectedAgent = agents.find((agent) => agent.agent_id === selected?.agent_id);
  return (
    <section className="task-workflow" aria-label="执行依赖">
      <header>
        <strong>Workflow DAG</strong>
        <span>
          {nodes.filter((node) => node.status === 'succeeded').length}/{nodes.length}
        </span>
      </header>
      <p className="workflow-caption">箭头表示依赖；同一层没有依赖关系的节点可以并行。</p>
      <div className="workflow-canvas-scroll">
        <div
          className="workflow-canvas"
          style={{ width: canvasWidth, height: canvasHeight }}
          role="group"
          aria-label="工作流依赖图"
        >
          <svg width={canvasWidth} height={canvasHeight} aria-hidden="true">
            <defs>
              <marker
                id="workflow-arrow"
                viewBox="0 0 8 8"
                refX="7"
                refY="4"
                markerWidth="6"
                markerHeight="6"
                orient="auto"
              >
                <path d="M0 0L8 4L0 8" fill="none" stroke="currentColor" strokeWidth="1.5" />
              </marker>
            </defs>
            {edges.map((edge) => {
              const from = positions.get(edge.from);
              const to = positions.get(edge.to);
              if (!from || !to) return null;
              const x1 = from.x + from.width / 2;
              const y1 = from.y + from.height;
              const x2 = to.x + to.width / 2;
              const y2 = to.y;
              const middle = y1 + (y2 - y1) / 2;
              return (
                <path
                  key={`${edge.from}-${edge.to}`}
                  d={`M ${x1} ${y1} C ${x1} ${middle}, ${x2} ${middle}, ${x2} ${y2}`}
                  markerEnd="url(#workflow-arrow)"
                  className={`workflow-edge workflow-edge-${nodeByID[edge.to]?.status || 'pending'}`}
                />
              );
            })}
          </svg>
          {nodes.map((node) => {
            const position = positions.get(node.id);
            if (!position) return null;
            return (
              <button
                type="button"
                key={node.id}
                className={`workflow-dag-node workflow-${node.status}${selected?.id === node.id ? ' selected' : ''}`}
                style={{
                  left: position.x,
                  top: position.y,
                  width: position.width,
                  height: position.height,
                }}
                aria-pressed={selected?.id === node.id}
                onClick={() => setSelectedID(node.id)}
              >
                <span className="workflow-node-status">{statusLabel(node.status)}</span>
                <strong>{node.title}</strong>
                <small>{workflowNodeSubtitle(node, names)}</small>
              </button>
            );
          })}
        </div>
      </div>
      <ul className="sr-only">
        {nodes.map((node) => (
          <li key={node.id}>
            {node.title}，{statusLabel(node.status)}，
            {node.depends_on.length
              ? `依赖 ${node.depends_on.map((id) => names[id] || id).join('、')}`
              : '无依赖'}
          </li>
        ))}
      </ul>
      {selected && (
        <div className="workflow-node-detail">
          <div>
            <span>{statusLabel(selected.status)}</span>
            <h4>{selected.title}</h4>
          </div>
          {selected.objective && <p>{selected.objective}</p>}
          {selected.success_criteria && (
            <p className="task-node-success">
              <strong>完成标准</strong>
              {selected.success_criteria}
            </p>
          )}
          {selectedAgent && (
            <small>
              Agent：{selectedAgent.title} ·{' '}
              {statusLabel(selectedAgent.execution_status || selectedAgent.status)}
            </small>
          )}
          {selected.result && <p className="workflow-node-result">{selected.result}</p>}
          {selected.error && <p className="workflow-node-error">{selected.error}</p>}
          {selectedAgent && (
            <details className="workflow-agent-activity">
              <summary>查看节点 Agent 的执行记录</summary>
              <AgentDetail
                agent={selectedAgent}
                login={login}
                label="工作流节点 Agent"
                showCommunications={false}
              />
            </details>
          )}
        </div>
      )}
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
  login,
  lead = false,
  label,
  showCommunications = false,
}: {
  agent: ExecutionAgent;
  login: LoginState;
  lead?: boolean;
  label: string;
  showCommunications?: boolean;
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
        <p className="task-agent-brief-summary">{readableSummary(visibleAgentBrief(agent.objective))}</p>
        {visibleAgentBrief(agent.objective) !== readableSummary(visibleAgentBrief(agent.objective)) && (
          <details className="task-agent-brief">
            <summary>查看职责、约束与交付要求</summary>
            <MessageMarkdown content={visibleAgentBrief(agent.objective)} login={login} />
          </details>
        )}
        <div className="task-agent-success">
          <strong>完成标准</strong>
          <span>{agent.success_criteria}</span>
        </div>
      </section>
      {showCommunications && !!agent.communications?.length && (
        <section>
          <h4>Agent 间通信</h4>
          {agent.communications.map((message) => (
            <Communication
              key={message.id}
              message={message}
              agentID={agent.agent_id}
              login={login}
            />
          ))}
        </section>
      )}
      {!!activities.length && (
        <section>
          <h4>执行记录</h4>
          {activities.map((activity) =>
            activity.detail ? (
              <details className="task-agent-activity-line" key={activity.id}>
                <summary>
                  <span className="task-agent-activity-title">{activity.title}</span>
                  {!!activity.createdAt && (
                    <time dateTime={new Date(activity.createdAt * 1000).toISOString()}>
                      {activityTime(activity.createdAt)}
                    </time>
                  )}
                </summary>
                <MessageMarkdown content={activity.detail} login={login} />
              </details>
            ) : (
              <p className="task-agent-activity-line" key={activity.id}>
                <span>{activity.title}</span>
                {!!activity.createdAt && (
                  <time dateTime={new Date(activity.createdAt * 1000).toISOString()}>
                    {activityTime(activity.createdAt)}
                  </time>
                )}
              </p>
            ),
          )}
        </section>
      )}
      {!!activities.some((activity) => activity.tool) && (
        <details className="task-agent-tools">
          <summary>工具调用</summary>
          {activities
            .filter((activity) => activity.tool)
            .map((activity) => (
              <p key={activity.id}>
                <span>
                  {activity.title}
                  <small>{activity.tool}</small>
                </span>
                {!!activity.createdAt && (
                  <time dateTime={new Date(activity.createdAt * 1000).toISOString()}>
                    {activityTime(activity.createdAt)}
                  </time>
                )}
              </p>
            ))}
        </details>
      )}
    </details>
  );
}

function Communication({
  message,
  agentID,
  login,
}: {
  message: TeamMessage;
  agentID: string;
  login: LoginState;
}) {
  const outgoing = message.sender_agent_id === agentID;
  return (
    <div className="task-communication">
      <small>
        {message.sender_title || 'Agent'} → {message.recipient_title || 'Agent'}
        {outgoing ? '（发出）' : '（收到）'}
      </small>
      <MessageMarkdown content={message.content} login={login} />
    </div>
  );
}

function visibleAgentBrief(value: string) {
  return value
    .split('\n')
    .filter((line) => {
      const normalized = line.trim().toLowerCase();
      return (
        !normalized.startsWith('dependencies:') &&
        normalized !== 'return a bounded result for this workflow node.'
      );
    })
    .join('\n')
    .trim();
}

function readableSummary(value: string, limit = 220) {
  for (const raw of value.split('\n')) {
    let line = raw.trim();
    if (
      !line ||
      line.startsWith('```') ||
      (line.startsWith('|') && /^[|\-\s:]+$/.test(line))
    )
      continue;
    line = line
      .replace(/^[#>*\-\s•]+/, '')
      .replace(/^\|/, '')
      .replace(/\|$/, '')
      .replace(/\|/g, ' · ')
      .trim();
    if (!line) continue;
    return line.length > limit ? `${line.slice(0, limit)}…` : line;
  }
  return '';
}

function semanticActivities(agent: ExecutionAgent) {
  const result: {
    id: string;
    title: string;
    detail: string;
    tool: string;
    createdAt: number;
  }[] = [];
  const seen = new Set<string>();
  for (const entry of agent.activity?.entries || []) {
    const values = [
      ...(entry.tool_description
        ? [
            {
              title: entry.tool_description,
              tool: entry.tool || '工具',
              createdAt: activityEpoch(entry.created_at),
            },
          ]
        : []),
      ...(entry.tool_calls || []).map((call) => ({
        title: call.description || call.name,
        tool: call.name,
        createdAt: activityEpoch(entry.created_at),
      })),
    ];
    for (const value of values) {
      const key = `${value.title}|${value.tool}`;
      if (!value.title || seen.has(key)) continue;
      seen.add(key);
      result.push({
        id: `${entry.id}-${result.length}`,
        detail: '',
        ...value,
      });
    }
    if (entry.kind === 'assistant.message' && entry.content) {
      const title = readableSummary(entry.content);
      if (title && !seen.has(entry.content)) {
        seen.add(entry.content);
        result.push({
          id: `${entry.id}-message`,
          title,
          detail: entry.content,
          tool: '',
          createdAt: activityEpoch(entry.created_at),
        });
      }
    }
  }
  return result.slice(-20);
}

function activityTime(value: number) {
  if (!value) return '';
  return new Date(value * 1000).toLocaleString('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

function activityEpoch(value: number | string) {
  if (typeof value === 'number') return value > 10_000_000_000 ? value / 1000 : value;
  if (!value) return 0;
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) ? timestamp / 1000 : 0;
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

function workflowNodeSubtitle(node: WorkflowNode, names: Record<string, string>) {
  if (node.status === 'pending') {
    return node.depends_on.length
      ? `等待 ${node.depends_on.map((id) => names[id] || id).join(' + ')}`
      : '准备执行';
  }
  return (
    {
      running: '正在执行',
      paused: '执行已暂停，可调整预算后继续',
      succeeded: node.result || '已完成',
      failed: node.error || '执行失败',
      blocked: '依赖未完成',
      cancelled: '已取消',
    }[node.status] || '状态更新中'
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
