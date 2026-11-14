import { useEffect, useRef, useState } from 'react';
import {
  ArrowLeft,
  Bookmark,
  BookOpen,
  ChevronRight,
  MessageCircle,
  Link,
  FileText,
  GitFork,
  LoaderCircle,
  Plus,
  RefreshCw,
  Sparkles,
  X,
  MoreHorizontal,
  UserRound,
} from 'lucide-react';
import { Companion } from '@hymio/ui';
import type { LoginState } from './useLogin';
import {
  contextEmptyAction,
  contextText,
  memoryProposal,
  memoryDate,
  readable,
  sourceTitle,
  uniqueItems,
  visibleItems,
} from './contextModel';
import type { ContextDetail, ContextItem, ContextPage } from './contextModel';
import './memory.css';

type Layer = 'artifacts' | 'records';
type PageState = { items: ContextItem[]; cursor: string | null; partial: boolean };
const emptyPage = (): PageState => ({ items: [], cursor: null, partial: false });
type Evidence = { id: string; item?: ContextItem; error?: string };
type ReaderHistory = { item: ContextItem };

function MemoryCard({ item, onOpen }: { item: ContextItem; onOpen: (item: ContextItem) => void }) {
  const text = readable(item.preview);
  const insight = item.kind === 'artifact';
  const end = text.search(/[。！？!?\n]/);
  const title = item.title || (end >= 0 ? text.slice(0, end + 1) : text.slice(0, 48));
  const SourceIcon =
    item.source?.kind === 'conversation'
      ? MessageCircle
      : item.source?.kind === 'user'
        ? Bookmark
        : item.source?.kind === 'connector'
          ? Link
          : FileText;
  return (
    <button
      className={`memory-card ${insight ? 'memory-understanding' : `memory-footprint memory-source-${item.source?.kind || 'legacy'}`}`}
      onClick={() => onOpen(item)}
    >
      <span className="memory-card-meta">
        <span className="memory-card-symbol">
          {insight ? <BookOpen size={20} /> : <SourceIcon size={17} />}
        </span>
      </span>
      <span className="memory-card-writing">
        <span className="memory-card-copy">{title || '打开查看内容'}</span>
        {text && text !== title && (
          <span className="memory-card-excerpt">
            {text.startsWith(title) ? text.slice(title.length).trim() : text}
          </span>
        )}
      </span>
      <span className="memory-card-bottom">
        <span className="memory-card-provenance">
          {insight ? item.topics?.[0] || '记忆' : sourceTitle(item.source)}
        </span>
        <time dateTime={item.created_at}>{memoryDate(item.updated_at || item.created_at)}</time>
      </span>
    </button>
  );
}

export function MomentsPanel({ login }: { login: LoginState }) {
  const [layer, setLayer] = useState<Layer>('records');
  const [pages, setPages] = useState<Record<Layer, PageState>>({
    artifacts: emptyPage(),
    records: emptyPage(),
  });
  const [category, setCategory] = useState('all');
  const [source, setSource] = useState('all');
  const draftCategory = 'uncategorized';
  const [correction, setCorrection] = useState<ContextItem | null>(null);
  const [overview, setOverview] = useState<{
    stable?: { content: string };
    dynamic?: { summary?: { content: string }; pending_count?: number };
  } | null>(null);
  const [overviewError, setOverviewError] = useState('');
  const [, setInput] = useState('');
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [moreBusy, setMoreBusy] = useState(false);
  const [selected, setSelected] = useState<ContextItem | null>(null);
  const [history, setHistory] = useState<ReaderHistory[]>([]);
  const [detail, setDetail] = useState<ContextDetail | null>(null);
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [detailError, setDetailError] = useState('');
  const [detailLoading, setDetailLoading] = useState(false);
  const [evidenceLimit, setEvidenceLimit] = useState(12);
  const [draft, setDraft] = useState('');
  const [saveError, setSaveError] = useState('');
  const [saving, setSaving] = useState(false);
  const generation = useRef(0);
  const detailGeneration = useRef(0);
  const confirmedSaves = useRef<ContextItem[]>([]);
  const saveOperation = useRef<{ key: string; text: string; category: string } | null>(null);
  const reader = useRef<HTMLDialogElement>(null);
  const composer = useRef<HTMLDialogElement>(null);
  const session = login.session!;

  async function request<T>(path: string, data?: object, key?: string): Promise<T> {
    const response = await fetch(`${session.backend}/context/${path}`, {
      method: data ? 'POST' : 'GET',
      headers: {
        Authorization: `Bearer ${session.access_token}`,
        'Content-Type': 'application/json',
        ...(key ? { 'Idempotency-Key': key } : {}),
      },
      body: data ? JSON.stringify(data) : undefined,
      signal: AbortSignal.timeout(path.startsWith('imports/') ? 90000 : 20000),
    });
    if (!response.ok)
      throw new Error(
        response.status === 401 ? '登录已过期，请重新登录。' : '暂时读不到记忆，请稍后重试。',
      );
    return response.json();
  }
  async function search(target: Layer, cursor: string | null = null): Promise<ContextPage> {
    return request('browse', {
      target,
      query: query || null,
      category: target === 'artifacts' ? category : 'all',
      source_kind: target === 'records' ? source : 'all',
      limit: 30,
      cursor,
    });
  }
  async function load(reset = false) {
    const current = ++generation.current;
    setLoading(true);
    setError('');
    setMoreBusy(false);
    if (reset) setPages({ artifacts: emptyPage(), records: emptyPage() });
    try {
      const [artifacts, records] = await Promise.all([search('artifacts'), search('records')]);
      if (current !== generation.current) return;
      setPages({
        artifacts: {
          items: visibleItems(artifacts.items),
          cursor: artifacts.next_cursor || null,
          partial: !!artifacts.partial,
        },
        records: {
          items: uniqueItems([
            ...confirmedSaves.current.filter(
              (item) =>
                (source === 'all' || item.source?.kind === source) &&
                (!query || item.preview.toLocaleLowerCase().includes(query.toLocaleLowerCase())),
            ),
            ...visibleItems(records.items),
          ]),
          cursor: records.next_cursor || null,
          partial: !!records.partial,
        },
      });
    } catch (reason) {
      if (current === generation.current) setError((reason as Error).message);
    } finally {
      if (current === generation.current) setLoading(false);
    }
  }
  useEffect(() => {
    void load(true);
    return () => {
      generation.current++;
      detailGeneration.current++;
    };
    // A query or authenticated session change invalidates older requests.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, category, source, session.backend, session.user_id, session.access_token]);
  useEffect(() => {
    let live = true;
    request<typeof overview>('assembly')
      .then((v) => {
        if (live) {
          setOverview(v);
          setOverviewError('');
        }
      })
      .catch(() => {
        if (live) setOverviewError('概述暂时无法读取');
      });
    return () => {
      live = false;
    };
  }, [session.backend, session.user_id, session.access_token, notice]);

  async function more(target: Layer) {
    const cursor = pages[target].cursor;
    if (!cursor || moreBusy || loading) return;
    const current = generation.current;
    setMoreBusy(true);
    try {
      const result = await search(target, cursor);
      if (current !== generation.current) return;
      setPages((value) => ({
        ...value,
        [target]: {
          items: uniqueItems([...value[target].items, ...visibleItems(result.items)]),
          cursor: result.next_cursor || null,
          partial: !!result.partial,
        },
      }));
    } catch (reason) {
      if (current === generation.current) setError((reason as Error).message);
    } finally {
      if (current === generation.current) setMoreBusy(false);
    }
  }
  function showReader() {
    if (!reader.current?.open) reader.current?.showModal();
  }
  async function open(item: ContextItem, backStack: ReaderHistory[] = []) {
    const current = ++detailGeneration.current;
    setSelected(item);
    setHistory(backStack);
    setDetail(null);
    setEvidence([]);
    setEvidenceLimit(12);
    setDetailError('');
    setDetailLoading(true);
    showReader();
    try {
      const value = await request<ContextDetail>(
        `${item.kind === 'artifact' ? 'artifacts' : 'records'}/${encodeURIComponent(item.id)}`,
      );
      if (current !== detailGeneration.current) return;
      setDetail(value);
      const ids = [...new Set((value.references || []).map((ref) => ref.record_id))];
      // Always read full originals. A loaded search preview is not evidence in full.
      const originals = await Promise.all(
        ids.slice(0, 12).map(async (id): Promise<Evidence> => {
          try {
            const record = await request<ContextDetail>(`records/${encodeURIComponent(id)}`);
            return {
              id,
              item: {
                id,
                kind: 'record',
                preview: contextText(record),
                source: record.source,
                created_at: record.created_at,
              },
            };
          } catch {
            return { id, error: '这条原始依据暂时无法读取。' };
          }
        }),
      );
      if (current === detailGeneration.current) setEvidence(originals);
    } catch (reason) {
      if (current === detailGeneration.current) setDetailError((reason as Error).message);
    } finally {
      if (current === detailGeneration.current) setDetailLoading(false);
    }
  }
  async function moreEvidence() {
    if (!detail || !selected || detailLoading) return;
    const current = detailGeneration.current;
    const ids = [...new Set((detail.references || []).map((ref) => ref.record_id))];
    const nextLimit = evidenceLimit + 12;
    setDetailLoading(true);
    const next = await Promise.all(
      ids.slice(evidenceLimit, nextLimit).map(async (id): Promise<Evidence> => {
        try {
          const record = await request<ContextDetail>(`records/${encodeURIComponent(id)}`);
          return {
            id,
            item: {
              id,
              kind: 'record',
              preview: contextText(record),
              source: record.source,
              created_at: record.created_at,
            },
          };
        } catch {
          return { id, error: '这条原始依据暂时无法读取。' };
        }
      }),
    );
    if (current !== detailGeneration.current) return;
    setEvidence((value) => [...value, ...next]);
    setEvidenceLimit(nextLimit);
    setDetailLoading(false);
  }
  async function save() {
    const text = draft.trim();
    if (!text || saving) return;
    if (!saveOperation.current)
      saveOperation.current = { key: crypto.randomUUID(), text, category: draftCategory };
    setSaving(true);
    setSaveError('');
    try {
      if (correction) {
        await request(
          'corrections',
          {
            target: { kind: correction.kind, id: correction.id },
            text: saveOperation.current.text,
          },
          saveOperation.current.key,
        );
        saveOperation.current = null;
        setDraft('');
        setCorrection(null);
        composer.current?.close();
        setNotice('你的补充已记下，相关理解会重新整理。');
        return;
      }
      const saved = await request<ContextDetail & { id: string }>(
        'saves',
        { text: saveOperation.current.text },
        saveOperation.current.key,
      );
      const savedItem: ContextItem = {
        id: saved.id,
        category: saveOperation.current.category,
        kind: 'record',
        preview: contextText(saved),
        source: saved.source,
        created_at: saved.created_at,
      };
      confirmedSaves.current = uniqueItems([savedItem, ...confirmedSaves.current]).slice(0, 20);
      setPages((value) => ({
        ...value,
        records: { ...value.records, items: uniqueItems([savedItem, ...value.records.items]) },
      }));
      saveOperation.current = null;
      setDraft('');
      composer.current?.close();
      setNotice('已保存到足迹。理解会在后续整理中形成。');
      setLayer('records');
      if (query || category !== 'all') {
        setCategory('all');
        setInput('');
        setQuery('');
      } else await load();
    } catch {
      setSaveError('暂时无法确认保存结果。输入仍保留在这里，重试会沿用同一条记录。');
    } finally {
      setSaving(false);
    }
  }
  const page = pages[layer];
  const hasAny = pages.artifacts.items.length + pages.records.items.length > 0;
  const emptyAction = contextEmptyAction({ layer, category, source, query, recordCount: pages.records.items.length });
  const emptyTitle =
    page.cursor && !page.items.length
      ? '这批内容里暂时没有匹配项'
      : emptyAction === 'clear'
        ? '这里暂时没有匹配的内容'
        : layer === 'artifacts' ? '理解会慢慢形成' : '留下第一条足迹';

  return (
    <main className="memory-page">
      <div className="memory-content">
        <header className="memory-header">
          <div>
            <h1>记忆</h1>
          </div>
          <div className="memory-actions">
            <button
              className="memory-add"
              aria-label="添加记忆"
              onClick={() => composer.current?.showModal()}
            >
              <Plus size={17} />
            </button>
            <button
              aria-label="刷新记忆"
              title="刷新记忆"
              onClick={() => void load()}
              disabled={loading}
            >
              <RefreshCw size={18} />
            </button>
          </div>
        </header>
        <div className="memory-viewbar">
          <div className="memory-tabs" role="tablist" aria-label="记忆类型">
            {(['records', 'artifacts'] as Layer[]).map((target) => (
              <button
                role="tab"
                aria-selected={layer === target}
                aria-controls="memory-results"
                id={`memory-tab-${target}`}
                key={target}
                onClick={() => setLayer(target)}
              >
                {target === 'artifacts' ? '记忆' : '足迹'}
              </button>
            ))}
          </div>
        </div>
        {layer === 'artifacts' && (
          <details className="memory-overview">
            <summary>
              <UserRound size={16} className="memory-person" /> 我眼中的你
            </summary>
            <p>
              {overviewError ||
                overview?.stable?.content ||
                '随着你留下更多资料，我会慢慢了解你的偏好和在意的事。'}
            </p>
          </details>
        )}
        <div
          className="memory-categories"
          role="group"
          aria-label={layer === 'artifacts' ? '理解分类' : '资料来源'}
        >
          {(layer === 'artifacts'
            ? [
                ['all', '全部'],
                ...Array.from(
                  new Set(pages.artifacts.items.flatMap((item) => item.labels || [])),
                ).map((label) => [label, label]),
              ]
            : [
                ['all', '全部'],
                ['conversation', '对话'],
                ['user', '手记'],
                ['connector', '连接来源'],
                ['kit', '应用'],
                ['legacy', '其他'],
              ]
          ).map(([key, label]) => (
            <button
              key={key}
              aria-pressed={(layer === 'artifacts' ? category : source) === key}
              onClick={() => (layer === 'artifacts' ? setCategory(key) : setSource(key))}
            >
              {label}
            </button>
          ))}
        </div>
        {notice && (
          <p className="memory-notice" role="status">
            <Companion compact />
            <span>{notice}</span>
            <button aria-label="收起提示" onClick={() => setNotice('')}>
              <X size={14} />
            </button>
          </p>
        )}
        {error && (
          <div className="memory-failure" role="alert">
            <strong>{hasAny ? '暂时没能刷新，仍显示上次读取的内容' : '暂时读不到记忆'}</strong>
            <p>{error}</p>
            <button onClick={() => void load()}>重试</button>
          </div>
        )}
        <section
          id="memory-results"
          role="tabpanel"
          aria-labelledby={`memory-tab-${layer}`}
          aria-busy={loading}
        >
          {loading && !page.items.length ? (
            <div className="memory-empty" role="status">
              <LoaderCircle className="spin" />
              <h2>正在读取记忆…</h2>
            </div>
          ) : page.items.length ? (
            <>
              <div className={`memory-grid ${layer === 'records' ? 'memory-records' : ''}`}>
                {page.items.map((item) => (
                  <div className="memory-card-wrap">
                    <MemoryCard
                      key={`${item.kind}:${item.id}`}
                      item={item}
                      onOpen={(value) => void open(value)}
                    />
                    <details className="memory-menu memory-card-menu">
                      <summary aria-label="更多卡片操作">
                        <MoreHorizontal size={18} />
                      </summary>
                      <div>
                        <button onClick={() => void open(item)}>查看内容</button>
                        <button
                          onClick={() => {
                            if (saveOperation.current) return;
                            setCorrection(item);
                            setDraft('');
                            composer.current?.showModal();
                          }}
                        >
                          补充或纠正
                        </button>
                      </div>
                    </details>
                  </div>
                ))}
              </div>
              <div className="memory-page-end">
                <span>
                  已显示 {page.items.length} 条{page.partial ? ' · 搜索结果尚不完整' : ''}
                </span>
                {page.cursor && (
                  <button disabled={moreBusy || loading} onClick={() => void more(layer)}>
                    {moreBusy ? '正在读取…' : '继续查看'}
                  </button>
                )}
              </div>
            </>
          ) : (
            !error && (
              <div className="memory-empty">
                <Bookmark size={28} aria-hidden="true" />
                <h2>{emptyTitle}</h2>
                <p>
                  {emptyAction === 'clear'
                    ? '清除筛选，看看其他已经留下的内容。'
                    : emptyAction === 'records'
                        ? '原文已保存在足迹中，不必等待整理就能查看。'
                        : '想法、偏好，或一段值得保留的话，都可以从这里开始。'}
                </p>
                <button
                  onClick={() => {
                    if (emptyAction === 'clear') {
                      setCategory('all');
                      setSource('all');
                      setInput('');
                      setQuery('');
                    } else if (emptyAction === 'records') setLayer('records');
                    else composer.current?.showModal();
                  }}
                >
                  {emptyAction === 'clear'
                    ? '查看全部'
                    : emptyAction === 'records'
                        ? '查看足迹'
                        : '记一笔'}
                </button>
                {page.cursor && (
                  <button disabled={moreBusy} onClick={() => void more(layer)}>
                    继续读取更多内容
                  </button>
                )}
              </div>
            )
          )}
        </section>
      </div>
      <dialog
        ref={composer}
        className="memory-dialog memory-composer"
        aria-labelledby="memory-save-title"
        onCancel={(event) => {
          if (saving) event.preventDefault();
        }}
      >
        <header>
          <h2 id="memory-save-title">{correction ? '补充或纠正' : '记一笔'}</h2>
          <button aria-label="关闭收集" disabled={saving} onClick={() => composer.current?.close()}>
            <X size={20} />
          </button>
        </header>
        <p className="memory-muted">先留下原文，理解会慢慢形成。</p>
        <label className="memory-sr" htmlFor="memory-draft">
          想保留的内容
        </label>
        <textarea
          id="memory-draft"
          placeholder="想留下什么？"
          maxLength={16000}
          value={draft}
          readOnly={saving || !!saveOperation.current}
          onChange={(event) => setDraft(event.target.value)}
        />
        {saveError && (
          <p className="memory-save-error" role="alert">
            {saveError}
          </p>
        )}
        <footer>
          <span>{draft.length} / 16000</span>
          <button
            className="memory-primary"
            disabled={saving || !draft.trim()}
            onClick={() => void save()}
          >
            {saving ? '正在保存…' : saveOperation.current ? '重试保存' : '保存到足迹'}
          </button>
        </footer>
      </dialog>
      <dialog
        ref={reader}
        className="memory-dialog memory-reader"
        aria-labelledby="memory-reader-title"
        onClose={() => {
          detailGeneration.current++;
          setSelected(null);
        }}
      >
        <header>
          {history.length > 0 && (
            <button
              aria-label="返回理解"
              onClick={() => {
                const previous = history[history.length - 1];
                void open(previous.item, history.slice(0, -1));
              }}
            >
              <ArrowLeft size={19} />
            </button>
          )}
          <h2 id="memory-reader-title">
            {selected?.title || (selected?.kind === 'artifact' ? 'Hymio 的理解' : '原始足迹')}
          </h2>
          <button aria-label="关闭详情" onClick={() => reader.current?.close()}>
            <X size={20} />
          </button>
        </header>
        {detailError ? (
          <div className="memory-failure" role="alert">
            <p>{detailError}</p>
            <button onClick={() => selected && void open(selected, history)}>重新读取</button>
          </div>
        ) : !selected ? (
          <div className="memory-empty">
            <GitFork size={28} />
            <h2>{query ? '这个搜索范围内没有可展示的理解' : '理解形成后，会在这里连起来'}</h2>
            <p>现在可以先收集足迹，或继续浏览原文。</p>
          </div>
        ) : (
          <>
            {detail && (
              <div className="memory-detail-content">
                <>
                  <p className="memory-detail-label">
                    {selected.kind === 'artifact'
                      ? selected.topics?.[0] || '当前理解'
                      : sourceTitle(detail.source)}
                    <time>{memoryDate(detail.updated_at || detail.created_at)}</time>
                  </p>
                  {selected.kind === 'artifact' && (
                    <h3 className="memory-understanding-label">当前理解</h3>
                  )}
                  <p className="memory-fulltext">
                    {contextText(detail) || '这条记录没有文字内容。'}
                  </p>
                </>
                {selected.kind === 'record' && memoryProposal(detail) && (
                  <section className="memory-proposal">
                    <span className="memory-card-meta">
                      <Sparkles size={15} />
                      提炼草稿
                    </span>
                    <p>{memoryProposal(detail)}</p>
                    <small>与原文一起保留，尚未发布为理解。</small>
                  </section>
                )}
                {selected.kind === 'artifact' && (
                  <>
                    <div className="memory-evidence-heading">
                      <h3>原始依据（{detail.references?.length || 0}）</h3>
                    </div>
                    {!detailLoading && !evidence.length && (
                      <p className="memory-muted">这条理解暂时没有可展示的原始关联。</p>
                    )}
                    {evidence.map((ref) => (
                      <div className="memory-evidence" key={ref.id}>
                        {ref.item ? (
                          <button
                            onClick={() => void open(ref.item!, [...history, { item: selected }])}
                          >
                            <span className="memory-card-meta">
                              <FileText size={14} />
                              {sourceTitle(ref.item.source)}
                              <time>{memoryDate(ref.item.created_at)}</time>
                            </span>
                            <span className="memory-evidence-copy">
                              {ref.item.preview || '无文字内容'}
                            </span>
                            <span className="memory-evidence-link">
                              查看原文
                              <ChevronRight size={15} />
                            </span>
                          </button>
                        ) : (
                          <p>
                            {ref.error}
                            <button onClick={() => void open(selected, history)}>重试依据</button>
                          </p>
                        )}
                      </div>
                    ))}
                  </>
                )}
                {selected.kind === 'artifact' &&
                  (detail.references?.length || 0) > evidenceLimit && (
                    <button disabled={detailLoading} onClick={() => void moreEvidence()}>
                      继续读取依据
                    </button>
                  )}
                <details className="memory-source-info">
                  <summary>来源信息</summary>
                  <p>
                    记录时间：
                    {detail.created_at
                      ? new Date(detail.created_at).toLocaleString('zh-CN')
                      : '未提供'}
                  </p>
                  {detail.produced_at && (
                    <p>发生时间：{new Date(detail.produced_at).toLocaleString('zh-CN')}</p>
                  )}
                  {detail.source && (
                    <>
                      <p>
                        {sourceTitle(detail.source)}
                        {detail.source.namespace ? ` · ${detail.source.namespace}` : ''}
                      </p>
                      {detail.source.version && <p>来源版本：{detail.source.version}</p>}
                    </>
                  )}
                </details>
              </div>
            )}
            {detailLoading && (
              <p className="memory-reading" role="status">
                <LoaderCircle className="spin" size={17} />
                正在读取完整内容与依据…
              </p>
            )}
          </>
        )}
      </dialog>
    </main>
  );
}
