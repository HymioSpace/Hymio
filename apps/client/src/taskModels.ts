export type Schedule = {
  mode: string;
  timezone: string;
  at?: string;
  time?: string;
  weekday?: number;
};
export type Run = {
  id: string;
  status: string;
  result: string;
  agent_id?: string;
  due_at: number;
  started_at?: number;
  updates: { note_id: string; content: string; created_at: number }[];
};
export type Work = {
  id: string;
  title: string;
  objective: string;
  success_criteria: string;
  state: string;
  schedule: Schedule;
  runs: Run[];
};
