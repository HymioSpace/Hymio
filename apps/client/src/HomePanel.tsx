import { useEffect, useState } from 'react';
import {
  ArrowRight,
  ArrowUpRight,
  Check,
  Clock3,
  LoaderCircle,
  RefreshCw,
  Hand,
  Sparkle,
  CircleDot,
  CalendarDays,
  Sunrise,
} from 'lucide-react';
import { Companion, type Mood } from '@hymio/ui';
import type { LoginState } from './useLogin';
import type { Work } from './taskModels';

export const workState = (task: Work) =>
  task.state === 'active' ? task.runs[0]?.status || 'scheduled' : task.state;
const labels: Record<string, string> = {
  running: '正在推进',
  blocked: '需要关注',
  failed: '未完成',
  succeeded: '已完成',
  scheduled: '已安排',
  ready: '等待开始',
  delivering: '正在开始',
  paused: '已暂停',
  expired: '已过期',
  cancelled: '已取消',
};
function fingerprint(task: Work) {
  const run = task.runs[0];
  // Summary and detail payloads share this revision even when prose/notes differ.
  const text = JSON.stringify([task.updated_at, task.title, task.state, run?.id, run?.status]);
  let hash = 2166136261;
  for (let i = 0; i < text.length; i++) hash = Math.imul(hash ^ text.charCodeAt(i), 16777619);
  return (hash >>> 0).toString(16);
}
function saved(key: string): Record<string, string> | null {
  try {
    return JSON.parse(localStorage.getItem(key) || 'null');
  } catch {
    return null;
  }
}
export function displayName(name?: string) {
  return !name || /^[\da-f]{32}$|^[\da-f]{8}(?:-[\da-f]{4}){3}-[\da-f]{12}$/i.test(name)
    ? '我的账号'
    : name;
}
export function HomePanel({
  login,
  onChat,
  onTask,
  mood,
  hasConversation,
  conversationReady,
}: {
  login: LoginState;
  onChat: () => void;
  onTask: (id?: string) => void;
  mood: Mood;
  hasConversation: boolean;
  conversationReady: boolean;
}) {
  const [tasks, setTasks] = useState<Work[]>([]),
    [loaded, setLoaded] = useState(false),
    [error, setError] = useState('');
  const key = `hymio.task-baseline:${login.backend}:${login.session?.user_id}`;
  const [baseline, setBaseline] = useState(() => saved(key));
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let running = false;
    async function refresh() {
      if (running || document.hidden) return;
      running = true;
      try {
        const response = await fetch(login.backend + '/tasks', {
          headers: { Authorization: 'Bearer ' + login.session!.access_token },
          signal: AbortSignal.any([controller.signal, AbortSignal.timeout(15000)]),
          redirect: 'error',
        });
        if (!response.ok) throw new Error('unavailable');
        const value = await response.json();
        if (!controller.signal.aborted) {
          setTasks(value.tasks);
          setLoaded(true);
          setError('');
        }
      } catch {
        if (!controller.signal.aborted) setError('暂时无法读取进展，对话仍可继续。');
      } finally {
        running = false;
      }
    }
    const visibility = () => {
      if (!document.hidden) void refresh();
    };
    void refresh();
    const timer = setInterval(() => void refresh(), 15000);
    document.addEventListener('visibilitychange', visibility);
    return () => {
      controller.abort();
      clearInterval(timer);
      document.removeEventListener('visibilitychange', visibility);
    };
  }, [key, login.session?.access_token, retry]);
  const attention = tasks.filter((t) => ['blocked', 'failed'].includes(workState(t)));
  const updates = tasks.filter(
    (t) =>
      !attention.includes(t) &&
      !['running', 'ready', 'delivering', 'scheduled', 'paused', 'expired', 'cancelled'].includes(
        workState(t),
      ) &&
      (baseline ? baseline[t.id] !== fingerprint(t) : workState(t) === 'succeeded'),
  );
  const ongoing = tasks.find((t) => ['running', 'ready', 'delivering'].includes(workState(t)));
  const upcoming = tasks.filter((t) => workState(t) === 'scheduled').slice(0, 1);
  const firstVisit = loaded && conversationReady && !tasks.length && !hasConversation;
  const modules = [
    { kind: 'attention' as const, title: '需要你看看', items: attention },
    { kind: 'updates' as const, title: baseline ? '新的进展' : '最近进展', items: updates },
    { kind: 'ongoing' as const, title: '正在推进', items: ongoing ? [ongoing] : [] },
    { kind: 'upcoming' as const, title: '接下来的安排', items: upcoming },
  ].filter((module) => module.items.length);
  function markSeen(task: Work) {
    const next = { ...(baseline || {}), [task.id]: fingerprint(task) };
    setBaseline(next);
    try {
      localStorage.setItem(key, JSON.stringify(next));
    } catch {
      /* In-memory read state still works. */
    }
  }
  function card(task: Work) {
    const state = workState(task),
      run = task.runs[0];
    return (
      <button
        className={`home-work ${['blocked', 'failed'].includes(state) ? 'attention' : ''}`}
        key={task.id}
        onClick={() => {
          markSeen(task);
          onTask(task.id);
        }}
      >
        <span className="home-work-status">
          {state === 'succeeded' ? <Check size={14} /> : <Clock3 size={14} />}
          {labels[state] || state}
        </span>
        <strong>{task.title}</strong>
        <p>{run?.result || run?.progress || task.objective}</p>
        {run?.next_step && <small>下一步：{run.next_step}</small>}
        <ArrowUpRight size={16} className="home-work-arrow" />
      </button>
    );
  }
  function section(
    title: string,
    values: Work[],
    kind: 'attention' | 'updates' | 'ongoing' | 'upcoming',
  ) {
    const Icon =
      kind === 'attention'
        ? Hand
        : kind === 'ongoing'
          ? CircleDot
          : kind === 'upcoming'
            ? CalendarDays
            : Sparkle;
    return (
      values.length > 0 && (
        <section className="home-section">
          <header className={`home-section-heading ${kind}`}>
            <span className="home-section-symbol" aria-hidden="true">
              <Icon size={14} />
            </span>
            <h2>{title}</h2>
            <span>{values.length}</span>
          </header>
          <div className="home-work-grid">{values.slice(0, 2).map(card)}</div>
        </section>
      )
    );
  }
  return (
    <main className="product-home">
      <header className="home-heading">
        <div>
          <span className="home-date">
            {new Date().toLocaleDateString(undefined, {
              month: 'long',
              day: 'numeric',
              weekday: 'long',
            })}
          </span>
          <h1>{firstVisit ? '嗨，我是 Hymio。' : '今天，继续向前。'}</h1>
          <p>{firstVisit ? '从一个想法，或一件小事开始。' : '进展、安排和重要的事，都在这里。'}</p>
        </div>
        <Companion mood={mood} />
      </header>
      <div className="home-columns">
        <div className="home-feed">
          {error && (
            <p className="home-error" role="status">
              {error}
              <button onClick={() => setRetry((v) => v + 1)}>
                <RefreshCw size={14} />
                重试
              </button>
            </p>
          )}
          {(!loaded || (!conversationReady && !hasConversation && !tasks.length)) && !error && (
            <p className="home-loading">
              <LoaderCircle size={16} className="spin" />
              {loaded ? '正在接回你的内容…' : '正在整理最新进展…'}
            </p>
          )}
          {modules.map((module) => (
            <div key={module.kind}>{section(module.title, module.items, module.kind)}</div>
          ))}
          {loaded &&
            !error &&
            !modules.length &&
            (conversationReady || hasConversation || tasks.length > 0) && (
              <section className="home-quiet">
                <span className="home-quiet-label">
                  <Sunrise size={17} />
                  {firstVisit ? '初次见面' : '此刻'}
                </span>
                <h2>{firstVisit ? '一件小事，就能开始。' : '暂时没有新的进展。'}</h2>
                <p>
                  {firstVisit
                    ? '理清一个想法、做一份计划，或把眼前的事交代给我。我们慢慢来。'
                    : '有了新结果，或有需要你确认的事，会在这里汇合。现在可以安心做自己的事。'}
                </p>
                {firstVisit ? (
                  <button className="home-chat-action" onClick={onChat}>
                    和 Hymio 说说
                    <ArrowRight size={17} />
                  </button>
                ) : (
                  tasks.length > 0 && (
                    <button className="home-task-link" onClick={() => onTask()}>
                      查看所有安排
                      <ArrowUpRight size={14} />
                    </button>
                  )
                )}
              </section>
            )}
        </div>
      </div>
    </main>
  );
}
