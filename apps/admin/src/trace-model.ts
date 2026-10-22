export function orderSpans<
  T extends {
    span_id: string;
    parent_span_id: string | null;
    start_unix_nano: number;
  },
>(spans: T[]) {
  const ids = new Set(spans.map((span) => span.span_id));
  const children = new Map<string, T[]>();
  for (const span of spans) {
    const parent =
      span.parent_span_id && ids.has(span.parent_span_id)
        ? span.parent_span_id
        : "";
    children.set(parent, [...(children.get(parent) || []), span]);
  }
  for (const siblings of children.values())
    siblings.sort((a, b) => a.start_unix_nano - b.start_unix_nano);
  const visited = new Set<string>();
  const result: { span: T; depth: number }[] = [];
  const visit = (span: T, depth: number) => {
    if (visited.has(span.span_id)) return;
    visited.add(span.span_id);
    result.push({ span, depth: Math.min(depth, 6) });
    for (const child of children.get(span.span_id) || [])
      visit(child, depth + 1);
  };
  for (const span of children.get("") || []) visit(span, 0);
  // Malformed or cyclic parents must not hide diagnostic evidence.
  for (const span of spans) visit(span, 0);
  return result;
}
