import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { OathEvent } from '@hymio/protocol';
import { compactionState } from './compaction.ts';
const now = Date.parse('2026-10-24T12:00:00Z');
function event(
  status: string,
  mode = 'async',
  at = now,
  compression = 'test',
  sequence = 1,
): OathEvent {
  return {
    v: 2,
    type: 'event',
    user_id: 'synthetic',
    event_seq: sequence,
    event_type: 'context.compaction',
    occur_dt: new Date(at).toISOString(),
    payload: {
      compression_id: compression,
      status,
      mode,
      input_tokens: 150_000,
      output_tokens: 346,
    },
  };
}

test('async preparation never appears in the conversation', () => {
  for (const status of ['started', 'ready', 'applied', 'failed']) {
    assert.equal(compactionState([event(status)], now), undefined);
  }
});

test('sync preparation is one human status without implementation details', () => {
  const state = compactionState([event('started', 'sync')], now);
  assert.equal(state?.title, '我整理一下前面的内容，马上继续');
  assert.equal(state?.working, true);
  assert.equal('detail' in state!, false);
  assert.equal('metrics' in state!, false);
});

test('a matching terminal event clears only its own sync status', () => {
  assert.equal(
    compactionState(
      [event('started', 'sync', now, 'first', 1), event('ready', 'async', now, 'other', 2)],
      now,
    )?.id,
    1,
  );
  for (const status of ['ready', 'applied', 'failed', 'skipped']) {
    assert.equal(
      compactionState(
        [event('started', 'sync', now, 'first', 1), event(status, 'sync', now, 'first', 2)],
        now,
      ),
      undefined,
    );
  }
});

test('stale or missing sync states do not stay forever', () => {
  assert.equal(compactionState([event('started', 'sync', now - 901000)], now), undefined);
  assert.equal(compactionState([], now), undefined);
});
