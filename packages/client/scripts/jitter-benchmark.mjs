import { TextBuffer } from '../src/presentation.ts';
for (const [name, size, pattern] of [
  ['steady', 4, [80]],
  ['batched', 12, [240]],
  ['jitter', 8, [40, 80, 360, 40, 160, 280]],
  ['slow', 2, [400]],
]) {
  const events = [];
  let t = 0;
  for (let i = 0; i < 60; i++) {
    t += pattern[i % pattern.length];
    events.push({ t, text: '字'.repeat(size * (i + 1)) });
  }
  const b = new TextBuffer();
  let i = 0,
    previous = 0,
    last = 0,
    finished = false,
    gaps = [];
  for (let now = 0; now <= t + 500; now += 16) {
    while (i < events.length && events[i].t <= now) {
      b.set(events[i++].text, now);
    }
    if (i === events.length && !finished) {
      b.complete(now);
      finished = true;
    }
    const text = b.tick(now);
    if (text.length > previous) {
      if (last > 0) gaps.push(now - last);
      last = now;
      previous = text.length;
    }
  }
  gaps.sort((a, b) => a - b);
  console.log(
    JSON.stringify({
      name,
      p95: gaps[Math.floor(gaps.length * 0.95)],
      max: gaps.at(-1),
      over160: gaps.filter((x) => x > 160).length,
      total: previous,
      expected: events.at(-1).text.length,
    }),
  );
}
