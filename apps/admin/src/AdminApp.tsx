import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  Boxes,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  Cloud,
  ListChecks,
  LogOut,
  Monitor,
  RefreshCw,
  Search,
  ScrollText,
  ShieldCheck,
  Smartphone,
  UserRound,
  Users,
  Workflow,
} from "lucide-react";
import {
  AdminError,
  accountLogin,
  adminRequest,
  savedSession,
  saveSession,
  type Overview,
  type Session,
} from "./api";
import { Monitoring } from "./Monitoring";

const states: Record<string, string> = {
  allocated: "已分配",
  reserved: "准备中",
  outcome_unknown: "等待核对",
  releasing: "释放中",
  release_unknown: "释放待核对",
  paused: "已暂停",
  active: "运行中",
};

const messages: Record<string, string> = {
  unauthorized: "登录已过期，请重新登录。",
  administrator_required: "这个账号没有管理权限。",
  account_rejected:
    "账号或密码不正确。本地与云端是独立账号体系，请使用当前部署的管理员账号。",
  origin_denied:
    "当前管理台地址未被服务端授权，请确认访问的是该部署的正确地址。",
  device_busy_or_outcome_unknown:
    "设备有未完成的执行记录。系统不会重复原操作；过期锁会自动核对，请刷新后重试。",
  device_execution_still_running:
    "远端仍有命令在运行。完成后才能暂停或释放云电脑。",
  device_state_unknown:
    "云端状态暂时无法确认，环境与文件已保留。请稍后刷新重试。",
  device_lock_changed: "设备状态刚刚发生变化，请刷新后再试。",
  device_unavailable: "云电脑当前不可用，无法完成该操作。",
  provision_requires_recovery: "云电脑创建结果尚未确认，暂时不能释放。",
  resource_release_required: "切换供应商前，请先释放当前云主机。",
  resource_provider_unavailable: "供应商暂不可用，名额已保留，请稍后核对。",
  invalid_admin_request: "请检查输入后重试。",
};

function translated(error: unknown) {
  const code = error instanceof Error ? error.message : String(error);
  return messages[code] || `管理服务暂不可用（${code}）`;
}

function Login({ onSession }: { onSession: (session: Session) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const session = await accountLogin(username, password);
      const access = await adminRequest<{ is_admin: boolean }>("me", {
        session,
      });
      if (!access.is_admin) throw new Error("administrator_required");
      saveSession(session);
      onSession(session);
    } catch (value) {
      setError(translated(value));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-page">
      <section className="login-card">
        <div className="login-mark">
          <ShieldCheck size={25} />
        </div>
        <p className="eyebrow">HYMIO OPERATIONS</p>
        <h1>管理控制台</h1>
        <p className="login-lede">独立于用户应用的资源与运营入口。</p>
        <form onSubmit={submit}>
          <label>
            管理员账号
            <input
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              required
            />
          </label>
          <label>
            密码
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>
          {error && (
            <p className="feedback error" role="alert">
              <CircleAlert size={15} /> {error}
            </p>
          )}
          <button className="primary wide" disabled={busy}>
            {busy ? "正在验证…" : "进入管理台"}
          </button>
        </form>
        <p className="login-foot">
          权限由服务器端账号校验，页面地址本身不代表管理权限。
        </p>
      </section>
    </main>
  );
}

export function AdminApp() {
  const [session, setSession] = useState(savedSession);
  const [view, setView] = useState<"resources" | "monitoring">(
    window.location.hash.startsWith("#/monitoring")
      ? "monitoring"
      : "resources",
  );
  const [hash, setHash] = useState(window.location.hash);
  const [data, setData] = useState<Overview | null>(null);
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [selection, setSelection] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const version = useRef(0);

  useEffect(() => {
    const route = () => {
      setHash(window.location.hash);
      setView(
        window.location.hash.startsWith("#/monitoring")
          ? "monitoring"
          : "resources",
      );
    };
    window.addEventListener("hashchange", route);
    return () => window.removeEventListener("hashchange", route);
  }, []);

  const load = useCallback(async () => {
    if (!session) return;
    const current = ++version.current;
    setLoading(true);
    try {
      const value = await adminRequest<Overview>(
        `resources?q=${encodeURIComponent(query)}&offset=${offset}`,
        { session },
      );
      if (current !== version.current) return;
      setData(value);
      setError("");
    } catch (value) {
      if (current === version.current) {
        if (value instanceof AdminError && value.status === 401) {
          saveSession();
          setSession(undefined);
          setData(null);
        } else setError(translated(value));
      }
    } finally {
      if (current === version.current) setLoading(false);
    }
  }, [offset, query, session]);

  useEffect(() => {
    if (!session) {
      setLoading(false);
      return;
    }
    const timer = setTimeout(() => void load(), 220);
    return () => {
      clearTimeout(timer);
      version.current++;
    };
  }, [load, session]);

  useEffect(() => {
    if (!session) return;
    const timer = setInterval(() => void load(), 20000);
    return () => clearInterval(timer);
  }, [load, session]);

  async function mutate(
    id: string,
    path: string,
    body: object,
    message: string,
  ) {
    if (!session) return;
    setBusy(id);
    setError("");
    setNotice("");
    try {
      await adminRequest(path, { session, body });
      setNotice(message);
      await load();
    } catch (value) {
      if (value instanceof AdminError && value.status === 401) {
        saveSession();
        setSession(undefined);
        setData(null);
      } else setError(translated(value));
    } finally {
      setBusy("");
    }
  }

  function logout() {
    if (session)
      void fetch(`${window.location.origin}/auth/logout`, {
        method: "POST",
        headers: { Authorization: `Bearer ${session.access_token}` },
      }).catch(() => {});
    saveSession();
    setSession(undefined);
    setData(null);
  }

  if (!session) return <Login onSession={setSession} />;

  const providerName = (provider: string) =>
    data?.providers.find((item) => item.provider === provider)?.name ||
    provider;
  const granted = data?.users.filter((user) => user.enabled).length || 0;
  const monitoringPage =
    hash.startsWith("#/monitoring/traces") ||
    hash.startsWith("#/monitoring/trace/")
      ? "traces"
      : hash.startsWith("#/monitoring/logs")
        ? "logs"
        : hash.startsWith("#/monitoring/runbook")
          ? "runbook"
          : "overview";

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">H</div>
          <div>
            <strong>Hymio</strong>
            <small>Operations</small>
          </div>
        </div>
        <nav aria-label="管理导航">
          <p>资源</p>
          <a
            className={`nav ${view === "resources" ? "active" : ""}`}
            href="#/resources"
            onClick={() => setView("resources")}
          >
            <Boxes size={17} />
            云资源
            <span>{data?.devices.length || 0}</span>
          </a>
          <p>观测</p>
          <a
            className={`nav ${view === "monitoring" && monitoringPage === "overview" ? "active" : ""}`}
            href="#/monitoring"
            onClick={() => setView("monitoring")}
            aria-current={
              view === "monitoring" && monitoringPage === "overview"
                ? "page"
                : undefined
            }
          >
            <Activity size={17} />
            概览
          </a>
          <a
            className={`nav ${view === "monitoring" && monitoringPage === "traces" ? "active" : ""}`}
            href="#/monitoring/traces"
            onClick={() => setView("monitoring")}
            aria-current={
              view === "monitoring" && monitoringPage === "traces"
                ? "page"
                : undefined
            }
          >
            <Workflow size={17} />
            Trace 排查
          </a>
          <a
            className={`nav ${view === "monitoring" && monitoringPage === "logs" ? "active" : ""}`}
            href="#/monitoring/logs"
            onClick={() => setView("monitoring")}
            aria-current={
              view === "monitoring" && monitoringPage === "logs"
                ? "page"
                : undefined
            }
          >
            <ScrollText size={17} />
            日志中心
          </a>
          <a
            className={`nav ${view === "monitoring" && monitoringPage === "runbook" ? "active" : ""}`}
            href="#/monitoring/runbook"
            onClick={() => setView("monitoring")}
            aria-current={
              view === "monitoring" && monitoringPage === "runbook"
                ? "page"
                : undefined
            }
          >
            <ListChecks size={17} />
            排查手册
          </a>
        </nav>
        <div className="sidebar-foot">
          <div className="operator">
            <UserRound size={17} />
            <div>
              <strong>{session.name}</strong>
              <small>管理员</small>
            </div>
          </div>
          <button className="icon-button" title="退出登录" onClick={logout}>
            <LogOut size={16} />
          </button>
        </div>
      </aside>

      {view === "monitoring" ? (
        <Monitoring session={session} />
      ) : (
        <main className="workspace">
          <header className="topbar">
            <div>
              <p className="eyebrow">RESOURCE CONTROL</p>
              <h1>云资源</h1>
            </div>
            <button
              className="icon-button bordered"
              onClick={() => void load()}
              disabled={loading}
            >
              <RefreshCw size={17} className={loading ? "spin" : ""} />
            </button>
          </header>

          <section className="hero">
            <div>
              <p className="eyebrow">ACCESS POLICY</p>
              <h2>先授权，再分配。</h2>
              <p>
                新用户默认没有云主机。每位用户同时只开通一个供应商，避免重复占用与误绑定。
              </p>
            </div>
            <dl>
              <div>
                <dt>已授权</dt>
                <dd>{granted}</dd>
              </div>
              <div>
                <dt>云主机</dt>
                <dd>{data?.devices.length || 0}</dd>
              </div>
              <div>
                <dt>待处理</dt>
                <dd>
                  {data?.devices.filter((device) =>
                    ["reserved", "outcome_unknown", "release_unknown"].includes(
                      device.state,
                    ),
                  ).length || 0}
                </dd>
              </div>
            </dl>
          </section>

          {(error || notice) && (
            <div
              className={`feedback ${error ? "error" : "success"}`}
              role="status"
            >
              {error ? <CircleAlert size={16} /> : <Check size={16} />}
              <span>{error || notice}</span>
              {error && <button onClick={() => void load()}>重试</button>}
            </div>
          )}

          <section className="providers" aria-label="供应商配额">
            {data?.providers.map((provider) => (
              <article key={provider.provider}>
                <header>
                  <Cloud size={18} />
                  <strong>{provider.name}</strong>
                  <span className={provider.configured ? "online" : ""}>
                    {provider.configured ? "已连接" : "未配置"}
                  </span>
                </header>
                <p>
                  <b>{provider.used}</b> / {provider.limit} 台
                </p>
                <div className="meter">
                  <i
                    style={{
                      width: `${Math.min(100, (provider.used / Math.max(provider.limit, 1)) * 100)}%`,
                    }}
                  />
                </div>
                <small>
                  {provider.used >= provider.limit
                    ? "名额已满"
                    : "暂停与待核对设备仍占名额"}
                </small>
              </article>
            ))}
          </section>

          <section className="panel">
            <header className="panel-head">
              <div>
                <h2>
                  <Users size={18} /> 用户权限
                </h2>
                <p>停用访问会立即阻止使用，但不会暂停、删除或释放已有环境；释放请到下方云主机区域。</p>
              </div>
              <label className="search">
                <Search size={15} />
                <input
                  value={query}
                  onChange={(event) => {
                    setQuery(event.target.value);
                    setOffset(0);
                  }}
                  placeholder="用户名或 ID"
                />
              </label>
            </header>
            <div className="user-table">
              {data?.users.map((user) => {
                const chosen =
                  selection[user.user_id] || user.provider || "daytona";
                const enabled = Boolean(user.enabled);
                const unchanged = enabled && chosen === user.provider;
                const holdsDevice = data.devices.some(
                  (device) => device.user_id === user.user_id,
                );
                return (
                  <article key={user.user_id}>
                    <div className="avatar">
                      {(user.name || "?").slice(0, 1).toUpperCase()}
                    </div>
                    <div className="identity">
                      <strong>{user.name}</strong>
                      <small title={user.user_id}>{user.user_id}</small>
                    </div>
                    <span className={`access ${enabled ? "enabled" : ""}`}>
                      {enabled ? "已授权" : holdsDevice ? "未授权 · 环境保留" : "未开通"}
                    </span>
                    <select
                      value={chosen}
                      onChange={(event) =>
                        setSelection((value) => ({
                          ...value,
                          [user.user_id]: event.target.value,
                        }))
                      }
                      aria-label={`为 ${user.name} 选择供应商`}
                    >
                      {data.providers.map((provider) => (
                        <option
                          key={provider.provider}
                          value={provider.provider}
                          disabled={!provider.configured}
                        >
                          {provider.name}
                          {provider.configured ? "" : "（未配置）"}
                        </option>
                      ))}
                    </select>
                    <button
                      className={unchanged ? "quiet" : "primary"}
                      disabled={!!busy}
                      onClick={() => {
                        if (
                          unchanged &&
                          !window.confirm(
                            "停用访问会立即阻止该用户使用云电脑，但云电脑和文件仍会保留并继续占用名额。确认停用？",
                          )
                        )
                          return;
                        void mutate(
                          user.user_id,
                          "resources/grants",
                          {
                            user_id: user.user_id,
                            provider: chosen,
                            enabled: !unchanged,
                          },
                          unchanged ? "已停用云电脑访问，环境仍保留。" : "权限已更新。",
                        );
                      }}
                    >
                      {busy === user.user_id
                        ? "保存中…"
                        : unchanged
                          ? "停用访问"
                          : enabled
                            ? "切换供应商"
                            : "开通权限"}
                    </button>
                  </article>
                );
              })}
              {!loading && data?.users.length === 0 && (
                <p className="empty">没有匹配的用户。</p>
              )}
            </div>
            <footer className="pagination">
              <button
                disabled={offset === 0 || loading}
                onClick={() => setOffset(Math.max(0, offset - 50))}
              >
                <ChevronLeft size={15} /> 上一页
              </button>
              <span>第 {offset / 50 + 1} 页</span>
              <button
                disabled={!data?.next_offset || loading}
                onClick={() => setOffset(data!.next_offset!)}
              >
                下一页 <ChevronRight size={15} />
              </button>
            </footer>
          </section>

          <section className="panel">
            <header className="panel-head">
              <div>
                <h2>
                  <Monitor size={18} /> 运行中的云主机
                </h2>
                <p>释放托管环境会删除其中的文件；外部 ECS 只会解除绑定。</p>
              </div>
              <span className="count">{data?.devices.length || 0} 台</span>
            </header>
            <div className="device-grid">
              {data?.devices.map((device) => (
                <article className="device" key={device.device_id}>
                  <div className="device-title">
                    <span className="device-icon">
                      <Monitor size={19} />
                    </span>
                    <div>
                      <strong>{device.user_name}</strong>
                      <small>{providerName(device.provider)}</small>
                    </div>
                    <span className="state">
                      {device.lock_state === "running"
                        ? "执行中"
                        : device.lock_state === "stale"
                          ? "待核对"
                          : states[
                              device.state === "allocated"
                                ? device.control_state
                                : device.state
                            ] || device.state}
                    </span>
                  </div>
                  <code>{device.device_id}</code>
                  <footer>
                    {["reserved", "outcome_unknown"].includes(device.state) && (
                      <button
                        disabled={!!busy}
                        onClick={() =>
                          void mutate(
                            device.device_id,
                            `resources/devices/${device.device_id}`,
                            { action: "reconcile" },
                            "已重新核对设备。",
                          )
                        }
                      >
                        核对
                      </button>
                    )}
                    <button
                      disabled={
                        !!busy ||
                        device.state !== "allocated" ||
                        device.lock_state === "running"
                      }
                      onClick={() =>
                        void mutate(
                          device.device_id,
                          `resources/devices/${device.device_id}`,
                          {
                            action:
                              device.control_state === "paused"
                                ? "resume"
                                : "pause",
                          },
                          "设备状态已更新。",
                        )
                      }
                    >
                      {busy === device.device_id
                        ? "处理中…"
                        : device.lock_state === "running"
                          ? "执行中"
                          : device.control_state === "paused"
                            ? "恢复"
                            : "暂停"}
                    </button>
                    <button
                      className="danger"
                      disabled={!!busy || device.lock_state === "running"}
                      onClick={() => {
                        if (
                          window.confirm(
                            device.provider === "device_api"
                              ? "解除绑定？外部 ECS 与文件会保留。"
                              : "释放这台云主机？环境与文件会被删除，无法撤回。",
                          )
                        )
                          void mutate(
                            device.device_id,
                            `resources/devices/${device.device_id}`,
                            { action: "release", confirm: device.device_id },
                            "资源已释放。",
                          );
                      }}
                    >
                      {busy === device.device_id ? "处理中…" : "释放"}
                    </button>
                  </footer>
                </article>
              ))}
              {!loading && data?.devices.length === 0 && (
                <p className="empty">当前没有云主机。授权不会立即创建资源。</p>
              )}
            </div>
          </section>

          <section className="lower-grid">
            <article className="panel audit">
              <header className="panel-head">
                <div>
                  <h2>
                    <Activity size={18} /> 最近操作
                  </h2>
                  <p>只记录管理员、目标和动作，不记录凭据。</p>
                </div>
              </header>
              <ul>
                {data?.audit.map((entry, index) => (
                  <li key={`${entry.created_at}-${index}`}>
                    <i />
                    <div>
                      <strong>{entry.action}</strong>
                      <small>{entry.target}</small>
                    </div>
                    <time>
                      {new Date(entry.created_at * 1000).toLocaleString(
                        "zh-CN",
                      )}
                    </time>
                  </li>
                ))}
                {!data?.audit.length && (
                  <li className="empty">还没有管理操作。</li>
                )}
              </ul>
            </article>
            <article className="phone-card">
              <span>
                <Smartphone size={21} />
              </span>
              <div>
                <p className="eyebrow">NEXT RESOURCE</p>
                <h2>云手机</h2>
                <p>沿用同一套授权、配额和审计模型。当前阶段暂未开放。</p>
              </div>
              <small>未启用</small>
            </article>
          </section>
        </main>
      )}
    </div>
  );
}
