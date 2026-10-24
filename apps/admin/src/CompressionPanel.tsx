import {
  AlertTriangle,
  ArrowUpRight,
  Layers3,
  TriangleAlert,
  Waypoints,
} from "lucide-react";
import type { CompressionAttempt, CompressionSummary } from "./api";

const statusNames: Record<string, string> = {
  started: "进行中",
  ready: "摘要就绪",
  failed: "失败",
  skipped: "跳过",
};

const reasonNames: Record<string, string> = {
  invalid_output: "输出格式无效",
  over_budget: "摘要超过预算",
  not_reduced: "摘要没有变短",
  empty_output: "输出为空",
  provider_error: "模型或链路失败",
  storage_error: "存储失败",
  lease_busy: "压缩互斥占用",
  superseded: "已有更新结果",
  capacity_exhausted: "压缩输入超限",
  chunk_capacity_exhausted: "单段输入超限",
};

function milliseconds(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value))
    return "—";
  return value >= 1000
    ? `${(value / 1000).toFixed(2)} s`
    : `${Math.round(value)} ms`;
}

function attemptTime(row: CompressionAttempt) {
  const value = row.started_at || row.finished_at;
  if (!value) return "—";
  return new Date(value * 1000).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function traceHref(row: CompressionAttempt) {
  if (!row.trace_id) return "";
  return `#/monitoring/traces/${encodeURIComponent(row.trace_id)}?user=${encodeURIComponent(
    row.user_id,
  )}`;
}

export function CompressionPanel({
  summary,
}: {
  summary?: CompressionSummary;
}) {
  if (!summary) {
    return (
      <section className="panel compression-panel">
        <div className="chart-empty compact">
          <Layers3 size={22} />
          <span>正在读取上下文整理记录</span>
        </div>
      </section>
    );
  }
  const terminal = summary.ready + summary.failed + summary.skipped;
  const success = terminal ? summary.ready / terminal : undefined;
  const sync = summary.by_mode.sync;
  const async = summary.by_mode.async;
  return (
    <section className="panel compression-panel" aria-label="上下文整理">
      <header className="panel-head">
        <div className="panel-heading-copy">
          <span className="panel-heading-icon">
            <Layers3 size={18} />
          </span>
          <div>
            <p className="eyebrow">CONTEXT COMPACTION</p>
            <h2>上下文整理</h2>
            <p>
              同步整理会阻塞当前回复；异步整理只准备后文视图。Token
              数据来自启发式估算，不是 provider 上报值。
            </p>
          </div>
        </div>
        <span className="section-note">最近 {summary.window_hours} 小时</span>
      </header>
      {summary.unavailable && (
        <p className="feedback">压缩事件源暂不可用；当前数字不是“零成功”。</p>
      )}
      <div className="compression-kpis">
        <article>
          <span>整理任务</span>
          <strong>{summary.attempts}</strong>
          <small>
            同步 {sync?.attempts || 0} · 异步 {async?.attempts || 0}
          </small>
        </article>
        <article className={terminal && !summary.ready ? "attention" : ""}>
          <span>产出成功率</span>
          <strong>
            {success === undefined ? "—" : `${(success * 100).toFixed(1)}%`}
          </strong>
          <small>
            就绪 {summary.ready} · 失败 {summary.failed} · 跳过{" "}
            {summary.skipped}
          </small>
        </article>
        <article className={summary.blocked_steps ? "attention" : ""}>
          <span>阻塞回复</span>
          <strong>{summary.blocked_steps}</strong>
          <small>上下文超过硬窗口而暂停的 Step</small>
        </article>
        <article>
          <span>完成耗时</span>
          <strong>{milliseconds(summary.duration.p95)}</strong>
          <small>P95 · P50 {milliseconds(summary.duration.p50)}</small>
        </article>
      </div>
      <div className="compression-health">
        <section>
          <h3>
            <Waypoints size={15} /> 同步 / 异步
          </h3>
          {(["sync", "async"] as const).map((mode) => {
            const value = summary.by_mode[mode];
            return (
              <div className="compaction-mode-row" key={mode}>
                <span>{mode === "sync" ? "同步" : "异步"}</span>
                <b>{value?.attempts || 0}</b>
                <small>
                  就绪 {value?.ready || 0} · 失败 {value?.failed || 0} · 跳过{" "}
                  {value?.skipped || 0}
                </small>
              </div>
            );
          })}
        </section>
        <section>
          <h3>
            <TriangleAlert size={15} /> 异常原因
          </h3>
          {summary.reasons.length ? (
            summary.reasons.slice(0, 6).map((item) => (
              <div className="compaction-reason-row" key={item.reason}>
                <span>{reasonNames[item.reason] || item.reason}</span>
                <b>{item.count}</b>
              </div>
            ))
          ) : (
            <p className="compaction-empty">当前时间窗没有失败或跳过记录。</p>
          )}
        </section>
      </div>
      <div className="compaction-table-wrap">
        <table className="compaction-table">
          <thead>
            <tr>
              <th>开始时间</th>
              <th>用户 / 渠道</th>
              <th>模式</th>
              <th>结果</th>
              <th>覆盖 / 窗口</th>
              <th>估算输入 → 输出</th>
              <th>耗时</th>
              <th>Trace</th>
            </tr>
          </thead>
          <tbody>
            {summary.recent.length ? (
              summary.recent.slice(0, 30).map((row) => {
                const href = traceHref(row);
                return (
                  <tr key={row.compression_id}>
                    <td>{attemptTime(row)}</td>
                    <td>
                      <strong>
                        {row.user_name || row.user_id.slice(0, 10)}
                      </strong>
                      <small>{row.channel}</small>
                    </td>
                    <td>
                      {row.mode === "sync"
                        ? "同步"
                        : row.mode === "async"
                          ? "异步"
                          : row.mode}
                    </td>
                    <td>
                      <span className={`compaction-outcome ${row.status}`}>
                        {statusNames[row.status] || row.status}
                      </span>
                      {row.reason && (
                        <small>{reasonNames[row.reason] || row.reason}</small>
                      )}
                    </td>
                    <td>
                      {row.covers ?? "—"} 条
                      <small>
                        {row.context_window
                          ? `${Math.round(row.context_window / 1000)}K 窗口`
                          : "窗口未知"}
                      </small>
                    </td>
                    <td>
                      {row.input_tokens?.toLocaleString("zh-CN") ?? "—"} →{" "}
                      {row.output_tokens?.toLocaleString("zh-CN") ?? "—"}
                      <small>估算 tokens</small>
                    </td>
                    <td>{milliseconds(row.duration_ms)}</td>
                    <td>
                      {href ? (
                        <a href={href} aria-label="打开关联 Trace">
                          {row.trace_id.slice(0, 10)} <ArrowUpRight size={12} />
                        </a>
                      ) : (
                        <span className="compaction-missing">
                          <AlertTriangle size={12} /> 未关联
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })
            ) : (
              <tr>
                <td colSpan={8}>
                  当前时间窗没有压缩记录。若运行中的 Oath 版本尚未发送
                  context.compaction，请先核对其事件版本。
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
