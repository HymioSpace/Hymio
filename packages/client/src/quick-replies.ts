export interface ParsedQuickReplies {
  content: string;
  suggestions: string[];
}

/** Remove hidden Hymio quick-reply directives from visible prose. */
export function parseQuickReplies(source: string): ParsedQuickReplies {
  const lines = source.split(/\r?\n/);
  const output: string[] = [];
  const suggestions: string[] = [];
  let block: string[] | undefined;
  let otherFence = '';
  for (const line of lines) {
    const trimmed = line.trim();
    if (block) {
      if (trimmed === '```') {
        try {
          const value: unknown = JSON.parse(block.join('\n'));
          if (Array.isArray(value)) {
            for (const item of value) {
              if (typeof item !== 'string') continue;
              const text = item.trim();
              if (!text || text.length > 40 || suggestions.includes(text)) continue;
              suggestions.push(text);
              if (suggestions.length === 3) break;
            }
          }
        } catch {
          // A malformed directive stays hidden and simply yields no suggestions.
        }
        block = undefined;
      } else {
        block.push(line);
      }
      continue;
    }
    if (!otherFence && trimmed === '```hymio-quick') {
      block = [];
      continue;
    }
    if (trimmed.startsWith('```') || trimmed.startsWith('~~~')) {
      const marker = trimmed.match(/^(`{3,}|~{3,})/)?.[1] || '';
      if (!otherFence) otherFence = marker;
      else if (trimmed === otherFence) otherFence = '';
    }
    output.push(line);
  }
  return {
    content: output
      .join('\n')
      .replace(/\n{3,}/g, '\n\n')
      .trim(),
    suggestions: suggestions.slice(0, 3),
  };
}
