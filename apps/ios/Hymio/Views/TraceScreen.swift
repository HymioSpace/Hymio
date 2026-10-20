import SwiftUI

struct TraceScreen: View {
  @ObservedObject var account: AccountService
  @ObservedObject var client: AgentClient
  @State private var traces: [JSON] = []
  @State private var loading = false
  @State private var failure = ""
  var body: some View {
    List {
      Section {
        HStack(spacing: 18) {
          Label("消息", systemImage: "antenna.radiowaves.left.and.right")
          Image(systemName: "arrow.right").foregroundStyle(.tertiary)
          Label("Agent", systemImage: "brain")
          Image(systemName: "arrow.right").foregroundStyle(.tertiary)
          Image(systemName: "terminal")
        }.font(.caption).foregroundStyle(.secondary).padding(.vertical, 12)
        Label(client.phase, systemImage: client.connected ? "checkmark.circle" : "wifi.slash")
          .font(.caption).foregroundStyle(.secondary)
      } header: {
        Text("执行链路")
      }
      Section {
        if loading { ProgressView("正在读取执行记录…") }
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
          Text("开始对话后，执行记录会出现在这里。").foregroundStyle(.secondary)
        }
      } header: {
        Text("执行记录 · \(traces.count)")
      }
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
    .navigationTitle("工作观察").navigationBarTitleDisplayMode(.inline)
    .toolbar {
      ToolbarItem(placement: .topBarTrailing) {
        Button {
          Task { await load() }
        } label: {
          Image(systemName: "arrow.clockwise")
        }.disabled(loading).accessibilityLabel("刷新执行记录")
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
      var result: [JSON] = []
      var seen: Set<String> = []
      var offset = 0
      while !Task.isCancelled {
        let page = try await account.request("oath-biz/list_traces?limit=100&offset=\(offset)")
        let items = page["trace_ids"].items
        let before = result.count
        for trace in items where seen.insert(trace["trace_id"].text).inserted {
          result.append(trace)
        }
        if !Task.isCancelled { traces = result }
        offset += items.count
        if items.isEmpty || result.count == before
          || (page["total"] != .null ? offset >= page["total"].int : items.count < 100)
        {
          break
        }
      }
      if !Task.isCancelled { traces = result }
    } catch { if !Task.isCancelled { failure = "执行记录读取失败，请重试。" } }
  }
}
struct TraceRecordScreen: View {
  let traceID: String
  @ObservedObject var account: AccountService
  @State private var trace: JSON = .null
  @State private var error = ""
  var body: some View {
    List {
      Section { Text(traceID).font(.system(.caption, design: .monospaced)).textSelection(.enabled) }
      if trace == .null && error.isEmpty { ProgressView("正在读取…") }
      if !error.isEmpty {
        Text(error)
        Button("重试") { Task { await load() } }
      }
      ForEach(Array(trace["spans"].items.enumerated()), id: \.offset) { _, span in
        Section {
          HStack {
            Label(span["name"].text, systemImage: "circle.dotted")
            Spacer()
            Text(String(format: "%.0fms", span["duration_ms"].double)).monospacedDigit()
          }.font(.caption)
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
          DisclosureGroup("原始数据") { TraceJsonTree(value: span) }
        }
      }
    }.navigationTitle("Trace 详情").navigationBarTitleDisplayMode(.inline).task { await load() }
  }
  @MainActor private func load() async {
    error = ""
    do {
      trace = try await account.request(
        "oath-biz/query_trace?trace_id=\(traceID.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? "")"
      )
    } catch { self.error = "详情读取失败，请重试。" }
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
