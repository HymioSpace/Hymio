import type { Span, Trace } from '@hymio/protocol';

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
