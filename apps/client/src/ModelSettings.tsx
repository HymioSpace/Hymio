import { SlidersHorizontal } from 'lucide-react';
import { useEffect, useState } from 'react';
import type { LoginState } from './useLogin';
export function ModelSettings({ login }: { login: LoginState }) {
  const [models, setModels] = useState<string[]>([]),
    [selected, setSelected] = useState('');
  const [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  async function request(model?: string) {
    const session = login.session;
    if (!session) return;
    const response = await fetch(session.backend + '/settings/models', {
      method: model ? 'POST' : 'GET',
      headers: {
        Authorization: 'Bearer ' + session.access_token,
        'Content-Type': 'application/json',
      },
      body: model ? JSON.stringify({ model }) : undefined,
      signal: AbortSignal.timeout(15000),
      redirect: 'error',
    });
    if (!response.ok) throw new Error('暂时无法读取模型设置');
    return response.json() as Promise<{ models: string[]; selected: string }>;
  }
  useEffect(() => {
    let active = true;
    void request()
      .then((data) => {
        if (active && data) {
          setModels(data.models);
          setSelected(data.selected);
        }
      })
      .catch(() => {
        if (active) setError('暂时无法读取模型设置');
      });
    return () => {
      active = false;
    };
  }, [login.session?.access_token]);
  async function change(model: string) {
    setBusy(true);
    setError('');
    try {
      const data = await request(model);
      if (data) setSelected(data.selected);
    } catch {
      setError('保存失败，模型未更换');
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
          value={selected}
          disabled={busy || !models.length}
          onChange={(event) => void change(event.target.value)}
        >
          {!models.length && <option value="">正在读取…</option>}
          {models.map((model) => (
            <option key={model}>{model}</option>
          ))}
        </select>
      </div>
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
