import SwiftUI

struct TraceScreen: View {
  @ObservedObject var account: AccountService
  @ObservedObject var client: AgentClient
  @State private var traces: [JSON] = []
  @State private var loading = false
  @State private var loadingMore = false
  @State private var failure = ""
  @State private var total = 0
  var body: some View {
    List {
      Section {
        if loading { ProgressView("正在读取探索记录…") }
        if !failure.isEmpty {
          Text(failure).font(.footnote)
          Button("重试") { Task { await load() } }
        }
        ForEach(traces, id: \.self) { trace in
          NavigationLink {
            TraceRecordScreen(traceID: trace["trace_id"].text, account: account)
          } label: {
            VStack(alignment: .leading, spacing: 8) {
              Text(String(trace["trace_id"].text.prefix(16))).font(
                .system(.caption, design: .monospaced)
              ).foregroundStyle(.secondary)
              HStack {
                Label(
                  "\(trace["step_count"].int) steps",
                  systemImage: "point.3.connected.trianglepath.dotted")
                Spacer()
                Text(
                  trace["duration_ms"] == .null
                    ? "—" : String(format: "%.1fs", trace["duration_ms"].double / 1000))
              }.font(.subheadline)
            }.padding(.vertical, 6)
          }
        }
        if !loading && traces.isEmpty && failure.isEmpty {
          Text("开始对话后，探索记录会出现在这里。").foregroundStyle(.secondary)
        }
        if !traces.isEmpty && traces.count < total {
          Button {
            Task { await loadMore() }
          } label: {
            HStack {
              Spacer()
              if loadingMore { ProgressView().controlSize(.small) }
              Text(loadingMore ? "正在加载…" : "加载更多")
              Spacer()
            }
          }.disabled(loadingMore)
        }
      } header: {
        Text("探索记录 · \(traces.count)")
      }
      if !client.state.events.isEmpty {
        Section("已同步事件 · 按发生顺序") {
          ForEach(client.state.events) { event in
            DisclosureGroup {
              TraceJsonTree(value: event.payload)
            } label: {
              HStack {
                Text("#\(event.event_seq)").monospacedDigit().foregroundStyle(.secondary)
                Text(event.event_type).lineLimit(1)
              }.font(.caption)
            }
          }
        }
      }
    }
    .navigationTitle("探索记录").navigationBarTitleDisplayMode(.inline)
    .toolbar {
      ToolbarItem(placement: .topBarTrailing) {
        Button {
          Task { await load() }
        } label: {
          Image(systemName: "arrow.clockwise")
        }.disabled(loading).accessibilityLabel("刷新探索记录")
      }
    }
    .task { await load() }
    .refreshable { await load() }
  }
  @MainActor private func load() async {
    guard !loading else { return }
    loading = true
    failure = ""
    defer { loading = false }
    do {
      let page = try await account.request("oath-biz/list_traces?limit=30&offset=0")
      if !Task.isCancelled {
        traces = page["trace_ids"].items
        total = page["total"].int
      }
    } catch { if !Task.isCancelled { failure = "探索记录读取失败，请重试。" } }
  }

  @MainActor private func loadMore() async {
    guard !loadingMore else { return }
    loadingMore = true
    defer { loadingMore = false }
    do {
      let page = try await account.request(
        "oath-biz/list_traces?limit=30&offset=\(traces.count)")
      let existing = Set(traces.map { $0["trace_id"].text })
      let next = page["trace_ids"].items.filter {
        !existing.contains($0["trace_id"].text)
      }
      traces.append(contentsOf: next)
      total = page["total"].int
      if next.isEmpty { total = traces.count }
    } catch { client.error = "更多探索记录读取失败，请重试。" }
  }
}

private struct TraceTimelineEntry: Identifiable {
  let id: String
  let sequence: Int
  let at: Double
  let name: String
  let spanName: String
  let toolName: String
  let span: JSON
  let event: JSON?

  var kind: String {
    if name == "gen_ai.request" { return "request" }
    if name == "gen_ai.response" { return "response" }
    if name == "oath.tool.request" { return "tool-request" }
    if name == "oath.tool.response" { return "tool-response" }
    if name.hasPrefix("oath.input.") { return "input" }
    if name.hasPrefix("oath.stage.") { return "stage" }
    if name == "span" { return "span" }
    return "event"
  }

  var label: String {
    switch kind {
    case "request": return "LLM 请求"
    case "response": return "LLM 响应"
    case "tool-request": return "Tool 调用"
    case "tool-response": return "Tool 结果"
    case "input": return "用户事件"
    case "stage": return "执行阶段"
    case "span": return "执行步骤"
    default: return "事件"
    }
  }

  var symbol: String {
    switch kind {
    case "request", "response": return "brain"
    case "tool-request", "tool-response": return "wrench.and.screwdriver"
    case "input": return "message"
    case "stage": return "sparkles"
    default: return "clock"
    }
  }

  var color: Color {
    switch kind {
    case "request": return Brand.blue
    case "response": return .purple
    case "tool-request", "tool-response": return .teal
    case "input": return Brand.ink
    default: return Brand.muted
    }
  }

  var title: String {
    if !toolName.isEmpty {
      if kind == "tool-request" { return "\(toolName) 调用" }
      if kind == "tool-response" { return "\(toolName) 结果" }
    }
    if kind == "request" {
      let model = span["attributes"]["gen_ai.request.model"].text
      return model.isEmpty ? "模型请求" : "\(model) 请求"
    }
    if kind == "response" { return "模型响应" }
    if kind == "input" {
      let queue = String(name.split(separator: ".").last ?? "")
      let label = ["user": "用户", "tool": "工具", "system": "系统"][queue] ?? queue
      return "收到\(label)输入"
    }
    if kind == "stage" { return name.replacingOccurrences(of: "oath.stage.", with: "") }
    return spanName
  }

  var summary: String {
    guard let event else {
      let outcome = span["attributes"]["oath.tool.outcome"].text
      return outcome.isEmpty ? "查看原始事件" : "结果：\(outcome)"
    }
    let body = traceEventBody(event)
    if kind == "request" {
      let messages = body["messages"].items
      let user = messages.reversed().first { $0["role"].text == "user" }
      let text = user?["content"].text ?? ""
      return text.isEmpty ? "\(messages.count) 条输入消息" : String(text.prefix(220))
    }
    if kind == "response" {
      let content = body["content"].text
      let calls = body["tool_calls"].items.count
      return content.isEmpty
        ? (calls > 0 ? "返回 \(calls) 个工具调用" : "无正文") : String(content.prefix(220))
    }
    if kind == "tool-request" {
      let description = body["description"].text
      return description.isEmpty ? "调用 \(toolName)" : description
    }
    if kind == "tool-response" {
      let content = body["content"].text.isEmpty
        ? body["content"].pretty : body["content"].text
      return content.isEmpty ? body["error"].text : String(content.prefix(220))
    }
    return body["content"].text.isEmpty ? event["name"].text : body["content"].text
  }
}

private func traceTimeline(_ trace: JSON) -> [TraceTimelineEntry] {
  let values = trace["spans"].items.flatMap { span -> [(Double, String, JSON, JSON?)] in
    let events = span["events"].items
    if events.isEmpty {
      return [(span["start_unix_nano"].double, "span", span, nil)]
    }
    return events.map {
      ($0["unix_nano"].double, $0["name"].text, span, $0)
    }
  }.sorted { $0.0 < $1.0 }
  return values.enumerated().map { index, value in
    TraceTimelineEntry(
      id: "\(value.2["span_id"].text):\(value.1):\(index)",
      sequence: index + 1,
      at: value.0,
      name: value.1,
      spanName: value.2["name"].text,
      toolName: value.2["attributes"]["oath.tool.name"].text,
      span: value.2,
      event: value.3)
  }
}

private func traceEventBody(_ event: JSON) -> JSON {
  let raw = event["attributes"]["body"]
  guard case .string(let value) = raw,
    let data = value.data(using: .utf8),
    let parsed = try? JSONDecoder().decode(JSON.self, from: data)
  else { return raw }
  return parsed
}

private func traceOffset(_ nanoseconds: Double) -> String {
  let seconds = max(0, nanoseconds / 1_000_000_000)
  return seconds < 1
    ? String(format: "%.0f ms", seconds * 1000)
    : String(format: "%.2f s", seconds)
}

struct TraceRecordScreen: View {
  let traceID: String
  var agentID: String = ""
  @ObservedObject var account: AccountService
  @State private var trace: JSON = .null
  @State private var fullTrace: JSON = .null
  @State private var error = ""
  @State private var fullError = ""
  @State private var loadingFull = false
  init(
    traceID: String, agentID: String = "", account: AccountService, previewTrace: JSON? = nil
  ) {
    self.traceID = traceID
    self.agentID = agentID
    _account = ObservedObject(wrappedValue: account)
    _trace = State(initialValue: previewTrace ?? .null)
    _fullTrace = State(initialValue: previewTrace ?? .null)
  }
  var body: some View {
    let display = fullTrace == .null ? trace : fullTrace
    let timeline = traceTimeline(display)
    let firstAt = timeline.first?.at ?? 0
    List {
      Section { Text(traceID).font(.system(.caption, design: .monospaced)).textSelection(.enabled) }
      if trace == .null && error.isEmpty { ProgressView("正在读取…") }
      if !error.isEmpty {
        Text(error)
        Button("重试") { Task { await load() } }
      }
      if trace != .null {
        if fullTrace == .null || !fullError.isEmpty {
          Section {
            if fullTrace == .null {
              Button {
                Task { await loadFull() }
              } label: {
                HStack {
                  if loadingFull { ProgressView().controlSize(.small) }
                  Text(loadingFull ? "正在读取完整事件…" : "加载完整模型事件与属性")
                  Spacer()
                  Image(systemName: "arrow.down.circle")
                }
              }.disabled(loadingFull)
            }
            if !fullError.isEmpty { Text(fullError).foregroundStyle(.secondary) }
          } footer: {
            Text("先按真实发生顺序看用户输入、模型请求、工具调用和工具结果；原始 Span 树放在最后。")
          }
        }
        Section {
          HStack(spacing: 18) {
            Label("\(timeline.count) 个事件", systemImage: "list.number")
            Label(
              "\(timeline.filter { $0.name == "gen_ai.request" }.count) 次模型请求",
              systemImage: "brain")
            Label(
              "\(timeline.filter { $0.name == "oath.tool.request" }.count) 次工具调用",
              systemImage: "wrench.and.screwdriver")
          }.font(.caption)
        } header: {
          Text("执行摘要")
        }
        Section("事件顺序") {
          if timeline.isEmpty {
            Text("这条 Trace 暂时没有事件。").foregroundStyle(.secondary)
          }
          ForEach(timeline) { entry in
            DisclosureGroup {
              if let event = entry.event {
                TraceJsonTree(value: event)
              }
              if fullTrace != .null {
                DisclosureGroup("所属 Span") { TraceJsonTree(value: entry.span) }
              }
            } label: {
              HStack(alignment: .top, spacing: 10) {
                Text(String(format: "%02d", entry.sequence))
                  .font(.caption2.monospacedDigit()).foregroundStyle(.secondary)
                  .frame(width: 22)
                Image(systemName: entry.symbol)
                  .font(.caption.weight(.semibold))
                  .foregroundStyle(entry.color)
                  .frame(width: 18)
                VStack(alignment: .leading, spacing: 4) {
                  HStack {
                    Text(entry.label).font(.caption.weight(.semibold))
                    Spacer()
                    Text("+\(traceOffset(entry.at - firstAt))")
                      .font(.caption2.monospacedDigit()).foregroundStyle(.secondary)
                  }
                  Text(entry.title).font(.subheadline.weight(.medium))
                  Text(entry.summary).font(.caption).foregroundStyle(.secondary)
                    .lineLimit(3).lineSpacing(2)
                }
              }.padding(.vertical, 4)
            }
          }
        }
        Section("原始 Span 树") {
          DisclosureGroup("\(display["spans"].items.count) 个 Span") {
            ForEach(Array(display["spans"].items.enumerated()), id: \.offset) { _, span in
              DisclosureGroup {
                TraceJsonTree(value: span)
              } label: {
                HStack {
                  Label(span["name"].text, systemImage: "circle.dotted")
                  Spacer()
                  Text(
                    span["duration_ms"] == .null
                      ? "—" : String(format: "%.0fms", span["duration_ms"].double)
                  ).monospacedDigit()
                }.font(.caption)
              }
            }
          }
        }
      }
    }.navigationTitle("Trace 详情").navigationBarTitleDisplayMode(.inline)
      .task { if trace == .null { await load() } }
  }
  @MainActor private func load() async {
    error = ""
    do {
      trace = try await account.request(
        "oath-biz/query_trace?agent_id=\(agentID)&summary=1&trace_id=\(traceID.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? "")"
      )
    } catch { self.error = "详情读取失败，请重试。" }
  }
  @MainActor private func loadFull() async {
    guard !loadingFull else { return }
    loadingFull = true
    fullError = ""
    defer { loadingFull = false }
    do {
      fullTrace = try await account.request(
        "oath-biz/query_trace?agent_id=\(agentID)&trace_id=\(traceID.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? "")"
      )
    } catch { fullError = "完整数据读取失败，请重试。" }
  }
}
struct TraceJsonTree: View {
  let value: JSON
  var depth = 0
  var body: some View {
    Group {
      if depth > 8 {
        Text(value.pretty).textSelection(.enabled)
      } else if case .object(let object) = value {
        ForEach(object.keys.sorted(), id: \.self) { key in
          DisclosureGroup(key) { TraceJsonTree(value: object[key] ?? .null, depth: depth + 1) }
        }
      } else if case .array(let array) = value {
        ForEach(Array(array.enumerated()), id: \.offset) { index, item in
          DisclosureGroup("[\(index)]") { TraceJsonTree(value: item, depth: depth + 1) }
        }
      } else {
        Text(value.pretty).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
      }
    }.font(.system(.caption, design: .monospaced))
  }
}

#if DEBUG
struct TraceTimelinePreview: View {
  let account: AccountService
  private let trace: JSON = .object([
    "trace_id": .string("synthetic-event-ordered-trace"),
    "duration_ms": .number(4800),
    "spans": .array([
      .object([
        "trace_id": .string("synthetic-event-ordered-trace"),
        "span_id": .string("1111111111111111"),
        "parent_span_id": .null,
        "name": .string("chat synthetic-model"),
        "start_unix_nano": .number(1_000_000_000),
        "end_unix_nano": .number(4_000_000_000),
        "status": .string("ok"),
        "duration_ms": .number(3000),
        "attributes": .object([
          "gen_ai.operation.name": .string("chat"),
          "gen_ai.request.model": .string("synthetic-model"),
        ]),
        "events": .array([
          .object([
            "name": .string("oath.input.user"),
            "unix_nano": .number(900_000_000),
            "attributes": .object([
              "body": .string("{\"content\":\"Compare two sources\"}")
            ]),
          ]),
          .object([
            "name": .string("gen_ai.request"),
            "unix_nano": .number(1_100_000_000),
            "attributes": .object([
              "body": .string(
                "{\"messages\":[{\"role\":\"user\",\"content\":\"Compare two sources\"}]}")
            ]),
          ]),
          .object([
            "name": .string("gen_ai.response"),
            "unix_nano": .number(3_900_000_000),
            "attributes": .object([
              "body": .string(
                "{\"content\":\"\",\"tool_calls\":[{\"id\":\"call-1\",\"function\":{\"name\":\"browser\"}}]}")
            ]),
          ]),
        ]),
        "links": .array([]),
      ]),
      .object([
        "trace_id": .string("synthetic-event-ordered-trace"),
        "span_id": .string("2222222222222222"),
        "parent_span_id": .string("1111111111111111"),
        "name": .string("execute_tool browser"),
        "start_unix_nano": .number(4_050_000_000),
        "end_unix_nano": .number(5_800_000_000),
        "status": .string("ok"),
        "duration_ms": .number(1750),
        "attributes": .object([
          "oath.tool.name": .string("browser"),
          "oath.tool.outcome": .string("succeeded"),
        ]),
        "events": .array([
          .object([
            "name": .string("oath.tool.request"),
            "unix_nano": .number(4_050_000_000),
            "attributes": .object([
              "body": .string(
                "{\"description\":\"Read the comparison page\",\"url\":\"https://example.test\"}")
            ]),
          ]),
          .object([
            "name": .string("oath.tool.response"),
            "unix_nano": .number(5_800_000_000),
            "attributes": .object([
              "body": .string("{\"content\":{\"title\":\"Comparison result\"}}")
            ]),
          ]),
        ]),
        "links": .array([]),
      ]),
    ]),
  ])

  var body: some View {
    NavigationStack {
      TraceRecordScreen(
        traceID: "synthetic-event-ordered-trace", account: account, previewTrace: trace)
    }
  }
}
#endif
