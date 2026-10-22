import assert from 'node:assert/strict';
import test from 'node:test';
import type { OathEvent, Data } from '@hymio/protocol';
import { replayBoundary, conversation, executionActivity } from './conversation.ts';

const event = (seq: number, type: string, payload: Data): OathEvent => ({
  v: 2,
  type: 'event',
  user_id: 'test',
  event_seq: seq,
  event_type: type,
  payload,
  occur_dt: '2026-01-01T00:00:00Z',
});

test('a retried stream is replaced by its new attempt and final response', () => {
  const result = conversation([
    event(1, 'assistant.delta', { step_id: 'a', attempt: 1, channel: 'content', text: 'partial' }),
    event(2, 'assistant.delta', { step_id: 'a', attempt: 2, channel: 'content', text: 'new' }),
    event(3, 'assistant.message', { step_id: 'a', content: 'final', tool_calls: [] }),
    event(4, 'assistant.delta', { step_id: 'a', attempt: 1, channel: 'content', text: 'late' }),
  ]);
  assert.equal(result.messages.length, 1);
  assert.equal(result.messages[0].content, 'final');
  assert.equal(result.messages[0].streaming, false);
});

test('hidden quick replies attach to the final assistant message', () => {
  const content = '先这样。\n\n```hymio-quick\n["先停下吧","换个方向"]\n```';
  const result = conversation([
    event(1, 'assistant.delta', {
      step_id: 'a',
      attempt: 1,
      channel: 'content',
      text: content,
    }),
    event(2, 'assistant.message', { step_id: 'a', content, tool_calls: [] }),
  ]);
  assert.equal(result.messages[0].content, '先这样。');
  assert.deepEqual(result.messages[0].suggestions, ['先停下吧', '换个方向']);
});

test('identical user text remains two distinct accepted inputs', () => {
  const result = conversation([
    event(1, 'user.message', { content: 'hello' }),
    event(2, 'user.message', { content: 'hello' }),
  ]);
  assert.equal(result.messages.length, 2);
  assert.notEqual(result.messages[0].id, result.messages[1].id);
});

test('approval resolution and tool terminal update their original identities', () => {
  const result = conversation([
    event(1, 'assistant.message', {
      step_id: 'a',
      content: '',
      tool_calls: [{ name: 'bash', arguments: { command: 'pwd' } }],
    }),
    event(2, 'permission.requested', {
      invocation_id: 'a-0',
      tool: 'bash',
      arguments: { command: 'pwd' },
      expires_at: 1,
    }),
    event(3, 'permission.resolved', { invocation_id: 'a-0', status: 'approved' }),
    event(4, 'tool.terminal', {
      invocation_id: 'a-0',
      tool: 'bash',
      outcome: 'succeeded',
      content: '/workspace',
    }),
  ]);
  assert.equal(result.approvals[0].status, 'approved');
  assert.equal(result.tools.length, 1);
  assert.equal(result.tools[0].outcome, 'succeeded');
  assert.equal(result.tools[0].result, '/workspace');
});

test('retry clears the failed step and a later message does not retain its error', () => {
  const failed = event(1, 'step.status', {
    step_id: 'first',
    status: 'failed',
    error: 'Server disconnected',
  });
  assert.equal(conversation([failed]).latestStep?.error, 'Server disconnected');
  const retried = event(2, 'step.status', {
    step_id: 'first',
    status: 'prepared',
    error: null,
  });
  assert.equal(conversation([failed, retried]).latestStep?.error, '');
  const later = event(3, 'user.message', { content: 'next task' });
  assert.equal(conversation([failed, later]).latestStep, undefined);
  const newFailure = event(4, 'step.status', {
    step_id: 'second',
    status: 'failed',
    error: 'Still disconnected',
  });
  assert.equal(conversation([failed, retried, later, newFailure]).latestStep?.eventSeq, 4);
});

test('a completed runtime does not inherit a historical unsubmitted tool proposal', () => {
  const events = [
    event(1, 'assistant.message', {
      step_id: 'old',
      content: '',
      tool_calls: [{ name: 'computer', arguments: {} }],
    }),
    event(2, 'step.status', { step_id: 'old', status: 'completed' }),
  ];
  const runtime = { calls: {}, steps: { old: { status: 'completed' } } };
  assert.equal(executionActivity(events, runtime, 2).busy, false);
  assert.equal(executionActivity(events, runtime, 2).toolsRunning, false);
  assert.equal(executionActivity(events, { calls: { a: { status: 'running' } } }, 2).busy, true);
  assert.equal(
    executionActivity(events, { calls: { a: { status: 'waiting_approval' } } }, 2).busy,
    false,
  );
});

test('a stale idle snapshot cannot hide a newer running step', () => {
  const events = [event(3, 'step.status', { step_id: 'new', status: 'running' })];
  assert.equal(executionActivity(events, { calls: {}, steps: {} }, 2).busy, true);
});

test('step completion closes a partial stream and latest status follows event order', () => {
  const events = [
    event(1, 'assistant.delta', { step_id: 'a', channel: 'content', text: 'hello' }),
    event(2, 'step.status', { step_id: 'b', status: 'completed' }),
    event(3, 'step.status', { step_id: 'a', status: 'completed' }),
  ];
  assert.equal(conversation(events).messages[0].streaming, false);
  assert.equal(conversation(events).latestStep?.id, 'a');
});

test('local messages render before events and exact echoed IDs replace them', () => {
  const make = (id: string) => ({
    id,
    account: 'test',
    at: Date.parse('2026-01-01T00:00:01Z'),
    command: {
      v: 2 as const,
      id,
      type: 'user.message',
      payload: { content: 'same', user_context: { hymio_message_id: id } },
    },
  });
  const pending = [make('one'), make('two')];
  assert.equal(conversation([], pending).messages.length, 2);
  assert.equal(conversation([], pending).messages[0].delivery, 'queued');
  const echo = event(1, 'user.message', {
    content: 'same',
    user_context: { hymio_message_id: 'one' },
  });
  const messages = conversation([echo], pending).messages;
  assert.equal(messages.length, 2);
  assert.equal(messages[0].id, 'user:1');
  assert.equal(messages[1].id, 'local:two');
  const other = event(2, 'user.message', {
    content: 'same',
    user_context: { hymio_message_id: 'other-device' },
  });
  assert.equal(conversation([other], pending).messages.length, 3);
  assert.equal(
    conversation([], [{ ...make('one'), delivery: 'accepted' as const }]).messages[0].delivery,
    'accepted',
  );
});

test('a finalised reply is stamped when it landed, not when its first delta arrived', () => {
  const stream = event(1, 'assistant.delta', {
    step_id: 'a',
    attempt: 1,
    channel: 'content',
    text: '答',
  });
  const result = conversation([
    { ...stream, occur_dt: '2026-01-01T00:00:00.000000Z' },
    {
      ...event(2, 'assistant.message', { step_id: 'a', content: '答案', tool_calls: [] }),
      occur_dt: '2026-01-01T00:00:04.000000Z',
    },
  ]);
  assert.equal(result.messages[0].time, '2026-01-01T00:00:04.000000Z');
  // 快照回放不带已完结 step 的增量，只有定稿事件 —— 两条路径必须给出同一个时间。
  const replayed = conversation([
    {
      ...event(2, 'assistant.message', { step_id: 'a', content: '答案', tool_calls: [] }),
      occur_dt: '2026-01-01T00:00:04.000000Z',
    },
  ]);
  assert.equal(replayed.messages[0].time, result.messages[0].time);
});

test('a failed send stays before later proactive replies', () => {
  const later = {
    ...event(9, 'assistant.message', { step_id: 'reminder', content: '提醒' }),
    occur_dt: '2026-01-01T02:00:00Z',
  };
  const pending = [
    {
      id: 'failed',
      account: 'test',
      at: Date.parse('2026-01-01T01:00:00Z'),
      delivery: 'failed' as const,
      command: {
        v: 2 as const,
        id: 'failed',
        type: 'user.message',
        payload: { content: 'hello', user_context: { hymio_message_id: 'failed' } },
      },
    },
  ];
  assert.deepEqual(
    conversation([later], pending).messages.map((m) => m.id),
    ['local:failed', 'assistant:reminder'],
  );
});

test('snapshot statuses arriving after messages restore trace identity', () => {
  const result = conversation([
    event(1, 'assistant.message', { step_id: 's', content: 'done' }),
    event(2, 'step.status', { step_id: 's', status: 'completed', trace_id: 'trace' }),
  ]);
  assert.equal(result.messages[0].traceId, 'trace');
});

test('unread boundary uses the pre-snapshot cursor and counts replies, not tool events', () => {
  const reply = event(20, 'assistant.message', { step_id: 's', content: 'hello', tool_calls: [] });
  assert.deepEqual(replayBoundary([reply], 10, 22), { after: 10, through: 22 });
  assert.equal(replayBoundary([reply], 0, 22), undefined);
  assert.equal(replayBoundary([event(20, 'tool.terminal', {})], 10, 22), undefined);
  assert.deepEqual(replayBoundary([reply], 15, 22, { after: 10, through: 14 }), {
    after: 10,
    through: 22,
  });
});
