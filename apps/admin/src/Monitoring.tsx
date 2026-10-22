import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  ChevronDown,
  CircleHelp,
  Code2,
  ExternalLink,
  ListChecks,
  Monitor,
  Radio,
  RefreshCw,
  ScrollText,
  Search,
  Smartphone,
  UserRound,
  Workflow,
  X,
} from "lucide-react";
import {
  adminRequest,
  type ClientTurn,
  type MonitoringOverview,
  type PromSeries,
  type Session,
  type TraceDetail,
  type TraceNode,
  type TraceSearchMatch,
  type TraceSearchResponse,
} from "./api";

const channelNames: Record<string, string> = {
  web: "Web",
  ios: "iOS",
  desk: "Desktop",
  chrome: "Chrome",
  unknown: "未知渠道",
};

const outcomeNames: Record<string, string> = {
  sent: "已发送",
  accepted: "已接纳",
  in_progress: "处理中",
  completed: "完成",
  failed: "失败",
  cancelled: "取消",
  partial: "部分完成",
  stalled: "无响应",
};

const stages = [
  [
    "accepted_ms",
    "服务端接纳",
    "t(ack) − t₀；包含本地持久化、传输与 queue.add",
  ],
  [
    "first_response_ms",
    "首响应",
    "t(first_delta) − t₀；reasoning 与 content 均计入",
  ],
  ["first_renderable_ms", "首个正文", "t(first_content) − t₀；仅 content 通道"],
  ["first_paint_ms", "首帧", "t(requestAnimationFrame) − t₀；仅 Web/Desktop"],
  ["completed_ms", "整条 Trace", "t(terminal step.status) − t₀"],
] as const;

const chartDefinitions = [
  {
    name: "host_memory_used",
    title: "宿主机内存",
    question: "是否因内存不足开始抖动？",
    unit: "percent",
    detail: "1 − MemAvailable / MemTotal；来自宿主机 node exporter。",
  },
  {
    name: "host_iowait",
    title: "磁盘等待",
    question: "CPU 是否在等待磁盘？",
    unit: "percent",
    detail: "CPU iowait 占比，5 分钟窗口。",
  },
  {
    name: "process_memory",
    title: "服务内存",
    question: "哪个服务占用或持续增长？",
    unit: "bytes",
    detail: "各服务进程 RSS；并非容器总内存或宿主机总占用。",
  },
  {
    name: "storage_bytes",
    title: "状态与磁盘归档",
    question: "热状态和历史数据是否持续增长？",
    unit: "bytes",
    detail: "执行热状态、归档压缩前后、SQLite 与 WAL 大小。",
  },
  {
    name: "storage_lock_p95",
    title: "存储锁等待",
    question: "任务领取是否堵在 SQLite？",
    unit: "ms",
    detail: "读取与写入的 SQLite 锁等待 p95，5 分钟窗口。",
  },
  {
    name: "rpc_p95",
    title: "内部服务延迟",
    question: "哪个服务正在拖慢链路？",
    unit: "ms",
    detail:
      "oath_rpc_duration_seconds 按 service 聚合后的桶内 P95；进程启动以来的累计直方图。",
  },
  {
    name: "wake_wait_p95",
    title: "队列到唤醒",
    question: "消息是卡在队列，还是卡在模型？",
    unit: "ms",
    detail:
      "oath_buffer_wake_delay_seconds；W = t_claim − t_occur，包含 broker、buffer 与 claim 等待。",
  },
  {
    name: "llm_ttft_p95",
    title: "模型 TTFT",
    question: "用户等首字，主要是不是模型？",
    unit: "s",
    detail:
      "oath_llm_ttft_seconds；T = t_first_delta − t_request，含 reasoning 首包。",
  },
  {
    name: "tool_duration_p95",
    title: "工具执行",
    question: "慢在模型决策，还是慢在工具？",
    unit: "ms",
    detail:
      "oath_tool_duration_seconds；E = t_terminal − t_worker_start，审批等待不计入 E。",
  },
  {
    name: "delivery_p95",
    title: "Outbox 投递",
    question: "服务端已经生成，为什么客户端还没看到？",
    unit: "ms",
    detail:
      "oath_delivery_delay_seconds；L = t_after_ws_send − t_created，测量持久化到发送完成。",
  },
  {
    name: "rabbit_ready",
    title: "RabbitMQ 积压",
    question: "队列里是否还有未消费的消息？",
    unit: "count",
    detail: "Σ_q rabbitmq_queue_messages_ready(q)；瞬时 Gauge，不做时间聚合。",
  },
] as const;

type MetricGuideItem = {
  name: string;
  formula: string;
  definition: string;
};

type MetricGuideGroup = {
  title: string;
  summary: string;
  notation: string;
  items: readonly MetricGuideItem[];
};

const metricGuide: readonly MetricGuideGroup[] = [
  {
    title: "端到端体验",
    summary:
      "每条 user.message 生成一个客户端样本；所有时间差使用同一单调时钟，单位为 ms。",
    notation:
      "t₀ = client.command.start；xᵢ = tᵢ − t₀；各阶段仅对 xᵢ ≠ NULL 的样本单独计算。",
    items: [
      {
        name: "服务端接纳",
        formula: "Aᵢ = tᵢ(ack) − tᵢ(t₀)",
        definition:
          "tᵢ(ack) 是同一 command_id 的 ACK 到达客户端。A 包含命令本地持久化、WebSocket 传输、鉴权与校验、queue.add 及 ACK 回传。",
      },
      {
        name: "首响应",
        formula: "Rᵢ = tᵢ(first_delta) − tᵢ(t₀)",
        definition:
          "tᵢ(first_delta) 是客户端收到的第一个 assistant.delta，不区分 reasoning 或 content；包含从发送到该帧完成接收的全部等待。",
      },
      {
        name: "首个正文",
        formula: "Cᵢ = tᵢ(first_content) − tᵢ(t₀)",
        definition:
          "tᵢ(first_content) 是第一个 payload.channel = content 的 assistant.delta 到达客户端的时刻；C − R 是推理首包到正文首包的等待。",
      },
      {
        name: "首帧",
        formula: "Pᵢ = tᵢ(first_paint) − tᵢ(t₀)",
        definition:
          "Web/Desktop 在首个正文后安排一次 requestAnimationFrame 并记录 P；iOS 不上报该字段。P − C 是浏览器调度到首帧回调的时间，不是浏览器合成器完成绘制的绝对时刻。",
      },
      {
        name: "整条 Trace",
        formula: "Eᵢ = tᵢ(terminal) − tᵢ(t₀)",
        definition:
          "tᵢ(terminal) 是首个 status ∈ {completed, failed, cancelled} 的 step.status，或命令被 Gateway 明确拒绝的时刻。只统计一次，不覆盖更早的终态。",
      },
      {
        name: "完成 / 失败 / 无响应率",
        formula:
          "CR = Σ[oᵢ = completed] / N\nFR = Σ[oᵢ = failed] / N\nNR = Σ[oᵢ = stalled] / N",
        definition:
          "N 为窗口内全部有效 turn 样本。stalled 表示发送后 30 秒内没有第一个 assistant.delta；cancelled、partial 仍进入分母，但不进入完成、失败或无响应分子。N = 0 时比率无定义并显示 —。",
      },
      {
        name: "P50 / P95 / P99",
        formula: "h = (n − 1)p；Qₚ = x₍⌊h⌋₎ + (h − ⌊h⌋)(x₍⌈h⌉₎ − x₍⌊h⌋₎)",
        definition:
          "对阶段原始样本升序排列后按上式线性插值，p 分别取 0.50、0.95、0.99；不是直方图近似。窗口按 received_at 过滤，最多保留最新 5000 条幂等 sample。",
      },
    ],
  },
  {
    title: "服务器链路",
    summary:
      "下式为单次 span/直方图观测值；P95 由 Prometheus 的有限桶做桶内线性插值。",
    notation:
      "Bₗ(t) = Σ bucketₗ(t)；Qₚ(t) = histogram_quantile(p, {Bₗ(t)})。当前图线取进程启动以来的累计桶，不做 rate 窗口平滑。",
    items: [
      {
        name: "RPC 处理",
        formula: "Dᵢ = tᵢ(return) − tᵢ(enter)",
        definition:
          "tᵢ(enter) 在 RPC handler 开始处理请求时取值，tᵢ(return) 在 finally 中状态码确定后取值；按 service、operation、status 记录 histogram。",
      },
      {
        name: "Gateway 命令",
        formula: "Gᵢ = tᵢ(ack_send) − tᵢ(frame_start)",
        definition:
          "从收到原始 WebSocket frame 开始，到该命令的 ACK/error 已发送至传输层为止；包含 JSON 解析、鉴权、校验和 queue.add，不包含客户端网络与浏览器处理。",
      },
      {
        name: "队列发布",
        formula: "Pᵢ = tᵢ(publish_confirmed) − tᵢ(occur)",
        definition:
          "tᵢ(occur) 是 outbox item 的创建时间；tᵢ(publish_confirmed) 是 RabbitMQ publisher confirm 返回后的时刻。",
      },
      {
        name: "队列消费",
        formula: "Cᵢ = tᵢ(buffer_insert) − tᵢ(occur)",
        definition:
          "从 item 创建到 consumer 完成校验并写入 buffer 的累计延迟，包含 broker 传输、consumer 调度与 lease 获取。",
      },
      {
        name: "队列到唤醒",
        formula: "Wᵢ = tᵢ(claim) − tᵢ(occur)",
        definition:
          "从 item 创建到 Worker claim 并 consume buffer 的累计等待；同时覆盖 broker、buffer 和 claim 等待，不能单独解释为 buffer wake。",
      },
      {
        name: "Brain 调度",
        formula: "Kᵢ = tᵢ(brain_claim) − tᵢ(ready_at)",
        definition:
          "用户状态满足调度条件后，到 worker 获得 brain lease 的等待时间；ready_at 由调度器写入。",
      },
      {
        name: "Agent Step",
        formula: "Sᵢ = tᵢ(step_end) − tᵢ(trace_started)",
        definition:
          "invoke_agent span 的持续时间，从 Step 认领到写入终态；包含模型调用和阶段处理，工具执行的后续 span 不计入该 Step 的 S。",
      },
      {
        name: "模型 TTFT / TPOT",
        formula:
          "Tᵢ = tᵢ(first_delta) − tᵢ(request)\nTPOT = (D − T) / (N_out − 1)",
        definition:
          "首增量包括 reasoning 或 content 通道；D 为完整模型 span 时长，N_out 为 provider 报告的 completion_tokens，仅当 N_out > 1 时计算 TPOT。",
      },
      {
        name: "工具执行",
        formula: "Eᵢ = tᵢ(terminal) − tᵢ(worker_start)",
        definition:
          "从工具 worker 开始处理 invocation 到工具终态落库、发布并写 trace 的完成时刻；审批等待不计入 E，排队时间单独记为 oath.tool.queue_ms。",
      },
      {
        name: "Outbox 投递",
        formula: "Lᵢ = tᵢ(after_ws_send) − tᵢ(created_at)",
        definition:
          "从事件 created_at 到 WebSocket send 完成的时刻；发送前包含 client.delivered 持久化与 Gateway 轮询。按事件 type 记录 histogram。",
      },
    ],
  },
  {
    title: "Agent 质量",
    summary:
      "在客户端 telemetry 上报时读取该 trace 的 span 快照；trace 不可用时字段保持 NULL，不按 0 处理。",
    notation:
      "P(trace) = {sᵢ | sᵢ.trace_id = trace_id}；计数均在单个 trace 内完成，比率在所选 channel 时间窗内汇总。",
    items: [
      {
        name: "Step 数",
        formula:
          "N_step = |{s ∈ P | s.name = invoke_agent ∧ s.parent_span_id = NULL}|",
        definition:
          "只统计 trace 根级 invoke_agent span；子级 invoke_agent 不计入。平均值取窗口内所有非 NULL trace 的算术平均。",
      },
      {
        name: "模型调用数",
        formula:
          "N_model = |{s ∈ P | s.attributes[gen_ai.operation.name] = chat}|",
        definition:
          "每次 chat span 计一次，包括失败或重试 attempt；不使用 token 数代替调用次数。",
      },
      {
        name: "工具调用数",
        formula: "N_tool = |{s ∈ P | s.name starts_with execute_tool }|",
        definition:
          "每个已进入工具执行并产生 span 的 invocation 计一次；仅存在于模型输出、尚未进入执行的 tool_call 不计数。",
      },
      {
        name: "工具成功率",
        formula:
          "TSR = Σᵢ N_success(i) / Σᵢ N_tool(i)\nN_success = |{s.tool.outcome = succeeded}|",
        definition:
          "按工具终态汇总；failed、timeout、cancelled 都在分母且不在分子。分母为 0 时无定义并显示 —。",
      },
      {
        name: "工具累计耗时",
        formula: "E_total(i) = Σ_{s ∈ tools(i)} s.duration_ms",
        definition:
          "先对单条 trace 的所有工具 span 求和，再对非 NULL 的 E_total 取算术平均；它不是单个工具的均值。",
      },
      {
        name: "渠道 / 设备",
        formula: "channel ∈ {web, ios, desk, chrome, unknown}",
        definition:
          "channel 是样本的一级分组维度；device_id 是独立的匿名设备标识。device_id 不写入 Prometheus label，详情只在 admin trace 中展示。",
      },
    ],
  },
];

function latency(value?: number | null, unit = "ms") {
  if (value === undefined || value === null || !Number.isFinite(value))
    return "—";
  if (unit === "count") return Math.round(value).toLocaleString("zh-CN");
  if (unit === "percent") return `${(value * 100).toFixed(1)}%`;
  if (unit === "bytes")
    return value >= 1048576
      ? `${(value / 1048576).toFixed(1)} MiB`
      : `${(value / 1024).toFixed(1)} KiB`;
  if (unit === "s")
    return `${(value / 1000).toFixed(value >= 10_000 ? 1 : 2)} s`;
  return value >= 1000
    ? `${(value / 1000).toFixed(2)} s`
    : `${Math.round(value)} ms`;
}

function latest(data: MonitoringOverview | undefined, name: string) {
  const row = data?.prometheus.metrics[name]?.[0];
  const value = Number(row?.value);
  return Number.isFinite(value) ? value : undefined;
}

function metricName(metric: Record<string, string>) {
  return (
    metric.tool ||
    metric.model ||
    metric.service ||
    metric.type ||
    metric.queue ||
    metric.channel ||
    metric.kind ||
    metric.mode ||
    metric.instance ||
    "overall"
  );
}

function LineChart({
  definition,
  series,
}: {
  definition: (typeof chartDefinitions)[number];
  series?: PromSeries;
}) {
  const lines = (series?.series || []).map((line) => ({
    ...line,
    values: line.values.map(
      ([at, raw]) =>
        [
          at,
          String(
            Number(raw) *
              (definition.unit === "ms" || definition.unit === "s" ? 1000 : 1),
          ),
        ] as [number, string],
    ),
  }));
  const points = lines.flatMap((line) =>
    line.values.map(([at, raw]) => ({ at, value: Number(raw) })),
  );
  const max = Math.max(0.001, ...points.map((point) => point.value));
  const minAt = Math.min(...points.map((point) => point.at));
  const maxAt = Math.max(...points.map((point) => point.at));
  const palette = [
    "#3f5bd8",
    "#12805c",
    "#b85f16",
    "#b13770",
    "#16798a",
    "#7450a8",
  ];
  if (!points.length)
    return (
      <div className="chart-empty">
        <BarChart3 size={22} />
        <span>当前时间窗没有样本</span>
      </div>
    );
  const y = (value: number) => 190 - (value / max) * 150;
  const x = (at: number) =>
    maxAt === minAt ? 54 : 54 + ((at - minAt) / (maxAt - minAt)) * 690;
  return (
    <>
      <svg
        className="monitor-chart"
        viewBox="0 0 760 220"
        role="img"
        aria-label={`${definition.title}。最高值 ${latency(max, definition.unit)}，共 ${lines.length} 个序列。`}
      >
        <title>{definition.title}</title>
        <desc>{definition.detail}</desc>
        {[0, 1, 2, 3].map((line) => {
          const at = 190 - line * 50;
          const value = (max * line) / 3;
          return (
            <g key={line}>
              <line x1="54" x2="744" y1={at} y2={at} stroke="#e7eaf0" />
              <text x="45" y={at + 4} textAnchor="end" className="axis-label">
                {latency(value, definition.unit).replace(" ", "")}
              </text>
            </g>
          );
        })}
        {[minAt, minAt + (maxAt - minAt) / 2, maxAt].map((at, index) => (
          <text
            key={at}
            x={54 + index * 345}
            y="214"
            textAnchor={index === 0 ? "start" : index === 2 ? "end" : "middle"}
            className="axis-label"
          >
            {new Date(at * 1000).toLocaleTimeString("zh-CN", {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </text>
        ))}
        {lines.map((line, index) => {
          const color = palette[index % palette.length];
          const path = line.values
            .map(
              ([at, raw], pointIndex) =>
                `${pointIndex ? "L" : "M"}${x(at).toFixed(1)},${y(Number(raw)).toFixed(1)}`,
            )
            .join(" ");
          const last = line.values.at(-1);
          return (
            <g key={`${definition.name}-${index}`}>
              <path
                d={path}
                fill="none"
                stroke={color}
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              {last && (
                <circle
                  cx={x(last[0])}
                  cy={y(Number(last[1]))}
                  r="3.5"
                  fill={color}
                />
              )}
            </g>
          );
        })}
      </svg>
      <div className="chart-legend">
        {lines.slice(0, 6).map((line, index) => (
          <span key={`${definition.name}-legend-${index}`}>
            <i style={{ background: palette[index % palette.length] }} />
            {metricName(line.metric)}
            <b>
              {latency(Number(line.values.at(-1)?.[1] || 0), definition.unit)}
            </b>
          </span>
        ))}
      </div>
    </>
  );
}

type ChannelRecord = MonitoringOverview["client"]["channels"][number];

function QuantileChart({ channel }: { channel: ChannelRecord }) {
  const quantiles = ["50", "95", "99"] as const;
  const maximum = Math.max(
    1,
    ...stages.flatMap(([key]) =>
      quantiles.map((quantile) => channel.latency[key]?.[quantile] || 0),
    ),
  );
  return (
    <div
      className="quantile-chart"
      role="img"
      aria-label={`${channelNames[channel.channel]} 各阶段 P50、P95、P99 延迟`}
    >
      <div className="quantile-legend">
        {quantiles.map((quantile) => (
          <span key={quantile}>
            <i className={`q-${quantile}`} />P{quantile}
          </span>
        ))}
      </div>
      {stages.map(([key, label]) => (
        <div className="quantile-row" key={key}>
          <span>{label}</span>
          <div>
            {quantiles.map((quantile) => {
              const value = channel.latency[key]?.[quantile];
              return (
                <i
                  key={quantile}
                  className={`q-${quantile}`}
                  style={{
                    width: `${value ? Math.max(2, (value / maximum) * 100) : 0}%`,
                  }}
                />
              );
            })}
          </div>
          <b>{latency(channel.latency[key]?.["95"])}</b>
        </div>
      ))}
      <small>每行显示 P50 / P95 / P99；右侧为 P95</small>
    </div>
  );
}

function StageDeltaChart({ channel }: { channel: ChannelRecord }) {
  const accepted = channel.latency.accepted_ms?.["95"] || 0;
  const response = channel.latency.first_response_ms?.["95"] || 0;
  const content = channel.latency.first_renderable_ms?.["95"] || 0;
  const completed = channel.latency.completed_ms?.["95"] || 0;
  const segments = [
    { label: "ACK", value: accepted },
    { label: "ACK → 首响应", value: Math.max(0, response - accepted) },
    { label: "首响应 → 正文", value: Math.max(0, content - response) },
    { label: "正文 → 终态", value: Math.max(0, completed - content) },
  ];
  const total = Math.max(
    1,
    segments.reduce((sum, item) => sum + item.value, 0),
  );
  return (
    <div
      className="stage-delta-chart"
      role="img"
      aria-label={`${channelNames[channel.channel]} P95 分段耗时`}
    >
      <div className="stage-delta-track">
        {segments.map((item, index) => (
          <i
            key={item.label}
            className={`delta-${index}`}
            style={{ width: `${(item.value / total) * 100}%` }}
          />
        ))}
      </div>
      <div className="stage-delta-legend">
        {segments.map((item, index) => (
          <div key={item.label}>
            <span>
              <i className={`delta-${index}`} />
              {item.label}
            </span>
            <b>{latency(item.value)}</b>
          </div>
        ))}
      </div>
    </div>
  );
}

function OutcomeBreakdown({ channel }: { channel: ChannelRecord }) {
  const count = (key: string) => {
    const fromMap = channel.outcomes?.[key];
    if (typeof fromMap === "number") return fromMap;
    if (key === "completed") return channel.completed;
    if (key === "failed") return channel.failed;
    if (key === "cancelled") return channel.cancelled || 0;
    if (key === "partial") return channel.partial || 0;
    if (key === "stalled") return channel.stalled || 0;
    return 0;
  };
  const outcomes = [
    ["completed", "完成"],
    ["stalled", "无响应"],
    ["failed", "失败"],
    ["partial", "部分"],
    ["cancelled", "取消"],
  ] as const;
  const total = Math.max(
    1,
    outcomes.reduce((sum, [key]) => sum + count(key), 0),
  );
  return (
    <div
      className="outcome-chart"
      role="img"
      aria-label={`${channelNames[channel.channel]} 结果分布`}
    >
      <strong>{channel.turns} turns</strong>
      <div className="outcome-track">
        {outcomes.map(([key, label]) => {
          const value = count(key);
          return (
            <i
              key={key}
              className={`outcome-${key}`}
              style={{ width: `${(value / total) * 100}%` }}
              title={`${label} ${value}`}
            />
          );
        })}
      </div>
      <dl>
        {outcomes.map(([key, label]) => (
          <div key={key}>
            <dt>
              <i className={`outcome-${key}`} />
              {label}
            </dt>
            <dd>{count(key)}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function DeviceTable({ turns }: { turns: ClientTurn[] }) {
  const grouped = new Map<
    string,
    { total: number; completed: number; stalled: number; last: number }
  >();
  for (const turn of turns) {
    const key = turn.device_id || turn.client_id || "unknown";
    const current = grouped.get(key) || {
      total: 0,
      completed: 0,
      stalled: 0,
      last: 0,
    };
    current.total++;
    current.completed += turn.outcome === "completed" ? 1 : 0;
    current.stalled += turn.outcome === "stalled" ? 1 : 0;
    current.last = Math.max(current.last, turn.received_at);
    grouped.set(key, current);
  }
  const rows = [...grouped.entries()]
    .sort((a, b) => b[1].last - a[1].last)
    .slice(0, 8);
  return (
    <div className="device-diagnostic-table">
      <div className="device-diagnostic-row head">
        <span>设备</span>
        <span>样本</span>
        <span>完成</span>
        <span>无响应</span>
        <span>最后上报</span>
      </div>
      {rows.map(([device, row]) => (
        <div className="device-diagnostic-row" key={device}>
          <code title={device}>{device}</code>
          <span>{row.total}</span>
          <span>{row.completed}</span>
          <span>{row.stalled}</span>
          <span>
            {new Date(row.last * 1000).toLocaleTimeString("zh-CN", {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </span>
        </div>
      ))}
      {!rows.length && <p className="empty">该渠道暂无最近样本。</p>}
    </div>
  );
}

function ChannelWorkspace({
  channel,
  turns,
}: {
  channel: ChannelRecord;
  turns: ClientTurn[];
}) {
  const completion =
    channel.turns > 0 ? channel.completed / channel.turns : undefined;
  const stalled = channel.stalled || channel.outcomes?.stalled || 0;
  const noAck = channel.no_ack || 0;
  const noDelta = channel.no_delta || 0;
  const channelTurns = turns.filter((turn) => turn.channel === channel.channel);
  return (
    <div className="channel-workspace">
      <div className="channel-kpis">
        <article>
          <span>请求</span>
          <strong>{channel.turns}</strong>
          <small>{channelNames[channel.channel]} 样本</small>
        </article>
        <article>
          <span>完成率</span>
          <strong>{latency(completion, "percent")}</strong>
          <small>{channel.completed} completed</small>
        </article>
        <article className={stalled ? "attention" : ""}>
          <span>无响应</span>
          <strong>{stalled}</strong>
          <small>
            {noAck} 未 ACK · {noDelta} 已 ACK 未首响应
          </small>
        </article>
        <article>
          <span>首响应 P95</span>
          <strong>{latency(channel.latency.first_response_ms?.["95"])}</strong>
          <small>
            端到端 P95 {latency(channel.latency.completed_ms?.["95"])}
          </small>
        </article>
      </div>
      <div className="channel-chart-grid">
        <article className="channel-chart">
          <header>
            <div>
              <p className="eyebrow">STAGE QUANTILES</p>
              <h3>每个阶段等多久</h3>
            </div>
            <span>{channel.turns} samples</span>
          </header>
          <QuantileChart channel={channel} />
        </article>
        <article className="channel-chart">
          <header>
            <div>
              <p className="eyebrow">P95 BREAKDOWN</p>
              <h3>时间花在哪一段</h3>
            </div>
            <span>累计 → 增量</span>
          </header>
          <StageDeltaChart channel={channel} />
        </article>
        <article className="channel-chart outcome-card">
          <header>
            <div>
              <p className="eyebrow">OUTCOMES</p>
              <h3>结果分布</h3>
            </div>
          </header>
          <OutcomeBreakdown channel={channel} />
        </article>
        <article className="channel-chart">
          <header>
            <div>
              <p className="eyebrow">AGENT QUALITY</p>
              <h3>Agent 与工具</h3>
            </div>
          </header>
          <dl className="agent-quality-grid">
            <div>
              <dt>Steps / trace</dt>
              <dd>{channel.steps_avg ?? "—"}</dd>
            </div>
            <div>
              <dt>Tools / trace</dt>
              <dd>{channel.tools_avg ?? "—"}</dd>
            </div>
            <div>
              <dt>工具成功率</dt>
              <dd>{latency(channel.tool_success_rate, "percent")}</dd>
            </div>
            <div>
              <dt>工具累计 / trace</dt>
              <dd>{latency(channel.tool_ms_avg)}</dd>
            </div>
          </dl>
        </article>
      </div>
      <div className="channel-device-section">
        <header>
          <div>
            <p className="eyebrow">DEVICE BREAKDOWN</p>
            <h3>设备维度</h3>
          </div>
          <span>按最近 80 条样本汇总</span>
        </header>
        <DeviceTable turns={channelTurns} />
      </div>
    </div>
  );
}

function MatchSnippet({ text, query }: { text: string; query: string }) {
  const index = text.toLocaleLowerCase().indexOf(query.toLocaleLowerCase());
  if (!query.trim() || index < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, index)}
      <mark>{text.slice(index, index + query.length)}</mark>
      {text.slice(index + query.length)}
    </>
  );
}

function ExplorerPage({
  mode,
  channels,
  turns,
  selectedChannel,
  onChannel,
  query,
  onQuery,
  selectedTurn,
  session,
  onOpen,
  onClose,
  searchMatches = [],
  searching = false,
  searched = false,
  scanned = 0,
  failed = 0,
  searchError = "",
  contentSearch = false,
}: {
  mode: "traces" | "logs";
  channels: ChannelRecord[];
  turns: ClientTurn[];
  selectedChannel: string;
  onChannel: (channel: string) => void;
  query: string;
  onQuery: (query: string) => void;
  selectedTurn?: ClientTurn;
  session: Session;
  onOpen: (turn: ClientTurn) => void;
  onClose: () => void;
  searchMatches?: TraceSearchMatch[];
  searching?: boolean;
  searched?: boolean;
  scanned?: number;
  failed?: number;
  searchError?: string;
  contentSearch?: boolean;
}) {
  const needle = query.trim().toLowerCase();
  const filtered = turns.filter((turn) => {
    if (turn.channel !== selectedChannel) return false;
    if (contentSearch) return true;
    if (!needle) return true;
    return `${turn.user_name} ${turn.user_id} ${turn.trace_id} ${turn.message_id} ${turn.device_id}`
      .toLowerCase()
      .includes(needle);
  });
  return (
    <div className={`explorer-shell ${mode}`}>
      <aside
        className="explorer-list"
        aria-label={mode === "logs" ? "日志来源" : "Trace 结果"}
      >
        <header>
          <div>
            <p className="eyebrow">
              {mode === "logs" ? "LOG SOURCES" : "TRACE RESULTS"}
            </p>
            <h2>
              {searching
                ? "正在检索…"
                : mode === "logs" && query.trim()
                  ? `${filtered.length} 个匹配`
                  : mode === "logs"
                    ? "选择一条 Trace"
                    : `${filtered.length} 条 Trace`}
            </h2>
          </div>
          <label className="search explorer-search">
            <Search size={15} />
            <input
              value={query}
              onChange={(event) => onQuery(event.target.value)}
              placeholder={
                mode === "logs"
                  ? "搜索用户 query、事件或字段"
                  : "用户、Trace、设备"
              }
              aria-label="搜索 Trace"
            />
          </label>
        </header>
        <div className="explorer-filters" aria-label="渠道筛选">
          {channels.map((channel) => (
            <button
              key={channel.channel}
              className={selectedChannel === channel.channel ? "active" : ""}
              onClick={() => onChannel(channel.channel)}
            >
              {channelNames[channel.channel] || channel.channel}
              <span>{channel.turns}</span>
            </button>
          ))}
        </div>
        {mode === "logs" && query.trim() && !searching && (
          <p className="explorer-scope">
            检索 {scanned} 条已索引 Turn
            {failed ? `，其中 ${failed} 条暂时无法读取` : ""}
          </p>
        )}
        <div className="explorer-column-head">
          <span>Trace / 用户</span>
          <span>耗时</span>
          <span>结果</span>
        </div>
        {searchError && (
          <p className="feedback error explorer-error">{searchError}</p>
        )}
        <div className="explorer-rows">
          {filtered.map((turn) => {
            const active =
              selectedTurn?.user_id === turn.user_id &&
              selectedTurn.trace_id === turn.trace_id;
            const contentMatch = searchMatches.find(
              (match) =>
                match.user_id === turn.user_id &&
                match.trace_id === turn.trace_id,
            );
            return (
              <a
                key={`${turn.user_id}-${turn.message_id}`}
                className={`explorer-row ${active ? "active" : ""}`}
                href={`#/monitoring/${mode === "logs" ? "logs" : "traces"}/${encodeURIComponent(turn.trace_id)}?user=${encodeURIComponent(turn.user_id)}`}
                onClick={() => onOpen(turn)}
              >
                <span className="trace-main">
                  <strong>{turn.user_name || "未命名用户"}</strong>
                  <code>{turn.trace_id.slice(0, 12)}</code>
                  <small>
                    {new Date(turn.received_at * 1000).toLocaleTimeString(
                      "zh-CN",
                      { hour12: false },
                    )}{" "}
                    · {turn.device_id || turn.client_id || "unknown"}
                  </small>
                  {contentMatch?.matches[0] && (
                    <small className="explorer-match">
                      {contentMatch.matches[0].event_name}:{" "}
                      <MatchSnippet
                        text={contentMatch.matches[0].snippet}
                        query={query.trim()}
                      />
                    </small>
                  )}
                </span>
                <span className="trace-duration">
                  {turn.completed_ms
                    ? latency(turn.completed_ms)
                    : turn.accepted_ms
                      ? `${latency(turn.accepted_ms)} ACK`
                      : "—"}
                </span>
                <span className={`turn-outcome ${turn.outcome}`}>
                  {outcomeNames[turn.outcome] || turn.outcome}
                </span>
              </a>
            );
          })}
          {!filtered.length && (
            <p className="empty">
              {searching
                ? "正在检索最近 Trace 的关联事件…"
                : mode === "logs" && query.trim() && searched
                  ? "所选时间和渠道内没有匹配事件。消息接收和 ACK 会独立记录，Trace 随执行补充。"
                  : "没有匹配的 Trace。"}
            </p>
          )}
        </div>
      </aside>
      <section className="explorer-detail" aria-label="Trace 详情">
        {selectedTurn ? (
          <TracePanel
            turn={selectedTurn}
            session={session}
            initialTab={mode === "logs" ? "logs" : "spans"}
            embedded
            onClose={onClose}
            highlightQuery={mode === "logs" ? query.trim() : ""}
          />
        ) : (
          <div className="explorer-empty">
            {mode === "logs" ? (
              <ScrollText size={28} />
            ) : (
              <Workflow size={28} />
            )}
            <h2>
              {mode === "logs" ? "选择 Trace 查看事件" : "选择 Trace 查看链路"}
            </h2>
            <p>
              从左侧选择一条样本。查询条件会同时作用于用户、Trace ID 和设备。
            </p>
          </div>
        )}
      </section>
    </div>
  );
}

const diagnosticRules = [
  {
    condition: "无 telemetry 样本，消息仍显示已送达",
    owner: "客户端上报",
    action: "检查 telemetry 上传、30 秒 stalled 定时器和登录状态。",
  },
  {
    condition: "stalled 且 accepted_ms = NULL",
    owner: "Gateway / 连接",
    action: "检查 WebSocket、鉴权、Origin、命令校验和 queue.add。",
  },
  {
    condition: "stalled 且 accepted_ms ≠ NULL，first_response_ms = NULL",
    owner: "队列 / Worker / 模型",
    action: "打开 Trace，依次看 queue.*、invoke_agent 和 chat。",
  },
  {
    condition: "Trace 有 chat，但客户端无 delta",
    owner: "投递 / 客户端连接",
    action: "检查 Outbox、WebSocket send、客户端重连与事件 cursor。",
  },
  {
    condition: "所有渠道同时无响应",
    owner: "共享依赖",
    action: "检查 Oath 服务、RPC 错误率、RabbitMQ ready 和模型 TTFT。",
  },
] as const;

function RunbookPage({
  stalledTurns,
  onInspect,
}: {
  stalledTurns: ClientTurn[];
  onInspect: (turn: ClientTurn) => void;
}) {
  return (
    <div className="runbook-page">
      <section className="runbook-intro">
        <div>
          <p className="eyebrow">ON-CALL RUNBOOK</p>
          <h2>从客户端 ACK 到 Step 终态</h2>
          <p>
            以消息和 trace_id
            为主键，从客户端准入一路检查到投递。每一条判断都有明确证据和下一步。
          </p>
        </div>
        {stalledTurns[0] && (
          <button
            className="primary"
            onClick={() => onInspect(stalledTurns[0])}
          >
            打开最近无响应 Trace <ArrowRight size={15} />
          </button>
        )}
      </section>
      <div className="runbook-layout">
        <aside className="runbook-gates">
          <p className="eyebrow">REQUEST LIFECYCLE</p>
          {[
            ["01", "发送", "client.command.start"],
            ["02", "服务端准入", "ack / accepted_ms"],
            ["03", "调度", "queue → claim"],
            ["04", "模型", "first_response_ms"],
            ["05", "投递", "first_renderable_ms"],
            ["06", "终态", "step.status"],
          ].map(([number, label, field]) => (
            <div key={number}>
              <span>{number}</span>
              <strong>{label}</strong>
              <code>{field}</code>
            </div>
          ))}
        </aside>
        <section className="runbook-rules">
          <header>
            <div>
              <p className="eyebrow">DECISION TABLE</p>
              <h3>现象 → 责任边界 → 下一步</h3>
            </div>
          </header>
          <div className="runbook-rule-table">
            <div className="runbook-rule head">
              <span>判断条件</span>
              <span>优先检查</span>
              <span>动作</span>
            </div>
            {diagnosticRules.map((rule) => (
              <div className="runbook-rule" key={rule.condition}>
                <span>{rule.condition}</span>
                <strong>{rule.owner}</strong>
                <p>{rule.action}</p>
              </div>
            ))}
          </div>
        </section>
      </div>
      <section className="runbook-checklist">
        <header>
          <div>
            <p className="eyebrow">OPERATOR CHECKLIST</p>
            <h3>人工排查顺序</h3>
          </div>
          <span>保留 trace_id 与时间窗</span>
        </header>
        <ol>
          {sopSteps.map((step, index) => (
            <li key={step.title}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <div>
                <strong>{step.title}</strong>
                <p>{step.action}</p>
                <code>{step.evidence}</code>
              </div>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}

function spanDetail(attributes: Record<string, unknown>) {
  const values: string[] = [];
  for (const key of [
    ["oath.llm.ttft_ms", "TTFT"],
    ["oath.llm.first_content_ms", "首正文"],
    ["oath.input.queue_to_claim_ms", "入队到认领"],
    ["oath.tool.outcome", "结果"],
  ] as const) {
    const value = attributes[key[0]];
    if (value !== undefined && value !== null)
      values.push(
        `${key[1]} ${key[0].endsWith("_ms") ? latency(Number(value)) : String(value)}`,
      );
  }
  return values.join(" · ");
}

function parsedBody(attributes: Record<string, unknown>) {
  const body = attributes.body;
  if (typeof body !== "string") return body;
  try {
    return JSON.parse(body);
  } catch {
    return body;
  }
}

function compactValue(value: unknown) {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean")
    return String(value);
  return JSON.stringify(value);
}

function modelBadges(attributes: Record<string, unknown>) {
  const badges: string[] = [];
  const model = attributes["gen_ai.request.model"];
  if (typeof model === "string") badges.push(model);
  const input = attributes["gen_ai.usage.input_tokens"];
  const output = attributes["gen_ai.usage.output_tokens"];
  if (typeof input === "number") badges.push(`输入 ${input} tokens`);
  if (typeof output === "number") badges.push(`输出 ${output} tokens`);
  if (typeof attributes["oath.llm.ttft_ms"] === "number")
    badges.push(`TTFT ${latency(Number(attributes["oath.llm.ttft_ms"]))}`);
  return badges;
}

function TraceEventLog({
  spans,
  initialQuery = "",
}: {
  spans: TraceNode[];
  initialQuery?: string;
}) {
  const [query, setQuery] = useState(initialQuery);
  useEffect(() => {
    setQuery(initialQuery);
  }, [initialQuery]);
  const events = spans
    .flatMap((span) =>
      span.events.map((event) => ({
        ...event,
        span_name: span.name,
        span_status: span.status,
      })),
    )
    .sort((a, b) => a.unix_nano - b.unix_nano);
  const needle = query.trim().toLowerCase();
  const visible = events.filter((event) => {
    if (!needle) return true;
    return `${event.span_name} ${event.name} ${JSON.stringify(event.attributes)}`
      .toLowerCase()
      .includes(needle);
  });
  return (
    <section className="trace-log-center" aria-label="Trace 关联事件日志">
      <header>
        <div>
          <p className="eyebrow">BUSINESS EVENTS</p>
          <h3>业务事件日志</h3>
          <p>
            按 trace_id 汇总 Oath
            业务事件与模型事件，包括用户输入、阶段和工具结果。
          </p>
        </div>
        <label className="search trace-log-search">
          <Search size={14} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="过滤事件或字段"
            aria-label="过滤 Trace 事件日志"
          />
        </label>
      </header>
      <div className="trace-log-list">
        {visible.map((event, index) => (
          <details
            key={`${event.span_name}-${event.name}-${event.unix_nano}`}
            className={event.span_status === "error" ? "error" : ""}
            open={index === 0 && Boolean(needle)}
          >
            <summary>
              <span className="log-severity">
                {event.span_status === "error" ? "ERR" : "EVT"}
              </span>
              <div>
                <strong>{event.name}</strong>
                <small>{event.span_name}</small>
              </div>
              <time>
                {new Date(event.unix_nano / 1_000_000).toLocaleTimeString(
                  "zh-CN",
                  {
                    hour12: false,
                    hour: "2-digit",
                    minute: "2-digit",
                    second: "2-digit",
                  },
                )}
              </time>
              <ChevronDown size={14} />
            </summary>
            <pre>{JSON.stringify(parsedBody(event.attributes), null, 2)}</pre>
          </details>
        ))}
        {!visible.length && <p className="empty">没有匹配的事件。</p>}
      </div>
    </section>
  );
}

function TracePanel({
  turn,
  session,
  onClose,
  initialTab = "spans",
  embedded = false,
  highlightQuery = "",
}: {
  turn: ClientTurn;
  session: Session;
  onClose: () => void;
  initialTab?: "spans" | "logs";
  embedded?: boolean;
  highlightQuery?: string;
}) {
  const [trace, setTrace] = useState<TraceDetail>();
  const [error, setError] = useState("");
  const [panelTab, setPanelTab] = useState<"spans" | "logs">(initialTab);
  useEffect(() => {
    let active = true;
    void adminRequest<TraceDetail>(
      `monitoring/trace?user_id=${encodeURIComponent(turn.user_id)}&trace_id=${encodeURIComponent(turn.trace_id)}`,
      { session },
    )
      .then((value) => {
        if (active) setTrace(value);
      })
      .catch((value: unknown) => {
        if (active)
          setError(value instanceof Error ? value.message : String(value));
      });
    return () => {
      active = false;
    };
  }, [session, turn.trace_id, turn.user_id]);
  const spans = [...(trace?.spans || [])].sort(
    (a, b) => a.start_unix_nano - b.start_unix_nano,
  );
  const start = spans.length
    ? Math.min(...spans.map((span) => span.start_unix_nano))
    : 0;
  const end = spans.length
    ? Math.max(
        ...spans.map((span) => span.end_unix_nano || span.start_unix_nano),
      )
    : 1;
  const total = Math.max(1, end - start);
  return (
    <aside
      className={embedded ? "trace-detail-pane" : "trace-drawer"}
      aria-label="Trace 明细"
    >
      <header>
        <div className="trace-heading">
          <p className="eyebrow">OPENTELEMETRY TRACE</p>
          <h2>{turn.user_name || "未命名用户"}</h2>
          <div className="trace-identity">
            <span>
              <UserRound size={12} /> {turn.user_id}
            </span>
            <span>{channelNames[turn.channel] || turn.channel}</span>
            <span>{turn.device_id || turn.client_id || "未绑定设备"}</span>
          </div>
          <code>{turn.trace_id}</code>
        </div>
        <button
          className="icon-button"
          onClick={onClose}
          aria-label="关闭 Trace"
        >
          <X size={17} />
        </button>
      </header>
      <div className="trace-summary">
        <span>端到端 {latency(turn.completed_ms || 0)}</span>
        <span>{turn.step_count ?? "—"} Steps</span>
        <span>{turn.tool_calls ?? "—"} 工具</span>
        <span>{trace?.spans.length ?? "—"} Spans</span>
      </div>
      <div className="trace-mode-tabs" role="tablist" aria-label="Trace 视图">
        <button
          role="tab"
          aria-selected={panelTab === "spans"}
          className={panelTab === "spans" ? "active" : ""}
          onClick={() => setPanelTab("spans")}
        >
          <Workflow size={14} /> 链路
        </button>
        <button
          role="tab"
          aria-selected={panelTab === "logs"}
          className={panelTab === "logs" ? "active" : ""}
          onClick={() => setPanelTab("logs")}
        >
          <ScrollText size={14} /> 事件日志
        </button>
      </div>
      {error && <p className="feedback error">{error}</p>}
      {!trace && !error && <p className="empty">正在读取服务端 span…</p>}
      {panelTab === "spans" && (
        <>
          <p className="trace-help">
            横条表示节点在整条 Trace 中的实际起止位置；展开节点可查看 OTel
            attributes、原始模型请求与响应。
          </p>
          <div className="trace-nodes waterfall">
            {spans.map((span) => {
              const offset = ((span.start_unix_nano - start) / total) * 100;
              const width = Math.max(
                0.8,
                (((span.end_unix_nano || span.start_unix_nano) -
                  span.start_unix_nano) /
                  total) *
                  100,
              );
              const detail = spanDetail(span.attributes);
              const badges = modelBadges(span.attributes);
              return (
                <details
                  className={span.parent_span_id ? "child" : ""}
                  key={`${span.span_id}-${span.start_unix_nano}`}
                >
                  <summary>
                    <div>
                      <span className={`span-status ${span.status}`}>
                        {span.status === "error" ? (
                          <AlertTriangle size={12} />
                        ) : span.status === "ok" ? (
                          <CheckCircle2 size={12} />
                        ) : (
                          <Radio size={12} />
                        )}
                        {span.name}
                      </span>
                      <b>{latency(span.duration_ms || undefined)}</b>
                      <ChevronDown size={14} />
                    </div>
                    <div className="waterfall-track">
                      <i style={{ left: `${offset}%`, width: `${width}%` }} />
                    </div>
                    {(detail || badges.length > 0) && (
                      <div className="span-tags">
                        {badges.map((badge) => (
                          <span key={badge}>{badge}</span>
                        ))}
                        {detail && <small>{detail}</small>}
                      </div>
                    )}
                  </summary>
                  <div className="otel-detail">
                    <div className="otel-context">
                      <span>span_id {span.span_id}</span>
                      <span>parent {span.parent_span_id || "root"}</span>
                      <span>kind {span.kind}</span>
                      <span>status {span.status}</span>
                      <span>
                        {new Date(
                          span.start_unix_nano / 1_000_000,
                        ).toLocaleString("zh-CN")}
                      </span>
                    </div>
                    <h4>
                      <Code2 size={14} /> OTel attributes
                    </h4>
                    <dl className="otel-attributes">
                      {Object.entries(span.attributes).map(([key, value]) => (
                        <div key={key}>
                          <dt>{key}</dt>
                          <dd>{compactValue(value)}</dd>
                        </div>
                      ))}
                    </dl>
                    {span.events.length > 0 && (
                      <div className="otel-events">
                        <h4>Span events</h4>
                        {span.events.map((event) => (
                          <details key={`${event.name}-${event.unix_nano}`}>
                            <summary>
                              <span>{event.name}</span>
                              <small>
                                {new Date(
                                  event.unix_nano / 1_000_000,
                                ).toLocaleTimeString("zh-CN")}
                              </small>
                              <ChevronDown size={13} />
                            </summary>
                            <pre>
                              {JSON.stringify(
                                parsedBody(event.attributes),
                                null,
                                2,
                              )}
                            </pre>
                          </details>
                        ))}
                      </div>
                    )}
                  </div>
                </details>
              );
            })}
          </div>
        </>
      )}
      {panelTab === "logs" && trace && (
        <TraceEventLog spans={spans} initialQuery={highlightQuery} />
      )}
    </aside>
  );
}

function traceKey() {
  const match = /^#\/monitoring\/(?:traces|trace|logs)\/([^?]+)/.exec(
    window.location.hash,
  );
  if (!match) return "";
  const query = window.location.hash.split("?", 2)[1] || "";
  const user = new URLSearchParams(query).get("user") || "";
  return `${user}|${decodeURIComponent(match[1])}`;
}

function monitoringPage(): "overview" | "traces" | "logs" | "runbook" {
  const hash = window.location.hash;
  if (hash.startsWith("#/monitoring/logs")) return "logs";
  if (hash.startsWith("#/monitoring/runbook")) return "runbook";
  if (
    hash.startsWith("#/monitoring/traces") ||
    hash.startsWith("#/monitoring/trace/")
  )
    return "traces";
  return "overview";
}

const sopSteps = [
  {
    title: "固定消息身份",
    evidence: "user_id / message_id / trace_id / channel / device_id",
    action:
      "先按用户或 Trace 定位具体 turn。没有 trace_id 时，只能用客户端样本判断是否 ACK、是否收到首个 delta。",
  },
  {
    title: "检查客户端准入",
    evidence: "accepted_ms, outcome=stalled, no_ack",
    action:
      "accepted_ms = NULL 且已超过 30 秒：命令没有收到 ACK。检查 WebSocket、登录有效期、来源 Origin 与 Gateway 命令校验。",
  },
  {
    title: "检查服务端推进",
    evidence: "queue.publish → queue.consume → invoke_agent → chat",
    action:
      "已 ACK 但 first_response_ms = NULL：打开 Trace。队列节点缺失看 broker/outbox；invoke_agent 前有长空档看 Worker claim；chat 很长看 Provider TTFT 和模型限流。",
  },
  {
    title: "检查工具与投递",
    evidence: "execute_tool, approval, Outbox → WebSocket",
    action:
      "模型已返回但页面不动：比较首个正文与首响应，检查工具终态和 Outbox 投递。服务端 trace 已完成但客户端无 delta，优先排查 Gateway 投递与客户端连接。",
  },
  {
    title: "判断影响面并处置",
    evidence: "channel tabs, RPC error, queue depth, model TTFT",
    action:
      "单 channel 异常先查该端网络/设备；所有 channel 同时异常再查全局依赖。保留 trace_id，修复后复测同 channel 并记录恢复时间。",
  },
] as const;

function MetricGuideModal({ onClose }: { onClose: () => void }) {
  const [active, setActive] = useState<string>(metricGuide[0].title);
  const closeButton = useRef<HTMLButtonElement>(null);
  const group =
    metricGuide.find((item) => item.title === active) || metricGuide[0];
  useEffect(() => {
    closeButton.current?.focus();
  }, []);
  useEffect(() => {
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [onClose]);
  return (
    <div
      className="modal-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        className="metric-guide-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="metric-guide-title"
      >
        <header>
          <div>
            <p className="eyebrow">METRIC GUIDE</p>
            <h2 id="metric-guide-title">指标说明</h2>
            <p>
              定义、样本集合、时间边界与统计口径；公式中的下标表示单个 turn。
            </p>
          </div>
          <button
            ref={closeButton}
            className="icon-button"
            onClick={onClose}
            aria-label="关闭指标说明"
          >
            <X size={18} />
          </button>
        </header>
        <div className="guide-layout">
          <nav aria-label="指标分类">
            {metricGuide.map((item) => (
              <button
                key={item.title}
                className={active === item.title ? "active" : ""}
                aria-pressed={active === item.title}
                onClick={() => setActive(item.title)}
              >
                <span>{item.title}</span>
                <small>{item.items.length} 项</small>
              </button>
            ))}
          </nav>
          <article>
            <h3>{group.title}</h3>
            <p>{group.summary}</p>
            <div className="metric-notation">
              <span>符号</span>
              <code>{group.notation}</code>
            </div>
            <dl className="metric-definitions">
              {group.items.map((item) => (
                <div key={item.name}>
                  <dt>{item.name}</dt>
                  <dd>
                    <code className="metric-formula">{item.formula}</code>
                    <p>{item.definition}</p>
                  </dd>
                </div>
              ))}
            </dl>
          </article>
        </div>
        <footer>
          <span>客户端 Qₚ：h=(n−1)p，线性插值原始样本。</span>
          <span>服务端 Qₚ：histogram_quantile 对 le 桶插值。</span>
          <span>客户端 telemetry 不含 prompt、附件或模型输出。</span>
        </footer>
      </section>
    </div>
  );
}

export function Monitoring({ session }: { session: Session }) {
  const [page, setPage] = useState(monitoringPage);
  const [hours, setHours] = useState(24);
  const [selectedChannel, setSelectedChannel] = useState("web");
  const [data, setData] = useState<MonitoringOverview>();
  const [charts, setCharts] = useState<Record<string, PromSeries>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedTrace, setSelectedTrace] = useState(traceKey);
  const [guideOpen, setGuideOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [traceSearch, setTraceSearch] = useState<TraceSearchResponse>();
  const [searchingLogs, setSearchingLogs] = useState(false);
  const [searchError, setSearchError] = useState("");

  useEffect(() => {
    const route = () => {
      setPage(monitoringPage());
      setSelectedTrace(traceKey());
    };
    window.addEventListener("hashchange", route);
    return () => window.removeEventListener("hashchange", route);
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const overview = await adminRequest<MonitoringOverview>(
        `monitoring/overview?hours=${hours}`,
        { session },
      );
      setData(overview);
      setError("");
      const loaded = await Promise.all(
        chartDefinitions.map(({ name }) =>
          adminRequest<PromSeries>(
            `monitoring/series?name=${name}&hours=${Math.min(hours, 24)}`,
            { session },
          ),
        ),
      );
      setCharts(Object.fromEntries(loaded.map((item) => [item.name, item])));
    } catch (value) {
      setError(value instanceof Error ? value.message : String(value));
    } finally {
      setLoading(false);
    }
  }, [hours, session]);

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), 20_000);
    return () => clearInterval(timer);
  }, [load]);

  useEffect(() => {
    const needle = query.trim();
    if (page !== "logs" || !needle) {
      setTraceSearch(undefined);
      setSearchingLogs(false);
      setSearchError("");
      return;
    }
    let active = true;
    setTraceSearch(undefined);
    setSearchingLogs(true);
    setSearchError("");
    const timer = setTimeout(() => {
      void adminRequest<TraceSearchResponse>(
        `monitoring/search?q=${encodeURIComponent(needle)}&hours=${hours}&channel=${encodeURIComponent(selectedChannel)}`,
        { session },
      )
        .then((value) => {
          if (active) setTraceSearch(value);
        })
        .catch((value: unknown) => {
          if (active)
            setSearchError(
              value instanceof Error ? value.message : String(value),
            );
        })
        .finally(() => {
          if (active) setSearchingLogs(false);
        });
    }, 350);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [hours, page, query, selectedChannel, session]);

  useEffect(() => {
    const available = data?.client.channels || [];
    if (!available.length) return;
    if (!available.some((item) => item.channel === selectedChannel))
      setSelectedChannel(available[0].channel);
  }, [data, selectedChannel]);

  const active = data?.prometheus.active || [];
  const services = latest(data, "services_up");
  const errorRate = latest(data, "rpc_error_rate");
  const ttft = latest(data, "llm_ttft_p95");
  const rabbit = latest(data, "rabbit_ready");
  const channels = data?.client.channels || [];
  const channelMap = new Map(channels.map((item) => [item.channel, item]));
  const selectedChannelData = channelMap.get(selectedChannel);
  const recentTurns = (data?.client.recent || []).map((turn) => ({
    ...turn,
    trace_id: turn.trace_id || `message:${turn.message_id}`,
  }));
  const stalledTurns = recentTurns.filter((turn) => turn.outcome === "stalled");
  const totalTurns = channels.reduce((sum, item) => sum + item.turns, 0) || 0;
  const failures = channels.reduce((sum, item) => sum + item.failed, 0) || 0;
  const completed =
    channels.reduce((sum, item) => sum + item.completed, 0) || 0;
  const completionRate = totalTurns ? completed / totalTurns : undefined;
  const stalled =
    channels.reduce(
      (sum, item) => sum + (item.stalled || item.outcomes?.stalled || 0),
      0,
    ) || 0;
  const noAck =
    channels.reduce((sum, item) => sum + (item.no_ack || 0), 0) || 0;
  const noDelta =
    channels.reduce((sum, item) => sum + (item.no_delta || 0), 0) || 0;
  const failureRate = totalTurns ? failures / totalTurns : undefined;
  const clientP95 = Math.max(
    0,
    ...channels.map((item) => item.latency.first_response_ms?.["95"] || 0),
  );
  const explorerTurns =
    page === "logs" && query.trim() ? traceSearch?.traces || [] : recentTurns;
  const selectedTurn = [...(traceSearch?.traces || []), ...recentTurns].find(
    (turn) => `${turn.user_id}|${turn.trace_id}` === selectedTrace,
  );
  return (
    <main className="workspace monitoring-workspace">
      <header className="topbar monitor-topbar">
        <div>
          <p className="eyebrow">OBSERVABILITY / {page.toUpperCase()}</p>
          <h1>
            {page === "overview"
              ? "观测概览"
              : page === "traces"
                ? "Trace 排查"
                : page === "logs"
                  ? "日志中心"
                  : "无回复排查"}
          </h1>
        </div>
        <div className="monitor-actions">
          {page !== "runbook" && (
            <select
              value={hours}
              onChange={(event) => setHours(Number(event.target.value))}
              aria-label="观测时间范围"
            >
              <option value={1}>最近 1 小时</option>
              <option value={6}>最近 6 小时</option>
              <option value={24}>最近 24 小时</option>
              <option value={168}>最近 7 天</option>
            </select>
          )}
          {page === "overview" && (
            <button
              className="guide-trigger"
              onClick={() => {
                window.location.hash = "/monitoring";
                setSelectedTrace("");
                setGuideOpen(true);
              }}
            >
              <CircleHelp size={16} />
              指标说明
            </button>
          )}
          <button
            className="icon-button bordered"
            onClick={() => void load()}
            aria-label="刷新观测数据"
          >
            <RefreshCw size={17} className={loading ? "spin" : ""} />
          </button>
        </div>
      </header>

      {error && (
        <div className="feedback error">
          <AlertTriangle size={16} /> 观测数据暂时不可用：{error}
        </div>
      )}

      {page === "overview" && (
        <>
          <section className="overview-snapshot">
            <header>
              <div>
                <p className="eyebrow">OPERATIONAL SNAPSHOT</p>
                <h2>最近 {hours === 168 ? "7 天" : `${hours} 小时`}</h2>
                <p>
                  客户端样本与 Prometheus
                  服务指标同屏查看。所有数字保留原始时间窗和分母。
                </p>
              </div>
              <nav aria-label="观测快捷入口">
                <a className="primary" href="#/monitoring/traces">
                  <Workflow size={15} /> 调查 Trace
                </a>
                <a className="quiet bordered-button" href="#/monitoring/logs">
                  <ScrollText size={15} /> 打开日志
                </a>
                <a
                  className="quiet bordered-button"
                  href="#/monitoring/runbook"
                >
                  <ListChecks size={15} /> 排查手册
                </a>
              </nav>
            </header>
            <dl className="overview-kpis">
              <div>
                <dt>请求</dt>
                <dd>{totalTurns}</dd>
                <span>有效客户端样本</span>
              </div>
              <div>
                <dt>完成率</dt>
                <dd>{latency(completionRate, "percent")}</dd>
                <span>{completed} completed</span>
              </div>
              <div className={stalled ? "attention" : ""}>
                <dt>无响应</dt>
                <dd>{stalled}</dd>
                <span>
                  {noAck} 未 ACK · {noDelta} 未 delta
                </span>
              </div>
              <div>
                <dt>首响应 P95</dt>
                <dd>{latency(clientP95 || undefined)}</dd>
                <span>阈值 15 s</span>
              </div>
              <div>
                <dt>服务与队列</dt>
                <dd>
                  {services ?? "—"}
                  <small>/ 9</small>
                </dd>
                <span>
                  RabbitMQ {latency(rabbit, "count")} · RPC{" "}
                  {latency(errorRate, "percent")}
                </span>
              </div>
            </dl>
          </section>

          <div className="overview-content">
            {active.length > 0 && (
              <section className="alert-stack" aria-label="活动告警">
                {active.map((item) => (
                  <article key={item.name} className={item.severity}>
                    <AlertTriangle size={17} />
                    <div>
                      <strong>{item.name}</strong>
                      <p>{item.summary}</p>
                    </div>
                    <span>
                      {item.state === "firing" ? "触发中" : "等待确认"}
                    </span>
                  </article>
                ))}
              </section>
            )}

            <section className="monitor-section">
              <header className="section-heading">
                <div>
                  <p className="eyebrow">GLOBAL METRICS</p>
                  <h2>服务端与依赖指标</h2>
                  <p>
                    覆盖服务延迟、队列、模型、工具与投递。图线来自 Prometheus
                    调用链指标，不混入客户端样本。
                  </p>
                </div>
                <span className="section-note">
                  服务端 P95 为有限桶插值；当前曲线使用进程启动以来累计 bucket
                </span>
              </header>
              <div className="chart-grid">
                {chartDefinitions.map((definition) => (
                  <article className="panel chart-card" key={definition.name}>
                    <header>
                      <div>
                        <h3>{definition.title}</h3>
                        <p>{definition.question}</p>
                      </div>
                      <BarChart3 size={18} />
                    </header>
                    <LineChart
                      definition={definition}
                      series={charts[definition.name]}
                    />
                  </article>
                ))}
              </div>
            </section>

            <section className="panel channel-panel">
              <header className="panel-head">
                <div>
                  <p className="eyebrow">CLIENT EXPERIENCE</p>
                  <h2>
                    <Activity size={18} /> 分渠道诊断
                  </h2>
                  <p>
                    切换渠道查看样本量、阶段分位数、P95
                    分段、结果分布和设备归因。
                  </p>
                </div>
                <div className="channel-head-actions">
                  {data?.grafana_url && (
                    <a
                      className="quiet link-button"
                      href={data.grafana_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Grafana <ExternalLink size={14} />
                    </a>
                  )}
                </div>
              </header>
              <div
                className="channel-tabs"
                role="tablist"
                aria-label="客户端渠道"
              >
                {[...channels]
                  .sort(
                    (a, b) =>
                      Object.keys(channelNames).indexOf(a.channel) -
                      Object.keys(channelNames).indexOf(b.channel),
                  )
                  .map((channel) => {
                    const key = channel.channel;
                    const label = channelNames[key] || key;
                    return (
                      <button
                        key={key}
                        role="tab"
                        aria-selected={selectedChannel === key}
                        className={selectedChannel === key ? "active" : ""}
                        onClick={() => setSelectedChannel(key)}
                      >
                        {key === "ios" ? (
                          <Smartphone size={15} />
                        ) : (
                          <Monitor size={15} />
                        )}
                        <span>{label}</span>
                        <small>{channel.turns}</small>
                      </button>
                    );
                  })}
              </div>
              {selectedChannelData ? (
                <ChannelWorkspace
                  channel={selectedChannelData}
                  turns={recentTurns}
                />
              ) : (
                <div className="empty-state channel-empty">
                  <Radio size={24} />
                  <strong>{channelNames[selectedChannel]} 当前没有样本</strong>
                  <p>切换渠道，或在客户端发送一条消息后重新刷新。</p>
                </div>
              )}
            </section>
          </div>
        </>
      )}

      {(page === "traces" || page === "logs") && (
        <ExplorerPage
          mode={page}
          channels={channels}
          turns={explorerTurns}
          selectedChannel={selectedChannel}
          onChannel={setSelectedChannel}
          query={query}
          onQuery={setQuery}
          selectedTurn={selectedTurn}
          session={session}
          onOpen={(turn) => {
            setSelectedTrace(`${turn.user_id}|${turn.trace_id}`);
          }}
          onClose={() => {
            window.location.hash = `/monitoring/${page}`;
            setSelectedTrace("");
          }}
          searchMatches={traceSearch?.traces}
          searching={searchingLogs}
          searched={Boolean(traceSearch)}
          scanned={traceSearch?.scanned}
          failed={traceSearch?.failed}
          searchError={searchError}
          contentSearch={page === "logs" && Boolean(query.trim())}
        />
      )}

      {page === "runbook" && (
        <RunbookPage
          stalledTurns={stalledTurns}
          onInspect={(turn) => {
            window.location.hash = `/monitoring/traces/${encodeURIComponent(turn.trace_id)}?user=${encodeURIComponent(turn.user_id)}`;
            setSelectedTrace(`${turn.user_id}|${turn.trace_id}`);
          }}
        />
      )}

      {guideOpen && <MetricGuideModal onClose={() => setGuideOpen(false)} />}
    </main>
  );
}
