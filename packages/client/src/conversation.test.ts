import assert from 'node:assert/strict';
import test from 'node:test';
import type { OathEvent, Data } from '@hymio/protocol';
import { conversation } from './conversation.ts';

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
