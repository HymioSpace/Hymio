import assert from 'node:assert/strict';
import test from 'node:test';
import { parseQuickReplies } from './quick-replies.ts';

test('quick replies are removed from prose and capped', () => {
  const parsed = parseQuickReplies(
    `先这样。\n\n\`\`\`hymio-quick\n["先停下吧","我改变主意了","换个方向","第四句"]\n\`\`\``,
  );
  assert.equal(parsed.content, '先这样。');
  assert.deepEqual(parsed.suggestions, ['先停下吧', '我改变主意了', '换个方向']);
});

test('an unfinished or malformed quick directive never leaks into the message', () => {
  assert.deepEqual(parseQuickReplies('答案\n```hymio-quick\n["未完成"'), {
    content: '答案',
    suggestions: [],
  });
  assert.deepEqual(parseQuickReplies('答案\n```hymio-quick\ninvalid\n```'), {
    content: '答案',
    suggestions: [],
  });
});

test('quick directive syntax inside a normal code fence is preserved', () => {
  const source = '```text\n```hymio-quick\nnot a directive\n```\n```';
  assert.equal(parseQuickReplies(source).content, source);
});
