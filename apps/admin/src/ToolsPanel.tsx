import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  Clock3,
  RefreshCw,
  Search,
  Wrench,
} from "lucide-react";
import { adminRequest, type Session } from "./api";
import { toolTotals, sortTools, type ToolReport } from "./tool-model";
import "./tools.css";

const names: Record<string, string> = {
  succeeded: "成功",
  failed: "失败",
  timeout: "超时",
  cancelled: "取消",
  outcome_unknown: "结果未知",
};
const count = (n: number) =>
  n.toLocaleString("zh-CN", { maximumFractionDigits: 1 });
const duration = (n?: number | null) =>
  n == null ? "—" : n < 1 ? `${Math.round(n * 1000)} ms` : `${n.toFixed(2)} s`;
const percent = (n?: number | null) =>
  n == null ? "—" : `${(n * 100).toFixed(1)}%`;

export function ToolsPanel({ session }: { session: Session }) {
  const [hours, setHours] = useState(24);
  const [data, setData] = useState<ToolReport>();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("volume");
  const [selected, setSelected] = useState("");
  const [updated, setUpdated] = useState<Date>();
  const generation = useRef(0);
  const inFlight = useRef(false);
  const load = useCallback(
    async (version: number) => {
      if (inFlight.current) return;
      inFlight.current = true;
      if (generation.current === version) setLoading(true);
      try {
        const value = await adminRequest<ToolReport>(
          `monitoring/tools?hours=${hours}`,
          { session },
        );
        if (generation.current !== version) return;
        setData(value);
        setError("");
        setUpdated(new Date());
      } catch (e) {
        if (generation.current === version)
          setError(e instanceof Error ? e.message : String(e));
      } finally {
        inFlight.current = false;
        if (generation.current === version) setLoading(false);
      }
    },
    [hours, session],
  );
  useEffect(() => {
    const version = ++generation.current;
    setData(undefined);
    setSelected("");
    setUpdated(undefined);
    const tick = () => {
      if (!document.hidden) void load(version);
    };
    // A range change can wait for the prior request, but never displays its response.
    tick();
    const timer = setInterval(tick, 20_000);
    document.addEventListener("visibilitychange", tick);
    return () => {
      generation.current++;
      clearInterval(timer);
      document.removeEventListener("visibilitychange", tick);
    };
  }, [load]);
  const totals = toolTotals(data?.tools || []);
  const rows = sortTools(
    (data?.tools || []).filter((row) =>
      row.tool.toLowerCase().includes(query.toLowerCase()),
    ),
    sort,
  );
  const detail = data?.tools.find((row) => row.tool === selected);
  const healthy = data?.collection.status === "ready";
  return (
    <main className="workspace tool-workspace">
      <header className="topbar monitor-topbar">
        <div>
          <p className="eyebrow">OBSERVABILITY / TOOLS</p>
          <h1>工具执行</h1>
          <p className="monitor-subtitle">
            一次调用，一个结果。观察工具是否可靠，以及时间花在哪里。
          </p>
        </div>
        <div className="monitor-actions">
          <label className="range-control">
            <Clock3 size={15} />
            <select
              aria-label="工具统计时间范围"
              value={hours}
              onChange={(e) => setHours(Number(e.target.value))}
            >
              <option value={1}>最近 1 小时</option>
              <option value={6}>最近 6 小时</option>
              <option value={24}>最近 24 小时</option>
              <option value={168}>最近 7 天</option>
            </select>
          </label>
          <button
            className="icon-button bordered"
            aria-label="刷新工具指标"
            disabled={loading}
            onClick={() => void load(generation.current)}
          >
            <RefreshCw size={17} className={loading ? "spin" : ""} />
          </button>
        </div>
      </header>
      {error && (
        <div className="feedback error" role="alert">
          <AlertTriangle size={16} />
          {error} · 保留上次成功的数据
        </div>
      )}
      {data && (!healthy || data.errors.length > 0) && (
        <div className="tool-warning" role="status">
          <AlertTriangle size={18} />
          <div>
            <strong>
              {!healthy ? "工具采集尚未正常连接" : "部分指标查询失败"}
            </strong>
            <p>
              {!healthy
                ? "检查 Prometheus 的 Oath Tools 采集目标；当前数据可能只覆盖此前的采样。"
                : `不可用：${data.errors.join("、")}。缺失值不会按零处理。`}
            </p>
          </div>
        </div>
      )}
      <section className="tool-kpis" aria-label="工具运行概况">
        {[
          {
            icon: Wrench,
            label: "终态调用",
            value:
              data && !data.errors.includes("outcomes")
                ? `≈ ${count(totals.total)}`
                : "—",
            note: "窗口内的采样估算",
          },
          {
            icon: CheckCircle2,
            label: "成功率",
            value:
              data && !data.errors.includes("outcomes")
                ? percent(totals.successRate)
                : "—",
            note: "成功 / 全部终态",
          },
          {
            icon: AlertTriangle,
            label: "未成功",
            value:
              data && !data.errors.includes("outcomes")
                ? `≈ ${count(totals.unsuccessful)}`
                : "—",
            note: "含失败、超时、取消与未知",
          },
          {
            icon: Activity,
            label: "执行均值",
            value: duration(
              data &&
                !data.errors.some((e) => ["samples", "average"].includes(e))
                ? totals.average
                : null,
            ),
            note: "按执行样本加权，不含排队",
          },
        ].map((item) => (
          <article key={item.label} className="tool-kpi">
            <span>
              <item.icon size={16} />
              {item.label}
            </span>
            <strong>{item.value}</strong>
            <small>{item.note}</small>
          </article>
        ))}
      </section>
      <section className="tool-catalog">
        <header className="tool-catalog-heading">
          <div>
            <h2>按工具观察</h2>
            <p>
              成功率与耗时使用相同时间范围；空闲工具保留名称，未采样的数据留空。
            </p>
          </div>
          <span className="tool-updated">
            <i className={healthy ? "healthy" : ""} />
            {updated
              ? `${updated.toLocaleTimeString("zh-CN", { hour12: false })} 更新`
              : "等待采集"}
          </span>
        </header>
        <div className="tool-filters">
          <label>
            <Search size={16} />
            <input
              aria-label="搜索工具"
              placeholder="搜索工具名称"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <select
            aria-label="工具排序"
            value={sort}
            onChange={(e) => setSort(e.target.value)}
          >
            <option value="volume">调用最多</option>
            <option value="reliability">成功率最低</option>
            <option value="latency">P95 最慢</option>
          </select>
        </div>
        <div className="tool-table-scroll">
          <table className="tool-table">
            <thead>
              <tr>
                <th>工具 / 终态分布</th>
                <th>调用估算</th>
                <th>成功率</th>
                <th>平均</th>
                <th>P50</th>
                <th>P95</th>
                <th>
                  <span className="sr-only">展开</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.tool}
                  className={selected === row.tool ? "selected" : ""}
                >
                  <td>
                    <button
                      className="tool-name"
                      onClick={() =>
                        setSelected(selected === row.tool ? "" : row.tool)
                      }
                      aria-expanded={selected === row.tool}
                    >
                      <Wrench size={15} />
                      <code>{row.tool}</code>
                    </button>
                    <div
                      className="tool-outcomes"
                      aria-label={`${row.tool} 终态分布`}
                    >
                      {Object.entries(row.outcomes).map(([outcome, n]) => (
                        <i
                          key={outcome}
                          className={`outcome-${outcome}`}
                          title={`${names[outcome] || outcome} ≈ ${count(n)}`}
                          style={{ flex: n }}
                        />
                      ))}
                    </div>
                  </td>
                  <td>
                    {data?.errors.includes("outcomes")
                      ? "—"
                      : `≈ ${count(row.total)}`}
                  </td>
                  <td>
                    <span
                      className={`tool-rate ${row.success_rate != null && row.success_rate < 0.95 ? "low" : ""}`}
                    >
                      {data?.errors.includes("outcomes")
                        ? "—"
                        : percent(row.success_rate)}
                    </span>
                  </td>
                  <td>{duration(row.average)}</td>
                  <td>{duration(row.p50)}</td>
                  <td className="tool-p95">{duration(row.p95)}</td>
                  <td>
                    <button
                      className="icon-button"
                      aria-label={`查看 ${row.tool} 统计口径`}
                      onClick={() =>
                        setSelected(selected === row.tool ? "" : row.tool)
                      }
                      aria-expanded={selected === row.tool}
                    >
                      <ArrowUpRight size={15} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!rows.length && (
          <div className="tool-empty">
            <Wrench size={25} />
            <h3>
              {loading && !data
                ? "正在读取工具指标"
                : query
                  ? "没有匹配的工具"
                  : healthy
                    ? "还没有可展示的工具样本"
                    : "等待工具数据源"}
            </h3>
            <p>
              {query
                ? "试试其他名称。"
                : healthy
                  ? "新启动的服务或稀疏调用需要更多采样；这里不会把缺失数据显示成 100% 成功。"
                  : "采集目标恢复后自动刷新。"}
            </p>
          </div>
        )}
        <footer className="tool-table-foot">
          <span>{rows.length} 个工具</span>
          <span>自动刷新 20s · 切到后台暂停刷新</span>
        </footer>
      </section>
      {detail && (
        <section className="tool-detail" aria-label="工具统计详情">
          <header>
            <div>
              <p className="eyebrow">OUTCOMES</p>
              <h2>{detail.tool}</h2>
            </div>
            <button className="text-button" onClick={() => setSelected("")}>
              收起
            </button>
          </header>
          <div className="tool-detail-outcomes">
            {[
              ...new Set([
                ...Object.keys(names),
                ...Object.keys(detail.outcomes),
              ]),
            ].map((outcome) => (
              <div key={outcome}>
                <i className={`outcome-${outcome}`} />
                <span>{names[outcome] || outcome}</span>
                <strong>
                  {data?.errors.includes("outcomes")
                    ? "—"
                    : `≈ ${count(detail.outcomes[outcome] || 0)}`}
                </strong>
              </div>
            ))}
          </div>
          <p>
            终态和执行耗时是不同样本集：审批取消等未执行的调用可以有终态，但没有执行耗时。单次失败原因与参数请进入
            Trace 排查。
          </p>
          <a href="#/monitoring/traces">
            打开 Trace 排查 <ArrowUpRight size={14} />
          </a>
        </section>
      )}
      <aside className="tool-method">
        <Clock3 size={17} />
        <div>
          <strong>如何读这些数值</strong>
          <p>
            调用量由 Prometheus increase
            估算，可能出现小数；首个采样、重启与保留期会影响覆盖。成功率包含全部终态；耗时来自执行直方图，不包含审批和队列等待。P95
            是桶内估计，不是精确分位数。
          </p>
        </div>
      </aside>
    </main>
  );
}
