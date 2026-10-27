import type { Message } from './conversation';

/**
 * 一次工作。对齐 Oath 的 trace：用户发话开新 trace，只要上一步还在产出工具调用就续同一条，
 * 直到某一步给出没有工具调用的最终回复，这条 trace 才结束。
 */
export interface Turn {
  id: string;
  trace: string;
  /** 用户那条消息，留在折叠块上方。 */
  user: Message | null;
  /** 最终回复：始终展开。 */
  final: Message | null;
  /** 全部思考、最终回复之前的正文和工具调用，收进折叠块。 */
  activity: Message[];
  /** 最终回复之后仍在流式的内容，保持展开。 */
  trailing: Message[];
  startedAt: number;
  /** 这条 trace 最新一条事件的服务端时间，客户端拿它对齐自己的时钟。 */
  latestAt: number;
  endedAt: number | null;
  /** 这条 trace 可以收起了。 */
  settled: boolean;
}

function at(value: string | undefined): number {
  if (!value) return 0;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

interface Draft {
  trace: string;
  items: Message[];
}

function isFinal(message: Message): boolean {
  return message.role === 'assistant' && !message.calls?.length && !message.streaming;
}

/**
 * 按 trace 切分消息。缺trace_id 的老消息退回「用户消息即分界」，
 * 免得整段历史塌成一条。
 */
export function buildTurns(messages: Message[], paused = false): Turn[] {
  const drafts: Draft[] = [];
  const byTrace = new Map<string, Draft>();
  let open: Draft | undefined;
  for (const message of messages) {
    const trace = message.traceId || '';
    // 同一条 trace 的事件即使被后开的 trace 打断过，也还归回原来那次工作。
    const known = trace ? byTrace.get(trace) : undefined;
    const closed = known?.items.at(-1);
    if (
      known &&
      !(closed && isFinal(closed) && message.role === 'assistant' && message.id !== closed.id)
    ) {
      known.items.push(message);
      continue;
    }
    const previous = open?.items.at(-1);
    if (
      !open ||
      message.role === 'user' ||
      (trace && open.trace) ||
      (previous && isFinal(previous) && message.role === 'assistant' && message.id !== previous.id)
    ) {
      open = { trace, items: [] };
      drafts.push(open);
    }
    open.items.push(message);
    if (trace) {
      open.trace = trace;
      byTrace.set(trace, open);
    }
  }
  return drafts.map((draft: Draft, index: number) => {
    const { items } = draft;
    let finalAt = -1;
    for (let i = items.length - 1; i >= 0; i -= 1) {
      if (isFinal(items[i])) {
        finalAt = i;
        break;
      }
    }
    const streaming = items.some((m) => m.streaming);
    const last = items.at(-1);
    // 没有最终回复的trace，只有在它后面又开了新 trace、且自己不再流式时才算结束。
    const settled =
      (paused && index === drafts.length - 1 && !streaming) ||
      (finalAt >= 0 ? finalAt === items.length - 1 : index < drafts.length - 1 && !streaming);
    let final = finalAt >= 0 ? items[finalAt] : null;
    const activity = items
      .slice(0, finalAt < 0 ? undefined : finalAt)
      .filter((m) => m.role === 'assistant');
    if (final?.reasoning?.trim()) {
      activity.push({ ...final, id: `${final.id}:reasoning`, content: '', thinking: false });
      final = final.content.trim() ? { ...final, reasoning: '', thinking: false } : null;
    }
    return {
      id: items[0].id,
      trace: draft.trace,
      user: items.find((m) => m.role === 'user') || null,
      final,
      activity,
      trailing: finalAt < 0 ? [] : items.slice(finalAt + 1),
      startedAt: at(items[0].time),
      latestAt: at(last?.time),
      endedAt: settled && last ? at(last.time) : null,
      settled,
    };
  });
}

/** 进行中的 trace 用服务端时钟口径的现在估算；已结束的用两端时间戳的精确值。 */
export function traceElapsed(turn: Turn, serverNow: number): number | null {
  if (!turn.startedAt) return null;
  if (turn.endedAt != null) return Math.max(0, turn.endedAt - turn.startedAt);
  return serverNow > turn.startedAt ? serverNow - turn.startedAt : null;
}

export function formatDuration(ms: number | null): string {
  if (ms == null) return '';
  const seconds = Math.max(1, Math.round(ms / 1000));
  if (seconds < 60) return `${seconds} 秒`;
  if (seconds < 3600) {
    const rest = seconds % 60;
    return rest ? `${Math.floor(seconds / 60)} 分 ${rest} 秒` : `${Math.floor(seconds / 60)} 分`;
  }
  const rest = Math.floor((seconds % 3600) / 60);
  return rest
    ? `${Math.floor(seconds / 3600)} 小时 ${rest} 分`
    : `${Math.floor(seconds / 3600)} 小时`;
}
