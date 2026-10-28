import { ShieldCheck, Trash2 } from 'lucide-react';
import { useEffect, useState } from 'react';
import {
  forgetApproval,
  loadAuthorizationSettings,
  setAuthorizationMode,
  type AuthorizationSettings,
} from './authorization';
import type { LoginState } from './useLogin';

const labels = {
  read_only: {
    title: '只读',
    detail: '读取、查看和检查类操作直接执行；任何写入都会被阻止。',
  },
  guided: {
    title: '按需确认',
    detail: '读取自动执行；修改操作可在当前任务中确认一次，也可加入始终允许。',
  },
  autonomous: {
    title: '完全访问',
    detail: '普通读写自动执行；支付、凭据、安全设置和不可逆操作仍会确认或阻止。',
  },
};

export function ToolPermissionSettings({ login }: { login: LoginState }) {
  const [data, setData] = useState<AuthorizationSettings>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    setData(undefined);
    setError('');
    void loadAuthorizationSettings(login)
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
      setData(await setAuthorizationMode(login, mode));
    } catch {
      setError('授权模式未更改，请稍后重试');
    } finally {
      setBusy(false);
    }
  }
  async function removeRule(id: string) {
    setBusy(true);
    setError('');
    try {
      setData(await forgetApproval(login, id));
    } catch {
      setError('始终允许规则未移除，请稍后重试');
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
      <div className="authorization-rules">
        <div className="authorization-rules-heading">
          <span>始终允许</span>
          <small>{data?.rules?.length || 0}</small>
        </div>
        {!data?.rules?.length ? (
          <p>还没有长期规则。确认操作时可选择“始终允许”。</p>
        ) : (
          data.rules.map((rule) => (
            <div className="authorization-rule" key={rule.id}>
              <div>
                <strong>{rule.title}</strong>
                <span>
                  {[rule.target, rule.last_used_at ? '最近使用过' : '尚未使用']
                    .filter(Boolean)
                    .join(' · ')}
                </span>
              </div>
              <button
                className="icon-button"
                aria-label={`撤销始终允许：${rule.title}`}
                disabled={busy}
                onClick={() => void removeRule(rule.id)}
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))
        )}
      </div>
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
