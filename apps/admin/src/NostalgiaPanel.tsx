import { useEffect, useState } from "react";
import Markdown from "react-markdown";
import { BookOpen, RefreshCw } from "lucide-react";
import { adminRequest, type Session } from "./api";
import "./nostalgia.css";

type Proposal = {
  id: string;
  state: string;
  task_id?: string;
  proposal: { title: string; reason: string; record_ids: string[] };
};
type Status = {
  users: string[];
  user_id: string;
  prompt: string;
  prompt_sha256: string;
  runtime?: {
    enabled?: boolean;
    unavailable?: boolean;
    running?: boolean;
    interval_seconds?: number;
    counts?: Record<string, number>;
    events?: { id: number; kind: string; created_at: string; data: unknown }[];
  };
  opportunities?: Proposal[];
};
type Card = { id: string; kind: string; title?: string; preview?: string };

export function NostalgiaPanel({ session }: { session: Session }) {
  const [owner, setOwner] = useState("");
  const [tab, setTab] = useState("status");
  const [status, setStatus] = useState<Status>();
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState("");
  const [target, setTarget] = useState("artifacts");
  const [cards, setCards] = useState<Card[]>([]);
  const [detail, setDetail] = useState<unknown>();
  const [correction, setCorrection] = useState("");
  const [cursor, setCursor] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    setError("");
    setStatus(undefined);
    setCards([]);
    setDetail(undefined);
    setCursor(null);
    void adminRequest<Status>(
      "nostalgia?user_id=" + encodeURIComponent(owner),
      { session },
    )
      .then((v) => {
        if (active) setStatus(v);
      })
      .catch(() => {
        if (active) setError("无法读取 Nostalgia，请检查服务与用户绑定。");
      });
    return () => {
      active = false;
    };
  }, [owner, revision, session]);
  async function action(body: object) {
    setBusy(true);
    setError("");
    try {
      return await adminRequest("nostalgia", {
        session,
        body: { user_id: status?.user_id, ...body },
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "操作未完成");
      throw e;
    } finally {
      setBusy(false);
    }
  }
  async function browse(more = false) {
    try {
      const page = (await action({
        action: "browse",
        options: {
          target,
          query,
          limit: 20,
          ...(more && cursor ? { cursor } : {}),
        },
      })) as { items: Card[]; next_cursor: string | null };
      setCards((v) => (more ? [...v, ...page.items] : page.items));
      setCursor(page.next_cursor);
      setDetail(undefined);
    } catch {
      /* error is displayed above */
    }
  }
  return (
    <main className="workspace nostalgia-workspace">
      <header className="topbar">
        <div>
          <h1>Nostalgia</h1>
          <p>个人上下文、整理过程与发现的线索。</p>
        </div>
        <button
          className="icon-button bordered"
          aria-label="刷新"
          onClick={() => setRevision(revision + 1)}
        >
          <RefreshCw size={17} />
        </button>
      </header>
      <div className="nostalgia-controls">
        <label>
          上下文用户{" "}
          <select
            value={owner || status?.user_id || ""}
            onChange={(e) => setOwner(e.target.value)}
          >
            {status?.users.map((id) => (
              <option key={id} value={id}>
                {id}
              </option>
            ))}
          </select>
        </label>
        <nav aria-label="上下文管理">
          {[
            ["status", "运行"],
            ["opportunities", "发现"],
            ["data", "数据"],
            ["prompt", "Prompt"],
          ].map(([key, title]) => (
            <button
              key={key}
              aria-pressed={tab === key}
              onClick={() => setTab(key)}
            >
              {title}
            </button>
          ))}
        </nav>
      </div>
      {error && (
        <p role="alert" className="nostalgia-error">
          {error}
        </p>
      )}
      {!status && !error && <p>正在读取…</p>}
      {status && !status.users.length && <p>尚未配置 Nostalgia 用户绑定。</p>}
      {tab === "status" && status?.runtime && (
        <section className="nostalgia-section">
          <h2>
            {status.runtime.unavailable
              ? "服务暂时不可用"
              : status.runtime.running
                ? "正在整理"
                : status.runtime.enabled
                  ? "等待下一轮整理"
                  : "自动整理未启用"}
          </h2>
          <dl className="nostalgia-counts">
            {Object.entries(status.runtime.counts || {}).map(([key, count]) => (
              <div key={key}>
                <dt>
                  {{
                    records: "原始记录",
                    versions: "版本",
                    context_events: "事件",
                  }[key] || key}
                </dt>
                <dd>{count.toLocaleString()}</dd>
              </div>
            ))}
          </dl>
          {status.runtime.interval_seconds && (
            <p>
              整理间隔 {status.runtime.interval_seconds}{" "}
              秒。运行记录按时间保留，失败不会冒充已完成。
            </p>
          )}
          <ol className="nostalgia-timeline">
            {status.runtime.events?.map((event) => (
              <li key={event.id}>
                <time>{new Date(event.created_at).toLocaleString()}</time>
                <strong>{event.kind}</strong>
                <details>
                  <summary>事件详情</summary>
                  <pre>{JSON.stringify(event.data, null, 2)}</pre>
                </details>
              </li>
            ))}
          </ol>
        </section>
      )}
      {tab === "opportunities" && (
        <section className="nostalgia-section">
          <h2>从上下文发现的事情</h2>
          <p>
            建议有来源，但不代表用户已委托。接纳后进入任务，忽略后不会自动重新创建。
          </p>
          {!status?.opportunities?.length && <p>还没有新的线索。</p>}
          {status?.opportunities?.map((item) => (
            <article className="nostalgia-proposal" key={item.id}>
              <div>
                <h3>{item.proposal.title}</h3>
                <span>{item.state}</span>
              </div>
              <p>{item.proposal.reason}</p>
              <small>来源记录：{item.proposal.record_ids.join(", ")}</small>
              {item.state === "pending" && (
                <div>
                  <button
                    disabled={busy}
                    onClick={() =>
                      void action({ action: "accept", id: item.id })
                        .then(() => setRevision(revision + 1))
                        .catch(() => {})
                    }
                  >
                    接纳为任务
                  </button>
                  <button
                    disabled={busy}
                    onClick={() =>
                      void action({ action: "dismiss", id: item.id })
                        .then(() => setRevision(revision + 1))
                        .catch(() => {})
                    }
                  >
                    忽略
                  </button>
                </div>
              )}
            </article>
          ))}
        </section>
      )}
      {tab === "data" && (
        <section className="nostalgia-section">
          <h2>查阅与修正</h2>
          <form
            className="nostalgia-search"
            onSubmit={(e) => {
              e.preventDefault();
              void browse();
            }}
          >
            <select
              aria-label="数据类型"
              value={target}
              onChange={(e) => {
                setTarget(e.target.value);
                setCards([]);
                setCursor(null);
              }}
            >
              <option value="artifacts">整理后的理解</option>
              <option value="records">原始记录</option>
            </select>
            <input
              aria-label="搜索上下文"
              placeholder="搜索内容或主题"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <button disabled={busy}>查询</button>
          </form>
          <div className="nostalgia-data">
            <div>
              {cards.map((card) => (
                <button
                  className="nostalgia-record"
                  key={card.kind + card.id}
                  onClick={() =>
                    void action({
                      action: "read",
                      id: card.id,
                      kind: card.kind,
                    })
                      .then(setDetail)
                      .catch(() => {})
                  }
                >
                  <BookOpen size={15} />
                  <span>
                    <strong>{card.title || card.id}</strong>
                    <small>{card.preview}</small>
                  </span>
                </button>
              ))}
              {cursor && (
                <button disabled={busy} onClick={() => void browse(true)}>
                  加载更多
                </button>
              )}
            </div>
            <pre>
              {detail
                ? JSON.stringify(detail, null, 2)
                : "选择记录查看内容、来源与版本。"}
            </pre>
          </div>
          <details>
            <summary>补充修正说明</summary>
            <p>追加修正记录，交由下一轮整理处理；保留原始证据。</p>
            <textarea
              aria-label="修正说明"
              value={correction}
              onChange={(e) => setCorrection(e.target.value)}
            />
            <button
              disabled={busy || !correction.trim()}
              onClick={() =>
                void action({ action: "correct", text: correction })
                  .then(() => {
                    setCorrection("");
                    setRevision(revision + 1);
                  })
                  .catch(() => {})
              }
            >
              保存修正
            </button>
          </details>
        </section>
      )}
      {tab === "prompt" && status && (
        <article className="nostalgia-section nostalgia-prompt">
          <h2>Dreaming Prompt</h2>
          <small>SHA-256 {status.prompt_sha256}</small>
          <Markdown
            components={{ a: ({ children }) => <span>{children}</span> }}
          >
            {status.prompt}
          </Markdown>
        </article>
      )}
    </main>
  );
}
