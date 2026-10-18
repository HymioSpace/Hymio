import { useState } from 'react';

function decoded(value: unknown): { value: unknown; encoded: boolean } {
  if (typeof value === 'string' && /^[\s]*[\[{]/.test(value)) {
    try {
      const parsed: unknown = JSON.parse(value);
      if (parsed && typeof parsed === 'object') return { value: parsed, encoded: true };
    } catch {
      /* Plain text remains unchanged. */
    }
  }
  return { value, encoded: false };
}
function Node({ value, label, depth = 0 }: { value: unknown; label?: string; depth?: number }) {
  const item = decoded(value);
  if (item.value !== null && typeof item.value === 'object' && depth < 30) {
    const entries = Object.entries(item.value);
    return (
      <details className="json-node" open={depth < 2}>
        <summary>
          {label !== undefined && <b>{label}: </b>}
          <span className="json-type">
            {Array.isArray(item.value) ? `Array (${entries.length})` : `Object (${entries.length})`}
            {item.encoded ? ' · JSON 字符串' : ''}
          </span>
        </summary>
        <div className="json-children">
          {entries.map(([key, child]) => (
            <Node key={key} label={key} value={child} depth={depth + 1} />
          ))}
        </div>
      </details>
    );
  }
  return (
    <div className="json-leaf">
      {label !== undefined && <b>{label}: </b>}
      <span className={typeof value === 'string' ? 'json-string' : 'json-literal'}>
        {typeof value === 'string' ? value : (JSON.stringify(value) ?? 'undefined')}
      </span>
    </div>
  );
}
export function JsonView({ value }: { value: unknown }) {
  const [raw, setRaw] = useState(false);
  return (
    <div className="json-inspector">
      <div className="json-toolbar">
        <span>JSON</span>
        <button onClick={() => setRaw(!raw)}>{raw ? '结构视图' : '原始 JSON'}</button>
      </div>
      {raw ? (
        <pre className="json-view">{JSON.stringify(value, null, 2)}</pre>
      ) : (
        <div className="json-tree">
          <Node value={value} />
        </div>
      )}
    </div>
  );
}
