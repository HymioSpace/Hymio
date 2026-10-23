import { useEffect, useRef, useState } from 'react';
import {
  ArrowRight,
  ArrowUpRight,
  Bookmark,
  CalendarDays,
  ChevronRight,
  Layers,
  LoaderCircle,
  MessageCircle,
  MoreHorizontal,
  RefreshCw,
  Sparkles,
  X,
} from 'lucide-react';
import { Companion } from '@hymio/ui';
import type { LoginState } from './useLogin';

type ContextItem = {
  id: string;
  kind: 'record' | 'artifact';
  preview: string;
  created_at?: string;
  source?: { kind?: string; namespace?: string };
  references?: { record_id: string }[];
  topics?: string[];
};

type ContextDetail = {
  content?: string;
  context?: { text?: string; title?: string };
  references?: { record_id: string }[];
  source?: { kind?: string; namespace?: string };
  created_at?: string;
};

const sourceNames: Record<string, string> = {
  conversation: '对话',
  connector: '连接',
  kit: '应用',
  user: '你留下的',
  legacy: '其他来源',
};

function label(item: Pick<ContextItem, 'source'>) {
  return sourceNames[item.source?.kind || 'legacy'] || '其他来源';
}

function connectorName(namespace = '') {
  const value = namespace.toLowerCase();
  if (value.includes('calendar')) return '日历';
  if (value.includes('mail')) return '邮件';
  if (value.includes('figma')) return 'Figma';
  if (value.includes('notion')) return 'Notion';
  if (value.includes('github')) return 'GitHub';
  return namespace ? namespace.replaceAll('_', ' ') : '连接服务';
}

function readable(text = '') {
  try {
    const value = JSON.parse(text);
    return value.text || value.content || value.title || text;
  } catch {
    return text;
  }
}

function detailText(value: ContextDetail | null) {
  if (!value) return '';
  return value.content || value.context?.text || value.context?.title || '';
}

function splitStatement(text: string) {
  const end = text.search(/[。！？!?]/);
  if (end < 0) return { title: text, detail: '' };
  const detail = text.slice(end + 1).trim();
  return { title: text.slice(0, end + 1), detail };
}

function dateLabel(value?: string) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return '';
  return date.toLocaleDateString('zh-CN', { month: 'long', day: 'numeric' });
}

function dateParts(value?: string) {
  const date = value ? new Date(value) : new Date();
  if (Number.isNaN(date.valueOf())) return { month: '·', day: '·' };
  return {
    month: date.toLocaleDateString('zh-CN', { month: 'short' }),
    day: date.toLocaleDateString('zh-CN', { day: '2-digit' }),
  };
}

function sourceSymbol(item: ContextItem) {
  switch (item.source?.kind) {
    case 'conversation':
      return MessageCircle;
    case 'user':
      return Bookmark;
    case 'connector':
      return CalendarDays;
    default:
      return Layers;
  }
}

function SourceMark({ item }: { item: ContextItem }) {
  const Symbol = sourceSymbol(item);
  return (
    <span className="understanding-source-mark" aria-hidden="true">
      <Symbol size={12} strokeWidth={2.2} />
    </span>
  );
}

function SourcePreview({ item }: { item: ContextItem }) {
  const text = readable(item.preview);
  const kind = item.source?.kind || 'legacy';
  const date = dateParts(item.created_at);

  if (kind === 'conversation') {
    return (
      <div className="understanding-quote">
        <span className="understanding-quote-mark" aria-hidden="true">
          “
        </span>
        <p>{text}</p>
      </div>
    );
  }

  if (kind === 'user') {
    return (
      <div className="understanding-note">
        <Bookmark size={13} fill="currentColor" aria-hidden="true" />
        <p>{text}</p>
        <i aria-hidden="true" />
      </div>
    );
  }

  if (kind === 'connector') {
    return (
      <div className="understanding-calendar">
        <time dateTime={item.created_at}>
          <small>{date.month}</small>
          <strong>{date.day}</strong>
        </time>
        <div>
          <p>{text}</p>
          <span>
            {connectorName(item.source?.namespace)}
            {item.created_at ? ` · ${dateLabel(item.created_at)}` : ''}
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="understanding-activity">
      <SourceMark item={item} />
      <p>{text}</p>
    </div>
  );
}

function SourceRow({ item, onOpen }: { item: ContextItem; onOpen: (item: ContextItem) => void }) {
  const source =
    item.source?.kind === 'connector' ? connectorName(item.source?.namespace) : label(item);
  return (
    <button className="understanding-source-row" onClick={() => onOpen(item)}>
      <span className="understanding-source-meta">
        <SourceMark item={item} />
        <span>{source}</span>
        <i aria-hidden="true">·</i>
        <time dateTime={item.created_at}>{dateLabel(item.created_at) || '刚刚留下'}</time>
        <ChevronRight size={14} aria-hidden="true" />
      </span>
      <SourcePreview item={item} />
    </button>
  );
}

export function MomentsPanel({ login, onChat }: { login: LoginState; onChat: () => void }) {
  const [insights, setInsights] = useState<ContextItem[]>([]);
  const [records, setRecords] = useState<ContextItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [showAllInsights, setShowAllInsights] = useState(false);
  const [showAllSources, setShowAllSources] = useState(false);
  const [recordCursor, setRecordCursor] = useState<string | null>(null);
  const [moreBusy, setMoreBusy] = useState(false);
  const [selected, setSelected] = useState<ContextItem | null>(null);
  const [detail, setDetail] = useState<ContextDetail | null>(null);
  const [related, setRelated] = useState<ContextItem[]>([]);
  const [detailError, setDetailError] = useState('');
  const generation = useRef(0);
  const reader = useRef<HTMLDialogElement>(null);

  async function request(path: string, data?: object) {
    const session = login.session!;
    const response = await fetch(`${session.backend}/context/${path}`, {
      method: data ? 'POST' : 'GET',
      headers: {
        Authorization: `Bearer ${session.access_token}`,
        'Content-Type': 'application/json',
      },
      body: data ? JSON.stringify(data) : undefined,
      signal: AbortSignal.timeout(20000),
    });
    const value = await response.json();
    if (!response.ok) {
      throw new Error(
        response.status === 503 ? 'Hymio 暂时没能接回这些内容。' : '暂时无法读取，请稍后再试。',
      );
    }
    return value;
  }

  async function load() {
    const current = ++generation.current;
    setError('');
    try {
      const filters = {};
      const [artifactResult, recordResult] = await Promise.all([
        request('search', {
          target: 'artifacts',
          mode: 'filter',
          query: null,
          filters,
          limit: 30,
          cursor: null,
        }),
        request('search', {
          target: 'records',
          mode: 'filter',
          query: null,
          filters,
          limit: 30,
          cursor: null,
        }),
      ]);
      if (current !== generation.current) return;
      setInsights(
        (artifactResult.items || []).filter((item: ContextItem) => !item.id.startsWith('_')),
      );
      setRecords(
        (recordResult.items || []).filter((item: ContextItem) => !item.id.startsWith('_')),
      );
      setRecordCursor(recordResult.next_cursor || null);
    } catch (reason) {
      if (current === generation.current) setError((reason as Error).message);
    } finally {
      if (current === generation.current) setLoading(false);
    }
  }

  async function loadMoreRecords() {
    if (!recordCursor || moreBusy) return;
    setMoreBusy(true);
    try {
      const value = await request('search', {
        target: 'records',
        mode: 'filter',
        query: null,
        filters: {},
        limit: 30,
        cursor: recordCursor,
      });
      setRecords((current) => {
        const known = new Set(current.map((item) => item.id));
        return [
          ...current,
          ...(value.items || []).filter(
            (item: ContextItem) => !item.id.startsWith('_') && !known.has(item.id),
          ),
        ];
      });
      setRecordCursor(value.next_cursor || null);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setMoreBusy(false);
    }
  }

  useEffect(() => {
    setLoading(true);
    void load();
    return () => {
      generation.current++;
    };
    // Login identity is the only reload boundary. Search and source filters are intentionally absent.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [login.session?.backend, login.session?.user_id, login.session?.access_token]);

  async function open(item: ContextItem) {
    setSelected(item);
    setDetail(null);
    setRelated([]);
    setDetailError('');
    if (!reader.current?.open) reader.current?.showModal();
    try {
      const value: ContextDetail = await request(
        `${item.kind === 'artifact' ? 'artifacts' : 'records'}/${encodeURIComponent(item.id)}`,
      );
      setDetail(value);
      const references = value.references || item.references || [];
      const sources = await Promise.all(
        references.map(async (reference) => {
          const known = records.find((candidate) => candidate.id === reference.record_id);
          if (known) return known;
          const record: ContextDetail = await request(
            `records/${encodeURIComponent(reference.record_id)}`,
          );
          return {
            id: reference.record_id,
            kind: 'record' as const,
            preview: detailText(record) || readable(item.preview),
            created_at: record.created_at,
            source: record.source,
          };
        }),
      );
      setRelated(sources);
    } catch (reason) {
      setDetailError((reason as Error).message);
    }
  }

  async function importConversation() {
    setNotice('Hymio 正在回看最近的对话…');
    setError('');
    try {
      const value = await request('imports/conversation', { limit: 10 });
      setNotice(
        value.record_ids?.length
          ? `接回了 ${value.record_ids.length} 段真实对话。`
          : '最近的对话已经在这里了。',
      );
      await load();
    } catch (reason) {
      setNotice('');
      setError((reason as Error).message);
    }
  }

  const sourceCounts = records.reduce<Record<string, number>>((result, item) => {
    const kind = item.source?.kind || 'legacy';
    result[kind] = (result[kind] || 0) + 1;
    return result;
  }, {});

  return (
    <main className="understanding-page">
      <div className="understanding-content">
        {!loading && !error && !insights.length && !records.length ? null : (
          <header className="understanding-hero">
            <div className="understanding-intro">
              <span className="understanding-kicker">
                <i aria-hidden="true" />
                Hymio 正在认识你
                <span>
                  {new Date().toLocaleDateString('zh-CN', { month: 'long', day: 'numeric' })}
                </span>
              </span>
              <h1>我眼中的你</h1>
              <p>我一边陪你做事，一边慢慢认识你。这些理解都能回到它们发生的地方。</p>
            </div>
            <div className="understanding-companion">
              <Companion mood="idle" />
            </div>
          </header>
        )}

        <details className="understanding-menu">
          <summary aria-label="整理 Hymio 对你的理解">
            <MoreHorizontal size={19} aria-hidden="true" />
          </summary>
          <div>
            <button onClick={() => void importConversation()}>
              <RefreshCw size={15} />
              回看最近对话
            </button>
          </div>
        </details>

        {notice && (
          <p className="understanding-notice" role="status">
            <Sparkles size={15} aria-hidden="true" />
            {notice}
          </p>
        )}
        {error && (
          <p className="understanding-error" role="alert">
            {error}
            <button onClick={() => void load()}>重试</button>
          </p>
        )}

        {loading && !insights.length && !records.length ? (
          <div className="understanding-state" role="status">
            <LoaderCircle className="spin" size={19} aria-hidden="true" />
            <p>正在接回 Hymio 对你的了解…</p>
          </div>
        ) : !insights.length && !records.length ? (
          <section className="understanding-empty">
            <p>和 Hymio 聊一件想让我记住的事，我会从这里慢慢认识你。</p>
            <button onClick={onChat}>
              开始聊聊
              <ArrowRight size={16} />
            </button>
          </section>
        ) : (
          <>
            <section className="understanding-section" aria-labelledby="understanding-insights">
              <header className="understanding-section-heading">
                <h2 id="understanding-insights">我慢慢看懂的</h2>
                <span>{insights.length} 个理解</span>
              </header>
              {insights.length ? (
                (showAllInsights ? insights : insights.slice(0, 4)).map((item, index) => {
                  const copy = splitStatement(readable(item.preview));
                  return (
                    <button
                      className={`understanding-insight ${index === 0 ? 'first' : ''}`}
                      key={item.id}
                      onClick={() => void open(item)}
                    >
                      <span className="understanding-insight-top">
                        <span>
                          <Sparkles size={12} aria-hidden="true" />
                          {item.topics?.[0] || '我注意到的'}
                        </span>
                        <ArrowUpRight size={14} aria-hidden="true" />
                      </span>
                      <strong>{copy.title}</strong>
                      {copy.detail && (
                        <span className="understanding-insight-detail">{copy.detail}</span>
                      )}
                      {!!item.references?.length && (
                        <small>
                          <span aria-hidden="true">↳</span>
                          沿着 {item.references.length} 条原始记录看到这句话
                        </small>
                      )}
                    </button>
                  );
                })
              ) : (
                <p className="understanding-inline-empty">
                  还没有形成稳定的理解。再多聊几次，Hymio 会从这里慢慢写下来。
                </p>
              )}
              {!showAllInsights && insights.length > 4 && (
                <button className="understanding-more" onClick={() => setShowAllInsights(true)}>
                  再看 {insights.length - 4} 个理解
                </button>
              )}
            </section>

            <section
              className="understanding-section source-section"
              aria-labelledby="understanding-sources"
            >
              <header className="understanding-section-heading">
                <h2 id="understanding-sources">这些从哪里知道</h2>
                <span>{records.length} 条来处</span>
              </header>
              {records.length ? (
                <>
                  <div className="understanding-source-summary" aria-label="来源分布">
                    {(['conversation', 'connector', 'user', 'kit'] as const).map((kind) =>
                      sourceCounts[kind] ? (
                        <span key={kind}>
                          {sourceNames[kind]} {sourceCounts[kind]}
                        </span>
                      ) : null,
                    )}
                  </div>
                  <div className="understanding-source-list">
                    {(showAllSources ? records : records.slice(0, 4)).map((item) => (
                      <SourceRow key={item.id} item={item} onOpen={(value) => void open(value)} />
                    ))}
                  </div>
                  {!showAllSources && records.length > 4 ? (
                    <button className="understanding-more" onClick={() => setShowAllSources(true)}>
                      查看全部 {records.length} 条来处
                    </button>
                  ) : recordCursor ? (
                    <button
                      className="understanding-more"
                      disabled={moreBusy}
                      onClick={() => void loadMoreRecords()}
                    >
                      {moreBusy ? '正在接回更早的记录…' : '继续往前看'}
                    </button>
                  ) : null}
                </>
              ) : (
                <p className="understanding-inline-empty">
                  原始记录会在这里保留。它们不会因为提炼而消失。
                </p>
              )}
            </section>

            <footer className="understanding-closing">
              <p>
                这些不是关于你的档案。
                <br />
                只是我此刻的理解，会随着我们继续相处而改变。
              </p>
              <button onClick={onChat}>
                告诉 Hymio 更多
                <ArrowRight size={16} />
              </button>
            </footer>
          </>
        )}
      </div>

      <dialog
        ref={reader}
        className="understanding-reader"
        aria-labelledby="understanding-reader-title"
        onClose={() => setSelected(null)}
        onClick={(event) => {
          if (event.target === event.currentTarget) reader.current?.close();
        }}
      >
        <header>
          <span id="understanding-reader-title">
            {selected?.kind === 'artifact' ? '我这样理解' : '原始来处'}
          </span>
          <button aria-label="关闭详情" onClick={() => reader.current?.close()}>
            <X size={19} />
          </button>
        </header>
        <div className="understanding-reader-body">
          {selected && (
            <>
              <span className="understanding-reader-type">
                {selected.kind === 'artifact' ? (
                  <>
                    <Sparkles size={12} />
                    {selected.topics?.[0] || 'Hymio 的理解'}
                  </>
                ) : (
                  <>
                    <SourceMark item={selected} />
                    {label(selected)}
                  </>
                )}
                <time>{dateLabel(selected.created_at || detail?.created_at)}</time>
              </span>
              {detailError ? (
                <p className="understanding-inline-empty">{detailError}</p>
              ) : detail ? (
                <>
                  {selected.kind === 'artifact' ? (
                    <p className="understanding-reader-lead">{detailText(detail)}</p>
                  ) : (
                    <SourcePreview
                      item={{
                        ...selected,
                        preview: detailText(detail) || selected.preview,
                        source: detail.source || selected.source,
                        created_at: detail.created_at || selected.created_at,
                      }}
                    />
                  )}
                  {selected.kind === 'artifact' && (
                    <section className="understanding-provenance">
                      <header>
                        <h3>这些话从哪里来</h3>
                        <span>{related.length} 条</span>
                      </header>
                      {related.map((item) => (
                        <SourceRow key={item.id} item={item} onOpen={(value) => void open(value)} />
                      ))}
                      {!related.length && <p>这一条暂时没有可打开的原始记录。</p>}
                      <small>Hymio 的整理会变，但这些原始记录会保留下来。</small>
                    </section>
                  )}
                  {selected.kind === 'record' && (
                    <button className="understanding-detail-chat" onClick={onChat}>
                      <MessageCircle size={16} />和 Hymio 聊聊这条
                    </button>
                  )}
                </>
              ) : (
                <p className="understanding-reading" role="status">
                  沿着来处找一找…
                </p>
              )}
            </>
          )}
        </div>
      </dialog>
    </main>
  );
}
