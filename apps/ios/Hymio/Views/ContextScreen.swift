import SwiftUI

/// A user-facing view of the context Hymio has assembled, with each synthesized
/// statement still traceable to its source records.
struct ContextEntry: Identifiable, Hashable {
  enum Entity: String {
    case artifact
    case record
  }

  let id: String
  let entity: Entity
  let preview: String
  let sourceKind: String
  let namespace: String
  let createdAt: String
  let topics: [String]
  let referenceCount: Int
  let value: JSON

  var compositeID: String { "\(entity.rawValue):\(id)" }
  var isInsight: Bool { entity == .artifact }
  var sourceTitle: String {
    switch sourceKind {
    case "conversation": return "对话"
    case "connector": return namespace.isEmpty ? "连接服务" : connectorName(namespace)
    case "kit": return "应用"
    case "user": return "你留下的"
    default: return "其他来源"
    }
  }
  var sourceSymbol: String {
    switch sourceKind {
    case "conversation": return "bubble.left.and.bubble.right.fill"
    case "connector": return connectorSymbol(namespace)
    case "kit": return "square.grid.2x2.fill"
    case "user": return "bookmark.fill"
    default: return "doc.text.fill"
    }
  }
  var dateLabel: String {
    guard let date = contextDate(createdAt) else { return "" }
    return date.formatted(.dateTime.month(.abbreviated).day())
  }

  init(_ value: JSON) {
    self.value = value
    id = value["id"].text
    entity = value["kind"].text == "artifact" ? .artifact : .record
    preview = contextReadable(value["preview"].text)
    sourceKind = value["source"]["kind"].text.isEmpty ? "legacy" : value["source"]["kind"].text
    namespace = value["source"]["namespace"].text
    createdAt = value["created_at"].text
    topics = value["topics"].items.map(\.text).filter { !$0.isEmpty }
    referenceCount = value["references"].items.count
  }
}

@MainActor
final class ContextStore: ObservableObject {
  @Published private(set) var insights: [ContextEntry] = []
  @Published private(set) var records: [ContextEntry] = []
  @Published private(set) var loading = true
  @Published private(set) var error = ""
  @Published private(set) var feedback = ""
  @Published private(set) var imported = false
  @Published private(set) var refined = false
  @Published private(set) var busy = false
  @Published private(set) var moreBusy = false

  private let account: AccountService?
  private let preview: Bool
  private var details: [String: JSON] = [:]
  private(set) var insightCursor = ""
  private(set) var recordCursor = ""

  init(account: AccountService, preview: Bool = false) {
    self.account = account
    self.preview = preview
    if preview { installPreview() }
  }

  var isEmpty: Bool { insights.isEmpty && records.isEmpty }

  func load(showBusy: Bool = true) async {
    if preview {
      loading = false
      return
    }
    guard let account else { return }
    if showBusy && isEmpty { loading = true }
    error = ""
    do {
      async let artifactResult = account.request(
        "context/search",
        body: .object([
          "target": .string("artifacts"), "mode": .string("filter"), "query": .null,
          "filters": .object([:]), "limit": .number(30), "cursor": .null,
        ]))
      async let recordResult = account.request(
        "context/search",
        body: .object([
          "target": .string("records"), "mode": .string("filter"), "query": .null,
          "filters": .object([:]), "limit": .number(30), "cursor": .null,
        ]))
      let (artifactValue, recordValue) = try await (artifactResult, recordResult)
      insights = artifactValue["items"].items.map(ContextEntry.init).filter {
        !$0.id.hasPrefix("_")
      }
      records = recordValue["items"].items.map(ContextEntry.init).filter {
        !$0.id.hasPrefix("_")
      }
      insightCursor = artifactValue["next_cursor"].text
      recordCursor = recordValue["next_cursor"].text
    } catch is CancellationError {
      return
    } catch {
      self.error = "暂时没能接回 Hymio 对你的了解。"
    }
    loading = false
  }

  func loadMoreRecords() async {
    guard !moreBusy, !recordCursor.isEmpty, let account, !preview else { return }
    moreBusy = true
    defer { moreBusy = false }
    do {
      let value = try await account.request(
        "context/search",
        body: .object([
          "target": .string("records"), "mode": .string("filter"), "query": .null,
          "filters": .object([:]), "limit": .number(30), "cursor": .string(recordCursor),
        ]))
      let known = Set(records.map(\.compositeID))
      records += value["items"].items.map(ContextEntry.init).filter {
        !$0.id.hasPrefix("_") && !known.contains($0.compositeID)
      }
      recordCursor = value["next_cursor"].text
    } catch {
      self.error = "还有更早的来处没有接回，请稍后再试。"
    }
  }

  func detail(for entry: ContextEntry) async throws -> JSON {
    if let cached = details[entry.compositeID] { return cached }
    guard let account else { throw ServiceError.message("这份内容暂时无法打开。") }
    let value = try await account.request(
      "context/\(entry.isInsight ? "artifacts" : "records")/\(entry.id)")
    details[entry.compositeID] = value
    return value
  }

  func importConversation() async {
    guard !busy, let account, !preview else { return }
    busy = true
    error = ""
    feedback = "Hymio 正在回看最近的对话…"
    defer { busy = false }
    do {
      let result = try await account.request(
        "context/imports/conversation", body: .object(["limit": .number(10)]), timeout: 90)
      let count = result["record_ids"].items.count
      imported = true
      feedback = count == 0 ? "最近的对话已经在这里了。" : "接回了 \(count) 段真实对话。"
      await load(showBusy: false)
    } catch {
      feedback = ""
      self.error = "这次没有回看完，已经接回的内容不会重复保存。"
    }
  }

  func refine() async {
    guard !busy, let account, !preview else { return }
    busy = true
    error = ""
    feedback = "Hymio 正在重新整理对你的理解…"
    defer { busy = false }
    do {
      let key = UUID().uuidString
      let result = try await account.request(
        "context/dreams", body: .object([:]), timeout: 30, idempotencyKey: key)
      let id = result["dream_id"].text
      for _ in 0..<90 {
        try await Task.sleep(for: .seconds(2))
        let status = try await account.request("context/dreams/" + id)
        if status["state"].text == "committed" {
          refined = true
          feedback = "整理好了。新的理解已和来处一起放进页面。"
          await load(showBusy: false)
          return
        }
        if ["aborted", "failed"].contains(status["state"].text) {
          feedback = ""
          error = "这次整理没有完成，原来的内容仍然保留。"
          return
        }
      }
      feedback = "Hymio 还在慢慢整理，稍后回来看看。"
    } catch {
      feedback = ""
      self.error = "整理结果还没有确认，原来的内容没有被替换。"
    }
  }

  private func installPreview() {
    let artifactA = previewArtifact(
      id: "preview-direction",
      content: "你更希望先看见方向和可行动的下一步，再一起补细节。比起更多功能，你在意的是事情能不能真的用起来。",
      topics: ["做事方式"],
      references: ["preview-conversation", "preview-note"],
      date: "2026-10-23T09:20:00Z")
    let artifactB = previewArtifact(
      id: "preview-focus",
      content: "这周，你一直在把 Hymio 从“工具”拉回“陪在身边的个人 agent”。小水獭不是装饰，它应该让每一次整理都更像有人真的记得。",
      topics: ["正在发生"],
      references: ["preview-conversation", "preview-calendar"],
      date: "2026-10-22T15:40:00Z")
    let artifactC = previewArtifact(
      id: "preview-rhythm",
      content: "下午更适合安排需要判断和沟通的事；零碎的整理放到安静的时候，会更容易收拢。",
      topics: ["生活节奏"],
      references: ["preview-calendar"],
      date: "2026-10-20T11:05:00Z")

    let conversation = previewRecord(
      id: "preview-conversation", kind: "conversation", namespace: "hymio",
      content: "先别做成一个管理后台。我想看到 Hymio 真正认识我，也知道它从哪里知道的。",
      title: "你", subtitle: "和 Hymio 的对话",
      date: "2026-10-22T15:12:00Z")
    let calendar = previewRecord(
      id: "preview-calendar", kind: "connector", namespace: "calendar",
      content: "产品体验复盘",
      title: "产品体验复盘", subtitle: "今天 15:30 · 设计团队",
      date: "2026-10-23T07:30:00Z")
    let note = previewRecord(
      id: "preview-note", kind: "user", namespace: "hymio.saved",
      content: "每一条理解都要能回到原处。提炼是 Hymio 的判断，原始记录是我真实说过、做过的事。",
      title: "你留下的", subtitle: "主动记下",
      date: "2026-10-21T10:18:00Z")
    let activity = previewRecord(
      id: "preview-activity", kind: "kit", namespace: "figma",
      content: "更新了「Hymio · 与你在同一页」画板",
      title: "Figma", subtitle: "设计工作区",
      date: "2026-10-21T08:42:00Z")

    insights = [artifactA, artifactB, artifactC].map(ContextEntry.init)
    records = [calendar, conversation, note, activity].map(ContextEntry.init)
    details["artifact:preview-direction"] = previewInsightDetail(
      id: "preview-direction",
      content: "你更希望先看见方向和可行动的下一步，再一起补细节。比起更多功能，你在意的是事情能不能真的用起来。",
      references: ["preview-conversation", "preview-note"])
    details["artifact:preview-focus"] = previewInsightDetail(
      id: "preview-focus",
      content: "这周，你一直在把 Hymio 从“工具”拉回“陪在身边的个人 agent”。小水獭不是装饰，它应该让每一次整理都更像有人真的记得。",
      references: ["preview-conversation", "preview-calendar"])
    details["artifact:preview-rhythm"] = previewInsightDetail(
      id: "preview-rhythm",
      content: "下午更适合安排需要判断和沟通的事；零碎的整理放到安静的时候，会更容易收拢。",
      references: ["preview-calendar"])
    details["record:preview-conversation"] = conversation
    details["record:preview-calendar"] = calendar
    details["record:preview-note"] = note
    details["record:preview-activity"] = activity
    loading = false
  }
}

struct ContextScreen: View {
  @StateObject private var store: ContextStore
  let onChat: () -> Void

  init(account: AccountService, onChat: @escaping () -> Void) {
    _store = StateObject(wrappedValue: ContextStore(account: account))
    self.onChat = onChat
  }

  var body: some View {
    NavigationStack {
      ContextPage(store: store, onChat: onChat)
    }
    .task { await store.load() }
  }
}

struct ContextPreviewScreen: View {
  let account: AccountService?
  @StateObject private var store: ContextStore
  @State private var selected = ProductTab.moments

  init(account: AccountService?) {
    self.account = account
    _store = StateObject(wrappedValue: ContextStore(account: account ?? AccountService(), preview: true))
  }

  var body: some View {
    TabView(selection: $selected) {
      Tab("此刻", systemImage: "house.fill", value: ProductTab.today) { Color.clear }
      Tab("对话", systemImage: "bubble.left.and.bubble.right.fill", value: ProductTab.chat) {
        Color.clear
      }
      Tab("任务", systemImage: "checklist", value: ProductTab.tasks) { Color.clear }
      Tab("认识", systemImage: "person.crop.circle.badge.checkmark.fill", value: ProductTab.moments) {
        NavigationStack { ContextPage(store: store, onChat: {}) }
      }
      Tab("我的", systemImage: "person.crop.circle", value: ProductTab.account) { Color.clear }
    }
    .tint(Brand.blue)
  }
}

private struct ContextPage: View {
  @ObservedObject var store: ContextStore
  let onChat: () -> Void
  @Environment(\.accessibilityReduceMotion) private var reduceMotion
  @State private var showAllInsights = false
  @State private var showAllSources = false

  var body: some View {
    ScrollView {
      LazyVStack(alignment: .leading, spacing: 0) {
        topBar
        hero
        if !store.feedback.isEmpty {
          Label(store.feedback, systemImage: "sparkles")
            .font(.footnote)
            .foregroundStyle(Brand.muted)
            .padding(.top, 16)
            .transition(.opacity)
        }
        if !store.error.isEmpty {
          HStack(alignment: .top, spacing: 10) {
            Image(systemName: "arrow.clockwise.circle").foregroundStyle(Brand.attention)
            Text(store.error).font(.footnote).foregroundStyle(Brand.muted)
            Spacer(minLength: 4)
            Button("重试") { Task { await store.load() } }
              .font(.footnote.weight(.semibold))
              .foregroundStyle(Brand.blue)
              .frame(minHeight: 44)
          }
          .padding(.vertical, 8)
        }
        if store.loading && store.isEmpty {
          loadingState
        } else if store.isEmpty {
          emptyState
        } else {
          insightSection
          sourceSection
          closingNote
        }
      }
      .padding(.horizontal, 22)
      .padding(.bottom, 36)
      .frame(maxWidth: 700)
      .frame(maxWidth: .infinity)
    }
    .scrollIndicators(.hidden)
    .background(Brand.surface)
    .navigationTitle("")
    .navigationBarTitleDisplayMode(.inline)
    .toolbar {
      ToolbarItem(placement: .topBarTrailing) {
        Menu {
          Button("重新整理", systemImage: "sparkles") { Task { await store.refine() } }
          Button("回看最近对话", systemImage: "bubble.left.and.bubble.right") {
            Task { await store.importConversation() }
          }
        } label: {
          Image(systemName: "ellipsis")
            .frame(width: 44, height: 44)
        }
        .accessibilityLabel("整理你的 context")
      }
    }
    .refreshable { await store.load(showBusy: false) }
  }

  private var topBar: some View {
    HStack {
      HStack(spacing: 7) {
        Circle().fill(Brand.blue).frame(width: 7, height: 7)
        Text("Hymio 正在认识你")
          .font(.caption.weight(.medium))
          .foregroundStyle(Brand.muted)
      }
      Spacer()
      Text(Date.now.formatted(.dateTime.month().day()))
        .font(.caption)
        .foregroundStyle(Brand.muted)
    }
    .padding(.top, 6)
  }

  private var hero: some View {
    HStack(alignment: .center, spacing: 8) {
      VStack(alignment: .leading, spacing: 10) {
        Text("我眼中的你")
          .font(.system(.largeTitle, design: .rounded, weight: .semibold))
          .tracking(-1.1)
          .foregroundStyle(Brand.ink)
        Text("我一边陪你做事，一边慢慢认识你。这些理解都能回到它们发生的地方。")
          .font(.subheadline)
          .lineSpacing(3)
          .foregroundStyle(Brand.muted)
          .fixedSize(horizontal: false, vertical: true)
      }
      .frame(maxWidth: .infinity, alignment: .leading)
      ZStack {
        Circle()
          .fill(Brand.softBlue)
          .frame(width: 112, height: 112)
          .offset(x: 8, y: 8)
        Companion(size: 98, mood: .greeting)
          .offset(x: 6, y: 5)
      }
      .frame(width: 112, height: 126, alignment: .trailing)
      .accessibilityHidden(true)
    }
    .padding(.top, 16)
    .padding(.bottom, 22)
  }

  private var insightSection: some View {
    VStack(alignment: .leading, spacing: 0) {
      sectionHeading("我慢慢看懂的", note: "\(store.insights.count) 个理解")
      ForEach(
        Array((showAllInsights ? store.insights : Array(store.insights.prefix(4))).enumerated()),
        id: \.element.compositeID
      ) {
        index, entry in
        NavigationLink {
          ContextDetailScreen(store: store, entry: entry, onChat: onChat)
        } label: {
          ContextInsightBlock(entry: entry, first: index == 0)
        }
        .buttonStyle(GentlePress())
        .accessibilityHint("查看这条理解以及它来自的原始记录")
      }
      if store.insights.isEmpty {
        HStack(spacing: 12) {
          Image(systemName: "ellipsis.bubble")
            .font(.title3)
            .foregroundStyle(Brand.blue)
          Text("还没有形成稳定的理解。再多聊几次，Hymio 会从这里慢慢写下来。")
            .font(.subheadline)
            .foregroundStyle(Brand.muted)
        }
        .padding(.vertical, 22)
      } else if !showAllInsights && store.insights.count > 4 {
        Button("再看 \(store.insights.count - 4) 个理解") {
          showAllInsights = true
        }
        .font(.subheadline.weight(.medium))
        .foregroundStyle(Brand.blue)
        .frame(minHeight: 44)
      }
    }
  }

  private var sourceSection: some View {
    VStack(alignment: .leading, spacing: 0) {
      sectionHeading("这些从哪里知道", note: "\(store.records.count) 条来处")
      if store.records.isEmpty {
        Text("原始记录会在这里保留。它们不会因为提炼而消失。")
          .font(.subheadline)
          .foregroundStyle(Brand.muted)
          .padding(.vertical, 20)
      } else {
        sourceSummary
        ForEach(
          Array((showAllSources ? store.records : Array(store.records.prefix(4))).enumerated()),
          id: \.element.compositeID
        ) {
          index, entry in
          NavigationLink {
            ContextDetailScreen(store: store, entry: entry, onChat: onChat)
          } label: {
            ContextSourceRow(entry: entry, first: index == 0)
          }
          .buttonStyle(GentlePress())
          .accessibilityHint("打开原始记录")
        }
        if !showAllSources && store.records.count > 4 {
          Button("查看全部 \(store.records.count) 条来处") {
            withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.22)) {
              showAllSources = true
            }
          }
          .font(.subheadline.weight(.medium))
          .foregroundStyle(Brand.blue)
          .frame(minHeight: 44)
        } else if showAllSources && !store.recordCursor.isEmpty {
          Button(store.moreBusy ? "正在接回更早的记录…" : "继续往前看") {
            Task { await store.loadMoreRecords() }
          }
          .font(.subheadline.weight(.medium))
          .foregroundStyle(Brand.blue)
          .frame(minHeight: 44)
          .disabled(store.moreBusy)
        }
      }
    }
  }

  private var sourceSummary: some View {
    let grouped = Dictionary(grouping: store.records, by: \.sourceKind)
    return HStack(spacing: 8) {
      ForEach(["conversation", "connector", "user", "kit"], id: \.self) { kind in
        if let count = grouped[kind]?.count {
          HStack(spacing: 4) {
            Image(systemName: sourceSummarySymbol(kind))
              .font(.system(size: 9, weight: .semibold))
            Text("\(sourceSummaryTitle(kind)) \(count)")
          }
          .font(.caption2.weight(.medium))
          .foregroundStyle(Brand.muted)
          .padding(.horizontal, 8)
          .padding(.vertical, 5)
          .background(Brand.mist, in: Capsule())
        }
      }
      Spacer(minLength: 0)
    }
    .padding(.bottom, 14)
    .accessibilityElement(children: .combine)
    .accessibilityLabel("来源分布")
  }

  private var closingNote: some View {
    VStack(alignment: .leading, spacing: 16) {
      Rectangle()
        .fill(Brand.paperLine)
        .frame(height: 1)
      Text("这些不是关于你的档案。\n只是我此刻的理解，会随着我们继续相处而改变。")
        .font(.system(.subheadline, design: .rounded, weight: .medium))
        .lineSpacing(5)
        .foregroundStyle(Brand.ink)
      Button(action: onChat) {
        HStack(spacing: 8) {
          Text("告诉 Hymio 更多")
          Image(systemName: "arrow.right")
        }
        .font(.subheadline.weight(.semibold))
        .padding(.horizontal, 16)
        .frame(minHeight: 44)
        .foregroundStyle(Brand.onAccent)
        .background(Brand.blue, in: Capsule())
      }
      .buttonStyle(GentlePress())
      .accessibilityIdentifier("context.chat")
    }
    .padding(.top, 30)
    .padding(.bottom, 8)
  }

  private var loadingState: some View {
    VStack(alignment: .leading, spacing: 12) {
      ProgressView().controlSize(.small)
      Text("正在接回 Hymio 对你的了解…")
        .font(.subheadline)
        .foregroundStyle(Brand.muted)
    }
    .padding(.vertical, 64)
  }

  private var emptyState: some View {
    VStack(alignment: .leading, spacing: 14) {
      Companion(size: 70, mood: .waiting)
      Text("我还不太认识你。")
        .font(.title3.weight(.semibold))
        .foregroundStyle(Brand.ink)
      Text("从一段对话、一件事或一个偏好开始。等有真实来处时，我会把理解写在这里。")
        .font(.subheadline)
        .lineSpacing(4)
        .foregroundStyle(Brand.muted)
      Button("和 Hymio 聊聊", action: onChat)
        .font(.subheadline.weight(.semibold))
        .foregroundStyle(Brand.blue)
        .frame(minHeight: 44)
    }
    .padding(.vertical, 52)
  }

  private func sectionHeading(_ title: String, note: String) -> some View {
    HStack(alignment: .firstTextBaseline) {
      Text(title)
        .font(.system(.headline, design: .rounded, weight: .semibold))
        .foregroundStyle(Brand.ink)
      Spacer()
      Text(note)
        .font(.caption)
        .foregroundStyle(Brand.muted)
    }
    .padding(.top, 24)
    .padding(.bottom, 10)
  }
}

private struct ContextInsightBlock: View {
  let entry: ContextEntry
  let first: Bool
  private var copy: (title: String, detail: String) { contextSplit(entry.preview) }

  var body: some View {
    VStack(alignment: .leading, spacing: 8) {
      HStack(spacing: 7) {
        Image(systemName: "sparkle")
          .font(.caption.weight(.semibold))
          .foregroundStyle(Brand.blue)
        Text(entry.topics.first ?? "我注意到的")
          .font(.caption.weight(.semibold))
          .foregroundStyle(Brand.blue)
        Spacer()
        Image(systemName: "arrow.up.right")
          .font(.caption2.weight(.semibold))
          .foregroundStyle(Brand.muted.opacity(0.75))
      }
      Text(copy.title)
        .font(.system(.headline, design: .rounded, weight: first ? .semibold : .medium))
        .lineSpacing(3)
        .foregroundStyle(Brand.ink)
        .fixedSize(horizontal: false, vertical: true)
      if !copy.detail.isEmpty {
        Text(copy.detail)
          .font(.subheadline)
          .lineSpacing(3)
          .foregroundStyle(Brand.muted)
          .fixedSize(horizontal: false, vertical: true)
      }
      if entry.referenceCount > 0 {
        Label(
          "沿着 \(entry.referenceCount) 条原始记录看到这句话",
          systemImage: "arrow.turn.down.right")
          .font(.caption2)
          .foregroundStyle(Brand.muted)
      }
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .padding(.vertical, 15)
    .overlay(alignment: .bottom) {
      Rectangle().fill(Brand.paperLine).frame(height: 1)
    }
    .contentShape(Rectangle())
  }
}

private struct ContextSourceRow: View {
  let entry: ContextEntry
  let first: Bool

  var body: some View {
    VStack(alignment: .leading, spacing: 10) {
      HStack(spacing: 7) {
        Image(systemName: entry.sourceSymbol)
          .font(.system(size: 10, weight: .semibold))
          .foregroundStyle(sourceAccent(entry.sourceKind))
          .frame(width: 18, height: 18)
          .background(sourceAccent(entry.sourceKind).opacity(0.1), in: RoundedRectangle(cornerRadius: 5))
        Text(entry.sourceTitle)
          .font(.caption.weight(.semibold))
          .foregroundStyle(Brand.ink)
        Text("·")
          .font(.caption)
          .foregroundStyle(Brand.muted)
        Text(entry.dateLabel.isEmpty ? "刚刚留下" : entry.dateLabel)
          .font(.caption)
          .foregroundStyle(Brand.muted)
        Spacer()
        if !entry.isInsight {
          Image(systemName: "chevron.right")
            .font(.caption2.weight(.semibold))
            .foregroundStyle(Brand.muted.opacity(0.75))
        }
      }
      switch entry.sourceKind {
      case "conversation":
        conversation
      case "user":
        savedNote
      case "connector":
        connector
      default:
        activity
      }
    }
    .padding(.vertical, first ? 2 : 14)
    .overlay(alignment: .bottom) {
      if !first {
        Rectangle().fill(Brand.paperLine.opacity(0.75)).frame(height: 1).padding(.leading, 26)
      }
    }
    .contentShape(Rectangle())
  }

  private var conversation: some View {
    HStack(alignment: .top, spacing: 10) {
      Text("“")
        .font(.system(size: 31, weight: .medium, design: .rounded))
        .foregroundStyle(Brand.blue.opacity(0.75))
        .frame(width: 18, alignment: .leading)
      Text(entry.preview)
        .font(.body)
        .lineSpacing(4)
        .foregroundStyle(Brand.ink)
        .fixedSize(horizontal: false, vertical: true)
    }
    .padding(15)
    .background(Brand.softBlue, in: RoundedRectangle(cornerRadius: 18))
  }

  private var savedNote: some View {
    HStack(alignment: .top, spacing: 12) {
      Image(systemName: "bookmark.fill")
        .font(.caption)
        .foregroundStyle(Brand.noteLine)
        .padding(.top, 3)
      Text(entry.preview)
        .font(.subheadline)
        .lineSpacing(4)
        .foregroundStyle(Brand.ink)
        .fixedSize(horizontal: false, vertical: true)
    }
    .padding(15)
    .background(Brand.notePaper, in: RoundedRectangle(cornerRadius: 5))
    .overlay(alignment: .topTrailing) {
      Triangle()
        .fill(Brand.noteLine.opacity(0.65))
        .frame(width: 18, height: 18)
        .accessibilityHidden(true)
    }
  }

  private var connector: some View {
    HStack(alignment: .center, spacing: 12) {
      VStack(spacing: 1) {
        Text(contextMonth(entry.createdAt))
          .font(.system(size: 9, weight: .bold))
          .textCase(.uppercase)
        Text(contextDay(entry.createdAt))
          .font(.system(size: 20, weight: .semibold, design: .rounded))
      }
      .foregroundStyle(Brand.blue)
      .frame(width: 42, height: 46)
      .background(Brand.softBlue, in: RoundedRectangle(cornerRadius: 11))
      VStack(alignment: .leading, spacing: 4) {
        Text(entry.preview)
          .font(.subheadline.weight(.medium))
          .foregroundStyle(Brand.ink)
          .lineLimit(3)
        if entry.namespace.lowercased().contains("calendar") {
          Text("来自日历")
            .font(.caption2)
            .foregroundStyle(Brand.muted)
        }
      }
    }
    .padding(14)
    .background(Brand.surface, in: RoundedRectangle(cornerRadius: 16))
    .overlay(RoundedRectangle(cornerRadius: 16).stroke(Brand.paperLine))
  }

  private var activity: some View {
    HStack(alignment: .top, spacing: 12) {
      Image(systemName: entry.sourceSymbol)
        .font(.system(size: 14, weight: .semibold))
        .foregroundStyle(Brand.blue)
        .frame(width: 34, height: 34)
        .background(Brand.softBlue, in: RoundedRectangle(cornerRadius: 10))
      Text(entry.preview)
        .font(.subheadline)
        .lineSpacing(3)
        .foregroundStyle(Brand.ink)
        .fixedSize(horizontal: false, vertical: true)
    }
    .padding(14)
    .background(Brand.paper, in: RoundedRectangle(cornerRadius: 14))
  }
}

private struct ContextDetailScreen: View {
  @ObservedObject var store: ContextStore
  let entry: ContextEntry
  let onChat: () -> Void
  @State private var value: JSON = .null
  @State private var related: [ContextEntry] = []
  @State private var error = ""
  @State private var loading = true

  private var content: String {
    let direct = value["content"].text
    if !direct.isEmpty { return direct }
    let nested = value["context"]["text"].text
    if !nested.isEmpty { return nested }
    return entry.preview
  }

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 0) {
        VStack(alignment: .leading, spacing: 12) {
          HStack(spacing: 8) {
            Image(systemName: entry.isInsight ? "sparkle" : entry.sourceSymbol)
              .font(.caption.weight(.semibold))
              .foregroundStyle(Brand.blue)
            Text(entry.isInsight ? (entry.topics.first ?? "Hymio 的理解") : entry.sourceTitle)
              .font(.caption.weight(.semibold))
              .foregroundStyle(Brand.blue)
            Spacer()
            Text(entry.dateLabel)
              .font(.caption)
              .foregroundStyle(Brand.muted)
          }
          if loading {
            ProgressView("沿着来处找一找…")
              .font(.subheadline)
              .padding(.vertical, 80)
          } else {
            Text(content)
              .font(
                entry.isInsight
                  ? .system(.title2, design: .rounded, weight: .medium)
                  : .system(.title3, design: .rounded, weight: .regular)
              )
              .lineSpacing(7)
              .foregroundStyle(Brand.ink)
              .textSelection(.enabled)
              .fixedSize(horizontal: false, vertical: true)
            if !error.isEmpty {
              Label(error, systemImage: "exclamationmark.circle")
                .font(.footnote)
                .foregroundStyle(Brand.muted)
                .padding(.top, 14)
            }
            if entry.isInsight {
              insightProvenance
            } else {
              rawSourceDetail
            }
          }
        }
        .padding(.horizontal, 22)
        .padding(.top, 18)
        .padding(.bottom, 34)
      }
      .frame(maxWidth: 680)
      .frame(maxWidth: .infinity)
    }
    .background(Brand.surface)
    .navigationTitle(entry.isInsight ? "我这样理解" : "原始来处")
    .navigationBarTitleDisplayMode(.inline)
    .task { await load() }
  }

  private var insightProvenance: some View {
    VStack(alignment: .leading, spacing: 12) {
      Rectangle()
        .fill(Brand.paperLine)
        .frame(height: 1)
        .padding(.vertical, 10)
      HStack {
        Text("这些话从哪里来")
          .font(.headline)
          .foregroundStyle(Brand.ink)
        Spacer()
        Text("\(related.count) 条")
          .font(.caption)
          .foregroundStyle(Brand.muted)
      }
      if related.isEmpty {
        Text("这一条暂时没有可打开的原始记录。")
          .font(.footnote)
          .foregroundStyle(Brand.muted)
      } else {
        ForEach(Array(related.enumerated()), id: \.element.compositeID) { index, source in
          NavigationLink {
            ContextDetailScreen(store: store, entry: source, onChat: onChat)
          } label: {
            ContextSourceRow(entry: source, first: index == 0)
          }
          .buttonStyle(GentlePress())
        }
      }
      Text("Hymio 的整理会变，但这些原始记录会保留下来。")
        .font(.caption)
        .foregroundStyle(Brand.muted)
        .padding(.top, 8)
    }
    .padding(.top, 26)
  }

  private var rawSourceDetail: some View {
    VStack(alignment: .leading, spacing: 16) {
      Rectangle()
        .fill(Brand.paperLine)
        .frame(height: 1)
        .padding(.vertical, 8)
      HStack(spacing: 10) {
        Image(systemName: entry.sourceSymbol)
          .font(.subheadline.weight(.semibold))
          .foregroundStyle(Brand.blue)
          .frame(width: 38, height: 38)
          .background(Brand.softBlue, in: RoundedRectangle(cornerRadius: 11))
        VStack(alignment: .leading, spacing: 2) {
          Text(entry.sourceTitle)
            .font(.subheadline.weight(.semibold))
          Text(
            entry.namespace.isEmpty
              ? "保留原始内容，不做改写" : "\(connectorName(entry.namespace)) · 原始内容"
          )
          .font(.caption)
          .foregroundStyle(Brand.muted)
        }
      }
      Text("原始记录是 Hymio 了解你的依据，不是一段后来补上的解释。")
        .font(.subheadline)
        .lineSpacing(4)
        .foregroundStyle(Brand.muted)
      Button(action: onChat) {
        Label("和 Hymio 聊聊这条", systemImage: "bubble.left")
          .font(.subheadline.weight(.semibold))
          .foregroundStyle(Brand.blue)
          .frame(minHeight: 44)
      }
    }
    .padding(.top, 24)
  }

  private func load() async {
    loading = true
    error = ""
    do {
      value = try await store.detail(for: entry)
      related = []
      for reference in value["references"].items {
        let id = reference["record_id"].text
        if let cached = store.records.first(where: { $0.id == id }) {
          related.append(cached)
        } else if !id.isEmpty,
          let fetched = try? await store.detail(
            for: ContextEntry(
              .object([
                "id": .string(id), "kind": .string("record"),
                "preview": .string("原始记录"), "source": .object([:]),
              ])))
        {
          related.append(ContextEntry(fetched))
        }
      }
    } catch {
      self.error = "暂时没能接回来处。"
    }
    loading = false
  }
}

private struct Triangle: Shape {
  func path(in rect: CGRect) -> Path {
    var path = Path()
    path.move(to: CGPoint(x: rect.maxX, y: rect.minY))
    path.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY))
    path.addLine(to: CGPoint(x: rect.minX, y: rect.minY))
    path.closeSubpath()
    return path
  }
}

private func sourceAccent(_ kind: String) -> Color {
  switch kind {
  case "user": return Brand.attention
  case "conversation": return Brand.blue
  case "connector", "kit": return Brand.ink.opacity(0.72)
  default: return Brand.muted
  }
}

private func sourceSummarySymbol(_ kind: String) -> String {
  switch kind {
  case "conversation": return "bubble.left.and.bubble.right.fill"
  case "connector": return "link"
  case "user": return "bookmark.fill"
  case "kit": return "square.grid.2x2.fill"
  default: return "doc.text"
  }
}

private func sourceSummaryTitle(_ kind: String) -> String {
  ["conversation": "对话", "connector": "连接", "user": "记下", "kit": "应用"][kind] ?? "其他"
}

private func connectorName(_ namespace: String) -> String {
  let lower = namespace.lowercased()
  if lower.contains("calendar") { return "日历" }
  if lower.contains("mail") { return "邮件" }
  if lower.contains("figma") { return "Figma" }
  if lower.contains("notion") { return "Notion" }
  if lower.contains("github") { return "GitHub" }
  return namespace.replacingOccurrences(of: "_", with: " ").capitalized
}

private func connectorSymbol(_ namespace: String) -> String {
  let lower = namespace.lowercased()
  if lower.contains("calendar") { return "calendar" }
  if lower.contains("mail") { return "envelope.fill" }
  if lower.contains("file") || lower.contains("drive") { return "doc.text.fill" }
  if lower.contains("figma") { return "square.on.circle" }
  return "link"
}

private func contextReadable(_ text: String) -> String {
  guard let data = text.data(using: .utf8), let value = try? JSON.decode(data) else { return text }
  if !value["text"].text.isEmpty { return value["text"].text }
  if !value["content"].text.isEmpty { return value["content"].text }
  if !value["title"].text.isEmpty { return value["title"].text }
  return text
}

private func contextSplit(_ text: String) -> (title: String, detail: String) {
  if let end = text.firstIndex(where: { "。！？!?".contains($0) }) {
    let next = text.index(after: end)
    let title = String(text[..<next]).trimmingCharacters(in: .whitespacesAndNewlines)
    let detail = String(text[next...]).trimmingCharacters(in: .whitespacesAndNewlines)
    if !detail.isEmpty { return (title, detail) }
  }
  return (text, "")
}

private func contextDate(_ value: String) -> Date? {
  let fractional = ISO8601DateFormatter()
  fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
  return fractional.date(from: value) ?? ISO8601DateFormatter().date(from: value)
}

private func contextMonth(_ value: String) -> String {
  guard let date = contextDate(value) else { return "" }
  return date.formatted(.dateTime.month(.abbreviated)).uppercased()
}

private func contextDay(_ value: String) -> String {
  guard let date = contextDate(value) else { return "·" }
  return date.formatted(.dateTime.day())
}

private func previewArtifact(
  id: String, content: String, topics: [String], references: [String], date: String
) -> JSON {
  .object([
    "id": .string(id), "kind": .string("artifact"), "preview": .string(content),
    "created_at": .string(date), "topics": .array(topics.map(JSON.string)),
    "references": .array(references.map { .object(["record_id": .string($0)]) }),
  ])
}

private func previewRecord(
  id: String, kind: String, namespace: String, content: String, title: String,
  subtitle: String, date: String
) -> JSON {
  .object([
    "id": .string(id), "kind": .string("record"), "preview": .string(content),
    "created_at": .string(date),
    "source": .object(["kind": .string(kind), "namespace": .string(namespace)]),
    "context": .object(["text": .string(content), "title": .string(title)]),
    "content": .string(content),
  ])
}

private func previewInsightDetail(id: String, content: String, references: [String]) -> JSON {
  .object([
    "id": .string(id), "kind": .string("artifact"), "content": .string(content),
    "references": .array(references.map { .object(["record_id": .string($0)]) }),
  ])
}
