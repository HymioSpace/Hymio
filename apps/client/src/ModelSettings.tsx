import { Layers3, SlidersHorizontal } from 'lucide-react';
import { useEffect, useState } from 'react';
import type { LoginState } from './useLogin';
type Preferences = {
  models: string[];
  selected: string;
  context_windows: number[];
  context_window: number;
  effective_context_window: number;
};
const windowLabel = (value: number) => (value >= 1_000_000 ? '1M' : `${value / 1000}K`);
export function ModelSettings({ login }: { login: LoginState }) {
  const [data, setData] = useState<Preferences>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function request(change?: { model?: string; context_window?: number }) {
    const session = login.session;
    if (!session) return;
    const response = await fetch(session.backend + '/settings/models', {
      method: change ? 'POST' : 'GET',
      headers: {
        Authorization: 'Bearer ' + session.access_token,
        'Content-Type': 'application/json',
      },
      body: change ? JSON.stringify(change) : undefined,
      signal: AbortSignal.timeout(15000),
      redirect: 'error',
    });
    if (!response.ok) throw new Error('暂时无法读取设置');
    return response.json() as Promise<Preferences>;
  }
  useEffect(() => {
    let active = true;
    setData(undefined);
    void request()
      .then((value) => {
        if (active) setData(value);
      })
      .catch(() => {
        if (active) setError('暂时无法读取设置');
      });
    return () => {
      active = false;
    };
  }, [login.session?.access_token]);
  async function change(value: { model?: string; context_window?: number }) {
    setBusy(true);
    setError('');
    try {
      setData(await request(value));
    } catch {
      setError('保存失败，设置未更改');
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="model-settings">
      <div className="model-setting-row">
        <span className="model-setting-icon">
          <SlidersHorizontal size={17} strokeWidth={1.6} />
        </span>
        <div className="model-setting-copy">
          <label htmlFor="chat-model">对话模型</label>
          <p>保留对话，下次发送时生效</p>
        </div>
        <select
          id="chat-model"
          value={data?.selected ?? ''}
          disabled={busy || !data}
          onChange={(event) => void change({ model: event.target.value })}
        >
          {!data && <option value="">正在读取…</option>}
          {data?.models.map((model) => (
            <option key={model}>{model}</option>
          ))}
        </select>
      </div>
      <div className="model-setting-row">
        <span className="model-setting-icon">
          <Layers3 size={17} strokeWidth={1.6} />
        </span>
        <div className="model-setting-copy">
          <label htmlFor="context-window">上下文长度</label>
          <p>
            {data && data.effective_context_window < data.context_window
              ? `当前模型最多使用 ${windowLabel(data.effective_context_window)}`
              : '较短更轻快，较长保留更多近期细节'}
          </p>
        </div>
        <select
          id="context-window"
          value={data?.context_window ?? 256_000}
          disabled={busy || !data}
          onChange={(event) => void change({ context_window: Number(event.target.value) })}
        >
          {(data?.context_windows ?? [256_000]).map((size) => (
            <option key={size} value={size}>
              {windowLabel(size)}
              {size === 256_000 ? '（默认）' : ''}
            </option>
          ))}
        </select>
      </div>
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
