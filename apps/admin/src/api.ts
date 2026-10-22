export type Session = {
  access_token: string;
  refresh_token: string;
  expires_at: number;
  user_id: string;
  name: string;
};

export type Provider = {
  provider: string;
  name: string;
  limit: number;
  used: number;
  configured: boolean;
};

export type User = {
  user_id: string;
  name: string;
  provider: string | null;
  enabled: number | null;
};

export type Device = {
  device_id: string;
  user_id: string;
  user_name: string;
  provider: string;
  state: string;
  control_state: string;
  lock_state: "idle" | "running" | "stale";
  updated_at: number;
};

export type Audit = {
  actor: string;
  target: string;
  action: string;
  created_at: number;
};

export type Overview = {
  providers: Provider[];
  users: User[];
  devices: Device[];
  next_offset: number | null;
  phone: { enabled: boolean };
  audit: Audit[];
};

export type Latency = Record<
  string,
  { "50"?: number; "95"?: number; "99"?: number }
>;

export type ChannelSummary = {
  channel: string;
  turns: number;
  acknowledged: number;
  first_response: number;
  renderable: number;
  terminal: number;
  traced: number;
  completed: number;
  failed: number;
  cancelled: number;
  partial: number;
  stalled: number;
  outcomes: Record<string, number>;
  no_ack: number;
  no_delta: number;
  latency: Latency;
  steps_avg: number | null;
  tools_avg: number | null;
  tool_success_rate: number | null;
  tool_ms_avg: number | null;
};

export type ClientTurn = {
  user_id: string;
  user_name: string;
  message_id: string;
  channel: string;
  client_id: string;
  device_id: string;
  trace_id: string;
  sent_at: number;
  accepted_ms: number | null;
  first_response_ms: number | null;
  first_renderable_ms: number | null;
  first_paint_ms: number | null;
  completed_ms: number | null;
  outcome: string;
  step_count: number | null;
  model_calls: number | null;
  tool_calls: number | null;
  tool_successes: number | null;
  tool_ms: number | null;
  received_at: number;
};

export type MonitoringOverview = {
  client: {
    window_hours: number;
    channels: ChannelSummary[];
    recent: ClientTurn[];
  };
  prometheus: {
    available: boolean;
    active: {
      name: string;
      state: "firing" | "pending";
      severity: string;
      summary: string;
      active_at: string;
      value: string;
    }[];
    rule_errors: { name: string; health: string; group: string }[];
    metrics: Record<
      string,
      { labels: Record<string, string>; value: string }[]
    >;
  };
  grafana_url: string;
};

export type PromSeries = {
  name: string;
  available: boolean;
  hours: number;
  series: {
    metric: Record<string, string>;
    values: [number, string][];
  }[];
};

export type TraceNode = {
  trace_id: string;
  span_id: string;
  parent_span_id: string | null;
  name: string;
  kind: string;
  status: string;
  start_unix_nano: number;
  end_unix_nano: number | null;
  duration_ms: number | null;
  attributes: Record<string, unknown>;
  events: {
    name: string;
    unix_nano: number;
    attributes: Record<string, unknown>;
  }[];
  links: {
    trace_id: string;
    span_id: string;
    attributes: Record<string, unknown>;
  }[];
};

export type TraceDetail = {
  trace_id: string;
  duration_ms: number | null;
  spans: TraceNode[];
};

export type TraceSearchMatch = ClientTurn & {
  matched_spans: number;
  match_count: number;
  matches: {
    span_id: string;
    span_name: string;
    event_name: string;
    unix_nano: number | null;
    snippet: string;
    source: "application" | "otel";
  }[];
};

export type TraceSearchResponse = {
  query: string;
  hours: number;
  channel: string;
  scanned: number;
  failed: number;
  matched: number;
  traces: TraceSearchMatch[];
};

const storageKey = "hymio.admin.session";
const backend = window.location.origin;

export class AdminError extends Error {
  constructor(
    public code: string,
    public status: number,
  ) {
    super(code);
  }
}

export function savedSession(): Session | undefined {
  try {
    return (
      JSON.parse(sessionStorage.getItem(storageKey) || "null") || undefined
    );
  } catch {
    return undefined;
  }
}

export function saveSession(value?: Session) {
  if (value) sessionStorage.setItem(storageKey, JSON.stringify(value));
  else sessionStorage.removeItem(storageKey);
}

async function parse(response: Response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok)
    throw new AdminError(
      String(data.error || `request_failed_${response.status}`),
      response.status,
    );
  return data;
}

export async function accountLogin(
  username: string,
  password: string,
): Promise<Session> {
  const response = await fetch(`${backend}/auth/account`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: "login", username, password }),
    signal: AbortSignal.timeout(15000),
  });
  return parse(response);
}

export async function refreshSession(session: Session): Promise<Session> {
  const response = await fetch(`${backend}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: session.refresh_token }),
    signal: AbortSignal.timeout(15000),
  });
  return parse(response);
}

export async function adminRequest<T>(
  path: string,
  options: { session: Session; body?: object },
): Promise<T> {
  let session = options.session;
  if (session.expires_at * 1000 <= Date.now() + 1500) {
    session = await refreshSession(session);
    saveSession(session);
  }
  const response = await fetch(`${backend}/admin/api/${path}`, {
    method: options.body ? "POST" : "GET",
    headers: {
      Authorization: `Bearer ${session.access_token}`,
      "Content-Type": "application/json",
    },
    body: options.body ? JSON.stringify(options.body) : undefined,
    signal: AbortSignal.timeout(options.body ? 130000 : 15000),
  });
  return parse(response);
}
