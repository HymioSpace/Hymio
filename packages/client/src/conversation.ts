import type { Pending } from './storage';
import { obj, str, list, type Data, type OathEvent } from '@hymio/protocol';
import { parseQuickReplies } from './quick-replies.ts';
export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  rawContent?: string;
  suggestions?: string[];
  time: string;
  streaming?: boolean;
  attempt?: number;
  stepId?: string;
  /** step.status 里的 trace_id：同一条 trace 的多个 step 属于同一次工作。 */
  traceId?: string;
  calls?: Data[];
  reasoning?: string;
  thinking?: boolean;
  eventSeq?: number;
  delivery?: 'queued' | 'accepted' | 'failed';
  reactions?: Record<string, string | null>;
}
export interface Approval {
  id: string;
  tool: string;
  arguments: Data;
  status: string;
  expiresAt: number;
}
export interface ToolActivity {
  id: string;
  tool: string;
  outcome: string;
  result: string;
  time: string;
}
export function conversation(events: OathEvent[], pending: Pending[] = []) {
  const messages: Message[] = [];
  const assistants = new Map<string, Message>();
  const approvals = new Map<string, Approval>();
  const tools = new Map<string, ToolActivity>();
  let pauseNotice = '';
  const steps = new Map<
    string,
    { id: string; status: string; traceId: string; error: string; eventSeq: number }
  >();
  for (const event of events) {
    const p = event.payload,
      step = str(p.step_id);
    if (event.event_type === 'user.message') {
      pauseNotice = '';
      steps.clear();
      messages.push({
        id: `user:${event.event_seq}`,
        role: 'user',
        content: str(p.content),
        time: event.occur_dt,
      });
    }
    if (
      event.event_type === 'assistant.delta' &&
      ['content', 'reasoning'].includes(str(p.channel)) &&
      step
    ) {
      let message = assistants.get(step);
      const attempt = Number(p.attempt ?? 0);
      if (message && !message.streaming) continue;
      if (!message) {
        message = {
          id: `assistant:${step}`,
          role: 'assistant',
          content: '',
          time: event.occur_dt,
          streaming: true,
          attempt,
          stepId: step,
          traceId: steps.get(step)?.traceId,
        };
        assistants.set(step, message);
        messages.push(message);
      }
      if (attempt > (message.attempt ?? 0)) {
        message.rawContent = '';
        message.content = '';
        message.reasoning = '';
        message.attempt = attempt;
      }
      if (attempt === message.attempt) {
        if (p.channel === 'reasoning') {
          message.reasoning = (message.reasoning || '') + str(p.text);
          message.thinking = true;
        } else {
          message.rawContent = (message.rawContent ?? '') + str(p.text);
          message.content = parseQuickReplies(message.rawContent).content;
          message.thinking = false;
        }
      }
    }
    if (event.event_type === 'assistant.message') {
      let message = assistants.get(step);
      if (!message) {
        message = {
          id: `assistant:${step || event.event_seq}`,
          role: 'assistant',
          content: '',
          time: event.occur_dt,
          stepId: step,
          traceId: steps.get(step)?.traceId,
        };
        assistants.set(step, message);
        messages.push(message);
      }
      message.rawContent = str(p.content);
      const parsed = parseQuickReplies(message.rawContent);
      message.content = parsed.content;
      message.suggestions = parsed.suggestions;
      // 定稿时间才是这条回复的时间。快照回放会丢掉已完结 step 的增量，
      // 不跟着改的话，实时流和刷新后的历史会算出两套时长。
      message.time = event.occur_dt;
      message.eventSeq = event.event_seq;
      message.streaming = false;
      message.thinking = false;
      if (typeof p.reasoning === 'string') message.reasoning = p.reasoning;
      message.calls = list(p.tool_calls).map(obj);
      for (const [i, call] of (message.calls ?? []).entries()) {
        const id = `${step}-${i}`;
        if (!tools.has(id))
          tools.set(id, {
            id,
            tool: str(call.name),
            outcome: 'running',
            result: '',
            time: event.occur_dt,
          });
      }
    }
    if (event.event_type === 'permission.requested') {
      const id = str(p.invocation_id);
      approvals.set(id, {
        id,
        tool: str(p.tool),
        arguments: obj(p.arguments),
        status: 'pending',
        expiresAt: Number(p.expires_at),
      });
    }
    if (event.event_type === 'permission.resolved') {
      const approval = approvals.get(str(p.invocation_id));
      if (approval) approval.status = str(p.status);
    }
    if (event.event_type === 'tool.terminal') {
      const id = str(p.invocation_id),
        old = tools.get(id);
      tools.set(id, {
        id,
        tool: str(p.tool) || old?.tool || '工具',
        outcome: str(p.outcome),
        result: str(p.content) || str(obj(p.result).content) || JSON.stringify(p, null, 2),
        time: event.occur_dt,
      });
    }
    if (event.event_type === 'agent.paused' && p.reason === 'tool_only_budget')
      pauseNotice = '已暂停自动续行，工具结果已保留。发送消息后继续。';
    if (event.event_type === 'agent.resumed') pauseNotice = '';
    if (event.event_type === 'step.status') {
      const existing = assistants.get(step);
      if (existing && str(p.trace_id)) existing.traceId = str(p.trace_id);
      steps.set(step, {
        id: step,
        status: str(p.status),
        traceId: str(p.trace_id),
        error: str(p.error),
        eventSeq: event.event_seq,
      });
      if (['completed', 'failed', 'paused', 'cancelled'].includes(str(p.status))) {
        const m = assistants.get(step);
        if (m) {
          m.streaming = false;
          m.thinking = false;
        }
      }
    }
    if (event.event_type === 'message.reaction.changed') {
      const message = messages.find((item) => item.id === str(p.target));
      if (message)
        message.reactions = {
          ...message.reactions,
          [str(p.actor)]: typeof p.emoji === 'string' ? p.emoji : null,
        };
    }
  }
  const echoed = new Set(
    events
      .filter((e) => e.event_type === 'user.message')
      .map((e) => str(obj(e.payload.user_context).hymio_message_id)),
  );
  for (const p of [...pending].sort((a, b) => a.at - b.at)) {
    if (
      p.command.type !== 'user.message' ||
      str(obj(p.command.payload.user_context).hymio_message_id) !== p.id ||
      echoed.has(p.id)
    )
      continue;
    const local: Message = {
      id: `local:${p.id}`,
      role: 'user',
      content: str(p.command.payload.content),
      time: new Date(p.at).toISOString(),
      delivery: p.delivery || 'queued',
    };
    const position = messages.findIndex((m) => Date.parse(m.time) > p.at);
    messages.splice(position < 0 ? messages.length : position, 0, local);
    if (p.delivery !== 'failed') pauseNotice = '';
  }
  const latestStep = [...steps.values()].sort((a, b) => a.eventSeq - b.eventSeq).at(-1);
  return {
    messages: messages.filter(
      (m) => m.content || m.reasoning || m.calls?.length || m.streaming || m.suggestions?.length,
    ),
    approvals: [...approvals.values()],
    tools: [...tools.values()],
    latestStep,
    pauseNotice,
  };
}

/** A current server snapshot owns liveness; historical tool proposals do not. */
export function executionActivity(events: OathEvent[], runtime?: Data, runtimeThrough?: number) {
  const model = conversation(events);
  const newest = events.reduce((seq, e) => Math.max(seq, e.event_seq), 0);
  if (runtime && runtimeThrough != null && runtimeThrough >= newest) {
    const toolsRunning = Object.values(obj(runtime.calls)).some((value) =>
      ['admitting', 'queued', 'running'].includes(str(obj(value).status)),
    );
    const stepRunning = Object.values(obj(runtime.steps)).some((value) =>
      ['prepared', 'running'].includes(str(obj(value).status)),
    );
    return { toolsRunning, busy: toolsRunning || stepRunning };
  }
  const approvalIds = new Set(
    model.approvals.filter((a) => a.status === 'pending').map((a) => a.id),
  );
  const toolsRunning = model.tools.some((t) => t.outcome === 'running' && !approvalIds.has(t.id));
  return {
    toolsRunning,
    busy: toolsRunning || ['prepared', 'running'].includes(model.latestStep?.status || ''),
  };
}

export function replayBoundary(
  events: OathEvent[],
  after: number,
  through: number,
  previous?: { after: number; through: number },
) {
  if (
    after <= 0 ||
    !events.some(
      (e) =>
        e.event_seq > after &&
        e.event_seq <= through &&
        e.event_type === 'assistant.message' &&
        str(e.payload.content).trim() &&
        !list(e.payload.tool_calls).length,
    )
  )
    return previous;
  return { after: Math.min(previous?.after ?? after, after), through };
}
