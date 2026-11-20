import assert from 'node:assert/strict';
import test from 'node:test';
import { scheduleLatestScroll } from './bottomAnchor.ts';

test('latest-message anchoring waits for the second layout frame', () => {
  const frames: FrameRequestCallback[] = [];
  const calls: (boolean | ScrollIntoViewOptions | undefined)[] = [];
  const viewport = { scrollHeight: 1200, scrollTop: 100 };
  const requestFrame = (callback: FrameRequestCallback) => {
    frames.push(callback);
    return frames.length;
  };

  scheduleLatestScroll({
    viewport,
    anchor: { scrollIntoView: (options) => calls.push(options) },
    shouldFollow: () => true,
    requestFrame,
  });

  assert.equal(calls.length, 0);
  frames.shift()?.(0);
  assert.equal(calls.length, 0);
  frames.shift()?.(16);

  assert.deepEqual(calls, [{ block: 'end', behavior: 'instant' }]);
  assert.equal(viewport.scrollTop, 100);
});

test('latest-message anchoring falls back to the scroll container', () => {
  const frames: FrameRequestCallback[] = [];
  const viewport = { scrollHeight: 1200, scrollTop: 100 };

  scheduleLatestScroll({
    viewport,
    anchor: null,
    shouldFollow: () => true,
    requestFrame: (callback) => {
      frames.push(callback);
      return frames.length;
    },
  });
  frames.shift()?.(0);
  frames.shift()?.(16);

  assert.equal(viewport.scrollTop, 1200);
});

test('latest-message anchoring never steals a manual scroll', () => {
  const frames: FrameRequestCallback[] = [];
  const calls: (boolean | ScrollIntoViewOptions | undefined)[] = [];

  scheduleLatestScroll({
    viewport: { scrollHeight: 1200, scrollTop: 100 },
    anchor: { scrollIntoView: (options) => calls.push(options) },
    shouldFollow: () => false,
    requestFrame: (callback) => {
      frames.push(callback);
      return frames.length;
    },
  });
  frames.shift()?.(0);
  frames.shift()?.(16);

  assert.equal(calls.length, 0);
});
