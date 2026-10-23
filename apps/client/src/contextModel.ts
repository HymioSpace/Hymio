export type ContextItem = {
  id: string;
  kind: 'record' | 'artifact';
  preview: string;
  truncated?: boolean;
  category?: string;
  title?: string;
  created_at?: string;
  updated_at?: string;
  source?: { kind?: string; namespace?: string; external_id?: string; version?: string };
  references?: { record_id: string }[];
  topics?: string[];
};
export type ContextDetail = {
  id?: string;
  content?: string;
  context?: Record<string, unknown>;
  command?: Record<string, unknown>;
  references?: { record_id: string }[];
  source?: ContextItem['source'];
  created_at?: string;
  produced_at?: string;
  updated_at?: string;
};
export type ContextPage = { items: ContextItem[]; next_cursor?: string | null; partial?: boolean };
export function contextText(value: ContextDetail): string {
  if (value.content) return value.content;
  const context = value.context;
  for (const key of ['text', 'content', 'title']) {
    if (typeof context?.[key] === 'string' && context[key]) return context[key] as string;
  }
  return context || value.command ? JSON.stringify(context || value.command, null, 2) : '';
}
export function readable(text: string): string {
  try {
    const parsed = JSON.parse(text);
    if (parsed && typeof parsed === 'object') {
      for (const key of ['text', 'content', 'title']) {
        if (typeof parsed[key] === 'string' && parsed[key]) return parsed[key];
      }
    }
  } catch {
    /* Plain text is already readable. */
  }
  return text;
}
export function sourceTitle(source?: ContextItem['source']): string {
  const names: Record<string, string> = {
    conversation: '对话原话',
    user: '主动记下',
    connector: '连接来源',
    kit: '应用记录',
    legacy: '其他来源',
  };
  return names[source?.kind || 'legacy'] || '其他来源';
}
export function memoryDate(value?: string): string {
  if (!value || Number.isNaN(new Date(value).valueOf())) return '';
  return new Date(value).toLocaleString('zh-CN', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}
export function visibleItems(items: ContextItem[]): ContextItem[] {
  return items.filter((item) => !item.id.startsWith('_'));
}
export function uniqueItems(items: ContextItem[]): ContextItem[] {
  return [...new Map(items.map((item) => [`${item.kind}:${item.id}`, item])).values()];
}

export function memoryProposal(value: ContextDetail): string {
  const memory = value.context?.memory;
  return memory &&
    typeof memory === 'object' &&
    'summary' in memory &&
    typeof memory.summary === 'string'
    ? memory.summary
    : '';
}

export const memoryCategories = [
  ['all', '全部'],
  ['work', '工作'],
  ['learning', '学习'],
  ['life', '生活'],
  ['uncategorized', '未分类'],
] as const;
