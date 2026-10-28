import { TextBuffer } from '../src/presentation.ts';
for (const size of [2000, 10000, 50000]) {
  const source = '你好é👨‍👩‍👧‍👦'.repeat(Math.ceil(size / 17)).slice(0, size);
  const b = new TextBuffer();
  let now = 0;
  const start = performance.now();
  for (let i = 64; i < source.length; i += 64) {
    b.set(source.slice(0, i), now);
    b.tick(now);
    now += 32;
  }
  b.set(source, now);
  if (b.complete) b.complete(now);
  const cpu = performance.now() - start;
  const ended = now;
  while (b.pending && now - ended < 400000) {
    now += 32;
    b.tick(now);
  }
  console.log(
    JSON.stringify({
      size,
      cpuMs: +cpu.toFixed(2),
      drainMs: now - ended,
      exact: b.value === source,
    }),
  );
}
