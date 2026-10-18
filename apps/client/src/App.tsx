import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import {
  ArrowUp,
  ArrowDown,
  SlidersHorizontal,
  AudioLines,
  Activity,
  Settings2,
  Circle,
  CheckCheck,
  ChevronDown,
  WifiOff,
  Plug,
  ArrowRight,
  Square,
  ShieldCheck,
  LoaderCircle,
  Terminal,
  X,
} from 'lucide-react';
import { OathClient, conversation } from '@hymio/client';
import { Companion, type Mood } from '@hymio/ui';
import { type Connection } from '@hymio/protocol';
import { Settings } from './Settings';
import { useLogin } from './useLogin';
import { MessageView } from './MessageView';
import { DebugPanel } from './DebugPanel';
import { desktop } from './platform';
import { LoginScreen } from './LoginScreen';
const client = new OathClient();
function Brand() {
  return (
    <svg viewBox="0 0 34 34" fill="none" aria-label="Hymio">
      <path d="M10 7V26M24 15V26" stroke="currentColor" strokeWidth="5" strokeLinecap="round" />
      <path d="M15 15L19 18" stroke="#4b70ff" strokeWidth="4" strokeLinecap="round" />
    </svg>
  );
}
export default function App() {
  const state = useSyncExternalStore(client.subscribe, client.getSnapshot);
  const model = useMemo(() => conversation(state.events), [state.events]);
  const [connection, setConnection] = useState<Connection>({
    wsUrl: '',
    bizUrl: '',
    credential: '',
  });
  const [settings, setSettings] = useState(false),
    [debug, setDebug] = useState(false),
    [draft, setDraft] = useState(() => sessionStorage.getItem('hymio.draft') || ''),
    [notice, setNotice] = useState(''),
    [dismissedFailure, setDismissedFailure] = useState(
      () => localStorage.getItem('hymio.dismissedFailure') || '',
    ),
    [toolsOpen, setToolsOpen] = useState(false),
    [nearBottom, setNearBottom] = useState(true),
    [sending, setSending] = useState(false),
    [clock, setClock] = useState(Date.now());
  const login = useLogin(
    (value, signedIn) => {
      client.connect(value);
      setConnection(value);
      if (signedIn) setSettings(false);
    },
    () => {
      client.signOut();
      sessionStorage.removeItem('hymio.credential');
      localStorage.removeItem('hymio.endpoints');
      setDraft('');
      setConnection((value) => ({ ...value, credential: '', userId: undefined }));
    },
  );
  const viewport = useRef<HTMLDivElement>(null),
    input = useRef<HTMLTextAreaElement>(null);
  const pendingApprovals = model.approvals.filter(
    (a) => a.status === 'pending' && a.expiresAt * 1000 > clock,
  );
  const approvalIds = new Set(pendingApprovals.map((a) => a.id));
  const toolsRunning = model.tools.some((t) => t.outcome === 'running' && !approvalIds.has(t.id));
  const busy = toolsRunning || ['prepared', 'running'].includes(model.latestStep?.status || '');
  const streaming = model.messages.some((m) => m.streaming);
  const connected = state.phase === 'connected';
  const latestFailure =
    model.latestStep?.status === 'failed' || model.latestStep?.status === 'paused'
      ? model.latestStep
      : undefined;
  const failureKey = latestFailure
    ? `${state.userId}:${latestFailure.id}:${latestFailure.eventSeq}`
    : '';
  function dismissFailure(key: string) {
    localStorage.setItem('hymio.dismissedFailure', key);
    setDismissedFailure(key);
  }
  const mood: Mood =
    state.phase === 'disconnected' || state.phase === 'error' || state.phase === 'reconnecting'
      ? 'offline'
      : pendingApprovals.length
        ? 'waiting'
        : streaming
          ? 'replying'
          : busy
            ? 'working'
            : 'idle';
  const status =
    state.phase === 'connecting'
      ? '正在连接'
      : state.phase === 'reconnecting'
        ? '正在重连'
        : state.phase === 'syncing'
          ? '正在接回进展'
          : !connected
            ? '未连接'
            : pendingApprovals.length
              ? '等你确认'
              : busy || streaming
                ? '正在处理'
                : '随时在这里';
  useEffect(() => () => client.disconnect(), []);
  useEffect(() => {
    if (!state.userId) return;
    const owner = JSON.stringify([connection.wsUrl, state.userId]);
    const previous = sessionStorage.getItem('hymio.draft.owner');
    if (previous && previous !== owner) setDraft('');
    sessionStorage.setItem('hymio.draft.owner', owner);
  }, [state.userId, connection.wsUrl]);
  useEffect(() => {
    sessionStorage.setItem('hymio.draft', draft);
    if (input.current) {
      input.current.style.height = 'auto';
      input.current.style.height = `${Math.min(180, input.current.scrollHeight)}px`;
    }
  }, [draft]);
  useEffect(() => {
    if (nearBottom) {
      viewport.current?.scrollTo({ top: viewport.current.scrollHeight, behavior: 'instant' });
    }
  }, [state.events.length, state.pending.length, debug]);
  useEffect(() => {
    const timer = setInterval(() => {
      setClock(Date.now());
      if (connected && busy) client.status();
    }, 5000);
    return () => clearInterval(timer);
  }, [connected, busy]);
  useEffect(() => {
    function key(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault();
        input.current?.focus();
      }
      if (e.key === 'Escape') setDebug(false);
    }
    window.addEventListener('keydown', key);
    return () => window.removeEventListener('keydown', key);
  }, []);
  async function act(fn: () => Promise<unknown>) {
    try {
      await fn();
    } catch (e) {
      setNotice(e instanceof Error ? e.message : String(e));
    }
  }
  async function send() {
    if (!draft.trim() || sending) return;
    if (!connected) {
      setSettings(true);
      return;
    }
    const content = draft.trim();
    setSending(true);
    try {
      await client.message(content);
      setDraft('');
      setNearBottom(true);
      input.current?.focus();
    } catch (e) {
      setNotice(e instanceof Error ? e.message : String(e));
    } finally {
      setSending(false);
    }
  }
  const welcome = model.messages.length === 0;
  if (!login.session) return <LoginScreen login={login} />;
  return (
    <div className={`app ${debug ? 'debug-open' : ''} ${desktop ? 'desktop' : ''}`}>
      <nav className="rail" aria-label="主导航">
        <a className="brand-mark" href="#" aria-label="Hymio 首页">
          <Brand />
        </a>
        <div className="rail-primary">
          <button
            className="rail-button active"
            title="持续对话"
            aria-label="持续对话"
            onClick={() => {
              setDebug(false);
              input.current?.focus();
            }}
          >
            <AudioLines size={23} />
          </button>
        </div>
        <div className="rail-bottom">
          <button
            className={`rail-button ${debug ? 'active' : ''}`}
            title="工作观察"
            aria-label="工作观察"
            onClick={() => setDebug(!debug)}
          >
            <Activity size={21} />
          </button>
          <button
            className="rail-button"
            title="账号设置"
            aria-label="账号设置"
            onClick={() => setSettings(true)}
          >
            <Settings2 size={21} />
          </button>
          <span className="rail-divider" />
          <button
            className="profile-button"
            title="我的账号"
            aria-label="我的账号"
            onClick={() => setSettings(true)}
          >
            我
          </button>
        </div>
      </nav>
      <main className="main">
        <header className="topbar">
          <div className="topbar-brand" data-tauri-drag-region>
            <span>hymio</span>
            <small>in tune with you</small>
          </div>
          <div className="topbar-actions">
            <button
              className={`connection-pill ${connected ? 'online' : ''}`}
              onClick={() => setSettings(true)}
            >
              <i className={busy ? 'pulse' : ''} />
              {status}
              <ChevronDown size={12} />
            </button>
            <button
              className={`icon-button observe-button ${debug ? 'selected' : ''}`}
              aria-label="打开工作观察"
              title="工作观察"
              onClick={() => setDebug(!debug)}
            >
              <SlidersHorizontal size={18} />
            </button>
          </div>
        </header>
        <div
          className="conversation-scroll"
          ref={viewport}
          onScroll={() => {
            const el = viewport.current;
            if (el) setNearBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 100);
          }}
        >
          {welcome ? (
            <section className="welcome">
              <div className="welcome-character">
                <Companion mood={mood} />
                <span className="character-caption">
                  <i />
                  YOUR EVERYDAY COMPANION
                </span>
              </div>
              <h1>
                今天，想从哪儿开始<span>？</span>
              </h1>
              <p>
                一个念头，一件小事。
                <br className="mobile-break" />
                我们慢慢把它变成现实。
              </p>
              <div className="starter-prompts">
                <button
                  onClick={() => {
                    setDraft('帮我理一理今天的安排，先问我几个必要的问题。');
                    input.current?.focus();
                  }}
                >
                  <span className="prompt-icon">☀</span>理理今天的安排
                  <ArrowRight size={14} />
                </button>
                <button
                  onClick={() => {
                    setDraft('你好 Hymio，介绍一下你现在能帮我做些什么。');
                    input.current?.focus();
                  }}
                >
                  <span className="prompt-icon note-icon">♪</span>先认识一下你
                  <ArrowRight size={14} />
                </button>
              </div>
            </section>
          ) : (
            <div className="transcript">
              <div className="day-divider">
                <span>同一段对话，随时接着聊</span>
              </div>
              {state.replay && state.replay.through > state.replay.after && (
                <div className="replay-note">
                  <CheckCheck size={14} />
                  {state.phase === 'syncing'
                    ? '正在同步离开期间的进展…'
                    : `已同步 ${state.replay.received} 条服务端事件`}
                </div>
              )}
              {model.messages.map((m) => (
                <MessageView key={m.id} message={m} tools={model.tools} />
              ))}
              {model.tools.length > 0 && (
                <div className="work-summary">
                  <button onClick={() => setToolsOpen(!toolsOpen)}>
                    <span className={`work-dot ${toolsRunning ? 'running' : ''}`} />
                    {toolsRunning ? '正在处理工具任务' : `已记录 ${model.tools.length} 次工具调用`}
                    <ChevronDown size={14} className={toolsOpen ? 'rotated' : ''} />
                  </button>
                  {toolsOpen && (
                    <div className="tool-results">
                      {model.tools.map((t) => (
                        <details key={t.id}>
                          <summary>
                            <Terminal size={14} />
                            {t.tool}
                            <span>
                              {t.outcome === 'succeeded'
                                ? '已完成'
                                : t.outcome === 'running'
                                  ? '处理中'
                                  : t.outcome}
                            </span>
                          </summary>
                          <pre>{t.result || '等待实际结果…'}</pre>
                        </details>
                      ))}
                    </div>
                  )}
                </div>
              )}
              {model.approvals.map((a) => (
                <section key={a.id} className="approval-card">
                  <div>
                    <ShieldCheck size={20} />
                    <strong>这一步，需要你点头</strong>
                  </div>
                  <p>
                    <b>{a.tool}</b>
                    <span>
                      {a.status === 'pending'
                        ? a.expiresAt * 1000 <= clock
                          ? '已过期'
                          : '等待授权'
                        : a.status === 'approved'
                          ? '已批准'
                          : a.status === 'denied'
                            ? '已拒绝'
                            : a.status}
                    </span>
                  </p>
                  <pre>{JSON.stringify(a.arguments, null, 2)}</pre>
                  {a.status === 'pending' && a.expiresAt * 1000 > clock && (
                    <div className="approval-actions">
                      <button
                        className="secondary-button"
                        disabled={
                          !connected ||
                          state.pending.some((p) => p.command.payload.invocation_id === a.id)
                        }
                        onClick={() => void act(() => client.decide(a.id, 'denied'))}
                      >
                        拒绝
                      </button>
                      <button
                        className="primary-button"
                        disabled={
                          !connected ||
                          state.pending.some((p) => p.command.payload.invocation_id === a.id)
                        }
                        onClick={() => void act(() => client.decide(a.id, 'approved'))}
                      >
                        允许这次操作
                      </button>
                    </div>
                  )}
                </section>
              ))}
              {(busy || streaming) && (
                <div className="working-indicator">
                  <Companion compact mood={mood} />
                  <span>
                    Hymio {streaming ? '正在回复' : '正在接着做'}
                    <i />
                    <i />
                    <i />
                  </span>
                </div>
              )}
              {latestFailure?.error && failureKey !== dismissedFailure && (
                <div className="task-error">
                  <p>{latestFailure.error}</p>
                  <div className="task-error-actions">
                    <button
                      className="text-button"
                      disabled={!connected}
                      onClick={() => {
                        void client.command('step.retry', {}).then(
                          () => {
                            dismissFailure(failureKey);
                            setNotice('已请求重试；如果服务端再次失败，会显示新的错误。');
                          },
                          (error: unknown) => setNotice(String(error)),
                        );
                      }}
                    >
                      重试这一步
                    </button>
                    <button className="text-button" onClick={() => dismissFailure(failureKey)}>
                      收起
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
        <div className={`composer-dock ${welcome ? 'welcome-dock' : ''}`}>
          {!nearBottom && !welcome && (
            <button
              className="jump-bottom"
              onClick={() => {
                setNearBottom(true);
                viewport.current?.scrollTo({
                  top: viewport.current.scrollHeight,
                  behavior: 'smooth',
                });
              }}
            >
              <ArrowDown size={15} />
              最新消息
            </button>
          )}
          {(notice || state.error || login.error) && (
            <div role="alert" className="notice-bar">
              <span>{notice || state.error || login.error}</span>
              <button
                className="icon-button"
                aria-label="收起提示"
                onClick={() => {
                  setNotice('');
                  client.clearError();
                }}
              >
                <X size={14} />
              </button>
            </div>
          )}
          {state.pending.length > 0 && (
            <div className="pending-note">
              <LoaderCircle size={12} className="spin" />
              {state.pending.length} 条操作等待服务端确认
              <button disabled={!connected} onClick={() => client.retryPending()}>
                重试未确认操作
              </button>
            </div>
          )}
          {!connected && !welcome && (
            <div className="offline-banner">
              <WifiOff size={14} />
              <span>连接暂时离开，Oath 上的工作仍会继续。</span>
              <button onClick={() => setSettings(true)}>账号设置</button>
            </div>
          )}
          <div className="composer" onClick={() => input.current?.focus()}>
            <textarea
              aria-label="给 Hymio 发消息"
              ref={input}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder={welcome ? '想到什么，就和我说说…' : '接着说，我在听…'}
              rows={2}
              onKeyDown={(e) => {
                if (
                  e.key === 'Enter' &&
                  !e.shiftKey &&
                  !e.nativeEvent.isComposing &&
                  e.keyCode !== 229
                ) {
                  e.preventDefault();
                  void send();
                }
              }}
            />
            <div className="composer-toolbar">
              <div className="composer-context">
                <AudioLines size={16} />
                <span>{connected ? 'Hymio · 一直在这里' : '与你同频，从一句话开始'}</span>
              </div>
              <div className="composer-actions">
                {busy && (
                  <button
                    className="icon-button stop-button"
                    disabled={!connected}
                    aria-label="停止当前任务"
                    title="停止当前任务"
                    onClick={(e) => {
                      e.stopPropagation();
                      void act(() => client.command('run.cancel', {}));
                    }}
                  >
                    <Square size={13} />
                  </button>
                )}
                <button
                  className={`send-button ${draft.trim() ? 'has-text' : ''}`}
                  aria-label={connected ? '发送消息' : '连接 Oath'}
                  disabled={sending || !draft.trim()}
                  onClick={(e) => {
                    e.stopPropagation();
                    void send();
                  }}
                >
                  {sending ? <LoaderCircle size={18} className="spin" /> : <ArrowUp size={19} />}
                </button>
              </div>
            </div>
          </div>
          <div className="composer-footer">
            <span>
              {connected ? (
                <>
                  <Circle size={7} fill="currentColor" />
                  你离开时，已接纳的工作依然继续。
                </>
              ) : (
                <button onClick={() => setSettings(true)}>
                  <Plug size={12} />
                  连接你的 Oath
                </button>
              )}
            </span>
            <span className="keyboard-hint">
              Enter 发送<span>·</span>Shift + Enter 换行
            </span>
          </div>
        </div>
      </main>
      {debug && (
        <DebugPanel
          key={`${connection.wsUrl}|${state.userId}`}
          state={state}
          connection={connection}
          onClose={() => setDebug(false)}
          onStatus={() => client.status()}
          onCancel={() => void act(() => client.command('run.cancel', {}))}
          onRetry={() => void act(() => client.command('step.retry', {}))}
        />
      )}
      {settings && <Settings login={login} onClose={() => setSettings(false)} />}
    </div>
  );
}
