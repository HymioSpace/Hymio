import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { TextBuffer } from './presentation.ts';
import { parseSurface, contentParts, validSpec, actionPrompt } from './agent-ui.ts';
test('jitter buffer meters bursts and drains final content without losing Unicode', () => {
  const b = new TextBuffer(10, 100);
  b.set('👨‍👩‍👧‍👦你好é', 0);
  assert.equal(b.tick(50), '');
  assert.equal(b.tick(150), '👨‍👩‍👧‍👦');
  b.set('👨‍👩‍👧‍👦你好é世界', 151);
  for (let t = 250; t < 1200; t += 100) b.tick(t);
  assert.equal(b.value, '👨‍👩‍👧‍👦你好é世界');
  assert.equal(b.pending, false);
  b.set('retry', 1200);
  assert.equal(b.value, '');
  b.set('history', 1300, true);
  assert.equal(b.value, 'history');
});
test('long gaps do not accumulate unlimited render credit', () => {
  const b = new TextBuffer(10, 0);
  b.set('a', 0);
  b.tick(100);
  b.tick(10000);
  b.set('abcdefghijkl', 10001);
  b.tick(10002);
  assert.equal(b.value, 'a');
});
const root = { type: 'Card', props: { title: 'Plan' }, children: ['choice', 'go'] };
const patch = (id: string, value: unknown) =>
  JSON.stringify({ op: 'add', path: '/elements/' + id, value });
const stream =
  JSON.stringify({ op: 'add', path: '/root', value: 'plan' }) + '\n' + patch('plan', root) + '\n';
test('complete JSON records appear before final fence; partial record keeps valid frame', () => {
  const result = parseSurface(stream + '{"op":"add"', false);
  assert.equal(result.error, false);
  assert.equal(result.spec?.root, 'plan');
  assert.equal(parseSurface(stream + '{"op":"add"', true).error, true);
  assert.equal(
    parseSurface(
      stream +
        patch('choice', { type: 'Choice', props: { label: 'Duration', options: ['15', '30'] } }),
      true,
    ).spec?.elements.choice.type,
    'Choice',
  );
});
test('reject scripts, unknown props, prototype keys, graph cycles and oversized documents', () => {
  for (const n of [
    { type: 'Script', props: {} },
    { type: 'Card', props: { onClick: 'fetch()' } },
    { type: 'Card', props: {}, children: ['plan'] },
  ])
    assert.equal(parseSurface(stream + patch('plan', n), true).error, true);
  assert.equal(
    parseSurface(stream + patch('__proto__', { type: 'Text', props: { text: 'bad' } }), true).error,
    true,
  );
  assert.equal(parseSurface('a'.repeat(65537), false).error, true);
  assert.equal(
    validSpec({
      root: 'x',
      elements: { x: { type: 'Card', props: {}, children: ['same', 'same'] } },
    }),
    false,
  );
});
test('surfaces coexist with Markdown, code examples are not executable and actions substitute only values', () => {
  const src = 'Hello\n```hymio-ui\n' + stream + '```\nDone';
  assert.deepEqual(
    contentParts(src).map((p) => p.kind),
    ['text', 'ui', 'text'],
  );
  assert.equal(
    contentParts('```text\n```hymio-ui\ntext\n```').filter((p) => p.kind === 'ui').length,
    0,
  );
  assert.equal(
    actionPrompt('Plan {{choice}} {{unknown}}', { choice: '30 minutes' }),
    'Plan 30 minutes',
  );
});

test('shared native/web catalog fixtures stay compatible', () => {
  const fixtures = JSON.parse(
    readFileSync(new URL('../../protocol/fixtures/agent-ui.json', import.meta.url), 'utf8'),
  );
  for (const f of fixtures) assert.equal(validSpec(f.spec), f.valid, f.name);
  assert.equal(
    contentParts('~~~text\n```hymio-ui\n{}\n```\n~~~').filter((p) => p.kind === 'ui').length,
    0,
  );
});

test('closed surface completes independently of the following message stream', () => {
  const part = contentParts('```hymio-ui\n' + stream + '```', true).find((p) => p.kind === 'ui');
  assert.equal(part?.complete, true);
});
