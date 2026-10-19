import {
  parseFrame,
  type Command,
  type Connection,
  type Data,
  type Frame,
  type OathEvent,
  type ConversationPage,
} from '@hymio/protocol';
import { storage, type Pending } from './storage';
const identity = () =>
  crypto.randomUUID?.() ??
  Array.from(crypto.getRandomValues(new Uint8Array(16)), (value) =>
    value.toString(16).padStart(2, '0'),
  ).join('');

export type Phase =
  | 'disconnected'
  | 'connecting'
  | 'reconnecting'
  | 'syncing'
  | 'connected'
  | 'error';
export interface ClientState {
  phase: Phase;
  userId: string;
  events: OathEvent[];
  pending: Pending[];
  error: string;
  replay?: { after: number; through: number; received: number };
  runtime?: Data;
  latency?: number;
  history?: { before: number | null; hasMore: boolean };
}
export class OathClient {
  private state: ClientState = {
    phase: 'disconnected',
    userId: '',
    events: [],
    pending: [],
    error: '',
  };
  private listeners = new Set<() => void>();
  private socket?: WebSocket;
  private timer?: ReturnType<typeof setTimeout>;
  private heartbeat?: ReturnType<typeof setInterval>;
  private watchdog?: ReturnType<typeof setTimeout>;
  private config?: Connection;
  private generation = 0;
  private retries = 0;
  private account = '';
  private seen = new Set<number>();
  private sent = new Set<string>();
  private ready = false;
  private pingAt = 0;
  private clientId = `hymio-${identity()}`;
  private sourceDeviceId = '';
  private cursor = 0;
  private ackTimer?: ReturnType<typeof setTimeout>;
  setSourceDevice(deviceId: string) {
    this.sourceDeviceId = deviceId;
  }
  subscribe = (fn: () => void) => {
    this.listeners.add(fn);
    return () => {
      this.listeners.delete(fn);
    };
  };
  getSnapshot = () => this.state;
  private update(patch: Partial<ClientState>) {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach((fn) => fn());
  }
  connect(config: Connection) {
    const url = new URL(config.wsUrl);
    if (
      !['ws:', 'wss:'].includes(url.protocol) ||
      url.username ||
      url.password ||
      (!config.credential.trim() && !config.userId?.trim())
    )
      throw new Error('请输入有效的 WS 地址和用户凭据');
    this.disconnect();
    this.account = '';
    this.seen.clear();
    this.update({
      events: [],
      pending: [],
      userId: '',
      replay: undefined,
      history: undefined,
      latency: undefined,
    });
    this.config = { ...config };
    this.retries = 0;
    this.open();
  }
  disconnect() {
    this.generation++;
    this.ready = false;
    clearTimeout(this.timer);
    clearTimeout(this.ackTimer);
    this.ackTimer = undefined;
    clearInterval(this.heartbeat);
    clearTimeout(this.watchdog);
    this.socket?.close();
    this.socket = undefined;
    this.config = undefined;
    this.update({ phase: 'disconnected', runtime: undefined });
  }
  signOut() {
    this.disconnect();
    this.account = '';
    this.seen.clear();
    this.sent.clear();
    this.sourceDeviceId = '';
    this.cursor = 0;
    this.update({ events: [], pending: [], userId: '', error: '', replay: undefined });
  }
  private open() {
    if (!this.config) return;
    const generation = ++this.generation;
    const config = this.config;
    this.update({ phase: this.retries ? 'reconnecting' : 'connecting', error: '' });
    this.ready = false;
    this.sent.clear();
    const socket = new WebSocket(config.wsUrl);
    this.socket = socket;
    let chain = Promise.resolve();
    const attachId = identity();
    // A window owns its delivery cursor. Duplicating a tab must not fence the original socket.
    const clientId = this.clientId;
    this.watchdog = setTimeout(() => socket.close(), 12000);
    socket.onopen = () =>
      this.raw({
        v: 2,
        type: 'agent.attach',
        id: attachId,
        payload: {
          credential: config.credential,
          user_id: config.userId,
          client_id: clientId!,
          history_limit: 10,
        },
      });
    socket.onmessage = (event) => {
      chain = chain
        .then(async () => {
          if (generation !== this.generation) return;
          const frame = parseFrame(String(event.data));
          if (frame.type === 'ack' && frame.id === attachId && frame.user_id) {
            clearTimeout(this.watchdog);
            this.account = `${config.wsUrl}|${frame.user_id}`;
            const snapshot = await storage.snapshot(this.account);
            const cached = snapshot ? await storage.events(this.account) : [];
            const visible = new Set(snapshot?.events.map((e) => e.event_seq));
            const events = cached.filter(
              (e) => e.event_seq > (snapshot?.checkpoint || 0) || visible.has(e.event_seq),
            );
            const pending = await storage.commands(this.account);
            if (generation !== this.generation) return;
            this.seen = new Set(events.map((e) => e.event_seq));
            this.cursor = snapshot?.checkpoint || 0;
            while (this.seen.has(this.cursor + 1)) this.cursor++;
            this.update({ userId: frame.user_id, events, pending, phase: 'syncing' });
          } else if (frame.type === 'conversation.snapshot') {
            const snapshot = this.validatePage(frame);
            await storage.savePage(this.account, snapshot, true);
            if (generation !== this.generation) return;
            this.seen = new Set(snapshot.events.map((e) => e.event_seq));
            this.cursor = snapshot.checkpoint;
            this.update({
              events: snapshot.events,
              history: { before: snapshot.before_cursor, hasMore: snapshot.has_more },
            });
            this.ephemeral('event.ack', { cursor: this.cursor });
          } else if (frame.type === 'event') {
            const e = frame as OathEvent;
            if (e.user_id !== this.state.userId) throw new Error('用户身份与事件不一致');
            if (!this.seen.has(e.event_seq)) {
              await storage.saveEvent(this.account, e);
              if (generation !== this.generation) return;
              this.seen.add(e.event_seq);
              this.update({
                events: [...this.state.events, e].sort((a, b) => a.event_seq - b.event_seq),
              });
            }
            if (e.event_seq > this.cursor + 1) {
              this.clientId = `hymio-${identity()}`;
              socket.close();
              return;
            }
            this.cursor = Math.max(this.cursor, e.event_seq);
            if (!this.ackTimer)
              this.ackTimer = setTimeout(() => {
                this.ackTimer = undefined;
                if (generation === this.generation)
                  this.ephemeral('event.ack', { cursor: this.cursor });
              }, 100);
            if (this.state.replay && this.state.phase === 'syncing')
              this.update({
                replay: { ...this.state.replay, received: this.state.replay.received + 1 },
              });
          } else if (frame.type === 'offline.start') {
            if ((frame.after_cursor ?? 0) > this.cursor) {
              // Local storage was evicted after an ACK. A fresh device cursor requests full replay.
              this.clientId = `hymio-${identity()}`;
              socket.close();
              return;
            }
            this.update({
              phase: 'syncing',
              replay: {
                after: frame.after_cursor ?? 0,
                through: frame.through_cursor ?? 0,
                received: 0,
              },
            });
            this.cursor = frame.after_cursor ?? 0;
          } else if (frame.type === 'offline.end') {
            this.ephemeral('event.ack', { cursor: this.cursor });
            this.ready = true;
            this.retries = 0;
            this.update({ phase: 'connected' });
            this.flush();
            this.status();
            clearInterval(this.heartbeat);
            this.heartbeat = setInterval(() => {
              this.pingAt = performance.now();
              this.ephemeral('ping', {});
              clearTimeout(this.watchdog);
              this.watchdog = setTimeout(() => socket.close(), 12000);
            }, 20000);
          } else if (frame.type === 'ack' && frame.id) {
            await storage.removeCommand(frame.id);
            if (generation === this.generation)
              this.update({ pending: this.state.pending.filter((p) => p.id !== frame.id) });
          } else if (frame.type === 'agent.status') this.update({ runtime: frame.payload });
          else if (frame.type === 'pong') {
            clearTimeout(this.watchdog);
            this.update({ latency: Math.round(performance.now() - this.pingAt) });
          } else if (frame.type === 'error') {
            const f = frame as Frame;
            if (f.id && this.state.pending.some((p) => p.id === f.id)) {
              // Keep the original identity for an explicit retry after rejection.
              this.update({ error: f.message || '命令被拒绝' });
              this.sent.delete(f.id);
            } else if (f.code === 'connection_closed') {
              // The gateway also uses this for temporary auth-service outages.
              // Preserve connection settings so onclose can retry with backoff.
              this.update({ phase: 'reconnecting', error: f.message || '连接暂时中断，正在重连…' });
              socket.close();
            } else {
              this.config = undefined;
              this.update({ phase: 'error', error: f.message || f.code || '连接认证失败' });
              socket.close();
            }
          }
        })
        .catch((error) => {
          if (generation !== this.generation) return;
          this.config = undefined;
          this.update({ phase: 'error', error: `无法安全保存或读取事件：${String(error)}` });
          socket.close();
        });
    };
    socket.onerror = () => {
      if (generation === this.generation)
        this.update({ error: '无法连接 Oath，请确认服务正在运行。' });
    };
    socket.onclose = () => {
      if (generation !== this.generation) return;
      this.ready = false;
      clearTimeout(this.ackTimer);
      this.ackTimer = undefined;
      clearInterval(this.heartbeat);
      clearTimeout(this.watchdog);
      if (!this.config) return;
      this.update({ phase: 'reconnecting' });
      const delay = Math.min(1000 * 2 ** this.retries++, 15000);
      this.timer = setTimeout(() => this.open(), delay);
    };
  }
  private validatePage(value: unknown): ConversationPage {
    const page = value as ConversationPage;
    if (
      !page ||
      !Number.isSafeInteger(page.checkpoint) ||
      page.checkpoint < 0 ||
      !Array.isArray(page.events) ||
      typeof page.has_more !== 'boolean' ||
      !(page.before_cursor === null || Number.isSafeInteger(page.before_cursor))
    )
      throw new Error('会话快照格式无效');
    for (const event of page.events) {
      parseFrame(JSON.stringify(event));
      if (event.user_id !== this.state.userId || event.event_seq > page.checkpoint)
        throw new Error('会话快照身份或进度无效');
    }
    return page;
  }
  async prependHistory(value: unknown) {
    const incoming = this.validatePage(value);
    const page = {
      ...incoming,
      events: incoming.events.filter((event) => event.event_seq <= this.cursor),
    };
    const generation = this.generation;
    await storage.savePage(this.account, page, false);
    if (generation !== this.generation) return;
    for (const event of page.events) this.seen.add(event.event_seq);
    const events = new Map(page.events.map((e) => [e.event_seq, e]));
    for (const event of this.state.events) events.set(event.event_seq, event);
    this.update({
      events: [...events.values()].sort((a, b) => a.event_seq - b.event_seq),
      history: { before: page.before_cursor, hasMore: page.has_more },
    });
  }
  private raw(command: Command) {
    if (this.socket?.readyState === WebSocket.OPEN) this.socket.send(JSON.stringify(command));
  }
  private ephemeral(type: string, payload: Data) {
    this.raw({ v: 2, id: identity(), type, payload });
  }
  private flush() {
    if (!this.ready) return;
    for (const pending of this.state.pending)
      if (!this.sent.has(pending.id)) {
        this.raw(pending.command);
        this.sent.add(pending.id);
      }
  }
  async command(type: string, payload: Data) {
    if (!this.ready || !this.account) throw new Error('连接恢复后再发送，草稿会保留。');
    const generation = this.generation;
    const command: Command = { v: 2, id: identity(), type, payload };
    const pending: Pending = { id: command.id, account: this.account, command, at: Date.now() };
    await storage.saveCommand(pending);
    if (generation !== this.generation || pending.account !== this.account) return command.id;
    this.update({ pending: [...this.state.pending, pending], error: '' });
    this.flush();
    return command.id;
  }
  message(content: string) {
    return this.command('user.message', {
      content,
      user_context: {
        locale: navigator.language,
        time_zone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        source_device_id: this.sourceDeviceId || null,
        client_id: this.clientId,
        received_event_seq: this.cursor,
      },
    });
  }
  decide(invocationId: string, status: 'approved' | 'denied') {
    return this.command('permission.decide', { invocation_id: invocationId, status });
  }
  status() {
    if (this.ready) this.ephemeral('agent.status', {});
  }
  retryPending() {
    this.sent.clear();
    this.flush();
  }
  clearError() {
    this.update({ error: '' });
  }
}
