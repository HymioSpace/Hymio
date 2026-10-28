/** Presentation only: never changes durable events or acknowledgement progress. */
export class TextBuffer {
  private target: string[] = [];
  private shown = 0;
  private start = 0;
  private previous = 0;
  private credit = 0;
  private source = '';
  private visible = '';
  private finishBy: number | undefined;
  private lastArrival: number | undefined;
  private inputRate = 0;
  private gapMs = 80;
  private jitterMs = 0;
  private speed = 0;
  private readonly segmenter = new Intl.Segmenter(undefined, { granularity: 'grapheme' });
  readonly rate: number;
  readonly prefillMs: number;
  constructor(rate = 90, prefillMs = 140) {
    this.rate = rate;
    this.prefillMs = prefillMs;
  }
  set(text: string, now: number, immediate = false) {
    if (text !== this.source) {
      const append = text.startsWith(this.source);
      const oldCount = append ? this.target.length : 0;
      if (!append) {
        this.lastArrival = undefined;
        this.inputRate = this.speed = this.jitterMs = 0;
        this.gapMs = 80;
        this.target = [];
        this.shown = 0;
        this.visible = '';
        this.start = now;
        this.previous = now;
        this.credit = 0;
      }
      if (!this.source && text) {
        this.start = now;
        this.previous = now;
      }
      // Re-segment the previous final cluster too: combining marks, flags and ZWJ
      // sequences may extend it across network deltas.
      const last = this.target.pop() || '';
      const offset = append ? this.source.length - last.length : 0;
      const prefix = this.target.length;
      const tail = Array.from(this.segmenter.segment(text.slice(offset)), (x) => x.segment);
      for (const cluster of tail) this.target.push(cluster);
      if (this.shown > prefix) {
        this.shown = prefix + Math.min(1, tail.length);
        this.visible = text.slice(0, offset) + (tail[0] || '');
      }
      const added = this.target.length - oldCount;
      if (added > 0) {
        const gap = this.lastArrival === undefined ? 0 : now - this.lastArrival;
        if (gap > 0 && gap < 1500) {
          const sample = Math.min(4000, (added * 1000) / Math.max(8, gap));
          if (!this.inputRate) {
            this.inputRate = sample;
            this.gapMs = gap;
          } else {
            this.inputRate += 0.25 * (sample - this.inputRate);
            this.jitterMs += 0.2 * (Math.abs(gap - this.gapMs) - this.jitterMs);
            this.gapMs += 0.2 * (gap - this.gapMs);
          }
        }
        if (gap >= 1500 && gap < 5000) {
          this.inputRate = (added * 1000) / gap;
          this.gapMs = Math.min(gap, 1500);
          this.jitterMs = 0;
        } else if (gap >= 5000) {
          this.inputRate = this.speed = this.jitterMs = 0;
          this.gapMs = 80;
          this.start = this.previous = now;
        }
        this.lastArrival = now;
      }
      this.source = text;
      this.finishBy = undefined;
    }
    if (immediate) {
      this.shown = this.target.length;
      this.visible = this.source;
      this.credit = 0;
      this.finishBy = undefined;
    }
    return this.value;
  }
  /** Bound presentation lag after the final server event, as on the native client. */
  complete(now: number) {
    if (this.pending && this.finishBy === undefined) this.finishBy = now + 450;
  }
  tick(now: number) {
    const elapsed = Math.min(100, Math.max(0, now - this.previous));
    this.previous = now;
    if (now - this.start < this.prefillMs) return this.value;
    if (!this.pending) {
      this.credit = 0;
      return this.value;
    }
    const backlog = this.target.length - this.shown;
    const input = this.inputRate || Math.min(this.rate, Math.max(8, backlog / 0.3));
    const reserveMs = Math.min(240, Math.max(100, this.gapMs * 0.5 + this.jitterMs * 1.5));
    const desired = (input * (reserveMs + this.gapMs * 0.5)) / 1000;
    let goal = Math.max(input * 0.25, input + (backlog - desired) / 0.35, 1);
    goal = Math.min(goal, input * 1.8 + 12);
    if (backlog > Math.max(256, input * 1.5)) goal = Math.max(goal, backlog / 0.65);
    // Smooth the speed itself instead of reacting to every queue-size sawtooth.
    this.speed = this.speed
      ? this.speed + (goal - this.speed) * (1 - Math.exp(-elapsed / 160))
      : goal;
    let rate = this.speed;
    const silence = this.lastArrival === undefined ? 0 : now - this.lastArrival;
    if (silence > Math.max(300, this.gapMs * 1.5))
      rate = Math.max(rate, (backlog * 1000) / Math.max(16, 900 - silence));
    if (this.finishBy !== undefined) {
      if (now >= this.finishBy) {
        this.shown = this.target.length;
        this.visible = this.source;
        this.credit = 0;
        return this.value;
      }
      rate = Math.max(rate, (backlog * 1000) / Math.max(16, this.finishBy - now));
    }
    this.credit += (elapsed * rate) / 1000;
    const count = Math.floor(this.credit);
    const next = Math.min(this.target.length, this.shown + count);
    if (next > this.shown) this.visible += this.target.slice(this.shown, next).join('');
    this.shown = next;
    this.credit -= count;
    return this.value;
  }
  get value() {
    return this.visible;
  }
  get pending() {
    return this.shown < this.target.length;
  }
}
