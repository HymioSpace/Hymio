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
