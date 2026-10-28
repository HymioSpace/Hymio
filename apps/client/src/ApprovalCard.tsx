import { ShieldAlert } from 'lucide-react';
import { useState } from 'react';
import type { Approval } from '@hymio/client';

const risks: Record<string, string> = {
  low: '低风险',
  medium: '需要确认',
  high: '高风险',
  critical: '受保护操作',
};

const scopes = {
  once: '允许一次',
  run: '本次任务允许',
  exact_rule: '一直允许这个操作',
};
const effectLabels: Record<string, string> = {
  execute: '执行命令',
  local_access: '访问本机文件',
  desktop_control: '控制桌面',
  browser_control: '控制浏览器',
  app_write: '修改应用数据',
  scheduled_work: '安排未来任务',
  unknown: '未分类影响',
};

export function ApprovalCard({
  approval,
  connected,
  pending,
  clock,
  onDecide,
}: {
  approval: Approval;
  connected: boolean;
  pending: boolean;
  clock: number;
  onDecide: (
    id: string,
    decision: 'approved' | 'denied',
    scope: 'once' | 'run' | 'exact_rule',
    actionDigest: string,
  ) => Promise<void>;
}) {
  const options = approval.scopeOptions.length ? approval.scopeOptions : (['once'] as const);
  const [scope, setScope] = useState<(typeof options)[number]>('once');
  const expired = approval.status === 'pending' && approval.expiresAt * 1000 <= clock;
  const waiting = approval.status === 'pending' && !expired;
  const status = expired ? '已过期，未执行' : statusLabel(approval.status);
  return (
    <section className={`approval-card risk-${approval.risk || 'medium'}`} aria-live="polite">
      <header>
        <span className="approval-icon">
          <ShieldAlert size={18} />
        </span>
        <div>
          <h3>{approval.title}</h3>
          <p>{approval.summary || `Hymio 请求使用 ${approval.tool}`}</p>
        </div>
        <span className="approval-risk">{risks[approval.risk] || approval.risk}</span>
      </header>
      <dl className="approval-facts">
        {approval.target.label && (
          <div>
            <dt>目标</dt>
            <dd>{approval.target.label}</dd>
          </div>
        )}
        {approval.effects.length > 0 && (
          <div>
            <dt>影响</dt>
            <dd>{approval.effects.map((effect) => effectLabels[effect] || effect).join('、')}</dd>
          </div>
        )}
        <div>
          <dt>状态</dt>
          <dd>{status}</dd>
        </div>
        {waiting && (
          <div>
            <dt>有效</dt>
            <dd>{expiryLabel(approval.expiresAt * 1000 - clock)}</dd>
          </div>
        )}
      </dl>
      <details className="approval-details">
        <summary>查看操作详情</summary>
        <pre>{JSON.stringify(approval.arguments, null, 2)}</pre>
      </details>
      {waiting && (
        <div className="approval-actions">
          <button
            className="secondary-button"
            disabled={!connected || pending}
            onClick={() => void onDecide(approval.id, 'denied', scope, approval.actionDigest)}
          >
            拒绝
          </button>
          {options.length > 1 && (
            <select
              aria-label="授权范围"
              value={scope}
              disabled={pending}
              onChange={(event) => setScope(event.target.value as 'once' | 'run' | 'exact_rule')}
            >
              {options.map((option) => (
                <option key={option} value={option}>
                  {scopes[option]}
                </option>
              ))}
            </select>
          )}
          <button
            className="primary-button"
            disabled={!connected || pending}
            onClick={() => void onDecide(approval.id, 'approved', scope, approval.actionDigest)}
          >
            {pending ? '正在提交…' : scopes[scope]}
          </button>
        </div>
      )}
    </section>
  );
}

function statusLabel(status: string) {
  return (
    {
      pending: '等待你的授权',
      approved: '已允许，等待执行',
      denied: '已拒绝，未执行',
      expired: '已过期，未执行',
      superseded: '授权已失效',
    }[status] || status
  );
}

function expiryLabel(milliseconds: number) {
  const seconds = Math.max(0, Math.ceil(milliseconds / 1000));
  return seconds < 60 ? `${seconds} 秒` : `${Math.ceil(seconds / 60)} 分钟`;
}
