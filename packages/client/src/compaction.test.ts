import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { OathEvent } from '@hymio/protocol';
import { compactionState } from './compaction.ts';
const now = Date.parse('2026-10-24T12:00:00Z');
function event(status: string, mode = 'async', at = now): OathEvent {
  return {
    v: 2,
    type: 'event',
    user_id: 'synthetic',
    event_seq: 1,
    event_type: 'context.compaction',
    occur_dt: new Date(at).toISOString(),
    payload: { compression_id: 'test', status, mode },
  };
}
test('pending and applied have different visible meanings', () => {
  const ready = compactionState([event('ready')], now);
  assert.match(ready!.detail, /才会使用/);
  assert.match(compactionState([event('applied')], now)!.detail, /近期内容保留原文/);
  assert.equal(ready!.working, false);
});
test('sync and async waiting explain different effects', () => {
  assert.match(compactionState([event('started')], now)!.detail, /不影响/);
  assert.match(compactionState([event('started', 'sync')], now)!.detail, /完成后继续回复/);
});
test('old completed states and stale spinners do not stay forever', () => {
  assert.equal(compactionState([event('applied', 'sync', now - 61000)], now), undefined);
  assert.equal(compactionState([event('started', 'sync', now - 901000)], now), undefined);
  assert.equal(compactionState([event('skipped')], now), undefined);
  assert.equal(compactionState([], now), undefined);
});
