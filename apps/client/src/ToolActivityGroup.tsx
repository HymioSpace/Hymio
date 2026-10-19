import { Check, ChevronRight, CircleAlert, Clock3, LoaderCircle, Terminal } from 'lucide-react';
import type { Approval, Message, ToolActivity } from '@hymio/client';
import { obj, str } from '@hymio/protocol';
import { JsonView } from './JsonView';

const names: Record<string, string> = {
  bash: '执行命令',
  devices: '查看设备',
  device_command: '查询执行结果',
  browser: '操作浏览器',
  computer: '操作桌面',
  skill: '使用技能',
};
const states: Record<string, string> = {
  expired: '授权已过期',
  succeeded: '已完成',
  running: '执行中',
  failed: '失败',
  denied: '已拒绝',
  timeout: '超时',
  timed_out: '超时',
  outcome_unknown: '结果待确认',
  pending: '等待授权',
  awaiting_approval: '等待授权',
};

function outcome(id: string, result: ToolActivity | undefined, approvals: Approval[]) {
  if (result && result.outcome !== 'running') return result.outcome;
  const permission = approvals.find((a) => a.id === id);
  if (permission?.status === 'pending')
    return permission.expiresAt * 1000 <= Date.now() ? 'expired' : 'awaiting_approval';
  if (!result || result.outcome === 'running') {
    if (permission?.status === 'denied') return 'denied';
    return 'running';
  }
  return result.outcome;
}
export function ToolCalls({
  message,
  tools,
  approvals = [],
}: {
  message: Message;
  tools: ToolActivity[];
  approvals?: Approval[];
}) {
  return (
    <div className="tool-pills">
      {message.calls?.map((call, i) => {
        const args = obj(call.arguments);
        const result = tools.find((t) => t.id === `${message.stepId}-${i}`);
        const state = outcome(`${message.stepId}-${i}`, result, approvals);
        const name = str(call.name);
        const hint = name === 'skill' ? str(args.query) || str(args.name) : str(args.action);
        return (
          <details key={i} className="tool-call-detail">
            <summary>
              <Terminal size={13} />
              <strong>{names[name] || name}</strong>
              {hint && <span className="tool-call-hint">{hint}</span>}
              <span>{states[state] || state}</span>
              <ChevronRight size={12} className="tool-chevron" />
            </summary>
            <div className="tool-call-content">
              <p>工具：{name}</p>
              <JsonView value={args} />
              {result?.result && (
                <>
                  <p>返回结果</p>
                  <JsonView value={result.result} />
                </>
              )}
            </div>
          </details>
        );
      })}
    </div>
  );
}

export function ToolActivityGroup({
  messages,
  tools,
  approvals = [],
}: {
  messages: Message[];
  tools: ToolActivity[];
  approvals?: Approval[];
}) {
  const calls = messages.flatMap((m) =>
    (m.calls || []).map((_, i) => ({
      call: m.calls![i],
      state: outcome(
        `${m.stepId}-${i}`,
        tools.find((t) => t.id === `${m.stepId}-${i}`),
        approvals,
      ),
    })),
  );
  const running = calls.find((c) => c.state === 'running');
  const waiting = calls.some((c) => c.state === 'awaiting_approval');
  const failed = calls.some((c) =>
    ['failed', 'denied', 'timeout', 'timed_out', 'outcome_unknown', 'expired'].includes(c.state),
  );
  const label = running
    ? `${names[str(running.call.name)] || str(running.call.name)}…`
    : waiting
      ? '等待你的授权'
      : failed
        ? '工具活动 · 有结果需要查看'
        : '已完成工具活动';
  return (
    <details className="activity-group" data-testid="tool-activity-group">
      <summary>
        {running ? (
          <LoaderCircle size={14} className="spin" />
        ) : waiting ? (
          <Clock3 size={14} />
        ) : failed ? (
          <CircleAlert size={14} />
        ) : (
          <Check size={14} />
        )}
        <span aria-live="polite">{label}</span>
        <span className="activity-count">{calls.length} 次调用</span>
        <ChevronRight size={13} className="activity-chevron" />
      </summary>
      <div className="activity-items">
        {messages.map((m) => (
          <ToolCalls key={m.id} message={m} tools={tools} approvals={approvals} />
        ))}
      </div>
    </details>
  );
}

export function groupMessages(messages: Message[]): Message[][] {
  const groups: Message[][] = [];
  for (const message of messages) {
    const toolOnly =
      message.role === 'assistant' && !message.content.trim() && !!message.calls?.length;
    const previous = groups.at(-1);
    const head = previous?.[0];
    if (toolOnly && head?.role === 'assistant' && !head.content.trim() && head.calls?.length)
      previous!.push(message);
    else groups.push([message]);
  }
  return groups;
}
