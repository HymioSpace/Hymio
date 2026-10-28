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
  private readonly segmenter = new Intl.Segmenter(undefined, { granularity: 'grapheme' });
  readonly rate: number;
  readonly prefillMs: number;
  constructor(rate = 90, prefillMs = 100) {
    this.rate = rate;
    this.prefillMs = prefillMs;
  }
  set(text: string, now: number, immediate = false) {
    if (text !== this.source) {
      const append = text.startsWith(this.source);
      if (!append) {
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
    let rate = Math.max(this.rate, backlog * 7);
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
