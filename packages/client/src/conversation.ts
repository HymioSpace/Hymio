import { obj, str, list, type Data, type OathEvent } from '@hymio/protocol';
export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  time: string;
  streaming?: boolean;
  attempt?: number;
  stepId?: string;
  calls?: Data[];
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
export function conversation(events: OathEvent[]) {
  const messages: Message[] = [];
  const assistants = new Map<string, Message>();
  const approvals = new Map<string, Approval>();
  const tools = new Map<string, ToolActivity>();
  const steps = new Map<string, { status: string; traceId: string; error: string }>();
  for (const event of events) {
    const p = event.payload,
      step = str(p.step_id);
    if (event.event_type === 'user.message')
      messages.push({
        id: `user:${event.event_seq}`,
        role: 'user',
        content: str(p.content),
        time: event.occur_dt,
      });
    if (event.event_type === 'assistant.delta' && p.channel === 'content' && step) {
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
        };
        assistants.set(step, message);
        messages.push(message);
      }
      if (attempt > (message.attempt ?? 0)) {
        message.content = '';
        message.attempt = attempt;
      }
      if (attempt === message.attempt) message.content += str(p.text);
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
        };
        assistants.set(step, message);
        messages.push(message);
      }
      message.content = str(p.content);
      message.streaming = false;
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
    if (event.event_type === 'step.status') {
      steps.set(step, { status: str(p.status), traceId: str(p.trace_id), error: str(p.error) });
      if (['failed', 'paused', 'cancelled'].includes(str(p.status))) {
        const m = assistants.get(step);
        if (m) m.streaming = false;
      }
    }
  }
  const latestStep = [...steps.values()].at(-1);
  return {
    messages: messages.filter((m) => m.content || m.calls?.length || m.streaming),
    approvals: [...approvals.values()],
    tools: [...tools.values()],
    latestStep,
  };
}
