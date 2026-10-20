import assert from 'node:assert/strict';
import test from 'node:test';
import type { Message } from './conversation.ts';
import { buildTurns, formatDuration, traceElapsed } from './turns.ts';

let clock = Date.parse('2026-01-01T00:00:00Z');
const message = (patch: Partial<Message> & Pick<Message, 'id' | 'role'>): Message => ({
  content: '',
  time: new Date(clock).toISOString(),
  ...patch,
});
const user = (id: string, patch: Partial<Message> = {}) => message({ id, role: 'user', ...patch });
const assistant = (id: string, patch: Partial<Message> = {}) =>
  message({ id, role: 'assistant', ...patch });

test('a trace collapses everything before its final tool-call-free message', () => {
  clock = Date.parse('2026-01-01T00:00:00Z');
  const turns = buildTurns([
    user('user:1', { content: '跑个命令' }),
    assistant('assistant:s1', { traceId: 't1', content: '我先看看', calls: [{ name: 'bash' }] }),
    assistant('assistant:s2', { traceId: 't1', content: '执行完了' }),
  ]);
  assert.equal(turns.length, 1);
  const [turn] = turns;
  assert.equal(turn.user?.id, 'user:1');
  assert.equal(turn.final?.id, 'assistant:s2');
  assert.deepEqual(
    turn.activity.map((m) => m.id),
    ['assistant:s1'],
  );
  assert.equal(turn.settled, true);
  assert.equal(traceElapsed(turn, 0), 0);
});

test('a message with tool calls never ends the trace', () => {
  const turns = buildTurns([
    user('user:1'),
    assistant('assistant:s1', { traceId: 't1', content: '先查一下', calls: [{ name: 'bash' }] }),
  ]);
  assert.equal(turns[0].final, null);
  assert.equal(turns[0].settled, false);
  assert.equal(turns[0].activity.length, 1);
});

test('a streaming final message keeps the whole trace expanded', () => {
  const turns = buildTurns([
    user('user:1'),
    assistant('assistant:s1', { traceId: 't1', content: '', calls: [{ name: 'bash' }] }),
    assistant('assistant:s2', { traceId: 't1', content: '正在写', streaming: true }),
  ]);
  assert.equal(turns[0].settled, false);
  assert.equal(turns[0].trailing.length, 0);
});

test('tool steps chained by one trace stay in the same turn', () => {
  const turns = buildTurns([
    user('user:1'),
    assistant('assistant:s1', { traceId: 't1', content: '', calls: [{ name: 'bash' }] }),
    assistant('assistant:s2', { traceId: 't1', content: '继续', calls: [{ name: 'browser' }] }),
    assistant('assistant:s3', { traceId: 't1', content: '好了' }),
  ]);
  assert.equal(turns.length, 1);
  assert.equal(turns[0].activity.length, 2);
  assert.equal(turns[0].final?.id, 'assistant:s3');
});

test('a new trace finishing first does not swallow the older trace final reply', () => {
  const turns = buildTurns([
    user('user:1'),
    assistant('assistant:s1', { traceId: 't1', content: '先查', calls: [{ name: 'bash' }] }),
    user('user:2'),
    assistant('assistant:s2', { traceId: 't2', content: '换个方向', calls: [{ name: 'browser' }] }),
    assistant('assistant:s3', { traceId: 't2', content: '都办完了' }),
    assistant('assistant:s4', { traceId: 't1', content: '先查那条也完了' }),
  ]);
  assert.deepEqual(
    turns.map((t) => [t.user?.id, t.final?.id, t.settled]),
    [
      ['user:1', 'assistant:s4', true],
      ['user:2', 'assistant:s3', true],
    ],
  );
  assert.deepEqual(
    turns.map((t) => t.activity.map((m) => m.id)),
    [['assistant:s1'], ['assistant:s2']],
  );
});

test('history without trace ids still splits on user messages', () => {
  const turns = buildTurns([
    user('user:1'),
    assistant('assistant:s1', { content: '', calls: [{ name: 'bash' }] }),
    assistant('assistant:s2', { content: '好' }),
    user('user:2'),
    assistant('assistant:s3', { content: '在' }),
  ]);
  assert.equal(turns.length, 2);
  assert.equal(turns[0].settled, true);
  assert.equal(turns[1].settled, true);
});

test('a trace abandoned by the next user message still collapses', () => {
  const turns = buildTurns([
    user('user:1'),
    assistant('assistant:s1', { traceId: 't1', content: '', calls: [{ name: 'bash' }] }),
    user('user:2'),
    assistant('assistant:s2', { content: '在' }),
  ]);
  assert.equal(turns[0].settled, true);
  assert.equal(turns[0].final, null);
  assert.equal(turns[0].activity.length, 1);
});

test('a trace with nothing after the user message stays open', () => {
  const turns = buildTurns([user('user:1')]);
  assert.equal(turns[0].settled, false);
  assert.equal(turns[0].activity.length, 0);
  assert.equal(turns[0].endedAt, null);
});

test('elapsed falls back to a server-clock estimate while a trace runs', () => {
  const start = Date.parse('2026-01-01T00:00:00Z');
  const [turn] = buildTurns([
    user('user:1', { time: new Date(start).toISOString() }),
    assistant('assistant:s1', {
      traceId: 't1',
      time: new Date(start + 4000).toISOString(),
      content: '',
      calls: [{ name: 'bash' }],
    }),
  ]);
  assert.equal(traceElapsed(turn, start + 9000), 9000);
  assert.equal(turn.endedAt, null);
});

test('durations read the way a person would say them', () => {
  assert.equal(formatDuration(900), '1 秒');
  assert.equal(formatDuration(43_000), '43 秒');
  assert.equal(formatDuration(163_000), '2 分 43 秒');
  assert.equal(formatDuration(120_000), '2 分');
  assert.equal(formatDuration(7_260_000), '2 小时 1 分');
  assert.equal(formatDuration(null), '');
});
