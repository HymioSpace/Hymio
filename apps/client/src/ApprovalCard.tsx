import { useId, useState } from 'react';
import type { Approval } from '@hymio/client';

const warningRisks: Record<string, string> = {
  high: '高风险',
  critical: '受保护操作',
};

const scopes = {
  once: '仅这次',
  run: '本次任务',
  exact_rule: '始终允许',
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
const toolLabels: Record<string, string> = {
  bash: '运行命令',
  cli: '执行云端操作',
  browser: '操作浏览器',
  computer: '操作桌面',
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
  const titleId = useId();
  const options = approval.scopeOptions.length ? approval.scopeOptions : (['once'] as const);
  const [scope, setScope] = useState<(typeof options)[number]>('once');
  const expired = approval.status === 'pending' && approval.expiresAt * 1000 <= clock;
  const waiting = approval.status === 'pending' && !expired;
  const title = displayTitle(approval);
  const warning = warningRisks[approval.risk];
  const metadata = [
    approval.target.label,
    approval.effects.map((effect) => effectLabels[effect] || effect).join('、'),
    waiting ? `${expiryLabel(approval.expiresAt * 1000 - clock)}后失效` : '',
  ].filter(Boolean);

  return (
    <section
      className={`approval-card risk-${approval.risk || 'medium'}`}
      aria-labelledby={titleId}
    >
      <div className="approval-copy">
        <div className="approval-heading">
          <h3 id={titleId}>{title}</h3>
          {warning && <span className="approval-risk">{warning}</span>}
        </div>
        <p className="approval-summary">
          {approval.summary || `Hymio 请求${toolLabels[approval.tool] || '执行操作'}。`}
        </p>
        {metadata.length > 0 && (
          <p className="approval-meta">
            {metadata.map((item) => (
              <span key={item}>{item}</span>
            ))}
          </p>
        )}
      </div>
      <details className="approval-details">
        <summary>操作详情</summary>
        <pre>{JSON.stringify(approval.arguments, null, 2)}</pre>
      </details>
      {waiting && (
        <div className="approval-actions">
          <button
            className="approval-reject"
            disabled={!connected || pending}
            onClick={() => void onDecide(approval.id, 'denied', scope, approval.actionDigest)}
          >
            {pending ? '正在提交…' : '拒绝'}
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
            {pending ? '正在提交…' : '允许'}
          </button>
        </div>
      )}
    </section>
  );
}

function displayTitle(approval: Approval) {
  const title = approval.title.trim();
  const description = approval.arguments.description;
  const toolLabel = toolLabels[approval.tool] || approval.tool;
  if (
    typeof description === 'string' &&
    description.trim() &&
    (!title ||
      title === approval.tool ||
      title === `允许运行 ${approval.tool}？` ||
      title === `Allow ${approval.tool}?`)
  ) {
    return description.trim();
  }
  return title || `允许${toolLabel}？`;
}

function expiryLabel(milliseconds: number) {
  const seconds = Math.max(0, Math.ceil(milliseconds / 1000));
  return seconds < 60 ? `${seconds} 秒` : `${Math.ceil(seconds / 60)} 分钟`;
}
