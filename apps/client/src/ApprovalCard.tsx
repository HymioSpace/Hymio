import { Globe2, Monitor, Terminal } from 'lucide-react';
import { useId, useState } from 'react';
import type { Approval } from '@hymio/client';

const scopes = {
  once: '仅这次',
  run: '此任务期间',
  exact_rule: '始终允许',
};
const toolLabels: Record<string, string> = {
  bash: '运行命令',
  cli: '执行云端操作',
  browser: '操作浏览器',
  computer: '操作桌面',
};
const ToolIcon = ({ tool }: { tool: string }) => {
  const Icon = tool === 'browser' ? Globe2 : tool === 'computer' ? Monitor : Terminal;
  return <Icon size={16} strokeWidth={1.7} aria-hidden="true" />;
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
  const critical = approval.tier === 'critical';
  const warning = critical ? '每次确认' : undefined;
  const preview = approvalPreview(approval);
  const metadata = [
    approval.target.label,
    waiting ? `${expiryLabel(approval.expiresAt * 1000 - clock)}后失效` : '',
  ].filter(Boolean);

  return (
    <section
      className={`approval-card risk-${approval.risk || 'medium'}`}
      aria-labelledby={titleId}
    >
      <div className="approval-header">
        <span className="approval-tool-icon">
          <ToolIcon tool={approval.tool} />
        </span>
        <div className="approval-copy">
          <div className="approval-heading">
            <h3 id={titleId}>{title}</h3>
            {warning && <span className="approval-risk">{warning}</span>}
          </div>
          <p className="approval-summary">
            {approval.summary || `Hymio 请求${toolLabels[approval.tool] || '执行操作'}。`}
          </p>
        </div>
      </div>
      {preview && (
        <div className="approval-preview" aria-label="操作预览">
          <span>{approval.tool === 'bash' ? '$' : '›'}</span>
          <code>{preview}</code>
        </div>
      )}
      {metadata.length > 0 && (
        <p className="approval-meta">
          {metadata.map((item) => (
            <span key={item}>{item}</span>
          ))}
        </p>
      )}
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
            <label className="approval-scope">
              <span className="sr-only">授权范围</span>
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
            </label>
          )}
          <button
            className="primary-button"
            disabled={!connected || pending}
            onClick={() => void onDecide(approval.id, 'approved', scope, approval.actionDigest)}
          >
            {pending ? '正在提交…' : critical ? '仅允许一次' : '允许'}
          </button>
        </div>
      )}
    </section>
  );
}

function approvalPreview(approval: Approval) {
  const arguments_ = approval.arguments;
  const value =
    approval.tool === 'bash'
      ? arguments_.command
      : approval.tool === 'browser'
        ? arguments_.url || arguments_.selector || arguments_.action
        : approval.tool === 'computer'
          ? arguments_.action
          : arguments_.operation || arguments_.action;
  return typeof value === 'string' ? value.trim().slice(0, 180) : '';
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
