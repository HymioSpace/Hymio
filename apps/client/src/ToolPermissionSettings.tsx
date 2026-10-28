import { ShieldCheck } from 'lucide-react';
import { useEffect, useState } from 'react';
import type { LoginState } from './useLogin';

type Settings = { mode: 'read_only' | 'guided' | 'autonomous'; modes: string[] };

const labels = {
  read_only: {
    title: '只读',
    detail: '只读取已授权来源，不修改文件、浏览器或外部数据。',
  },
  guided: {
    title: '按需授权',
    detail: '低风险操作自动执行，命令、设备控制和外部写入先询问你。',
  },
  autonomous: {
    title: '自动执行',
    detail: '精确规则和任务授权自动执行，未知或高风险操作仍会询问。',
  },
};

export function ToolPermissionSettings({ login }: { login: LoginState }) {
  const [data, setData] = useState<Settings>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function request(mode?: string) {
    const session = login.session;
    if (!session) return;
    const response = await fetch(session.backend + '/settings/tool-authorization', {
      method: mode ? 'POST' : 'GET',
      headers: {
        Authorization: 'Bearer ' + session.access_token,
        'Content-Type': 'application/json',
      },
      body: mode ? JSON.stringify({ mode }) : undefined,
      signal: AbortSignal.timeout(15000),
      redirect: 'error',
    });
    if (!response.ok) throw new Error('tool_authorization_unavailable');
    return response.json() as Promise<Settings>;
  }
  useEffect(() => {
    let active = true;
    setData(undefined);
    setError('');
    void request()
      .then((value) => {
        if (active) setData(value);
      })
      .catch(() => {
        if (active) setError('暂时无法读取工具授权设置');
      });
    return () => {
      active = false;
    };
  }, [login.session?.access_token]);
  async function save(mode: string) {
    setBusy(true);
    setError('');
    try {
      setData(await request(mode));
    } catch {
      setError('授权模式未更改，请稍后重试');
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="model-settings">
      <div className="model-setting-row">
        <span className="model-setting-icon">
          <ShieldCheck size={17} strokeWidth={1.6} />
        </span>
        <div className="model-setting-copy">
          <label htmlFor="tool-authorization-mode">工具授权</label>
          <p>{data ? labels[data.mode as keyof typeof labels]?.detail : '正在读取…'}</p>
        </div>
        <select
          id="tool-authorization-mode"
          value={data?.mode || ''}
          disabled={busy || !data}
          onChange={(event) => void save(event.target.value)}
        >
          {!data && <option value="">正在读取…</option>}
          {data?.modes.map((mode) => (
            <option key={mode} value={mode}>
              {labels[mode as keyof typeof labels]?.title || mode}
            </option>
          ))}
        </select>
      </div>
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
