import SwiftUI

private let memoryCategories: [(key: String, label: String)] = [
  ("all", "全部"), ("work", "工作"), ("learning", "学习"), ("life", "生活"), ("uncategorized", "未分类"),
]
private let memorySources: [(key: String, label: String)] = [
  ("all", "日常足迹"), ("conversation", "对话"), ("user", "手记"), ("gmail", "Gmail"),
  ("dida", "滴答清单"), ("apple_calendar", "苹果日历"), ("apple_health", "苹果健康"), ("kit", "应用"), ("legacy", "其他"),
]

/// A user-facing view of the context Hymio has assembled, with each synthesized
/// statement still traceable to its source records.
struct ContextEntry: Identifiable, Hashable, Sendable {
  enum Entity: String, Sendable {
    case artifact
    case record
  }

  let id: String
  let entity: Entity
  let preview: String
  let sourceKind: String
  let namespace: String
  let createdAt: String
  let title: String
  let category: String
  let topics: [String]
  let referenceCount: Int
  let value: JSON

  var compositeID: String { "\(entity.rawValue):\(id)" }
  var isInsight: Bool { entity == .artifact }
  var sourceProvider: String {
    let provider = namespace.split(separator: ".").first.map(String.init) ?? ""
    return ["apple_health", "apple_calendar", "gmail", "dida"].contains(provider) ? provider : sourceKind
  }
  var sourceTitle: String {
    switch sourceKind {
    case "conversation": return "对话原话"
    case "connector": return namespace.isEmpty ? "连接服务" : connectorName(namespace)
    case "kit": return "应用"
    case "user": return "主动记下"
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
    return date.formatted(.dateTime.month(.abbreviated).day().hour().minute())
  }

  init(_ value: JSON) {
    self.value = value
    id = value["id"].text
    entity = value["kind"].text == "artifact" ? .artifact : .record
    preview = contextReadable(value["preview"].text)
    sourceKind = value["source"]["kind"].text.isEmpty ? "legacy" : value["source"]["kind"].text
    namespace = value["source"]["namespace"].text
    createdAt =
      value["updated_at"].text.isEmpty ? value["created_at"].text : value["updated_at"].text
    let metadata = entity == .artifact ? value["fields"] : value["context"]["memory"]
    title =
      value["title"].text.isEmpty
      ? (metadata["title"].text.isEmpty ? value["context"]["title"].text : metadata["title"].text)
      : value["title"].text
    let storedCategory =
      value["category"].text.isEmpty ? metadata["category"].text : value["category"].text
    category =
      storedCategory.isEmpty
      ? (value["context"]["category"].text.isEmpty
        ? "uncategorized" : value["context"]["category"].text) : storedCategory
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
  @Published private(set) var moreBusy = false
  @Published private(set) var saving = false
  @Published var draft = ""
  @Published var correctionTarget: ContextEntry?
  @Published var draftCategory = "uncategorized"
  @Published private(set) var category = "all"
  @Published private(set) var source = "all"
  @Published private(set) var overview: JSON = .null
  @Published private(set) var overviewError = ""
  @Published private(set) var saveError = ""
  @Published private(set) var pendingSave = false
  @Published private(set) var insightCursor = ""
  @Published private(set) var recordCursor = ""
  @Published private(set) var partial = false
  private let account: AccountService?
  let accountService: AccountService
  private let preview: Bool
  private var details: [String: JSON] = [:]
  private var allPreviewInsights: [ContextEntry] = []
  private var allPreviewRecords: [ContextEntry] = []
  private var generation = UUID()
  private(set) var query = ""
  private var confirmedSaves: [ContextEntry] = []
  private var saveOperation: (key: String, text: String, category: String)?

  init(account: AccountService, preview: Bool = false, installFixtures: Bool = true) {
    self.account = account
    self.accountService = account
    self.preview = preview
    if preview {
      if installFixtures { installPreview() } else { loading = false }
      #if DEBUG
        if ProcessInfo.processInfo.arguments.contains("-HymioContextRecordsOnly") { insights = [] }
        if ProcessInfo.processInfo.arguments.contains("-HymioContextInsightsOnly") { records = [] }
      #endif
      allPreviewInsights = insights
      allPreviewRecords = records
    }
  }
  var isEmpty: Bool { insights.isEmpty && records.isEmpty }

  private func search(_ target: String, cursor: String = "") async throws -> JSON {
    guard let account else { throw ServiceError.message("暂时读不到记忆。") }
    return try await account.request(
      "context/browse",
      body: .object([
        "target": .string(target), "category": .string(target == "artifacts" ? category : "all"),
        "source_kind": .string(target == "records" ? source : "all"),
        "query": query.isEmpty ? .null : .string(query),
        "limit": .number(30), "cursor": cursor.isEmpty ? .null : .string(cursor),
      ]))
  }
  func load(
    query nextQuery: String? = nil, category nextCategory: String? = nil,
    source nextSource: String? = nil
  ) async {
    let next = nextQuery ?? query
    let changed =
      next != query || (nextCategory != nil && nextCategory != category)
      || (nextSource != nil && nextSource != source)
    category = nextCategory ?? category
    source = nextSource ?? source
    query = next
    let current = UUID()
    generation = current
    loading = true
    error = ""
    moreBusy = false
    if changed {
      insights = []
      records = []
      insightCursor = ""
      recordCursor = ""
    }
    if preview {
      insights = allPreviewInsights.filter {
        (category == "all" || $0.category == category)
          && (next.isEmpty || $0.preview.localizedCaseInsensitiveContains(next))
      }
      records = allPreviewRecords.filter {
        (source == "all" || $0.sourceProvider == source)
          && (next.isEmpty || $0.preview.localizedCaseInsensitiveContains(next))
      }
      loading = false
      return
    }
    do {
      async let artifactResult = search("artifacts")
      async let recordResult = search("records")
      let (a, r) = try await (artifactResult, recordResult)
      guard current == generation, !Task.isCancelled else { return }
      insights = a["items"].items.map(ContextEntry.init).filter { !$0.id.hasPrefix("_") }
      let fetched = r["items"].items.map(ContextEntry.init).filter { !$0.id.hasPrefix("_") }
      let recent = confirmedSaves.filter {
        (source == "all" || $0.sourceProvider == source)
          && (next.isEmpty || $0.preview.localizedCaseInsensitiveContains(next))
      }
      let recentIDs = Set(recent.map(\.compositeID))
      records = recent + fetched.filter { !recentIDs.contains($0.compositeID) }
      insightCursor = a["next_cursor"].text
      recordCursor = r["next_cursor"].text
      partial = a["partial"] == .bool(true) || r["partial"] == .bool(true)
      details.removeAll()
      if let account {
        do {
          overview = try await account.request("context/assembly")
          overviewError = ""
        } catch { overviewError = "概述暂时无法读取" }
      }
    } catch {
      guard current == generation else { return }
      if !Task.isCancelled { self.error = "暂时读不到记忆，请稍后重试。" }
    }
    if current == generation { loading = false }
  }
  func loadMore(insights targetInsights: Bool) async {
    let cursor = targetInsights ? insightCursor : recordCursor
    guard !cursor.isEmpty, !moreBusy, !loading, !preview else { return }
    let current = generation
    moreBusy = true
    defer { if current == generation { moreBusy = false } }
    do {
      let result = try await search(targetInsights ? "artifacts" : "records", cursor: cursor)
      guard current == generation, !Task.isCancelled else { return }
      let items = result["items"].items.map(ContextEntry.init).filter { !$0.id.hasPrefix("_") }
      if targetInsights {
        let known = Set(insights.map(\.compositeID))
        insights += items.filter { !known.contains($0.compositeID) }
        insightCursor = result["next_cursor"].text
      } else {
        let known = Set(records.map(\.compositeID))
        records += items.filter { !known.contains($0.compositeID) }
        recordCursor = result["next_cursor"].text
      }
    } catch { if current == generation { self.error = "未能读取更多记忆，请重试。" } }
  }
  func detail(for entry: ContextEntry) async throws -> JSON {
    if let value = details[entry.compositeID] { return value }
    guard let account else { throw ServiceError.message("暂时无法读取完整内容。") }
    let allowed = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "-._~"))
    guard let encoded = entry.id.addingPercentEncoding(withAllowedCharacters: allowed) else {
      throw ServiceError.message("记录地址无效。")
    }
    let value = try await account.request(
      "context/\(entry.isInsight ? "artifacts" : "records")/\(encoded)")
    details[entry.compositeID] = value
    return value
  }
  func original(_ id: String) async throws -> ContextEntry {
    let stub = ContextEntry(.object(["id": .string(id), "kind": .string("record")]))
    let value = try await detail(for: stub)
    return ContextEntry(
      .object([
        "id": .string(id), "kind": .string("record"), "preview": .string(contextContent(value)),
        "source": value["source"], "created_at": value["created_at"], "context": value["context"],
      ]))
  }
  func save() async -> Bool {
    let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !text.isEmpty, text.unicodeScalars.count <= 16000, !saving else { return false }
    if saveOperation == nil { saveOperation = (UUID().uuidString, text, draftCategory) }
    guard let operation = saveOperation else { return false }
    saving = true
    saveError = ""
    pendingSave = true
    defer { saving = false }
    do {
      if let target = correctionTarget, let account {
        _ = try await account.request(
          "context/corrections",
          body: .object([
            "target": .object(["kind": .string(target.entity.rawValue), "id": .string(target.id)]),
            "text": .string(operation.text),
          ]), idempotencyKey: operation.key)
        saveOperation = nil
        pendingSave = false
        draft = ""
        correctionTarget = nil
        feedback = "你的补充已记下，相关理解会重新整理。"
        return true
      }
      if preview {
        let id = UUID().uuidString
        let value = previewRecord(
          id: id, kind: "user", namespace: "hymio.saved", content: operation.text,
          title: "主动记下", subtitle: "预览", date: ISO8601DateFormatter().string(from: Date()))
        allPreviewRecords.insert(ContextEntry(value), at: 0)
        details["record:\(id)"] = value
      } else {
        guard let account else { throw ServiceError.message("暂时无法保存。") }
        let saved = try await account.request(
          "context/saves",
          body: .object(["text": .string(operation.text)]),
          idempotencyKey: operation.key)
        let entry = ContextEntry(
          .object([
            "id": saved["id"], "kind": .string("record"),
            "preview": .string(contextContent(saved)), "source": saved["source"],
            "created_at": saved["created_at"], "category": .string(operation.category),
          ]))
        confirmedSaves = [entry] + confirmedSaves.filter { $0.id != entry.id }
        confirmedSaves = Array(confirmedSaves.prefix(20))
        records = [entry] + records.filter { $0.id != entry.id }
      }
      saveOperation = nil
      pendingSave = false
      draft = ""
      feedback = preview ? "预览：已添加一条足迹。" : "已保存到足迹。理解会在后续整理中形成。"
      await load(query: "", category: "all")
      return true
    } catch {
      saveError = "暂时无法确认保存结果。输入仍保留在这里，重试会沿用同一条记录。"
      return false
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
      id: "preview-calendar", kind: "connector", namespace: "apple_calendar.preview",
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
  let onAccount: () -> Void
  init(account: AccountService, onAccount: @escaping () -> Void = {}) {
    _store = StateObject(wrappedValue: ContextStore(account: account))
    self.onAccount = onAccount
  }
  var body: some View {
    NavigationStack { ContextPage(store: store, onAccount: onAccount) }
      .task { await store.load() }
  }
}

struct ContextPreviewScreen: View {
  @StateObject private var store: ContextStore
  @State private var selected = ProductTab.moments
  init(account: AccountService?, empty: Bool = false) {
    _store = StateObject(
      wrappedValue: ContextStore(
        account: account ?? AccountService(), preview: true, installFixtures: !empty))
  }
  var body: some View {
    TabView(selection: $selected) {
      Tab("此刻", systemImage: "house.fill", value: ProductTab.today) { Color.clear }
      Tab("对话", systemImage: "bubble.left.and.bubble.right.fill", value: ProductTab.chat) {
        Color.clear
      }
      Tab("回忆", systemImage: "book.closed.fill", value: ProductTab.moments) {
        NavigationStack { ContextPage(store: store, onAccount: {}) }
      }

    }.tint(Brand.blue)
  }
}

private struct ContextPage: View {
  @ObservedObject var store: ContextStore
  let onAccount: () -> Void
  @State private var insights = false
  @State private var searchText = ""
  @State private var showCollect = false
  @State private var selectedEntry: ContextEntry?
  @State private var lastOpenedID = ""
  @Environment(\.dynamicTypeSize) private var typeSize
  private var items: [ContextEntry] {
    insights ? store.insights : store.records.filter { store.source != "all" || !$0.namespace.hasPrefix("apple_health") }
  }
  private var cursor: String { insights ? store.insightCursor : store.recordCursor }

  var body: some View {
    ScrollView {
      LazyVStack(alignment: .leading, spacing: 12) {
        viewControls
        if insights {
          DisclosureGroup {
            Text(
              store.overviewError.isEmpty
                ? (store.overview["stable"]["content"].text.isEmpty
                  ? "还没有形成概述。整理后的长期背景会在这里呈现。" : store.overview["stable"]["content"].text)
                : store.overviewError
            )
            .font(.subheadline).foregroundStyle(Brand.ink).lineSpacing(5)

          } label: {
            Label {
              Text("我眼中的你")
            } icon: {
              Image(systemName: "person.crop.circle")
                .foregroundStyle(
                  LinearGradient(
                    colors: [.blue, .purple], startPoint: .topLeading, endPoint: .bottomTrailing))
            }.font(.subheadline.weight(.medium))
          }.padding(.horizontal, 14).padding(.vertical, 8).background(
            Brand.softBlue, in: RoundedRectangle(cornerRadius: 12))
        }
        HStack {
          categoryPicker
        }
        if !store.feedback.isEmpty {
          HStack(spacing: 10) {
            Companion(size: 30)
            Text(store.feedback).font(.footnote).foregroundStyle(Brand.blue)
          }.padding(14).frame(maxWidth: .infinity, alignment: .leading)
            .background(Brand.softBlue, in: RoundedRectangle(cornerRadius: 12))
        }
        if !store.error.isEmpty {
          VStack(alignment: .leading, spacing: 10) {
            Text(store.isEmpty ? "暂时读不到记忆" : "暂时没能刷新，仍显示上次读取的内容").font(.headline)
            Text(store.error).font(.subheadline).foregroundStyle(Brand.muted)
            Button("重试") { Task { await store.load() } }.frame(minHeight: 44)
          }.padding(18).frame(maxWidth: .infinity, alignment: .leading)
            .background(Brand.mist, in: RoundedRectangle(cornerRadius: 15))
        }
        if store.loading && items.isEmpty {
          ProgressView("正在读取记忆…").frame(maxWidth: .infinity).padding(.vertical, 70)
        } else if !items.isEmpty {
          ForEach(items, id: \.compositeID) { entry in
            ZStack(alignment: .topTrailing) {
              Button {
                lastOpenedID = entry.compositeID
                selectedEntry = entry
              } label: {
                ContextCard(entry: entry)
                  .background(lastOpenedID == entry.compositeID ? Brand.base : Color.clear)
              }.buttonStyle(GentlePress())
              Menu {
                Button("查看内容") { selectedEntry = entry }
                Button("补充或纠正") {
                  guard !store.pendingSave else { return }
                  store.correctionTarget = entry
                  store.draft = ""
                  showCollect = true
                }
              } label: {
                Image(systemName: "ellipsis").foregroundStyle(Brand.muted).frame(
                  width: 44, height: 44)
              }
              .accessibilityLabel("更多卡片操作")
            }
          }
          HStack {
            Text("已显示 \(items.count) 条\(store.partial ? " · 结果尚不完整" : "")")
              .font(.caption).foregroundStyle(Brand.muted)
            Spacer()
            if !cursor.isEmpty {
              Button(store.moreBusy ? "正在读取…" : "继续查看") {
                Task { await store.loadMore(insights: insights) }
              }.disabled(store.moreBusy || store.loading).frame(minHeight: 44)
            }
          }
        } else if store.error.isEmpty {
          emptyState
          if !cursor.isEmpty {
            Button("继续读取更多内容") { Task { await store.loadMore(insights: insights) } }
              .disabled(store.moreBusy).frame(minHeight: 44)
          }
        }
      }
      .padding(.horizontal, 16).padding(.bottom, 30)
      .frame(maxWidth: 700).frame(maxWidth: .infinity)
    }
    .background(Brand.surface).navigationTitle("").navigationBarTitleDisplayMode(.inline)
    .toolbar {
      ToolbarItem(placement: .topBarLeading) {
        AccountButton(account: store.accountService, action: onAccount)
      }.memoryUnframed()
      ToolbarItem(placement: .principal) {
        Text("回忆").font(.headline).foregroundStyle(Brand.ink)
      }
      ToolbarItem(placement: .topBarTrailing) {
        AddActionButton(title: "添加回忆") { showCollect = true }
          .accessibilityIdentifier("context.collect")
      }.memoryUnframed()
    }
    .refreshable { await store.load() }
    .sheet(isPresented: $showCollect) {
      ContextCollectSheet(store: store) {
        searchText = ""
        insights = false
        showCollect = false
      }
    }
    .sheet(item: $selectedEntry) { entry in
      NavigationStack {
        ContextDetailScreen(store: store, entry: entry)
          .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
              Button {
                selectedEntry = nil
              } label: {
                Image(systemName: "xmark")
              }
              .accessibilityLabel("关闭详情")
            }
          }
      }.presentationDetents([.large]).presentationDragIndicator(.visible)
    }

  }
  private var understandingLabels: [(key: String, label: String)] {
    let labels = Set(store.insights.flatMap { $0.value["labels"].items.map(\.text) })
    return [("all", "全部")] + labels.sorted().map { ($0, $0) }
  }
  private var categoryPicker: some View {
    ScrollView(.horizontal, showsIndicators: false) {
      HStack(spacing: 9) {
        ForEach(insights ? understandingLabels : memorySources, id: \.key) { option in
          Button {
            Haptics.selection()
            Task {
              if insights {
                await store.load(category: option.key)
              } else {
                await store.load(source: option.key)
              }
            }
          } label: {
            Text(option.label).font(
              .subheadline.weight(
                (insights ? store.category : store.source) == option.key ? .semibold : .regular)
            )
            .padding(.horizontal, 12).frame(minHeight: 32)
            .foregroundStyle(
              (insights ? store.category : store.source) == option.key ? Brand.onAccent : Brand.ink
            )
            .background(
              (insights ? store.category : store.source) == option.key ? Brand.blue : Brand.mist,
              in: Capsule()
            )
            .frame(minHeight: 44)
          }.buttonStyle(.plain)
            .accessibilityAddTraits(
              (insights ? store.category : store.source) == option.key ? .isSelected : []
            )
            .accessibilityLabel("\(insights ? "分类" : "来源")，\(option.label)")
        }
      }
    }.dynamicTypeSize(...DynamicTypeSize.xxxLarge)
  }
  @ViewBuilder private var viewControls: some View {
    if typeSize.isAccessibilitySize {
      VStack(alignment: .trailing, spacing: 6) {
        layerPicker
      }
    } else {
      HStack(spacing: 12) {
        layerPicker
      }.frame(minHeight: 44)
    }
  }
  private var layerPicker: some View {
    Picker("记忆类型", selection: $insights) {
      Text("足迹").tag(false)
      Text("记住的事").tag(true)
    }.pickerStyle(.segmented).frame(maxWidth: .infinity).accessibilityIdentifier("context.tabs")
  }
  private var searchField: some View {
    HStack(spacing: 10) {
      Image(systemName: "magnifyingglass").foregroundStyle(Brand.muted)
      TextField("搜索你的记忆", text: $searchText)
        .submitLabel(.search).onSubmit {
          Task {
            await store.load(query: searchText.trimmingCharacters(in: .whitespacesAndNewlines))
          }
        }
        .accessibilityIdentifier("context.search")
      if !searchText.isEmpty {
        Button {
          searchText = ""
          Task { await store.load(query: "") }
        } label: {
          Image(systemName: "xmark.circle.fill").foregroundStyle(Brand.muted)
        }.accessibilityLabel("清除搜索").frame(minWidth: 44, minHeight: 44)
      }
    }.padding(.horizontal, 14).frame(minHeight: 48)
      .background(Brand.mist, in: RoundedRectangle(cornerRadius: 12))
      .dynamicTypeSize(...DynamicTypeSize.xxxLarge)
  }
  private var hasVisibleFilter: Bool {
    !store.query.isEmpty || (insights ? store.category != "all" : store.source != "all")
  }
  private var canViewFootprints: Bool {
    insights && store.records.contains { !$0.namespace.hasPrefix("apple_health") }
  }
  private var emptyActionTitle: String {
    if hasVisibleFilter { return store.query.isEmpty ? "查看全部" : "清除搜索与筛选" }
    return canViewFootprints ? "查看足迹" : "记一笔"
  }
  private var emptyState: some View {
    VStack(spacing: 16) {
      Image(systemName: insights ? "sparkle.magnifyingglass" : "bookmark")
        .font(.title2).foregroundStyle(Brand.blue)
      Text(hasVisibleFilter ? "这里暂时没有匹配的内容" : insights ? "理解会慢慢形成" : "留下第一条足迹")
        .font(.title3.weight(.semibold))
      Text(hasVisibleFilter ? "清除筛选，看看其他已经留下的内容。" :
        canViewFootprints ? "原文已保存在足迹中，不必等待整理就能查看。" :
        "想法、偏好，或一段值得保留的话，都可以从这里开始。")
        .font(.subheadline).foregroundStyle(Brand.muted).lineSpacing(4)
      Button(emptyActionTitle) {
        Haptics.selection()
        if hasVisibleFilter {
          searchText = ""
          Task { await store.load(query: "", category: "all", source: "all") }
        } else if canViewFootprints {
          insights = false
        } else {
          showCollect = true
        }
      }.buttonStyle(.borderedProminent).frame(minHeight: 44)
        .accessibilityIdentifier("context.empty.action")
    }.multilineTextAlignment(.center).frame(maxWidth: .infinity).padding(.vertical, 65)
  }

}

private struct ContextCard: View {
  let entry: ContextEntry
  @Environment(\.dynamicTypeSize) private var typeSize
  private var copy: (title: String, summary: String) {
    if !entry.title.isEmpty {
      let summary = entry.preview.trimmingCharacters(in: .whitespacesAndNewlines)
      return (entry.title, summary == entry.title.trimmingCharacters(in: .whitespacesAndNewlines) ? "" : summary)
    }
    guard let end = entry.preview.firstIndex(where: { "。！？!?\n".contains($0) })
    else {
      return (String(entry.preview.prefix(48)), entry.preview.count > 48 ? entry.preview : "")
    }
    let next = entry.preview.index(after: end)
    return (
      String(entry.preview[..<next]),
      String(entry.preview[next...]).trimmingCharacters(in: .whitespacesAndNewlines)
    )
  }
  var body: some View {
    Group {
      if entry.isInsight { understanding } else { footprint }
    }
    .padding(.horizontal, 0).padding(.vertical, 12)
    .overlay(alignment: .bottom) { Rectangle().fill(Brand.base).frame(height: 1) }
    .contentShape(Rectangle())
  }
  private var understanding: some View { cardContent }
  private var footprint: some View { cardContent }
  private var cardContent: some View {
    HStack(alignment: .top, spacing: 12) {
      ContextSourceIcon(entry: entry)
      VStack(alignment: .leading, spacing: 5) {
        Text(copy.title.isEmpty ? "查看内容" : copy.title)
          .font(.subheadline.weight(.medium)).foregroundStyle(Brand.ink)
          .lineLimit(typeSize.isAccessibilitySize ? nil : 2)
        if !copy.summary.isEmpty {
          Text(copy.summary).font(.caption).foregroundStyle(Brand.muted)
            .lineLimit(typeSize.isAccessibilitySize ? nil : 2)
        }
        ViewThatFits(in: .horizontal) {
          HStack {
            Text(entry.isInsight ? entry.topics.first ?? "记忆" : entry.sourceTitle)
            Spacer(minLength: 8)
            Text(entry.dateLabel)
          }.fixedSize(horizontal: true, vertical: false)
          VStack(alignment: .leading, spacing: 3) {
            Text(entry.isInsight ? entry.topics.first ?? "记忆" : entry.sourceTitle)
            Text(entry.dateLabel)
          }
        }.font(.caption).foregroundStyle(Brand.muted)
          .fixedSize(horizontal: false, vertical: true)
      }.frame(maxWidth: .infinity, alignment: .leading)
    }.frame(minHeight: 44)
  }
}

private struct ContextSourceIcon: View {
  let entry: ContextEntry
  private var insightSymbol: String {
    let domains = entry.value["domains"].items.map(\.text).joined(separator: " ")
    if domains.contains("health") { return "heart.text.clipboard" }
    if domains.contains("routine") { return "sun.horizon" }
    if entry.category == "work" { return "briefcase" }
    if entry.category == "learning" { return "book" }
    return "bookmark"
  }
  var body: some View {
    Group {
      if !entry.isInsight && entry.namespace.hasPrefix("gmail") { Image("GmailBrand").resizable().scaledToFit().padding(7) }
      else if !entry.isInsight && entry.namespace.hasPrefix("dida") { Image("DidaBrand").resizable().scaledToFit().padding(7) }
      else { Image(systemName: entry.isInsight ? insightSymbol : entry.sourceSymbol)
          .font(.system(size: 16, weight: .regular))
          .foregroundStyle(entry.namespace.hasPrefix("apple_health") ? Color.pink : Brand.blue) }
    }.frame(width: 34, height: 34).background(Brand.base, in: RoundedRectangle(cornerRadius: 10))
      .accessibilityHidden(true)
  }
}

private struct ContextCollectSheet: View {
  @ObservedObject var store: ContextStore
  let onSaved: () -> Void
  @Environment(\.dismiss) private var dismiss
  var body: some View {
    NavigationStack {
      VStack(alignment: .leading, spacing: 18) {
        Text("先留下原文，理解会慢慢形成。").font(.subheadline).foregroundStyle(Brand.muted)
        ZStack(alignment: .topLeading) {
          if store.draft.isEmpty {
            Text("想留下什么？").foregroundStyle(Brand.muted)
              .padding(.horizontal, 13).padding(.top, 16).allowsHitTesting(false)
          }
          TextEditor(text: $store.draft).scrollContentBackground(.hidden).font(.body)
            .frame(minHeight: 140, maxHeight: 300).padding(8)
            .accessibilityLabel("想保留的内容").accessibilityIdentifier("context.draft")
            .disabled(store.saving || store.pendingSave)
        }.background(Brand.mist, in: RoundedRectangle(cornerRadius: 12))
        if !store.saveError.isEmpty {
          Text(store.saveError).font(.footnote).foregroundStyle(Brand.ink).accessibilityAddTraits(
            .updatesFrequently)
        }
        HStack {
          Text("\(store.draft.count) / 16000").font(.caption).foregroundStyle(Brand.muted)
          Spacer()
          Button(store.saving ? "正在保存…" : store.pendingSave ? "重试保存" : "保存到足迹") {
            Task { if await store.save() { onSaved() } }
          }.buttonStyle(.borderedProminent)
            .disabled(
              store.saving || store.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                || store.draft.unicodeScalars.count > 16000
            )
            .accessibilityIdentifier("context.save")
        }
      }.padding(22).navigationTitle(store.correctionTarget == nil ? "记一笔" : "补充或纠正")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
          ToolbarItem(placement: .topBarTrailing) {
            Button("关闭") { dismiss() }.disabled(store.saving)
          }
        }
    }.presentationDetents([.medium, .large]).presentationDragIndicator(.visible)
      .interactiveDismissDisabled(
        store.saving)
  }
}

private struct ContextEvidence: Identifiable, Sendable {
  let id: String
  let entry: ContextEntry?
}

private struct ContextDetailScreen: View {
  @ObservedObject var store: ContextStore
  let entry: ContextEntry
  @State private var value: JSON = .null
  @State private var evidence: [ContextEvidence] = []
  @State private var loading = true
  @State private var error = ""
  @State private var evidenceLimit = 12
  @State private var evidenceTotal = 0
  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 22) {
        if loading {
          ProgressView("正在读取完整内容与依据…").padding(.vertical, 70)
        } else if !error.isEmpty {
          Text("暂时无法读取完整内容").font(.headline)
          Text(error).font(.subheadline).foregroundStyle(Brand.muted)
          Button("重试") { Task { await load() } }.frame(minHeight: 44)
        } else {
          if !entry.isInsight {
            HStack(alignment: .firstTextBaseline, spacing: 12) {
              Label(
                entry.isInsight ? entry.topics.first ?? "当前理解" : entry.sourceTitle,
                systemImage: entry.isInsight ? "sparkles" : entry.sourceSymbol
              ).font(.caption.weight(.medium)).foregroundStyle(Brand.blue)
              Spacer(minLength: 0)
              Text(entry.dateLabel).font(.caption).foregroundStyle(Brand.muted)
            }
          }
          if entry.isInsight {
            Text(entry.title.isEmpty ? "Hymio 的理解" : entry.title).font(.title2.weight(.bold))
            HStack {
              Text("当前理解").font(.headline)
              Spacer()
              Text("Hymio 的理解").font(.caption).foregroundStyle(Brand.muted)
            }
          }
          Text(contextContent(value).isEmpty ? "这条记录没有文字内容。" : contextContent(value))
            .font(.body).lineSpacing(6).foregroundStyle(Brand.ink)
            .textSelection(.enabled)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(18)
            .background(
              Brand.mist,
              in: RoundedRectangle(cornerRadius: 16))
          if !entry.isInsight && !value["context"]["memory"]["summary"].text.isEmpty {
            VStack(alignment: .leading, spacing: 12) {
              Label("提炼草稿", systemImage: "sparkles").font(.caption.weight(.medium)).foregroundStyle(
                Brand.blue)
              Text(value["context"]["memory"]["summary"].text).font(.body).lineSpacing(4)
              Text("与原文一起保留，尚未发布为理解。").font(.caption).foregroundStyle(Brand.muted)
            }.padding(16).frame(maxWidth: .infinity, alignment: .leading)
              .background(Brand.softBlue, in: RoundedRectangle(cornerRadius: 14))
          }
          if entry.isInsight {
            HStack {
              Text("原始依据（\(evidenceTotal)）").font(.headline)
              Spacer()

            }
            ContextEvidenceList(store: store, evidence: evidence)
            if evidenceTotal > evidenceLimit {
              Button("继续读取依据") {
                evidenceLimit += 12
                Task { await load() }
              }.frame(minHeight: 44)
            }
          }
          DisclosureGroup("来源信息") {
            VStack(alignment: .leading, spacing: 10) {
              Text("记录时间：\(value["created_at"].text.isEmpty ? "未提供" : value["created_at"].text)")
              if !value["produced_at"].text.isEmpty { Text("发生时间：\(value["produced_at"].text)") }
              Text(entry.sourceTitle)
            }.font(.caption).foregroundStyle(Brand.muted).padding(.top, 12)
          }.font(.subheadline)
        }
      }.padding(16).frame(maxWidth: 700).frame(maxWidth: .infinity, alignment: .leading)
    }.background(Brand.surface).toolbar(.visible, for: .navigationBar).navigationTitle(
      entry.isInsight ? "Hymio 的理解" : "原始足迹"
    )
    .navigationBarTitleDisplayMode(.inline).task(id: entry.compositeID) { await load() }
  }
  private func load() async {
    loading = true
    error = ""
    evidence = []
    do {
      let detail = try await store.detail(for: entry)
      evidenceTotal = detail["references"].items.count
      let sources = await contextEvidence(store: store, value: detail, limit: evidenceLimit)
      guard !Task.isCancelled else { return }
      value = detail
      evidence = sources
    } catch { if !Task.isCancelled { self.error = "请稍后再试。" } }
    loading = false
  }
}

private struct ContextEvidenceList: View {
  @ObservedObject var store: ContextStore
  let evidence: [ContextEvidence]
  var body: some View {
    if evidence.isEmpty {
      Text("这条理解暂时没有可展示的原始关联。").font(.subheadline).foregroundStyle(Brand.muted)
    }
    ForEach(evidence) { reference in
      if let entry = reference.entry {
        NavigationLink {
          ContextDetailScreen(store: store, entry: entry)
        } label: {
          VStack(alignment: .leading, spacing: 12) {
            Label(entry.sourceTitle, systemImage: entry.sourceSymbol).font(.caption)
              .foregroundStyle(Brand.blue)
            if !entry.title.isEmpty { Text(entry.title).font(.headline).foregroundStyle(Brand.ink) }
            Text(entry.preview.isEmpty ? "无文字内容" : entry.preview).font(.subheadline)
              .foregroundStyle(Brand.ink)
              .lineLimit(3).lineSpacing(4).frame(maxWidth: .infinity, alignment: .leading)
            HStack {
              Text(entry.dateLabel)
              Spacer()
              Label("查看原文", systemImage: "chevron.right")
            }
            .font(.caption).foregroundStyle(Brand.blue)
          }.padding(16).background(Brand.mist, in: RoundedRectangle(cornerRadius: 14))
        }.buttonStyle(GentlePress())
      } else {
        VStack(alignment: .leading, spacing: 8) {
          Label("这条原始依据暂时无法读取。", systemImage: "exclamationmark.circle")
          NavigationLink("重新打开原始依据") {
            ContextDetailScreen(
              store: store,
              entry: ContextEntry(
                .object(["id": .string(reference.id), "kind": .string("record")])))
          }.frame(minHeight: 44)
        }.font(.footnote).foregroundStyle(Brand.muted)
      }
    }
  }
}

private let relationNames = [
  "supports": "支撑", "supplements": "补充", "related": "相关", "contradicts": "矛盾", "supersedes": "取代",
  "navigates": "关联",
]

@MainActor private func contextEvidence(store: ContextStore, value: JSON, limit: Int) async
  -> [ContextEvidence]
{
  var seen = Set<String>()
  let ids = value["references"].items.map { $0["record_id"].text }.filter {
    !$0.isEmpty && seen.insert($0).inserted
  }
  return await withTaskGroup(of: (Int, ContextEvidence).self) { group in
    for (index, id) in ids.prefix(limit).enumerated() {
      group.addTask {
        let entry = try? await store.original(id)
        return (index, ContextEvidence(id: id, entry: entry))
      }
    }
    var result: [(Int, ContextEvidence)] = []
    for await entry in group { result.append(entry) }
    return result.sorted { $0.0 < $1.0 }.map { $0.1 }
  }
}

private func contextContent(_ value: JSON) -> String {
  if value["source"]["namespace"].text.hasPrefix("apple_health") {
    let context = value["context"]
    var lines = ["苹果健康 · " + context["day"].text]
    if context["steps"] != .null { lines.append("步数：\(Int(context["steps"].double)) 步") }
    if context["active_kcal"] != .null { lines.append("活动能量：\(Int(context["active_kcal"].double)) 千卡") }
    return lines.joined(separator: "\n")
  }
  if !value["content"].text.isEmpty { return value["content"].text }
  for key in ["text", "content", "title"] {
    if !value["context"][key].text.isEmpty { return value["context"][key].text }
  }
  return ""
}
private func connectorName(_ namespace: String) -> String {
  let lower = namespace.lowercased()
  if lower.contains("apple_calendar") { return "苹果日历" }
  if lower.contains("calendar") { return "日历" }
  if lower.contains("gmail") { return "Gmail" }
  if lower.contains("mail") { return "邮件" }
  if lower.contains("figma") { return "Figma" }
  if lower.contains("notion") { return "Notion" }
  if lower.contains("github") { return "GitHub" }
  if lower.hasPrefix("apple_health") { return "苹果健康" }
  if lower.hasPrefix("dida") { return "滴答清单" }
  return "其他来源"
}

private func connectorSymbol(_ namespace: String) -> String {
  let lower = namespace.lowercased()
  if lower.contains("apple_health") { return "heart.fill" }
  if lower.contains("dida") { return "checkmark.circle.fill" }
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
  return ""
}

private func contextDate(_ value: String) -> Date? {
  let fractional = ISO8601DateFormatter()
  fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
  return fractional.date(from: value) ?? ISO8601DateFormatter().date(from: value)
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

extension ToolbarContent {
  @ToolbarContentBuilder fileprivate func memoryUnframed() -> some ToolbarContent {
    if #available(iOS 26.0, *) {
      self.sharedBackgroundVisibility(.hidden)
    } else {
      self
    }
  }
}
