import assert from 'node:assert/strict';
import test from 'node:test';
import { orderedTraceEntries, traceTitle } from './traceTimeline.ts';
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

test('trace title uses the first input body and truncates it', () => {
  const trace: Trace = {
    trace_id: 'b'.repeat(32),
    duration_ms: 20,
    spans: [
      span('model', 10, [
        {
          name: 'oath.input.user',
          unix_nano: 11,
          attributes: {
            body: JSON.stringify({
              kind: 'user',
              source: 'user.message',
              payload: {
                content:
                  '分析最新的基线快照任务为什么执行缓慢，并指出耗时最长的工具调用和模型上下文增长问题。请按时间顺序说明主 Agent、子 Agent 和工具之间发生了什么，以及后续应该如何减少重复上下文和空转消耗。',
              },
            }),
          },
        },
        { name: 'gen_ai.request', unix_nano: 20, attributes: {} },
      ]),
    ],
  };
  const title = traceTitle(orderedTraceEntries(trace));
  assert.match(title, /^分析最新的基线快照任务/);
  assert.ok(title.endsWith('…'));
  assert.ok(title.length <= 72);
});
