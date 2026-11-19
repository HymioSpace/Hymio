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
  close_reason?: string | null;
  kind?: 'task' | 'reminder';
  schedule: Schedule;
  runs: Run[];
  context?: { brief: string; refs: string[] };
  plan?: unknown[];
  evidence?: { kind: string; ref: string; summary: string }[];
  execution?: {
    executor: string;
    task_agent?: ExecutionAgent | null;
    subagents: ExecutionAgent[];
    checkpoint?: { progress?: string; next_step?: string };
    wait?: { condition?: { kind: string; reason: string } } | null;
    usage?: { steps: number; tokens: number; active_seconds: number };
    events: { id: number; type: string; created_at: number; data: Record<string, unknown> }[];
  };
};

export type ExecutionAgent = {
  agent_id: string;
  title: string;
  role: string;
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
      content: string;
      status: string;
      created_at: number;
    }[];
  };
};
