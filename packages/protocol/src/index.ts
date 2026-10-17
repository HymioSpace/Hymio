export type Data = Record<string, unknown>;
export interface Command {
  v: 2;
  id: string;
  type: string;
  payload: Data;
}
export interface OathEvent {
  v: 2;
  type: 'event';
  user_id: string;
  event_seq: number;
  event_type: string;
  payload: Data;
  occur_dt: string;
}
export interface Frame {
  v: 2;
  type: string;
  id?: string;
  user_id?: string;
  payload?: Data;
  after_cursor?: number;
  through_cursor?: number;
  code?: string;
  message?: string;
}
export interface Connection {
  wsUrl: string;
  bizUrl: string;
  credential: string;
}
export interface TraceSummary {
  trace_id: string;
  span_count: number;
  step_count: number;
  duration_ms: number | null;
}
export interface Span {
  span_id: string;
  parent_span_id: string | null;
  name: string;
  status: string;
  duration_ms: number | null;
  attributes: Data;
  events: { name: string; attributes: Data }[];
  links: Data[];
}
export interface Trace {
  trace_id: string;
  duration_ms: number | null;
  spans: Span[];
}
export const obj = (v: unknown): Data =>
  v && typeof v === 'object' && !Array.isArray(v) ? (v as Data) : {};
export const str = (v: unknown): string => (typeof v === 'string' ? v : '');
export const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
export function parseFrame(raw: string): Frame | OathEvent {
  const value: unknown = JSON.parse(raw);
  const f = obj(value);
  if (f.v !== 2 || typeof f.type !== 'string') throw new Error('Oath 协议版本不匹配');
  if (
    f.type === 'event' &&
    (typeof f.user_id !== 'string' ||
      !Number.isSafeInteger(f.event_seq) ||
      Number(f.event_seq) < 1 ||
      typeof f.event_type !== 'string' ||
      !f.payload ||
      typeof f.payload !== 'object' ||
      Array.isArray(f.payload))
  ) {
    throw new Error('无效的 Oath 事件');
  }
  return value as Frame | OathEvent;
}
