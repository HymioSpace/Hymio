import { useEffect, useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import {
  ArrowUp,
  ArrowDown,
  SlidersHorizontal,
  AudioLines,
  Activity,
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
import { OathClient, conversation, executionActivity } from '@hymio/client';
import { Companion, StatusBadge, type Mood } from '@hymio/ui';
import { type Connection } from '@hymio/protocol';
import { Settings } from './Settings';
import { useLogin } from './useLogin';
import { MessageView } from './MessageView';
import { groupMessages, ToolActivityGroup } from './ToolActivityGroup';
import { DebugPanel } from './DebugPanel';
import { desktop, bizGet } from './platform';
import { LoginScreen } from './LoginScreen';
import { deviceRequest } from './deviceApi';
const client = new OathClient();
const overlayQuery = '(max-width: 1150px)';
const watchOverlay = (notify: () => void) => {
  const query = window.matchMedia(overlayQuery);
  query.addEventListener('change', notify);
  return () => query.removeEventListener('change', notify);
};
const overlaySnapshot = () => window.matchMedia(overlayQuery).matches;
function Brand() {
  return (
    <svg viewBox="0 0 34 34" fill="none" aria-label="Hymio">
      <path d="M10 7V26M24 15V26" stroke="currentColor" strokeWidth="5" strokeLinecap="round" />
      <path d="M15 15L19 18" stroke="#4b70ff" strokeWidth="4" strokeLinecap="round" />
    </svg>
  );
}
export default function App() {
  const narrow = useSyncExternalStore(watchOverlay, overlaySnapshot, () => false);
  const state = useSyncExternalStore(client.subscribe, client.getSnapshot);
  const model = useMemo(
    () => conversation(state.events, state.pending),
    [state.events, state.pending],
  );
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
  useEffect(() => {
    if (!login.session) return;
    let active = true;
    let deviceId = '';
    const key = `hymio.installation:${login.backend}:${login.session.user_id}`;
    const installation = localStorage.getItem(key) || crypto.randomUUID();
    localStorage.setItem(key, installation);
    void deviceRequest(login, '/register', {
      installation_id: installation,
      kind: desktop ? 'mac' : 'web',
    })
      .then((device) => {
        if (!active) return;
        deviceId = device.device_id;
        client.setSourceDevice(deviceId);
      })
      .catch(() => {
        if (active) setNotice('设备绑定暂不可用，对话仍可继续。');
      });
    const timer = setInterval(() => {
      if (deviceId) void deviceRequest(login, `/${deviceId}/heartbeat`, {}).catch(() => {});
    }, 30000);
    return () => {
      active = false;
      clearInterval(timer);
      client.setSourceDevice('');
    };
  }, [login.session?.access_token]);
  useEffect(() => {
    if (!login.session) return;
    let active = true;
    void deviceRequest(login, '/ensure', {})
      .then((binding) => {
        if (active && binding.action === 'replaced')
          setNotice('原云电脑已失效，已自动绑定新环境；旧文件未恢复，聊天记录保留。');
      })
      .catch(() => {
        if (active) setNotice('云电脑暂时无法准备，对话仍可继续；需要用电脑时会自动重试。');
      });
    return () => {
      active = false;
    };
  }, [login.session?.user_id, login.backend]);
  const viewport = useRef<HTMLDivElement>(null),
    input = useRef<HTMLTextAreaElement>(null);
  const pendingApprovals = model.approvals.filter(
    (a) => a.status === 'pending' && a.expiresAt * 1000 > clock,
  );
  const attachedToolIds = new Set(
    model.messages.flatMap((m) => (m.calls || []).map((_, i) => `${m.stepId}-${i}`)),
  );
  const unattachedTools = model.tools.filter((t) => !attachedToolIds.has(t.id));
  const { toolsRunning, busy } = executionActivity(
    state.events,
    state.runtime,
    state.runtimeThrough,
  );
  const streaming = model.messages.some((m) => m.streaming);
  const lastMessage = model.messages.at(-1);
  const awaitingReply =
    lastMessage?.role === 'user' &&
    lastMessage.delivery !== 'failed' &&
    (!!lastMessage.delivery ||
      !['failed', 'paused', 'cancelled'].includes(model.latestStep?.status || ''));
  const delayedCommands = state.pending.filter(
    (p) => p.delivery === 'failed' || (p.delivery !== 'accepted' && clock - p.at > 8000),
  );
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
          : busy || awaitingReply
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
              : busy || streaming || awaitingReply
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
  const [historyLoading, setHistoryLoading] = useState(false);
  const historyAnchor = useRef<{ top: number; height: number } | null>(null);
  useLayoutEffect(() => {
    const el = viewport.current;
    const anchor = historyAnchor.current;
    if (el && anchor) {
      el.scrollTop = anchor.top + el.scrollHeight - anchor.height;
      historyAnchor.current = null;
    }
  }, [state.events]);
  async function loadHistory() {
    if (historyLoading || !state.history?.before) return;
    setHistoryLoading(true);
    try {
      const page = await bizGet(
        connection.bizUrl,
        `/conversation_history?before=${state.history.before}&limit=10`,
        connection.credential,
      );
      const el = viewport.current;
      following.current = false;
      if (el) historyAnchor.current = { top: el.scrollTop, height: el.scrollHeight };
      await client.prependHistory(page);
    } catch (error) {
      historyAnchor.current = null;
      setNotice(`历史加载失败：${String(error)}`);
    } finally {
      setHistoryLoading(false);
    }
  }
  const following = useRef(true);
  const scrollFrame = useRef(0);
  useEffect(() => {
    const el = viewport.current;
    if (!el) return;
    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(scrollFrame.current);
      if (!following.current) return;
      scrollFrame.current = requestAnimationFrame(() => {
        if (following.current) el.scrollTo({ top: el.scrollHeight, behavior: 'instant' });
      });
    });
    observer.observe(el);
    if (el.firstElementChild) observer.observe(el.firstElementChild);
    return () => {
      observer.disconnect();
      cancelAnimationFrame(scrollFrame.current);
    };
  }, [model.messages.length === 0]);
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
      login.reconnect();
      setNotice('正在重新连接，草稿已保留，连接后可发送。');
      return;
    }
    const content = draft.trim();
    setSending(true);
    setDraft('');
    following.current = true;
    setNearBottom(true);
    try {
      await client.message(content);
      following.current = true;
      setNearBottom(true);
      requestAnimationFrame(() =>
        viewport.current?.scrollTo({ top: viewport.current.scrollHeight, behavior: 'instant' }),
      );
      input.current?.focus();
    } catch (e) {
      setDraft((current) => current || content);
      setNotice(e instanceof Error ? e.message : String(e));
    } finally {
      setSending(false);
    }
  }
  const welcome = model.messages.length === 0;
  if (!login.session) return <LoginScreen login={login} />;
  return (
    <div className={`app ${debug ? 'debug-open' : ''} ${desktop ? 'desktop' : ''}`}>
      <nav className="rail" aria-label="主导航" inert={debug && narrow}>
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
            aria-expanded={debug}
            aria-controls="work-observer"
            onClick={() => setDebug(!debug)}
          >
            <Activity size={21} />
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
      <main className="main" inert={debug && narrow}>
        <header className="topbar">
          <div className="topbar-brand" data-tauri-drag-region>
            <span>hymio</span>
          </div>
          <div className="topbar-actions">
            <button
              className={`connection-pill ${connected ? 'online' : ''}`}
              onClick={() => setSettings(true)}
              aria-label="我的账号与连接状态"
            >
              <StatusBadge tone={connected ? 'active' : 'neutral'}>{status}</StatusBadge>
              <ChevronDown size={12} />
            </button>
            <button
              className={`icon-button observe-button ${debug ? 'selected' : ''}`}
              aria-label="打开工作观察"
              aria-expanded={debug}
              aria-controls="work-observer"
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
          onWheel={(event) => {
            if (event.deltaY < 0) following.current = false;
          }}
          onTouchStart={() => {
            following.current = false;
          }}
          onPointerDown={() => {
            following.current = false;
          }}
          onScroll={() => {
            const el = viewport.current;
            if (el) {
              const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
              following.current = atBottom;
              setNearBottom(atBottom);
            }
          }}
        >
          {welcome ? (
            <section className="welcome">
              <div className="welcome-character">
                <Companion mood={mood} />
              </div>
              <h1>嗨，我在。</h1>
              <p>想到什么，就和我说说。</p>
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
              {state.history?.hasMore && (
                <button
                  className="load-history"
                  disabled={historyLoading}
                  onClick={() => void loadHistory()}
                >
                  {historyLoading ? '正在加载…' : '加载更早的消息'}
                </button>
              )}
              <div className="day-divider">
                <span>我们的对话</span>
              </div>
              {state.replay && state.replay.through > state.replay.after && (
                <div className="replay-note">
                  <CheckCheck size={14} />
                  {state.phase === 'syncing'
                    ? '正在同步离开期间的进展…'
                    : `已同步 ${state.replay.received} 条服务端事件`}
                </div>
              )}
              {groupMessages(model.messages).map((group) => {
                const first = group[0];
                return first.role === 'assistant' &&
                  !first.content.trim() &&
                  first.calls?.length ? (
                  <article
                    key={first.id}
                    className="message message-assistant message-tool-activity"
                  >
                    <div className="message-avatar">
                      <Companion compact mood="idle" />
                    </div>
                    <div className="message-body">
                      <ToolActivityGroup
                        messages={group}
                        tools={model.tools}
                        approvals={model.approvals}
                      />
                    </div>
                  </article>
                ) : (
                  <MessageView
                    key={first.id}
                    message={first}
                    tools={model.tools}
                    login={login}
                    approvals={model.approvals}
                  />
                );
              })}
              {unattachedTools.length > 0 && (
                <div className="work-summary">
                  <button onClick={() => setToolsOpen(!toolsOpen)}>
                    <span className={`work-dot ${toolsRunning ? 'running' : ''}`} />
                    {toolsRunning
                      ? '正在处理工具任务'
                      : `其他工具活动 · ${unattachedTools.length} 次调用`}
                    <ChevronDown size={14} className={toolsOpen ? 'rotated' : ''} />
                  </button>
                  {toolsOpen && (
                    <div className="tool-results">
                      {unattachedTools.map((t) => (
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
              {(busy || streaming || awaitingReply) && (
                <div className="message working-indicator">
                  <div className="message-avatar">
                    <Companion compact mood={mood} />
                  </div>
                  <span>
                    Hymio {streaming ? '正在回复' : awaitingReply ? '正在等候回复' : '正在接着做'}
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
                following.current = true;
                setNearBottom(true);
                viewport.current?.scrollTo({
                  top: viewport.current.scrollHeight,
                  behavior: 'instant',
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
              {!connected && login.session && <button onClick={login.reconnect}>重新连接</button>}
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
          {delayedCommands.length > 0 && (
            <div className="pending-note">
              <LoaderCircle size={12} className="spin" />
              {delayedCommands.length} 条操作尚未完成发送
              <button disabled={!connected} onClick={() => void act(() => client.retryPending())}>
                重试未确认操作
              </button>
            </div>
          )}
          {!connected && !welcome && (
            <div className="offline-banner">
              <WifiOff size={14} />
              <span>暂时离线，已接纳的工作仍会继续。</span>
              <button onClick={login.reconnect}>重新连接</button>
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
              rows={1}
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
                aria-label={connected ? '发送消息' : '重新连接'}
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
                  查看连接状态
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
          modal={narrow}
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
