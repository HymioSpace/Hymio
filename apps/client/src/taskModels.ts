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
  resume_at?: number;
  phase: string;
  next_step: string;
  agent_id?: string;
  due_at: number;
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
  updated_at: number;
  id: string;
  title: string;
  objective: string;
  success_criteria: string;
  state: string;
  source: string;
  kind?: 'task' | 'reminder';
  schedule: Schedule;
  runs: Run[];
};
