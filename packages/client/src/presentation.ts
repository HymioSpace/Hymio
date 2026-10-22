/** Presentation only: never changes durable events or acknowledgement progress. */
export class TextBuffer {
  private target: string[] = [];
  private shown = 0;
  private start = 0;
  private previous = 0;
  private credit = 0;
  private source = '';
  readonly rate: number;
  readonly prefillMs: number;
  constructor(rate = 90, prefillMs = 100) {
    this.rate = rate;
    this.prefillMs = prefillMs;
  }
  set(text: string, now: number, immediate = false) {
    const rewrite = !text.startsWith(this.source);
    if (rewrite) {
      this.shown = 0;
      this.start = now;
      this.previous = now;
      this.credit = 0;
    }
    if (!this.source && text) {
      this.start = now;
      this.previous = now;
    }
    this.source = text;
    this.target = Array.from(
      new Intl.Segmenter(undefined, { granularity: 'grapheme' }).segment(text),
      (x) => x.segment,
    );
    if (immediate) {
      this.shown = this.target.length;
      this.credit = 0;
    }
    return this.value;
  }
  tick(now: number) {
    const elapsed = Math.min(100, Math.max(0, now - this.previous));
    this.previous = now;
    if (now - this.start < this.prefillMs) return this.value;
    if (this.shown >= this.target.length) {
      this.credit = 0;
      return this.value;
    }
    const backlog = this.target.length - this.shown;
    const rate = Math.min(180, Math.max(this.rate, backlog * 7));
    this.credit += (elapsed * rate) / 1000;
    const count = Math.floor(this.credit);
    this.shown = Math.min(this.target.length, this.shown + count);
    this.credit -= count;
    return this.value;
  }
  get value() {
    return this.target.slice(0, this.shown).join('');
  }
  get pending() {
    return this.shown < this.target.length;
  }
}
