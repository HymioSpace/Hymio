import { useEffect, useState } from "react";
import Markdown from "react-markdown";
import { Check, Code2, Copy, FileText, RefreshCw } from "lucide-react";
import { adminRequest, type Session } from "./api";
import "./prompt.css";

type Prompt = {
  markdown: string;
  sha256: string;
  channel: string;
  characters: number;
  includes_personal_context: boolean;
  source: string;
};
export function PromptPanel({ session }: { session: Session }) {
  const [channel, setChannel] = useState("web");
  const [data, setData] = useState<Prompt>();
  const [source, setSource] = useState(false);
  const [copied, setCopied] = useState(false);
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    setData(undefined);
    void adminRequest<Prompt>(`monitoring/prompt?channel=${channel}`, {
      session,
    })
      .then((value) => {
        if (active) setData(value);
      })
      .catch((e) => {
        if (active) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [channel, revision, session]);
  const sections =
    data?.markdown.split("\n").filter((line) => /^#{1,2} /.test(line)) || [];
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(data?.markdown || "");
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      setError("无法复制，请切换到 Markdown 源码后手动选择。");
    }
  };
  return (
    <main className="workspace prompt-workspace">
      <header className="topbar">
        <div>
          <h1>System Prompt</h1>
          <p className="prompt-intro">
            查看 Agent 当前使用的角色、运行规则和能力索引。
          </p>
        </div>
        <div className="prompt-actions">
          <select
            aria-label="Prompt 渠道"
            value={channel}
            onChange={(e) => setChannel(e.target.value)}
          >
            {["web", "ios", "desk", "chrome"].map((name) => (
              <option key={name} value={name}>
                {name === "ios"
                  ? "iOS"
                  : name === "desk"
                    ? "Desktop"
                    : name === "web"
                      ? "Web"
                      : "Chrome"}
              </option>
            ))}
          </select>
          <button
            className="icon-button bordered"
            disabled={loading}
            aria-label="刷新 Prompt"
            onClick={() => setRevision((n) => n + 1)}
          >
            <RefreshCw size={16} className={loading ? "spin" : ""} />
          </button>
        </div>
      </header>
      <div className="prompt-notice">
        <FileText size={17} />
        <p>
          与 Oath Worker
          共用同一份组装逻辑，展示服务启动时加载的当前配置。这里不包含用户记忆、动态上下文或某次请求的完整输入。
        </p>
      </div>
      {error && (
        <div className="feedback error" role="alert">
          {error}
        </div>
      )}
      {loading && (
        <div className="prompt-loading" role="status">
          正在读取当前 Prompt…
        </div>
      )}
      {data && (
        <div className="prompt-reader">
          <aside className="prompt-outline">
            <span>内容概览</span>
            {sections.map((text, i) => (
              <p key={i} className={text.startsWith("## ") ? "subsection" : ""}>
                {text.replace(/^#+ /, "")}
              </p>
            ))}
            <div className="prompt-fingerprint">
              <span>SHA-256</span>
              <code title={data.sha256}>{data.sha256.slice(0, 16)}</code>
              <span>{data.characters.toLocaleString()} 字符</span>
            </div>
          </aside>
          <section className="prompt-document">
            <header>
              <div role="group" aria-label="Prompt 显示方式">
                <button
                  className={!source ? "selected" : ""}
                  onClick={() => setSource(false)}
                >
                  <FileText size={14} />
                  阅读
                </button>
                <button
                  className={source ? "selected" : ""}
                  onClick={() => setSource(true)}
                >
                  <Code2 size={14} />
                  Markdown
                </button>
              </div>
              <button disabled={copied} onClick={() => void copy()}>
                {copied ? <Check size={14} /> : <Copy size={14} />}{" "}
                {copied ? "已复制" : "复制"}
              </button>
            </header>
            {source ? (
              <pre className="prompt-source">{data.markdown}</pre>
            ) : (
              <article className="prompt-markdown">
                <Markdown
                  skipHtml
                  components={{
                    a: ({ children }) => (
                      <span className="prompt-link">{children}</span>
                    ),
                  }}
                >
                  {data.markdown}
                </Markdown>
              </article>
            )}
          </section>
        </div>
      )}
    </main>
  );
}
