import { CompactionStatus } from './CompactionStatus';
import { MomentsPanel } from './MomentsPanel';
import { HomePanel } from './HomePanel';
import { enqueueTelemetry, flushTelemetry } from './telemetry';
import { Home, MessageCircle, UserRound } from 'lucide-react';
import { Attachments, attachmentText, type Attachment } from './Attachments';
import { useEffect, useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import {
  Flag,
  ArrowUp,
  ArrowDown,
  Bookmark,
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
import {
  OathClient,
  buildTurns,
  compactionState,
  conversation,
  executionActivity,
  createIdentity,
} from '@hymio/client';
import { Companion, StatusBadge, type Mood } from '@hymio/ui';
import { type Connection } from '@hymio/protocol';
import { Settings } from './Settings';
import { TasksPanel } from './TasksPanel';
import { useLogin } from './useLogin';
import { TraceBlock } from './TraceBlock';
import { TracePage } from './TracePage';
import { desktop, bizGet } from './platform';
import { LoginScreen } from './LoginScreen';
import { deviceRequest } from './deviceApi';
const client = new OathClient();
client.channelKind = desktop ? 'desk' : 'web';
export default function App() {
  const state = useSyncExternalStore(client.subscribe, client.getSnapshot);
  const model = useMemo(
    () => conversation(state.events, state.pending),
    [state.events, state.pending],
  );
  const unreadMessages = model.messages.filter(
    (m) =>
      state.unread &&
      m.role === 'assistant' &&
      !m.streaming &&
      !m.calls?.length &&
      m.content &&
      (m.eventSeq ?? 0) > state.unread.after &&
      (m.eventSeq ?? 0) <= state.unread.through,
  );
  const [connection, setConnection] = useState<Connection>({
    wsUrl: '',
    bizUrl: '',
    credential: '',
  });
  const [tasksOpen, setTasksOpen] = useState(false);
  const [selectedTask, setSelectedTask] = useState('');
  const [page, setPage] = useState<'home' | 'chat' | 'moments'>(
    window.location.hash === '#/moments'
      ? 'moments'
      : window.location.hash === '#/chat'
        ? 'chat'
        : 'home',
  );
  const [memoryVisited, setMemoryVisited] = useState(page === 'moments');
  useEffect(() => {
    if (page === 'moments') setMemoryVisited(true);
  }, [page]);
  function navigate(next: 'home' | 'chat' | 'moments') {
    setPage(next);
    changeDebug(false);
    window.location.hash = '/' + next;
  }
  function openTask(id = '') {
    setSelectedTask(id);
    setTasksOpen(true);
  }
  const [settings, setSettings] = useState(false),
    [debug, changeDebug] = useState(window.location.hash === '#/trace'),
    [draft, setDraft] = useState(() => sessionStorage.getItem('hymio.draft') || ''),
    [notice, setNotice] = useState(''),
    [dismissedFailure, setDismissedFailure] = useState(
      () => localStorage.getItem('hymio.dismissedFailure') || '',
    ),
    [toolsOpen, setToolsOpen] = useState(false),
    [nearBottom, setNearBottom] = useState(true),
    [sending, setSending] = useState(false),
    [clock, setClock] = useState(Date.now());
  function setDebug(value: boolean) {
    window.location.hash = value ? '/trace' : '/' + page;
    changeDebug(value);
  }
  useEffect(() => {
    const route = () => {
      changeDebug(window.location.hash === '#/trace');
      if (window.location.hash === '#/moments') setPage('moments');
      if (window.location.hash === '#/home') setPage('home');
      if (window.location.hash === '#/chat') setPage('chat');
    };
    window.addEventListener('hashchange', route);
    return () => window.removeEventListener('hashchange', route);
  }, []);
  const login = useLogin(
    (value, signedIn) => {
      client.connect(value, signedIn);
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
    const installation = localStorage.getItem(key) || createIdentity();
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
  const telemetryReported = useRef(new Set<string>());
  const stalledReported = useRef(new Set<string>());
  type ResponseTiming = NonNullable<typeof state.responseTiming>;
  function reportTelemetry(
    timing: ResponseTiming,
    outcome: string,
    completedMs?: number,
    stage?: string,
  ) {
    if (!login.session) return;
    enqueueTelemetry(
      {
        id: `${login.session.user_id}:${timing.messageId}:${stage ?? outcome}`,
        user: login.session.user_id,
        backend: login.backend,
        body: {
          message_id: timing.messageId,
          sent_at: timing.sentAt,
          channel: timing.channel,
          client_id: timing.clientId,
          device_id: timing.deviceId,
          trace_id: timing.traceId || '',
          accepted_ms: timing.acceptedMs,
          first_response_ms: timing.firstResponseMs,
          first_renderable_ms: timing.firstRenderableMs,
          first_paint_ms: timing.firstPaintMs,
          completed_ms: completedMs,
          outcome,
          stage: stage ?? `client.${outcome}`,
        },
      },
      login.session.access_token,
    );
  }
  const lifecycleReported = useRef(new Set<string>());
  useEffect(() => {
    const timing = state.responseTiming;
    if (!timing || !login.session) return;
    const transitions = [
      ['client.ack', timing.acceptedMs],
      ['client.first_response', timing.firstResponseMs],
      ['client.first_renderable', timing.firstRenderableMs],
      ['client.first_paint', timing.firstPaintMs],
    ] as const;
    for (const [stage, value] of transitions) {
      if (value === undefined) continue;
      const key = `${timing.messageId}:${stage}`;
      if (lifecycleReported.current.has(key)) continue;
      lifecycleReported.current.add(key);
      reportTelemetry(timing, 'in_progress', undefined, stage);
    }
  }, [state.responseTiming, login.session?.user_id]);
  useEffect(() => {
    if (!login.session) return;
    const { user_id, access_token } = login.session;
    const flush = () => {
      void flushTelemetry(user_id, login.backend, access_token);
    };
    flush();
    const timer = setInterval(flush, 10000);
    window.addEventListener('online', flush);
    return () => {
      clearInterval(timer);
      window.removeEventListener('online', flush);
    };
  }, [login.session?.access_token, login.backend]);
  useEffect(() => {
    const timing = state.responseTiming;
    if (
      !login.session ||
      !timing?.completedMs ||
      !timing.outcome ||
      telemetryReported.current.has(timing.messageId)
    )
      return;
    const messageId = timing.messageId;
    const timer = setTimeout(
      () => {
        const current = client.getSnapshot().responseTiming;
        if (
          !current ||
          current.messageId !== messageId ||
          !current.completedMs ||
          !current.outcome ||
          telemetryReported.current.has(messageId)
        )
          return;
        telemetryReported.current.add(messageId);
        reportTelemetry(
          current,
          current.outcome,
          current.completedMs,
          current.outcome === 'failed' ? 'client.error' : 'client.terminal',
        );
      },
      timing.traceId ? 250 : 900,
    );
    return () => clearTimeout(timer);
  }, [state.responseTiming, login.backend, login.session?.access_token]);
  useEffect(() => {
    const timing = state.responseTiming;
    if (
      !login.session ||
      !timing ||
      timing.completedMs ||
      timing.firstResponseMs !== undefined ||
      timing.outcome ||
      stalledReported.current.has(timing.messageId)
    )
      return;
    const messageId = timing.messageId;
    const wait = Math.max(0, 30_000 - (Date.now() - timing.sentAt));
    const timer = setTimeout(() => {
      const current = client.getSnapshot().responseTiming;
      if (
        !current ||
        current.messageId !== messageId ||
        current.completedMs ||
        current.firstResponseMs !== undefined ||
        current.outcome ||
        stalledReported.current.has(messageId)
      )
        return;
      stalledReported.current.add(messageId);
      reportTelemetry(current, 'stalled', undefined, 'client.stalled');
    }, wait);
    return () => clearTimeout(timer);
  }, [state.responseTiming, login.backend, login.session?.access_token]);
  useEffect(() => {
    if (state.responseTiming?.firstRenderableMs === undefined) return;
    if (state.responseTiming.firstPaintMs !== undefined) return;
    const frame = requestAnimationFrame(() => client.markFirstPaint());
    return () => cancelAnimationFrame(frame);
  }, [state.responseTiming?.firstRenderableMs, state.responseTiming?.firstPaintMs]);
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
  const compacting = compactionState(state.events, clock);
  const lastMessage = model.messages.at(-1);
  const awaitingReply =
    !model.pauseNotice &&
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
  }, [model.messages.length === 0, page]);
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
  function reconnect() {
    client.allowTakeover();
    login.reconnect();
  }
  useEffect(() => {
    if (!login.session) {
      client.setUserMessageObserver();
      return;
    }
    const session = login.session;
    client.setUserMessageObserver((message) => {
      enqueueTelemetry(
        {
          id: `${session.user_id}:${message.messageId}:user.message`,
          user: session.user_id,
          backend: login.backend,
          body: {
            message_id: message.messageId,
            sent_at: message.sentAt,
            channel: message.channel,
            client_id: message.clientId,
            device_id: message.deviceId,
            trace_id: '',
            content: message.content,
            outcome: 'sent',
            stage: 'user.message',
          },
        },
        session.access_token,
      );
    });
    return () => client.setUserMessageObserver();
  }, [login.backend, login.session?.access_token, login.session?.user_id]);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [uploading, setUploading] = useState(false);
  async function send() {
    if ((!draft.trim() && !attachments.length) || sending || uploading) return;
    if (!connected) {
      reconnect();
      setNotice('正在重新连接，草稿已保留，连接后可发送。');
      return;
    }
    const sentAttachments = [...attachments];
    const content = [draft.trim(), attachmentText(sentAttachments)].filter(Boolean).join('\n\n');
    setSending(true);
    setDraft('');
    setAttachments([]);
    following.current = true;
    setNearBottom(true);
    try {
      await client.message(
        content,
        sentAttachments.map((file) => file.attachment_id),
      );
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
  async function sendQuick(text: string) {
    if (sending || uploading || !text.trim()) return;
    if (!connected) {
      reconnect();
      setNotice('正在重新连接，连接后即可发送。');
      return;
    }
    setSending(true);
    following.current = true;
    setNearBottom(true);
    try {
      await client.message(text, []);
      requestAnimationFrame(() =>
        viewport.current?.scrollTo({ top: viewport.current.scrollHeight, behavior: 'instant' }),
      );
      input.current?.focus();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : String(error));
    } finally {
      setSending(false);
    }
  }
  const welcome = model.messages.length === 0;
  const latestMessage = model.messages.at(-1);
  const quickReplies =
    latestMessage?.role === 'assistant' && !latestMessage.streaming
      ? latestMessage.suggestions || []
      : [];
  if (!login.session) return <LoginScreen login={login} />;
  return (
    <div className={`app ${debug ? 'trace-page-open' : ''} ${desktop ? 'desktop' : ''}`}>
      <nav className="rail product-rail" aria-label="主导航">
        <button className="product-brand" onClick={() => navigate('home')} aria-label="Hymio 首页">
          <Companion compact />
          <b>hymio</b>
        </button>
        <div className="rail-primary">
          <button
            className={`rail-button ${page === 'home' && !debug ? 'active' : ''}`}
            aria-current={page === 'home' && !debug ? 'page' : undefined}
            onClick={() => navigate('home')}
          >
            <Home size={19} />
            <span>此刻</span>
          </button>
          <button
            className={`rail-button ${page === 'chat' && !debug ? 'active' : ''}`}
            aria-current={page === 'chat' && !debug ? 'page' : undefined}
            onClick={() => navigate('chat')}
          >
            <MessageCircle size={19} />
            <span>对话</span>
          </button>
          <button
            className={`rail-button ${page === 'moments' && !debug ? 'active' : ''}`}
            aria-current={page === 'moments' && !debug ? 'page' : undefined}
            onClick={() => navigate('moments')}
          >
            <Bookmark size={19} />
            <span>记忆</span>
          </button>
          <button className={`rail-button ${tasksOpen ? 'active' : ''}`} onClick={() => openTask()}>
            <Flag size={19} />
            <span>任务</span>
          </button>
          <button
            className={`rail-button ${settings ? 'active' : ''}`}
            onClick={() => setSettings(true)}
          >
            <UserRound size={19} />
            <span>我的</span>
          </button>
        </div>
        <div className="rail-bottom">
          <small>
            对话随时继续。
            <br />
            交代的事，也继续推进。
          </small>
        </div>
      </nav>
      {!debug && page === 'home' && (
        <HomePanel
          key={`${login.backend}|${login.session.user_id}`}
          login={login}
          mood={mood}
          hasConversation={model.messages.length > 0}
          conversationReady={connected}
          onChat={() => navigate('chat')}
          onTask={openTask}
        />
      )}
      {memoryVisited && (
        <div className="memory-route" hidden={debug || page !== 'moments'}>
          <MomentsPanel key={`${login.session.backend}|${login.session.user_id}`} login={login} />
        </div>
      )}
      <main className="main" hidden={debug || page !== 'chat'}>
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
              {(busy || streaming || awaitingReply) && <Companion compact mood={mood} />}
              <StatusBadge tone={connected ? 'active' : 'neutral'}>{status}</StatusBadge>
              <ChevronDown size={12} />
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
            input.current?.blur();
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
              {buildTurns(model.messages).map((turn) => (
                <div key={turn.id}>
                  {unreadMessages[0] && turn.final?.id === unreadMessages[0].id && (
                    <div className="unread-divider">
                      <span />
                      <button onClick={() => client.markRead()}>
                        {unreadMessages.length} 条未读消息
                      </button>
                      <span />
                    </div>
                  )}
                  <TraceBlock
                    key={turn.id}
                    turn={turn}
                    tools={model.tools}
                    login={login}
                    approvals={model.approvals}
                    onAction={async (text) => {
                      following.current = true;
                      setNearBottom(true);
                      await client.message(text);
                    }}
                  />
                </div>
              ))}
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
              {(busy || streaming || awaitingReply) && !compacting && (
                <div className="message working-indicator">
                  <span>
                    Hymio {streaming ? '正在回复' : awaitingReply ? '正在等候回复' : '正在接着做'}
                    <i />
                    <i />
                    <i />
                  </span>
                </div>
              )}
              {model.pauseNotice && (
                <p role="status" className="tool-history-summary">
                  {model.pauseNotice}
                </p>
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
          <CompactionStatus events={state.events} now={clock} />
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
              {!connected && login.session && <button onClick={reconnect}>重新连接</button>}
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
              <button onClick={reconnect}>重新连接</button>
              <button onClick={() => setSettings(true)}>账号设置</button>
            </div>
          )}
          {quickReplies.length > 0 && !sending && !streaming && (
            <div className="quick-replies" aria-label="快捷回复">
              {quickReplies.map((text) => (
                <button
                  key={text}
                  onClick={(event) => {
                    event.stopPropagation();
                    void sendQuick(text);
                  }}
                >
                  {text}
                </button>
              ))}
            </div>
          )}
          <div className="composer" onClick={() => input.current?.focus()}>
            <Attachments
              login={login}
              files={attachments}
              onChange={setAttachments}
              onBusy={setUploading}
              onError={setNotice}
              pasteTarget={input}
            />
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
                  onClick={(event) => {
                    event.stopPropagation();
                    void act(() => client.command('run.cancel', {}));
                  }}
                >
                  <Square size={13} />
                </button>
              )}
              <button
                className={`send-button ${draft.trim() || attachments.length ? 'has-text' : ''}`}
                aria-label={connected ? '发送消息' : '重新连接'}
                disabled={sending || uploading || (!draft.trim() && !attachments.length)}
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
        <TracePage
          key={`${connection.wsUrl}|${state.userId}`}
          state={state}
          connection={connection}
          onClose={() => setDebug(false)}
          onStatus={() => client.status()}
          onCancel={() => void act(() => client.command('run.cancel', {}))}
          onRetry={() => void act(() => client.command('step.retry', {}))}
        />
      )}
      {tasksOpen && (
        <TasksPanel
          login={login}
          initialSelected={selectedTask}
          onClose={() => setTasksOpen(false)}
        />
      )}
      {settings && (
        <Settings
          login={login}
          onClose={() => setSettings(false)}
          onTrace={() => {
            setSettings(false);
            setDebug(true);
          }}
        />
      )}
    </div>
  );
}
