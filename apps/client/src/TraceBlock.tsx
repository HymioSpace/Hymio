import { useEffect, useRef, useState } from 'react';
import { ChevronRight } from 'lucide-react';
import { formatDuration, traceElapsed, type Turn } from '@hymio/client';
import type { Approval, ToolActivity } from '@hymio/client';
import { ActivityStream } from './ActivityStream';
import { MessageView } from './MessageView';
import type { LoginState } from './useLogin';

/**
 * 用最新一条事件把客户端时钟对齐到服务端，再让它按本地秒针走。
 * 服务端时间做锚，客户端只负责数秒，两边有时差也不会算错。
 */
function useServerNow(latestAt: number, live: boolean): number {
  const anchor = useRef({ at: -1, seen: 0 });
  if (anchor.current.at !== latestAt) anchor.current = { at: latestAt, seen: Date.now() };
  const [, tick] = useState(0);
  useEffect(() => {
    if (!live) return;
    const timer = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(timer);
  }, [live]);
  return latestAt ? latestAt + (Date.now() - anchor.current.seen) : 0;
}

export function TraceBlock({
  turn,
  tools,
  login,
  approvals,
  onAction,
}: {
  turn: Turn;
  tools: ToolActivity[];
  login: LoginState;
  approvals?: Approval[];
  onAction: (text: string) => Promise<void>;
}) {
  const stream = { messages: turn.activity, tools, login, approvals, onAction };
  const foldable = turn.settled && turn.activity.length > 0;
  const serverNow = useServerNow(turn.latestAt, !turn.settled);
  const elapsed = formatDuration(traceElapsed(turn, serverNow));
  return (
    <div className="trace-turn">
      {turn.user && (
        <MessageView
          onAction={onAction}
          message={turn.user}
          tools={tools}
          login={login}
          approvals={approvals}
        />
      )}
      {foldable ? (
        <details className="trace-fold" data-testid="trace-fold">
          <summary>
            <ChevronRight size={13} className="trace-fold-chevron" />
            <span className="trace-fold-label">{elapsed ? `已工作 ${elapsed}` : '已工作'}</span>
          </summary>
          <div className="trace-fold-body">
            <ActivityStream {...stream} />
          </div>
        </details>
      ) : (
        <>
          {turn.activity.length > 0 && (
            <p className="trace-live" aria-live="polite">
              {elapsed ? `已工作 ${elapsed}` : '正在处理…'}
            </p>
          )}
          <ActivityStream {...stream} />
        </>
      )}
      {turn.final && (
        <MessageView
          onAction={onAction}
          message={turn.final}
          tools={tools}
          login={login}
          approvals={approvals}
        />
      )}
      {turn.trailing.length > 0 && (
        <ActivityStream
          messages={turn.trailing}
          tools={tools}
          login={login}
          approvals={approvals}
          onAction={onAction}
        />
      )}
    </div>
  );
}
