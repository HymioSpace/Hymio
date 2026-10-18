import {
  parseFrame,
  type Command,
  type Connection,
  type Data,
  type Frame,
  type OathEvent,
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
    this.update({ events: [], pending: [], userId: '', replay: undefined, latency: undefined });
    this.config = { ...config };
    this.retries = 0;
    this.open();
  }
  disconnect() {
    this.generation++;
    this.ready = false;
    clearTimeout(this.timer);
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
    const deviceKey = `hymio.device:${config.wsUrl}`;
    let clientId = sessionStorage.getItem(deviceKey);
    if (!clientId) {
      clientId = `hymio-${identity()}`;
      sessionStorage.setItem(deviceKey, clientId);
    }
    this.watchdog = setTimeout(() => socket.close(), 12000);
    socket.onopen = () =>
      this.raw({
        v: 2,
        type: 'agent.attach',
        id: attachId,
        payload: { credential: config.credential, user_id: config.userId, client_id: clientId! },
      });
    socket.onmessage = (event) => {
      chain = chain
        .then(async () => {
          if (generation !== this.generation) return;
          const frame = parseFrame(String(event.data));
          if (frame.type === 'ack' && frame.id === attachId && frame.user_id) {
            clearTimeout(this.watchdog);
            this.account = `${config.wsUrl}|${frame.user_id}`;
            const events = await storage.events(this.account);
            const pending = await storage.commands(this.account);
            if (generation !== this.generation) return;
            this.seen = new Set(events.map((e) => e.event_seq));
            this.update({ userId: frame.user_id, events, pending, phase: 'syncing' });
          } else if (frame.type === 'event') {
            const e = frame as OathEvent;
            if (e.user_id !== this.state.userId) throw new Error('用户身份与事件不一致');
            await storage.saveEvent(this.account, e);
            if (generation !== this.generation) return;
            if (!this.seen.has(e.event_seq)) {
              this.seen.add(e.event_seq);
              this.update({
                events: [...this.state.events, e].sort((a, b) => a.event_seq - b.event_seq),
              });
            }
            this.ephemeral('event.ack', { cursor: e.event_seq });
            if (this.state.replay && this.state.phase === 'syncing')
              this.update({
                replay: { ...this.state.replay, received: this.state.replay.received + 1 },
              });
          } else if (frame.type === 'offline.start') {
            if ((frame.after_cursor ?? 0) > (this.state.events.at(-1)?.event_seq ?? 0)) {
              // Local storage was evicted after an ACK. A fresh device cursor requests full replay.
              sessionStorage.setItem(deviceKey, `hymio-${identity()}`);
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
          } else if (frame.type === 'offline.end') {
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
      clearInterval(this.heartbeat);
      clearTimeout(this.watchdog);
      if (!this.config) return;
      this.update({ phase: 'reconnecting' });
      const delay = Math.min(1000 * 2 ** this.retries++, 15000);
      this.timer = setTimeout(() => this.open(), delay);
    };
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
