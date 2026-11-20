import { obj, str, list, type Span, type Trace } from '@hymio/protocol';

export type TimelineEntry = {
  id: string;
  at: number;
  span: Span;
  name: string;
  event?: Span['events'][number];
};

export function orderedTraceEntries(trace: Trace): TimelineEntry[] {
  return trace.spans
    .flatMap((span) =>
      span.events.length
        ? span.events.map((event) => ({
            id: `${span.span_id}:${event.unix_nano}:${event.name}`,
            at: event.unix_nano,
            span,
            name: event.name,
            event,
          }))
        : [
            {
              id: `${span.span_id}:span`,
              at: span.start_unix_nano,
              span,
              name: 'span',
            },
          ],
    )
    .sort((left, right) => left.at - right.at);
}

function body(value: unknown) {
  if (typeof value !== 'string') return obj(value);
  try {
    return obj(JSON.parse(value));
  } catch {
    return { content: value };
  }
}

function contentText(value: unknown): string {
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) {
    return value
      .map((part) => str(obj(part).text))
      .filter(Boolean)
      .join('\n');
  }
  const valueObject = obj(value);
  for (const key of ['payload', 'content', 'text', 'message', 'preview']) {
    if (valueObject[key] == null) continue;
    const text = contentText(valueObject[key]);
    if (text) return text;
  }
  return '';
}

function truncate(value: string, limit = 72) {
  const text = value.replace(/\s+/g, ' ').trim();
  return text.length > limit ? `${text.slice(0, limit - 1).trimEnd()}…` : text;
}

export function traceTitle(entries: TimelineEntry[]) {
  for (const entry of entries) {
    if (!entry.name.startsWith('oath.input.')) continue;
    const title = truncate(
      contentText(body(entry.event?.attributes.body)),
    );
    if (title) return title;
  }
  for (const entry of entries) {
    if (entry.name !== 'gen_ai.request') continue;
    const messages = list(body(entry.event?.attributes.body).messages);
    const user = [...messages].reverse().find((message) => obj(message).role === 'user');
    const title = truncate(contentText(obj(user).content));
    if (title) return title;
  }
  return '未命名执行记录';
}
