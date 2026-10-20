export const uiTypes = [
  'Card',
  'Column',
  'Row',
  'Text',
  'Metric',
  'Badge',
  'Input',
  'Choice',
  'Button',
] as const;
export interface UiNode {
  type: (typeof uiTypes)[number];
  props: Record<string, string | string[]>;
  children?: string[];
}
export interface UiSpec {
  root: string;
  elements: Record<string, UiNode>;
}
export interface ContentPart {
  id: string;
  kind: 'text' | 'ui';
  source: string;
  complete: boolean;
}
const idPattern = /^[A-Za-z0-9_-]{1,64}$/;
const validId = (id: string) =>
  idPattern.test(id) && !['__proto__', 'constructor', 'prototype'].includes(id);
const fields: Record<string, string[]> = {
  Card: ['title', 'subtitle'],
  Column: [],
  Row: [],
  Text: ['text', 'tone'],
  Metric: ['label', 'value', 'detail'],
  Badge: ['text'],
  Input: ['label', 'placeholder', 'value'],
  Choice: ['label', 'options', 'value'],
  Button: ['label', 'prompt'],
};
export function contentParts(text: string, streaming = false): ContentPart[] {
  const parts: ContentPart[] = [];
  const lines = text.split('\n');
  let textLines: string[] = [],
    uiLines: string[] = [],
    inUI = false,
    otherFence = '',
    index = 0;
  const prose = () => {
    if (textLines.length) {
      parts.push({
        id: `text-${index++}`,
        kind: 'text',
        source: textLines.join('\n'),
        complete: true,
      });
      textLines = [];
    }
  };
  for (const line of lines) {
    if (!inUI && !otherFence && /^\s*```hymio-ui\s*$/.test(line)) {
      prose();
      inUI = true;
      continue;
    }
    if (inUI) {
      if (/^\s*```\s*$/.test(line)) {
        parts.push({ id: `ui-${index++}`, kind: 'ui', source: uiLines.join('\n'), complete: true });
        uiLines = [];
        inUI = false;
      } else uiLines.push(line);
      continue;
    }
    const fence = /^\s*(`{3,}|~{3,})(.*)$/.exec(line);
    if (fence) {
      if (!otherFence) otherFence = fence[1];
      else if (
        fence[1][0] === otherFence[0] &&
        fence[1].length >= otherFence.length &&
        !fence[2].trim()
      )
        otherFence = '';
    }
    textLines.push(line);
  }
  if (
    streaming &&
    textLines.length &&
    /^\s*`{1,3}(?:h(?:y(?:m(?:i(?:o(?:-(?:u(?:i)?)?)?)?)?)?)?)?$/.test(
      textLines[textLines.length - 1],
    )
  )
    textLines.pop();
  if (inUI)
    parts.push({
      id: `ui-${index++}`,
      kind: 'ui',
      source: uiLines.join('\n'),
      complete: !streaming,
    });
  else {
    prose();
    if (parts.at(-1)?.kind === 'text') parts[parts.length - 1].complete = !streaming;
  }
  return parts;
}
function node(raw: unknown): raw is UiNode {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return false;
  const v = raw as UiNode;
  if (
    !uiTypes.includes(v.type) ||
    !v.props ||
    typeof v.props !== 'object' ||
    Array.isArray(v.props)
  )
    return false;
  if (
    Object.entries(v.props).some(
      ([k, x]) =>
        !fields[v.type].includes(k) ||
        !(k === 'options'
          ? Array.isArray(x) &&
            x.length <= 12 &&
            x.every((a) => typeof a === 'string' && a.length <= 200)
          : typeof x === 'string' && x.length <= 2000),
    )
  )
    return false;
  return (
    v.children === undefined ||
    (Array.isArray(v.children) &&
      v.children.length <= 64 &&
      v.children.every((x) => typeof x === 'string' && validId(x)))
  );
}
export function validSpec(raw: unknown): raw is UiSpec {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return false;
  const s = raw as UiSpec;
  if (
    typeof s.root !== 'string' ||
    !validId(s.root) ||
    !s.elements ||
    typeof s.elements !== 'object' ||
    Array.isArray(s.elements)
  )
    return false;
  if (
    Object.keys(s.elements).length > 64 ||
    Object.entries(s.elements).some(([id, n]) => !validId(id) || !node(n))
  )
    return false;
  const references = new Set<string>();
  for (const n of Object.values(s.elements))
    for (const child of n.children || []) {
      if (references.has(child)) return false;
      references.add(child);
    }
  const visit = (id: string, path: Set<string>, depth: number): boolean => {
    if (depth > 12 || path.has(id)) return false;
    const n = s.elements[id];
    if (!n) return true; // unresolved child is a reserved streaming slot
    const next = new Set(path);
    next.add(id);
    return (n.children || []).every((c) => visit(c, next, depth + 1));
  };
  return Object.keys(s.elements).every((id) => visit(id, new Set(), 0));
}
export function parseSurface(source: string, complete: boolean): { spec?: UiSpec; error: boolean } {
  if (new TextEncoder().encode(source).length > 65536) return { error: true };
  let current: UiSpec = { root: '', elements: {} };
  let last: UiSpec | undefined;
  let error = false;
  const lines = source.split('\n');
  for (let i = 0; i < lines.length; i++) {
    if (!lines[i].trim()) continue;
    try {
      const value = JSON.parse(lines[i]);
      let candidate: UiSpec;
      if (value && Object.hasOwn(value, 'root') && Object.hasOwn(value, 'elements'))
        candidate = value;
      else {
        if (!['add', 'replace', 'remove'].includes(value?.op) || typeof value.path !== 'string')
          throw Error();
        candidate = { root: current.root, elements: { ...current.elements } };
        if (value.path === '/root' && value.op !== 'remove' && typeof value.value === 'string')
          candidate.root = value.value;
        else {
          const match = /^\/elements\/([A-Za-z0-9_-]{1,64})$/.exec(value.path);
          if (!match || !validId(match[1])) throw Error();
          if (value.op === 'remove') delete candidate.elements[match[1]];
          else candidate.elements[match[1]] = value.value;
        }
      }
      // Elements may precede root. Validate graph with a harmless temporary root.
      if (!validSpec({ ...candidate, root: candidate.root || 'pending' })) throw Error();
      current = candidate;
      if (current.root && current.elements[current.root]) last = current;
    } catch {
      if (complete || i < lines.length - 1) error = true;
    }
  }
  return { spec: last, error };
}
export function actionPrompt(template: string, values: Record<string, string>) {
  return template
    .replace(/\{\{([A-Za-z0-9_-]{1,64})\}\}/g, (_, id: string) => values[id] || '')
    .trim()
    .slice(0, 8000);
}
