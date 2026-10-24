import { obj, str, type OathEvent } from '@hymio/protocol';

const terminal = new Set(['ready', 'applied', 'failed', 'skipped']);

export function compactionState(events: OathEvent[], now = Date.now()) {
  const finished = new Set<string>();
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index];
    if (event.event_type !== 'context.compaction') continue;
    const payload = obj(event.payload);
    const status = str(payload.status);
    const mode = str(payload.mode);
    const compression = str(payload.compression_id);
    if (terminal.has(status) && compression) {
      finished.add(compression);
      continue;
    }
    if (status !== 'started' || mode !== 'sync') continue;
    if (compression && finished.has(compression)) continue;
    const age = now - Date.parse(event.occur_dt);
    if (!Number.isFinite(age) || age > 300_000) continue;
    return {
      id: event.event_seq,
      status,
      title: '我整理一下前面的内容，马上继续',
      working: true,
    };
  }
}
