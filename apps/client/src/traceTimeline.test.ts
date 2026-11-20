import assert from 'node:assert/strict';
import test from 'node:test';
import { orderedTraceEntries } from './traceTimeline.ts';
import type { Span, Trace } from '@hymio/protocol';

function span(name: string, start: number, events: Span['events']): Span {
  return {
    span_id: name.padEnd(16, '0').slice(0, 16),
    parent_span_id: null,
    name,
    start_unix_nano: start,
    end_unix_nano: start + 10,
    status: 'ok',
    duration_ms: 10,
    attributes: {},
    events,
    links: [],
  };
}

test('trace events are ordered by actual occurrence across spans', () => {
  const trace: Trace = {
    trace_id: 'a'.repeat(32),
    duration_ms: 20,
    spans: [
      span('tool', 50, [
        { name: 'oath.tool.response', unix_nano: 70, attributes: {} },
        { name: 'oath.tool.request', unix_nano: 50, attributes: {} },
      ]),
      span('model', 10, [
        { name: 'gen_ai.response', unix_nano: 40, attributes: {} },
        { name: 'gen_ai.request', unix_nano: 20, attributes: {} },
      ]),
    ],
  };
  assert.deepEqual(
    orderedTraceEntries(trace).map((entry) => entry.name),
    ['gen_ai.request', 'gen_ai.response', 'oath.tool.request', 'oath.tool.response'],
  );
});
