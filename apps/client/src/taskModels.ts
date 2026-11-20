export type Schedule = {
  mode: string;
  timezone: string;
  at?: string;
  time?: string;
  weekday?: number;
  grace_seconds?: number;
  run_timeout_seconds?: number;
};
export type Run = {
  id: string;
  status: string;
  result: string;
  progress: string;
  wait_reason?: string;
  wait_kind?: string | null;
  error_code?: string;
  resume_at?: number;
  phase?: string;
  next_step: string;
  agent_id?: string;
  notification_status?: string;
  due_at: number | null;
  started_at?: number;
  updates: {
    note_id: string;
    content: string;
    created_at: number;
    status: string;
    phase: string;
  }[];
};
export type Work = {
  revision?: number;
  needs_attention?: boolean;
  next_due_at?: number | null;
  for_user?: boolean;
  updated_at: number;
  id: string;
  title: string;
  objective: string;
  success_criteria: string;
  state: string;
  source?: string;
  executor_kind?: string;
  execution_mode?: ExecutionMode;
  completion?: 'achieve' | 'maintain';
  scope?: 'temporary' | 'ongoing';
  close_reason?: string | null;
  kind?: 'task' | 'reminder';
  schedule: Schedule;
  runs: Run[];
  context?: { brief: string; refs: string[] };
  plan?: unknown[];
  evidence?: { kind: string; ref: string; summary: string }[];
  execution?: {
    executor: string;
    mode?: ExecutionMode;
    task_agent?: ExecutionAgent | null;
    subagents: ExecutionAgent[];
    checkpoint?: { progress?: string; next_step?: string };
    wait?: { condition?: { kind: string; reason: string } } | null;
    usage?: { steps: number; tokens: number; active_seconds: number };
    team_messages?: TeamMessage[];
    workflow?: { nodes: WorkflowNode[]; edges: { from: string; to: string }[] };
    events: { id: number; type: string; created_at: number; data: Record<string, unknown> }[];
  };
};

export type ExecutionMode = 'program' | 'parallel_subagents' | 'agent_team' | 'dynamic_workflow';
export type TaskPortfolioScope = 'ongoing' | 'temporary' | 'completed';

export type ExecutionAgent = {
  agent_id: string;
  title: string;
  role: string;
  delegation_role?: 'subagent' | 'teammate' | 'workflow_node';
  status: string;
  execution_status?: string;
  objective: string;
  success_criteria: string;
  result: string;
  notes: { note_id: string; content: string; created_at: number }[];
  activity: {
    entries: {
      id: number;
      kind: string;
      tool: string;
      tool_description?: string;
      content: string;
      status: string;
      created_at: number;
      tool_calls?: { name: string; description: string; invocation_id?: string }[];
    }[];
  };
  communications?: TeamMessage[];
};

export type TeamMessage = {
  id: string;
  sender_agent_id: string;
  recipient_agent_id: string;
  sender_title: string;
  recipient_title: string;
  content: string;
  created_at: number;
};

export type WorkflowNode = {
  id: string;
  title: string;
  objective?: string;
  success_criteria?: string;
  depends_on: string[];
  agent_id?: string;
  status: string;
  result: string;
  error?: string;
};

const modeDefinitions: Record<ExecutionMode, { label: string; description: string }> = {
  program: {
    label: '自动执行',
    description: '按时间或条件执行固定动作，不启动模型。',
  },
  parallel_subagents: {
    label: 'Agent 并行',
    description: '主 Agent 拆分独立步骤，完成后整合结果。',
  },
  agent_team: {
    label: 'Agent Team',
    description: 'Leader 与成员可以互相沟通并共同完成。',
  },
  dynamic_workflow: {
    label: '动态工作流',
    description: '先拆成有依赖关系的步骤，再按顺序自动执行。',
  },
};

export function taskExecutionMode(task: Work): ExecutionMode {
  if (task.execution_mode) return task.execution_mode;
  if (task.execution?.mode) return task.execution.mode;
  if ((task.executor_kind || task.execution?.executor) === 'program') return 'program';
  return 'parallel_subagents';
}

export function taskModeLabel(task: Work) {
  return modeDefinitions[taskExecutionMode(task)].label;
}

export function taskModeDescription(task: Work) {
  return modeDefinitions[taskExecutionMode(task)].description;
}

export function taskTemporalScope(task: Work): 'ongoing' | 'temporary' {
  if (task.scope) return task.scope;
  if (
    task.completion === 'maintain' ||
    ['daily', 'weekly', 'event'].includes(task.schedule?.mode || '')
  )
    return 'ongoing';
  return 'temporary';
}

export function taskIsCancelled(task: Work) {
  return (
    task.close_reason === 'cancelled' ||
    (['closed', 'archived'].includes(task.state) && task.runs[0]?.status === 'cancelled')
  );
}

export function taskPortfolioScope(task: Work): TaskPortfolioScope {
  const run = task.runs[0];
  if (
    ['closed', 'archived'].includes(task.state) ||
    ['succeeded', 'cancelled', 'expired'].includes(run?.status || '')
  )
    return 'completed';
  return taskTemporalScope(task);
}

export function taskNeedsAttention(task: Work) {
  const run = task.runs[0];
  return Boolean(
    task.needs_attention ||
      ['paused', 'blocked', 'failed', 'expired'].includes(run?.status || '') ||
      (run?.status === 'waiting' && run.wait_kind === 'user'),
  );
}

export function taskStatusLabel(task: Work) {
  if (task.state === 'closed') {
    if (task.close_reason === 'achieved') return '已完成';
    if (task.close_reason === 'cancelled') return '已取消';
    return '已结束';
  }
  if (task.state !== 'active') {
    return task.state === 'paused' ? '已暂停' : task.state;
  }
  const run = task.runs[0];
  if (run?.status === 'succeeded' && task.next_due_at) return '已安排';
  if (run?.status === 'waiting') {
    if (run.wait_kind === 'user') return '等待你回复';
    return taskExecutionMode(task) === 'program' ? '发送中' : '等待完成';
  }
  return (
    {
      queued: '准备中',
      running: '进行中',
      paused: '已暂停',
      blocked: '需要你处理',
      failed: '未完成',
      expired: '已过期',
      cancelled: '已取消',
      succeeded: '已完成',
    }[run?.status || 'active'] || '进行中'
  );
}
