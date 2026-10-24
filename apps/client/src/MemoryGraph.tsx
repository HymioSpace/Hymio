import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, BookOpen, FileText, MoreHorizontal, Search, X } from 'lucide-react';
import type { ContextItem } from './contextModel';

type Node = ContextItem & {
  key: string;
  role: string;
  degree: number;
  hidden_neighbors: number;
  change: string;
};
type Edge = {
  id: string;
  source: { kind: string; id: string };
  target: { kind: string; id: string };
  type: string;
  rationale: string;
  status: string;
  origin: string;
  change: string;
};
type Graph = {
  nodes: Node[];
  edges: Edge[];
  snapshot: string;
  next_offset: number | null;
  truncated: boolean;
  scope_count: number;
};
export const relationLabels: Record<string, string> = {
  supports: '支撑',
  supplements: '补充',
  related: '相关',
  contradicts: '矛盾',
  supersedes: '取代',
  navigates: '关联',
};
type Request = <T>(path: string, data?: object, key?: string) => Promise<T>;

export function MemoryGraph({
  request,
  onClose,
  onRead,
  initial,
}: {
  request: Request;
  onClose: () => void;
  onRead: (item: ContextItem) => void;
  initial?: ContextItem | null;
}) {
  const [data, setData] = useState<Graph | null>(null);
  const [seed, setSeed] = useState<ContextItem | null>(initial || null);
  const [selected, setSelected] = useState('');
  const [edgeID, setEdgeID] = useState('');
  const [query, setQuery] = useState('');
  const [changes, setChanges] = useState(false);
  const [list, setList] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const generation = useRef(0);
  const requestRef = useRef(request);
  requestRef.current = request;
  const dialog = useRef<HTMLDialogElement>(null);
  async function load(more = false) {
    const turn = ++generation.current;
    setBusy(true);
    setError('');
    try {
      const page = await requestRef.current<Graph>('graph', {
        seed: seed ? { kind: seed.kind, id: seed.id } : null,
        query,
        changes_only: changes,
        limit: 18,
        depth: 1,
        offset: more ? data?.next_offset || 0 : 0,
        snapshot: more ? data?.snapshot : null,
      });
      if (turn !== generation.current) return;
      setData(page);
      setEdgeID('');
      setSelected(seed ? `${seed.kind}:${seed.id}` : page.nodes[0]?.key || '');
    } catch {
      if (turn === generation.current) setError('暂时无法读取关系。内容可能已更新，请重新读取。');
    } finally {
      if (turn === generation.current) setBusy(false);
    }
  }
  useEffect(() => {
    dialog.current?.showModal();
    return () => {
      generation.current++;
    };
  }, []);
  useEffect(() => {
    void load();
    return () => {
      generation.current++;
    };
  }, [seed, changes]); // query is submitted explicitly
  const node = data?.nodes.find((n) => n.key === selected);
  const edge = data?.edges.find((e) => e.id === edgeID);
  const keys = (e: Edge) => [`${e.source.kind}:${e.source.id}`, `${e.target.kind}:${e.target.id}`];
  const related = data?.edges.filter((e) => keys(e).includes(selected)) || [];
  const positions = new Map(
    (data?.nodes || []).map((n, i) => [
      n.key,
      { x: 170 + (i % 3) * 235, y: 90 + Math.floor(i / 3) * 145 },
    ]),
  );
  const height = Math.max(440, Math.ceil((data?.nodes.length || 0) / 3) * 145 + 40);
  return (
    <dialog ref={dialog} className="relation-dialog" onCancel={onClose} aria-label="记忆星图">
      <header>
        <button onClick={onClose}>
          <ArrowLeft size={18} />
          记忆
        </button>
        <h2>星图</h2>
        <button onClick={onClose} aria-label="关闭星图">
          <X size={20} />
        </button>
      </header>
      <div className="relation-toolbar">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void load();
          }}
        >
          <Search size={17} />
          <input
            aria-label="搜索星图"
            placeholder="搜索卡片"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </form>
        <button
          aria-pressed={changes}
          onClick={() => {
            setSeed(null);
            setChanges(!changes);
          }}
        >
          最近变化
        </button>
        <button onClick={() => setList(!list)}>{list ? '图浏览' : '列表浏览'}</button>
        {seed && <button onClick={() => setSeed(null)}>回到全景</button>}
      </div>
      {error && (
        <p role="alert">
          {error} <button onClick={() => void load()}>重试</button>
        </p>
      )}
      <div className="relation-layout">
        <section className="relation-surface" aria-label="卡片关系">
          <div className="relation-scope">
            {busy ? '正在读取…' : `当前展示 ${data?.nodes.length || 0} 张`}
            {data?.truncated ? ' · 部分内容未展开' : ''}
          </div>
          {!busy && !data?.nodes.length && !error && (
            <div className="relation-empty">
              {query ? '没有找到相关卡片' : '还没有可展示的卡片'}
              <p>原文保留后，真实关联会在这里呈现。</p>
            </div>
          )}
          {list ? (
            <div className="relation-list">
              {data?.nodes.map((n) => (
                <button
                  key={n.key}
                  onClick={() => {
                    setSelected(n.key);
                    setEdgeID('');
                  }}
                >
                  <strong>{n.title || n.preview.slice(0, 32)}</strong>
                  <span>{n.degree} 项关联</span>
                </button>
              ))}
            </div>
          ) : (
            <div className="relation-scroll">
              <div className="relation-canvas" style={{ width: 810, height }}>
                <svg width="810" height={height} aria-label="选择卡片后可在右侧逐条查看关系">
                  <defs>
                    <marker
                      id="relation-arrow"
                      markerWidth="7"
                      markerHeight="7"
                      refX="6"
                      refY="3.5"
                      orient="auto"
                    >
                      <path d="M0,0 L7,3.5 L0,7" fill="#8a9ebd" />
                    </marker>
                  </defs>
                  {data?.edges.map((e) => {
                    const [a, b] = keys(e),
                      p = positions.get(a),
                      q = positions.get(b);
                    if (!p || !q) return null;
                    const highlighted = a === selected || b === selected;
                    return (
                      <g key={e.id} onClick={() => setEdgeID(e.id)} className="relation-edge">
                        <path
                          d={`M${p.x},${p.y + 35} Q${(p.x + q.x) / 2 + 25},${(p.y + q.y) / 2 + 65} ${q.x},${q.y - 35}`}
                          fill="none"
                          stroke={highlighted ? '#477ae5' : '#d4deec'}
                          strokeWidth={highlighted ? 2 : 1}
                          strokeDasharray={e.status === 'disputed' ? '5 5' : undefined}
                          markerEnd={
                            ['related', 'contradicts'].includes(e.type)
                              ? undefined
                              : 'url(#relation-arrow)'
                          }
                        />
                        {highlighted && (
                          <text x={(p.x + q.x) / 2 + 20} y={(p.y + q.y) / 2 + 35}>
                            {relationLabels[e.type]}
                          </text>
                        )}
                      </g>
                    );
                  })}
                </svg>
                {data?.nodes.map((n) => {
                  const p = positions.get(n.key)!;
                  return (
                    <button
                      key={n.key}
                      className={`relation-node ${n.key === selected ? 'selected' : ''}`}
                      style={{ left: p.x - 94, top: p.y - 36 }}
                      onClick={() => {
                        setSelected(n.key);
                        setEdgeID('');
                      }}
                    >
                      <span className="relation-node-role">
                        {n.kind === 'record' ? <FileText size={14} /> : <BookOpen size={14} />}{' '}
                        {n.role === 'overview' ? '概述' : n.kind === 'record' ? '原文' : '理解'}
                        {n.change && <i>{n.change === 'added' ? '新增' : '更新'}</i>}
                      </span>
                      <strong>
                        {n.role === 'overview' ? '关于你的概述' : n.title || n.preview.slice(0, 32)}
                      </strong>
                      <small>
                        {n.degree} 项关联
                        {n.hidden_neighbors ? ` · ${n.hidden_neighbors} 未展开` : ''}
                      </small>
                    </button>
                  );
                })}
              </div>
            </div>
          )}
          {data?.next_offset != null && (
            <button onClick={() => void load(true)} disabled={busy}>
              继续浏览
            </button>
          )}
        </section>
        <aside className="relation-inspector">
          {node && (
            <>
              <div className="relation-inspector-title">
                <h3>{node.role === 'overview' ? '关于你的概述' : node.title}</h3>
                <details className="memory-menu">
                  <summary aria-label="卡片操作">
                    <MoreHorizontal size={19} />
                  </summary>
                  <div>
                    <button onClick={() => onRead(node)}>查看完整内容</button>
                    <button onClick={() => setSeed(node)}>展开周围关联</button>
                  </div>
                </details>
              </div>
              <p className="relation-content">{node.preview}</p>
              <small>
                {node.kind === 'record' ? '保留的原始资料' : '模型整理'} · {node.degree} 项关联
              </small>
              {edge ? (
                <section className="relation-explanation">
                  <h4>{relationLabels[edge.type]}</h4>
                  <p>{edge.rationale}</p>
                  <small>
                    {edge.origin === 'model'
                      ? '模型建立'
                      : edge.origin === 'user'
                        ? '用户建立'
                        : '已有关系'}
                    {edge.status === 'disputed' ? ' · 待核对' : ''}
                  </small>
                  <button onClick={() => setEdgeID('')}>所有关联</button>
                </section>
              ) : (
                <section className="relation-neighbors">
                  <h4>相关内容</h4>
                  {related.map((e) => {
                    const otherKey = keys(e).find((k) => k !== selected);
                    const other = data?.nodes.find((n) => n.key === otherKey);
                    return (
                      <div key={e.id}>
                        <button onClick={() => setEdgeID(e.id)}>
                          {relationLabels[e.type]}
                          {e.status === 'disputed' ? ' · 待核对' : ''}
                        </button>
                        <button
                          onClick={() => {
                            if (other) {
                              setSelected(other.key);
                              setEdgeID('');
                            }
                          }}
                        >
                          {other?.title || '关联卡片'}
                        </button>
                      </div>
                    );
                  })}
                  {!related.length && <p>当前范围尚无关联。</p>}
                  {node.hidden_neighbors > 0 && (
                    <button onClick={() => setSeed(node)}>
                      展开其余 {node.hidden_neighbors} 项关联
                    </button>
                  )}
                </section>
              )}
            </>
          )}
        </aside>
      </div>
    </dialog>
  );
}
