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
        Section("已同步事件") {
          ForEach(client.state.events.reversed()) { event in
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
struct TraceRecordScreen: View {
  let traceID: String
  var agentID: String = ""
  @ObservedObject var account: AccountService
  @State private var trace: JSON = .null
  @State private var fullTrace: JSON = .null
  @State private var error = ""
  @State private var fullError = ""
  @State private var loadingFull = false
  var body: some View {
    let display = fullTrace == .null ? trace : fullTrace
    List {
      Section { Text(traceID).font(.system(.caption, design: .monospaced)).textSelection(.enabled) }
      if trace == .null && error.isEmpty { ProgressView("正在读取…") }
      if !error.isEmpty {
        Text(error)
        Button("重试") { Task { await load() } }
      }
      if trace != .null {
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
          } else {
            Label("已加载完整事件与属性", systemImage: "checkmark.circle")
              .foregroundStyle(.secondary)
          }
          if !fullError.isEmpty { Text(fullError).foregroundStyle(.secondary) }
        } footer: {
          Text("快速视图先返回节点、状态、耗时和事件名称；原始请求与响应按需加载。")
        }
      }
      ForEach(Array(display["spans"].items.enumerated()), id: \.offset) { _, span in
        Section {
          HStack {
            Label(span["name"].text, systemImage: "circle.dotted")
            Spacer()
            Text(String(format: "%.0fms", span["duration_ms"].double)).monospacedDigit()
          }.font(.caption)
          if !span["events"].items.isEmpty {
            Text("\(span["events"].items.count) 个链路事件")
              .font(.caption2).foregroundStyle(.secondary)
          }
          if case .object(let attributes) = span["attributes"] {
            ForEach(
              attributes.keys.filter {
                $0.contains("ttft") || $0.contains("tpot") || $0.contains("tokens")
                  || $0.contains("first_content")
              }.sorted(), id: \.self
            ) { key in
              LabeledContent(key, value: attributes[key]?.pretty ?? "—").font(.caption)
            }
          }
          if fullTrace != .null {
            DisclosureGroup("原始数据") { TraceJsonTree(value: span) }
          }
        }
      }
    }.navigationTitle("Trace 详情").navigationBarTitleDisplayMode(.inline).task { await load() }
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
