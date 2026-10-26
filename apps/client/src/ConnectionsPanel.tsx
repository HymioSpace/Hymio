import { useEffect, useState } from 'react';
import {
  ArrowLeft,
  ArrowUpRight,
  Check,
  ChevronRight,
  Clock3,
  Link2,
  LockKeyhole,
  RefreshCw,
  ShieldCheck,
  Smartphone,
  Unplug,
} from 'lucide-react';
import gmailLogo from './assets/connectors/gmail.png';
import didaLogo from './assets/connectors/dida.png';
import type { LoginState } from './useLogin';
import './connections.css';

type Provider = {
  id: string;
  name: string;
  summary: string;
  transport: string;
  configured: boolean;
  permissions: string[];
  platforms: string[];
};
type Connection = {
  id: string;
  provider: string;
  name: string;
  device_id: string;
  state: string;
  enabled: boolean;
  last_success: number | null;
  next_sync: number | null;
  item_count: number;
  pending_count: number;
  error: string;
  runs: { id: string; started_at: number; status: string; received: number; error: string }[];
};
const labels: Record<string, string> = {
  ready: '已连接',
  syncing: '同步中',
  queued: '等待同步',
  waiting_device: '等待 iPhone 同步',
  authorization_required: '需要重新授权',
  paused: '已暂停',
  retrying: '稍后重试',
  disconnected: '已断开',
};
export const connectorPreview = {
  providers: [
    {
      id: 'gmail',
      name: 'Gmail',
      summary: '让邮件里的安排和线索，有迹可循。',
      transport: 'oauth',
      configured: true,
      platforms: ['web', 'ios'],
      permissions: ['读取最近收件箱及后续变化', '不发送、修改或删除邮件'],
    },
    {
      id: 'dida',
      name: '滴答清单',
      summary: '把清单里的待办，带进日常对话。',
      transport: 'oauth',
      configured: true,
      platforms: ['web', 'ios'],
      permissions: ['读取项目和任务', '不修改或完成外部任务'],
    },
    {
      id: 'apple_calendar',
      name: 'Apple 日历',
      summary: '知道你的安排，留出合适的空隙。',
      transport: 'device',
      configured: true,
      platforms: ['ios'],
      permissions: ['只读所选日历', '在 iPhone 上授权与同步'],
    },
    {
      id: 'apple_health',
      name: 'Apple 健康',
      summary: '从步数与活动量，了解生活的节奏。',
      transport: 'device',
      configured: true,
      platforms: ['ios'],
      permissions: ['每日步数与活动能量', '仅同步你确认分享的数据'],
    },
  ],
  connections: [
    {
      id: 'sample',
      provider: 'gmail',
      name: '个人邮箱',
      device_id: '',
      state: 'ready',
      enabled: true,
      last_success: Date.now() / 1000 - 120,
      next_sync: Date.now() / 1000 + 780,
      item_count: 24,
      pending_count: 0,
      error: '',
      runs: [
        {
          id: 'sample-run',
          started_at: Date.now() / 1000 - 120,
          status: 'succeeded',
          received: 8,
          error: '',
        },
      ],
    },
  ],
};
export function ConnectionsPanel({
  login,
  preview = false,
  onBack,
}: {
  login?: LoginState;
  preview?: boolean;
  onBack: () => void;
}) {
  const [data, setData] = useState<{ providers: Provider[]; connections: Connection[] }>(
    preview ? connectorPreview : { providers: [], connections: [] },
  );
  const [selected, setSelected] = useState('');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [consent, setConsent] = useState(false);
  async function api(path = '', body?: object) {
    if (!login?.session) throw new Error('请先登录');
    const r = await fetch(login.session.backend + '/connectors' + path, {
      method: body ? 'POST' : 'GET',
      headers: {
        Authorization: 'Bearer ' + login.session.access_token,
        'Content-Type': 'application/json',
      },
      body: body ? JSON.stringify(body) : undefined,
      signal: AbortSignal.timeout(20000),
    });
    const value = await r.json();
    if (!r.ok)
      throw new Error(
        value.error === 'provider_not_configured'
          ? '部署者尚未配置此服务的授权。'
          : value.error === 'reconnect_required'
            ? '请重新连接并授权。'
            : '操作未完成，请稍后重试。',
      );
    return value;
  }
  async function load() {
    try {
      setData(await api());
      setError('');
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    if (preview) return;
    void load();
    const id = window.setInterval(() => void load(), 15000);
    const focus = () => void load();
    window.addEventListener('focus', focus);
    return () => {
      clearInterval(id);
      window.removeEventListener('focus', focus);
    };
  }, [login?.session?.user_id, preview]);
  const provider = data.providers.find((p) => p.id === selected);
  const connected = data.connections.filter((c) => c.provider === selected);
  async function connect() {
    if (!provider || !consent || preview) return;
    const popup = window.open('', '_blank');
    if (popup) popup.opener = null;
    setBusy(provider.id);
    setError('');
    try {
      const row =
        connected.find((c) => c.state === 'authorization_required') ||
        (await api('', { provider: provider.id, consent: true }));
      const auth = await api('/' + row.id + '/authorize', {});
      if (popup) popup.location.replace(auth.url);
      else window.location.assign(auth.url);
      await load();
    } catch (e) {
      popup?.close();
      setError((e as Error).message);
    } finally {
      setBusy('');
    }
  }
  async function action(c: Connection, name: string) {
    if (preview) return;
    setBusy(c.id);
    try {
      const result = await api('/' + c.id, { action: name });
      await load();
      if (result.revocation === 'not_confirmed')
        setError('Hymio 已停止同步并移除凭据；服务端撤权未确认，可在服务账号设置中移除授权。');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy('');
    }
  }
  const connectionFor = (id: string) =>
    data.connections.find((c) => c.provider === id && c.state !== 'disconnected');
  function card(p: Provider) {
    const c = connectionFor(p.id);
    const state = c
      ? labels[c.state] || c.state
      : !p.configured
        ? '待部署者配置'
        : p.transport === 'device'
          ? 'iPhone 同步'
          : '尚未连接';
    return (
      <button
        key={p.id}
        className={`source-card ${selected === p.id ? 'selected' : ''} ${p.transport === 'device' ? 'device-source' : ''}`}
        onClick={() => {
          setSelected(p.id);
          setConsent(false);
        }}
      >
        <div className="source-card-heading">
          <SourceIcon id={p.id} />
          <span className={`source-status ${c?.state === 'ready' ? 'positive' : ''}`}>
            <i />
            {state}
          </span>
        </div>
        <strong>{p.name}</strong>
        <p>{p.summary}</p>
        <div className="source-card-footer">
          <span>
            {c
              ? `${c.item_count} 条来源记录`
              : p.transport === 'device'
                ? '在手机上选择分享范围'
                : '由你授权，只读同步'}
          </span>
          <span className="source-card-open">
            {c ? '查看' : p.transport === 'device' ? '了解' : p.configured ? '连接' : '设置'}
            <ChevronRight size={14} />
          </span>
        </div>
      </button>
    );
  }
  return (
    <section className="connections-panel" aria-label="连接来源">
      <header className="connections-header">
        <button onClick={onBack} aria-label="返回账号设置">
          <ArrowLeft size={17} />
        </button>
        <span>连接来源</span>
        <button onClick={() => !preview && void load()} aria-label="刷新连接">
          <RefreshCw size={16} />
        </button>
      </header>
      <div className="connections-page-heading">
        <div>
          <h2>连接你的日常</h2>
          <p>邮件、计划与生活节奏，由你决定分享。</p>
        </div>
        <span className="connection-privacy-pill">
          <ShieldCheck size={15} />
          逐项授权 · 随时断开
        </span>
      </div>
      {error && (
        <p role="alert" className="connections-error">
          {error}
          <button onClick={() => void load()}>重试</button>
        </p>
      )}
      <div className={`connections-workspace ${provider ? 'detail-open' : ''}`}>
        <div className="connections-library">
          <div className="connection-section-heading">
            <h3>云端服务</h3>
            <p>账号授权后，由云端同步新的变化。</p>
          </div>
          <div className="connection-catalog">
            {data.providers.filter((p) => p.transport === 'oauth').map(card)}
          </div>
          <div className="connection-section-heading device-heading">
            <h3>来自 iPhone</h3>
            <p>权限留在设备上，只分享你选中的部分。</p>
          </div>
          <div className="connection-catalog">
            {data.providers.filter((p) => p.transport === 'device').map(card)}
          </div>
          {!data.providers.length && !error && (
            <p className="connection-footnote">正在读取可连接的来源…</p>
          )}
          <div className="connection-principle">
            <LockKeyhole size={17} />
            <p>
              连接不代表交出控制。
              <br />
              Hymio 只读这些来源，不会代发邮件或修改外部任务。
            </p>
          </div>
        </div>
        {provider ? (
          <aside className="connection-inspector" aria-label="来源详情">
            <button className="inspector-back" onClick={() => setSelected('')}>
              <ArrowLeft size={14} />
              所有来源
            </button>
            <div className="connection-detail-intro">
              <SourceIcon id={provider.id} />
              <h3>{provider.name}</h3>
              <p>{provider.summary}</p>
            </div>
            {connected.map((c) => (
              <article key={c.id} className="connection-account">
                <div className="connection-account-name">
                  <strong>{c.name}</strong>
                  <span className={'source-status ' + (c.state === 'ready' ? 'positive' : '')}>
                    <i />
                    {labels[c.state] || c.state}
                  </span>
                </div>
                <div className="connection-stats">
                  <div>
                    <strong>{c.item_count}</strong>
                    <span>来源记录</span>
                  </div>
                  <div>
                    <strong>{c.pending_count}</strong>
                    <span>待写入记忆</span>
                  </div>
                  <div>
                    <strong>只读</strong>
                    <span>访问权限</span>
                  </div>
                </div>
                <p className="connection-last-sync">
                  <Clock3 size={12} />
                  {c.last_success
                    ? '最近同步 ' + new Date(c.last_success * 1000).toLocaleString()
                    : '尚未完成首次同步'}
                </p>
                {c.state === 'waiting_device' && (
                  <p className="connection-footnote">
                    在已连接的 iPhone 上打开 Hymio，同步后即可查看。
                  </p>
                )}
                {c.error && (
                  <p className="connections-error">
                    {c.error === 'reconnect_required'
                      ? '服务授权已失效，请重新连接。'
                      : '同步遇到问题，系统会保留进度并重试。'}
                  </p>
                )}
                {c.enabled &&
                  provider.transport === 'oauth' &&
                  c.state !== 'authorization_required' && (
                    <div className="connection-actions">
                      <button disabled={!!busy} onClick={() => void action(c, 'sync')}>
                        <RefreshCw size={14} />
                        立即同步
                      </button>
                      <button disabled={!!busy} onClick={() => void action(c, 'pause')}>
                        暂停
                      </button>
                    </div>
                  )}
                {c.state === 'paused' && (
                  <button className="connection-resume" onClick={() => void action(c, 'resume')}>
                    恢复同步
                  </button>
                )}
                {c.runs.length > 0 && (
                  <div className="connection-runs">
                    <h4>最近同步</h4>
                    {c.runs.slice(0, 3).map((r) => (
                      <div key={r.id}>
                        <span className={'run-dot ' + (r.status === 'succeeded' ? 'done' : '')}>
                          <Check size={10} />
                        </span>
                        <span>
                          {r.status === 'succeeded'
                            ? `已接收 ${r.received} 条记录`
                            : r.status === 'failed'
                              ? '未完成，保留进度'
                              : '同步处理中'}
                        </span>
                        <time>
                          {new Date(r.started_at * 1000).toLocaleTimeString([], {
                            hour: '2-digit',
                            minute: '2-digit',
                          })}
                        </time>
                      </div>
                    ))}
                  </div>
                )}
                {c.state !== 'disconnected' && (
                  <button
                    className="connection-disconnect"
                    onClick={() => {
                      if (window.confirm('断开后停止同步并移除凭据。已导入的记录会保留。'))
                        void action(c, 'disconnect');
                    }}
                  >
                    <Unplug size={13} />
                    断开连接
                  </button>
                )}
              </article>
            ))}
            <div className="connection-permissions">
              <h4>
                分享的范围<span>只读</span>
              </h4>
              {provider.permissions.map((p) => (
                <div key={p}>
                  <span className="permission-check">
                    <Check size={13} />
                  </span>
                  <p>{p}</p>
                </div>
              ))}
            </div>
            {provider.transport === 'device' ? (
              <div className="connection-device-note">
                <Smartphone size={21} />
                <div>
                  <strong>在 iPhone 上连接</strong>
                  <p>手机授权后，在这里查看同步进展。Web 不会请求本机健康或日历权限。</p>
                </div>
              </div>
            ) : !provider.configured ? (
              <div className="connection-device-note">
                <LockKeyhole size={19} />
                <div>
                  <strong>等待部署者配置</strong>
                  <p>此部署尚未设置 {provider.name} OAuth 应用，配置后即可连接。</p>
                </div>
              </div>
            ) : (
              <div className="connection-consent">
                <label>
                  <input
                    type="checkbox"
                    checked={consent}
                    onChange={(e) => setConsent(e.target.checked)}
                  />
                  <span>
                    同意将上述来源同步至 Hymio，保存为个人上下文，供助手及配置的 AI 模型使用。
                  </span>
                </label>
                <button
                  className="connection-primary"
                  disabled={!consent || !!busy || preview}
                  onClick={() => void connect()}
                >
                  {connected.some((c) => c.state === 'authorization_required')
                    ? '重新连接'
                    : connected.length
                      ? '连接另一个账号'
                      : '连接'}{' '}
                  {provider.name}
                  <ArrowUpRight size={15} />
                </button>
              </div>
            )}
          </aside>
        ) : (
          <aside className="connection-inspector connection-inspector-empty">
            <div className="inspector-empty-symbol">
              <Link2 size={24} />
            </div>
            <h3>一点连接，多一点了解。</h3>
            <p>选一个来源，查看分享范围与同步方式。授权前不会读取数据。</p>
            <span>
              <ShieldCheck size={14} />
              每一项都由你决定
            </span>
          </aside>
        )}
      </div>
    </section>
  );
}
function SourceIcon({ id }: { id: string }) {
  return (
    <span className={`connection-brand ${id}`}>
      {id === 'gmail' ? (
        <img src={gmailLogo} alt="" />
      ) : id === 'dida' ? (
        <img src={didaLogo} alt="" />
      ) : id === 'apple_calendar' ? (
        <span className="calendar-brand">
          <small>日历</small>
          <b>{new Date().getDate()}</b>
        </span>
      ) : id === 'apple_health' ? (
        <svg viewBox="0 0 32 32" aria-hidden="true">
          <defs>
            <linearGradient id="health-brand-gradient" x1="0" y1="0" x2="0" y2="1">
              <stop stopColor="#ff5b9a" />
              <stop offset="1" stopColor="#ff244e" />
            </linearGradient>
          </defs>
          <path
            fill="url(#health-brand-gradient)"
            d="M16 28C12 24.5 3 18.5 3 11.5 3 6.5 6.5 4 10 4c2.8 0 4.8 1.5 6 3.5C17.2 5.5 19.2 4 22 4c3.5 0 7 2.5 7 7.5C29 18.5 20 24.5 16 28Z"
          />
        </svg>
      ) : (
        <Link2 size={24} />
      )}
    </span>
  );
}
