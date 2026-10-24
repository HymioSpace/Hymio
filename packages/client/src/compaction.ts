import { obj, str, type OathEvent } from '@hymio/protocol';
export function compactionState(events: OathEvent[], now = Date.now()) {
  const event = events
    .slice()
    .reverse()
    .find((e) => e.event_type === 'context.compaction');
  if (!event) return;
  const payload = obj(event.payload),
    status = str(payload.status),
    mode = str(payload.mode);
  if (!['started', 'ready', 'applied', 'failed'].includes(status)) return;
  const age = now - Date.parse(event.occur_dt);
  if (!Number.isFinite(age) || age > (status === 'started' ? 900_000 : 60_000)) return;
  const title =
    status === 'started'
      ? mode === 'async'
        ? '正在后台整理较早的对话'
        : '正在整理前面的对话…'
      : status === 'ready'
        ? '较早的对话已备好摘要'
        : status === 'applied'
          ? '已整理较早的对话'
          : '这次整理未完成';
  const detail =
    status === 'ready'
      ? '摘要已准备好，达到需要整理的长度时才会使用。聊天记录完整保留。'
      : status === 'started' && mode === 'async'
        ? '在后台准备摘要，不影响当前对话。'
        : status === 'started'
          ? '正在保留关键内容，完成后继续回复。聊天记录不会删除。'
          : status === 'failed'
            ? '聊天记录仍完整保留，已有摘要不变。'
            : '已将较早的对话整理成摘要，近期内容保留原文。聊天记录不会删除。';
  const before = Number(payload.input_tokens),
    after = Number(payload.output_tokens);
  const metrics =
    before > 0 && after > 0
      ? `本次整理约 ${Math.round(before / 1000)}K → ${after < 1000 ? Math.round(after) : Math.round(after / 1000) + 'K'} tokens`
      : '';
  return { id: event.event_seq, status, title, detail, metrics, working: status === 'started' };
}
