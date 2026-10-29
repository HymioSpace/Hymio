import Combine
import CryptoKit
import SwiftUI

@MainActor final class TaskBoard: ObservableObject {
  @Published var items: [JSON] = []
  @Published var suggestions: [JSON] = []
  @Published var loaded = false
  @Published var error = ""
  @Published private(set) var changes: [JSON] = []
  private var loading = false
  @Published private var baseline: [String: String]?
  private var owner = ""
  private var key: String { "hymio.task-baseline." + owner }
  func bind(_ account: AccountService) {
    let next = account.backend.absoluteString + "|" + (account.session?.user_id ?? "")
    guard next != owner else { return }
    owner = next
    items = []
    suggestions = []
    loaded = false
    error = ""
    changes = []
    baseline = UserDefaults.standard.dictionary(forKey: key) as? [String: String]
    rebuildChanges()
  }
  private func fingerprint(_ item: JSON) -> String {
    let run = item["runs"].items.first ?? .null
    // List responses omit notes and truncate prose; use their shared server revision.
    let text = [
      String(item["updated_at"].double), item["state"].text, item["title"].text,
      run["id"].text, run["status"].text,
    ].joined(separator: "\u{1F}")
    return SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined()
  }
  var hasBaseline: Bool { baseline != nil }
  private func rebuildChanges() {
    guard let baseline else {
      changes = Array(
        items.filter { ["succeeded", "blocked", "failed"].contains(taskStatus($0)) }.prefix(2))
      return
    }
    changes = items.filter { baseline[$0["id"].text] != fingerprint($0) }
  }
  func markSeen(_ item: JSON) {
    guard loaded, !item["id"].text.isEmpty else { return }
    let stamp = fingerprint(item)
    guard baseline?[item["id"].text] != stamp else { return }
    var values = baseline ?? [:]
    values[item["id"].text] = stamp
    baseline = values
    rebuildChanges()
    remember()
  }
  func remember() {
    guard let baseline else { return }
    UserDefaults.standard.set(baseline, forKey: key)
  }
  func refresh(_ account: AccountService) async {
    guard !loading else { return }
    loading = true
    let user = account.session?.user_id
    defer { loading = false }
    do {
      let result = try await account.request("tasks")
      guard user == account.session?.user_id, !Task.isCancelled else { return }
      let nextSuggestions = result["suggestions"].items
      if suggestions != nextSuggestions { suggestions = nextSuggestions }
      let next = result["tasks"].items
      if items != next {
        items = next
        rebuildChanges()
      }
      if !loaded { loaded = true }
      if !error.isEmpty { error = "" }
    } catch is CancellationError {
    } catch { if user == account.session?.user_id { self.error = "暂时无法读取进展。" } }
  }
}

enum ProductTab: Hashable { case today, chat, tasks, moments, kits }

struct ProductShell: View, Equatable {
  static func == (lhs: Self, rhs: Self) -> Bool {
    lhs.account === rhs.account && lhs.client === rhs.client && lhs.previewMode == rhs.previewMode
  }
  @ObservedObject var account: AccountService
  let client: AgentClient
  var previewMode = false
  @EnvironmentObject private var notifications: PushNotificationManager
  @StateObject private var board = TaskBoard()
  @State private var selected: ProductTab = .today
  @State private var notificationTask: JSON?
  @State private var showAccount = false
  @State private var showTasks = false
  @State private var showKits = false
  @Environment(\.scenePhase) private var scene

  var body: some View {
    TabView(selection: $selected) {
      Tab("此刻", systemImage: "house.fill", value: ProductTab.today) {
        HomeScreen(
          account: account, client: client, board: board, selected: $selected,
          onAccount: { showAccount = true }, onTasks: { showTasks = true }, onKits: { showKits = true })
      }
      Tab("对话", systemImage: "bubble.left.and.bubble.right.fill", value: ProductTab.chat) {
        ChatScreen(account: account, client: client, onAccount: { showAccount = true })
      }
      Tab("回忆", systemImage: "book.closed.fill", value: ProductTab.moments) {
        ContextScreen(account: account, onAccount: { showAccount = true })
      }

    }
    .toolbarBackground(.ultraThinMaterial, for: .tabBar)
    .task(id: scene) {
      #if DEBUG
      if previewMode { installExperienceFixture(board); return }
      #endif
      board.bind(account)
      guard scene == .active else { return }
      while !Task.isCancelled {
        await board.refresh(account)
        do { try await Task.sleep(for: .seconds(60)) } catch { return }
      }
    }
    .onChange(of: selected) { _, _ in Haptics.selection(); if !previewMode { Task { await board.refresh(account) } } }
    .onChange(of: notifications.destination) { _, destination in
      open(destination)
    }
    .onAppear { open(notifications.destination) }
    .overlay(alignment: .bottom) {
      ShellAgentStatus(account: account, client: client, board: board, selected: $selected)
    }
    .sheet(isPresented: $showAccount) {
      AccountScreen(account: account, client: client)
    }
    .sheet(isPresented: $showTasks) {
      NavigationStack { TasksScreen(account: account, board: board, onAccount: {}, showAccountButton: false)
        .toolbar { ToolbarItem(placement: .cancellationAction) { Button("完成") { showTasks = false } } } }
    }
    .sheet(isPresented: $showKits) { KitsScreen(account: account, onAccount: {}, showAccountButton: false) }
    .sheet(isPresented: Binding(get: { notificationTask != nil }, set: { if !$0 { notificationTask = nil } })) {
      if let item = notificationTask {
        NavigationStack { TaskDetailScreen(account: account, taskID: item["id"].text, initial: item) }
      }
    }
  }

  private func open(_ destination: AppDestination?) {
    guard let destination else { return }
    switch destination {
    case .task(let id):
      notificationTask = .object(["id": .string(id)])
    case .chat:
      selected = .chat
    }
    notifications.consume(destination)
  }
}

enum TaskLane: Hashable {
  case attention, active, scheduled, inbox, finished
}

func taskLane(_ item: JSON) -> TaskLane {
  let status = taskStatus(item)
  if ["blocked", "failed"].contains(status) { return .attention }
  if ["running", "ready", "delivering"].contains(status) { return .active }
  if ["succeeded", "cancelled", "expired"].contains(status) { return .finished }
  if ["now", ""].contains(item["schedule"]["mode"].text) { return .inbox }
  return .scheduled
}

func taskSortDate(_ item: JSON) -> Double {
  if let due = item["runs"].items.first?["due_at"].double, due > 0 { return due }
  if item["schedule"]["mode"].text == "once" {
    let text = item["schedule"]["at"].text
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    if let date = formatter.date(from: text) ?? ISO8601DateFormatter().date(from: text) {
      return date.timeIntervalSince1970
    }
  }
  return .greatestFiniteMagnitude
}

struct HomeScreen: View {
  @ObservedObject var account: AccountService
  let client: AgentClient
  @ObservedObject var board: TaskBoard
  @Binding var selected: ProductTab
  let onAccount: () -> Void
  var onTasks: () -> Void = {}
  var onKits: () -> Void = {}
  @State private var applications: [JSON] = []
  @State private var openedTask: JSON?
  @State private var agent = HomeAgentSnapshot()
  @State private var decisionPage: String?
  @State private var allDecisions = false
  private struct Decision: Identifiable {
    let id: String
    let title: String
    let detail: String
    let task: JSON?
  }
  private var decisions: [Decision] {
    pendingApprovals.map { Decision(id: "approval-" + $0.id, title: $0.title, detail: $0.summary, task: nil) }
      + attention.map { item in
        let run = item["runs"].items.first ?? .null
        let detail = [run["next_step"].text, run["progress"].text, item["objective"].text].first { !$0.isEmpty } ?? ""
        return Decision(id: item["id"].text, title: item["title"].text, detail: detail, task: item)
      }
  }

  private var attention: [JSON] {
    board.items.filter { taskLane($0) == .attention }
      .sorted { taskSortDate($0) < taskSortDate($1) }
  }
  private var active: [JSON] {
    board.items.filter { taskLane($0) == .active }
  }
  private var upcoming: [JSON] {
    board.items.filter { taskLane($0) == .scheduled && $0["for_user"].flag }
      .sorted { taskSortDate($0) < taskSortDate($1) }
  }
  private var recent: [JSON] {
    let primary = Set((attention + active + upcoming).map { $0["id"].text })
    return board.changes.filter { !primary.contains($0["id"].text) }
  }
  private var pendingApprovals: [Approval] {
    agent.approvals.filter {
      $0.status == "pending" && $0.expires > Date().timeIntervalSince1970
    }
  }
  private var needsAttention: Int {
    attention.count + pendingApprovals.count
  }
  @Environment(\.dynamicTypeSize) private var typeSize
  private var focusTask: JSON? { attention.first ?? upcoming.first ?? recent.first }
  private var focusTitle: String {
    if let approval = pendingApprovals.first { return approval.title }
    if let task = focusTask { return task["title"].text }
    return agent.working ? "正在替你处理。" : "有什么想做的？"
  }
  private var focusLabel: String {
    if !pendingApprovals.isEmpty || !attention.isEmpty { return "等你决定" }
    if !upcoming.isEmpty { return "下一项安排" }
    if !recent.isEmpty { return "刚刚完成" }
    return "此刻"
  }
  private var focusDetail: String {
    if let approval = pendingApprovals.first { return approval.summary }
    if let task = focusTask {
      let run = task["runs"].items.first ?? .null
      return [run["next_step"].text, run["result"].text, run["progress"].text, task["objective"].text].first { !$0.isEmpty } ?? ""
    }
    return "说个想法，或把眼前的事交给 Hymio。"
  }
  private func openFocus() {
    Haptics.selection()
    if !pendingApprovals.isEmpty { selected = .chat }
    else if let task = focusTask { openedTask = task }
    else { selected = .chat }
  }
  var body: some View {
    NavigationStack {
      ScrollView {
        VStack(alignment: .leading, spacing: 24) {
          HStack(alignment: .center) {
            VStack(alignment: .leading, spacing: 6) {
              Text(Date.now.formatted(.dateTime.weekday(.wide))).font(.caption).foregroundStyle(Brand.muted)
              Text(Date.now.formatted(.dateTime.month().day())).font(.system(.largeTitle, design: .default, weight: .semibold)).tracking(-1.5)
            }
            Spacer()
            VStack(spacing: 5) {
              Companion(size: 52, mood: agent.working ? .working : .greeting)
              Text(agent.working ? "正在忙" : "在这里").font(.system(size: 10)).foregroundStyle(Brand.muted)
            }
          }.padding(.top, 12)
          if !decisions.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
              HStack {
                Text("等你决定").font(.subheadline.weight(.semibold)).foregroundStyle(Brand.attention)
                Spacer()
                Button("查看全部 · \(decisions.count)") { allDecisions = true }
                  .font(.caption).frame(minHeight: 36).accessibilityIdentifier("home.decisions.all")
              }
              ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 12) {
                  ForEach(decisions) { item in
                    decisionCard(item).containerRelativeFrame(.horizontal).id(item.id)
                  }
                }.scrollTargetLayout()
              }.scrollTargetBehavior(.viewAligned).scrollPosition(id: $decisionPage)
                .accessibilityIdentifier("home.decisions")
              if decisions.count > 1 {
                HStack(spacing: 6) {
                  ForEach(Array(decisions.prefix(7))) { item in
                    Circle().fill((decisionPage ?? decisions.first?.id) == item.id ? Brand.blue : Brand.line)
                      .frame(width: 5, height: 5)
                  }
                  Spacer()
                  Text("左右滑动查看").font(.caption2).foregroundStyle(Brand.muted)
                }.accessibilityLabel("共 \(decisions.count) 项待决定，可左右滑动")
              }
            }
          } else {
          Button(action: openFocus) {
            VStack(alignment: .leading, spacing: 20) {
              HStack {
                Label(focusLabel, systemImage: needsAttention > 0 ? "hand.raised" : "circle.dotted")
                  .font(.caption.weight(.medium)).foregroundStyle(needsAttention > 0 ? Brand.attention : Brand.muted)
                Spacer()

              }
              Text(focusTitle).font(.title2.weight(.semibold)).tracking(-0.6)
                .foregroundStyle(Brand.ink).multilineTextAlignment(.leading).lineLimit(typeSize.isAccessibilitySize ? nil : 3)
              if !focusDetail.isEmpty {
                Text(focusDetail).font(.subheadline).foregroundStyle(Brand.muted).lineSpacing(4)
                  .multilineTextAlignment(.leading).lineLimit(typeSize.isAccessibilitySize ? nil : 2)
              }
              HStack {
                Text(needsAttention > 0 ? "看一下" : focusTask == nil ? "开始对话" : "查看详情").font(.subheadline.weight(.medium))
                Spacer()
                Image(systemName: "arrow.up.right").font(.system(size: 17, weight: .medium))
              }.foregroundStyle(Brand.blue).padding(.top, 6)
            }.padding(24).frame(maxWidth: .infinity, alignment: .leading)
              .background(Brand.raised, in: RoundedRectangle(cornerRadius: 26))
              .overlay(RoundedRectangle(cornerRadius: 26).strokeBorder(Brand.line.opacity(0.8), lineWidth: 0.7))
          }.buttonStyle(.plain).accessibilityIdentifier("home.focus")
          }
          if typeSize.isAccessibilitySize {
            VStack(spacing: 12) { scheduleTile; agentTile }
          } else {
            EqualHeightColumns { scheduleTile; agentTile }
          }
          if !applications.isEmpty { commonApplications }
          if let idea = board.suggestions.first { inspiration(idea) }
          if !board.error.isEmpty {
            Button("暂时未能更新，点击重试") { Task { await board.refresh(account) } }
              .font(.caption).foregroundStyle(Brand.muted).frame(minHeight: 44)
          }
        }.padding(.horizontal, 22).padding(.bottom, 28).frame(maxWidth: 620).frame(maxWidth: .infinity)
      }
      .background(Brand.base)
      .onReceive(client.$ready.combineLatest(client.$phase, client.$model).map(HomeAgentSnapshot.init).removeDuplicates()) { agent = $0 }
      .task {
        if let result = try? await account.request("kits") {
          applications = Array(result["kits"].items.filter { $0["installed"].flag }.prefix(4))
        }
      }
      .navigationTitle("").navigationBarTitleDisplayMode(.inline)
      .toolbarBackground(.regularMaterial, for: .navigationBar)
      .toolbar { ToolbarItem(placement: .topBarLeading) { AccountButton(account: account, action: onAccount) }.accountUnframed() }
      .refreshable { await board.refresh(account) }
      .sheet(isPresented: $allDecisions) {
        NavigationStack {
          ScrollView {
            LazyVStack(spacing: 12) { ForEach(decisions) { decisionCard($0) } }.padding(20)
          }.background(Brand.base).navigationTitle("等你决定").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("关闭") { allDecisions = false } } }
        }
      }
      .navigationDestination(item: $openedTask) { item in
        TaskDetailScreen(account: account, taskID: item["id"].text, initial: item, onViewed: { board.markSeen($0) })
      }
    }
  }
  private func decisionCard(_ item: Decision) -> some View {
    Button {
      Haptics.selection()
      allDecisions = false
      if let task = item.task { openedTask = task } else { selected = .chat }
    } label: {
      VStack(alignment: .leading, spacing: 16) {
        HStack {
          Image(systemName: "hand.raised").foregroundStyle(Brand.attention)
          Spacer()
          Text("\((decisions.firstIndex { $0.id == item.id } ?? 0) + 1) / \(decisions.count)")
            .font(.caption).monospacedDigit().foregroundStyle(Brand.muted)
        }
        Text(item.title).font(.title2.weight(.semibold)).foregroundStyle(Brand.ink)
          .lineLimit(typeSize.isAccessibilitySize ? nil : 3).multilineTextAlignment(.leading)
        Text(item.detail).font(.subheadline).foregroundStyle(Brand.muted)
          .lineLimit(typeSize.isAccessibilitySize ? nil : 2).multilineTextAlignment(.leading)
        HStack { Text("看一下"); Spacer(); Image(systemName: "arrow.up.right") }
          .font(.subheadline.weight(.medium)).foregroundStyle(Brand.blue)
      }.padding(22).frame(maxWidth: .infinity, minHeight: 200, alignment: .topLeading)
        .background(Brand.raised, in: RoundedRectangle(cornerRadius: 24))
        .overlay(RoundedRectangle(cornerRadius: 24).strokeBorder(Brand.line, lineWidth: 0.7))
    }.buttonStyle(.plain).accessibilityIdentifier("home.focus")
  }

  private var scheduleTile: some View {
    Button { Haptics.selection(); onTasks() } label: {
      VStack(alignment: .leading, spacing: 10) {
        HStack { Text("接下来").font(.caption); Spacer(); Image(systemName: "arrow.up.right").font(.caption2) }.foregroundStyle(Brand.muted)
        if let item = upcoming.first {
          let due = taskSortDate(item)
          Text(due.isFinite ? Date(timeIntervalSince1970: due).formatted(.dateTime.hour().minute()) : "待定")
            .font(.system(.title, design: .rounded, weight: .medium)).foregroundStyle(Brand.ink)
          Text(item["title"].text).font(.caption).foregroundStyle(Brand.muted).lineLimit(2)
        } else {
          HStack(spacing: 6) {
            FeatureArtwork(kind: .notebook, size: 36)
            Text("留一点空白").font(.headline).foregroundStyle(Brand.ink)
          }
          Text("有想记住的事，随时安排。")
            .font(.caption).foregroundStyle(Brand.muted).fixedSize(horizontal: false, vertical: true)
          Text("安排一件事").font(.caption.weight(.medium)).foregroundStyle(Brand.blue)

        }
      }.frame(maxWidth: .infinity, minHeight: 136, maxHeight: .infinity, alignment: .topLeading).padding(18)
        .background(Brand.surface, in: RoundedRectangle(cornerRadius: 22))
    }.buttonStyle(.plain).accessibilityIdentifier("home.schedule")
  }
  private var agentTile: some View {
    Button { Haptics.selection(); selected = .chat } label: {
      VStack(alignment: .leading, spacing: 10) {
        HStack { Text("Hymio").font(.caption); Spacer(); Image(systemName: "arrow.up.right").font(.caption2) }.foregroundStyle(Brand.muted)
        Text(!active.isEmpty || agent.working ? "正在推进" : "最近进展").font(.headline).foregroundStyle(Brand.ink)
          .frame(minHeight: upcoming.isEmpty ? 36 : 0, alignment: .leading)
        Text((active.first ?? recent.first)?["title"].text ?? (agent.working ? "有新结果时告诉你。" : agent.lastReply.isEmpty ? "暂时没有新的进展。" : agent.lastReply))
          .font(.caption).foregroundStyle(Brand.muted).lineLimit(2).multilineTextAlignment(.leading)
        Capsule().fill(Brand.blue.opacity(agent.working || !active.isEmpty ? 0.7 : 0.15)).frame(width: 32, height: 2)
      }.frame(maxWidth: .infinity, minHeight: 136, maxHeight: .infinity, alignment: .topLeading).padding(18)
        .background(Brand.surface, in: RoundedRectangle(cornerRadius: 22))
    }.buttonStyle(.plain).accessibilityIdentifier("home.agent")
  }
  private func inspiration(_ idea: JSON) -> some View {
    VStack(alignment: .leading, spacing: 14) {
      HStack { Image(systemName: "lightbulb").font(.subheadline); Text("灵感").font(.caption.weight(.medium)); Spacer() }.foregroundStyle(Brand.attention)
      Text(idea["proposal"]["title"].text).font(.headline).foregroundStyle(Brand.ink)
      Text(idea["proposal"]["reason"].text).font(.caption).foregroundStyle(Brand.muted).lineSpacing(3).lineLimit(3)
      HStack {
        Button("聊聊这个") {
          Haptics.selection(); selected = .chat
          Task { do { try await client.message("想聊聊：" + idea["proposal"]["title"].text) }
            catch { client.error = "暂时未能发送，想法仍保留在此刻。" } }
        }.font(.caption.weight(.medium)).foregroundStyle(Brand.blue).frame(minHeight: 44)
        Spacer()
        Button("暂不需要") { Task { await handleSuggestion(idea, accept: false) } }.font(.caption).foregroundStyle(Brand.muted).frame(minHeight: 44)
      }
    }.padding(22).frame(maxWidth: .infinity, alignment: .leading)
      .background(Brand.paper, in: RoundedRectangle(cornerRadius: 22))
  }

  private var commonApplications: some View {
    VStack(alignment: .leading, spacing: 14) {
      HStack { Text("常用应用").font(.subheadline.weight(.semibold)); Spacer(); Button("全部", action: onKits).font(.caption).frame(minHeight: 44) }
      HStack(spacing: 12) {
        ForEach(applications, id: \.["id"]) { item in
          NavigationLink { KitAppScreen(account: account, item: item) } label: {
            VStack(spacing: 8) {
              Image(systemName: "square.stack.3d.up.fill").font(.title3).frame(width: 48, height: 48)
                .foregroundStyle(Brand.blue).background(Brand.softBlue, in: RoundedRectangle(cornerRadius: 14))
              Text(item["title"].text.isEmpty ? item["name"].text : item["title"].text).font(.caption).foregroundStyle(Brand.ink).lineLimit(1)
            }.frame(maxWidth: .infinity)
          }.buttonStyle(.plain)
        }
      }
    }.padding(.top, 22)
  }

  private func handleSuggestion(_ item: JSON, accept: Bool) async {
    do {
      _ = try await account.request(
        "tasks",
        body: .object([
          "action": .string(accept ? "accept_suggestion" : "dismiss_suggestion"),
          "suggestion_id": .string(item["id"].text),
        ]))
      await board.refresh(account)
    } catch { board.error = "这次操作未完成，请重试。" }
  }
}

private struct HomeAgentSnapshot: Equatable {
  var connected = false
  var phase = "未连接"
  var approvals: [Approval] = []
  var working = false
  var awaitingReply = false
  var messagesEmpty = true
  var lastReply = ""

  init() {}
  init(ready: Bool, phase: String, model: Conversation) {
    connected = ready
    self.phase = phase
    approvals = model.approvals
    working = model.working
    awaitingReply = model.awaitingReply
    messagesEmpty = model.messages.isEmpty
    lastReply = String((model.messages.last { $0.role == "assistant" && !$0.streaming && !$0.content.isEmpty }?.content ?? "").prefix(100))
  }
}

struct TaskSummaryCard: View {
  let item: JSON
  private var state: String { taskStatus(item) }
  private var run: JSON { item["runs"].items.first ?? .null }
  private var attention: Bool { ["blocked", "failed"].contains(state) }
  var body: some View {
    VStack(alignment: .leading, spacing: 10) {
      HStack(alignment: .firstTextBaseline) {
        Text(item["title"].text).font(.body.weight(.semibold)).foregroundStyle(Brand.ink).lineLimit(
          2)
        Spacer(minLength: 12)
        Label(taskLabel(state), systemImage: taskSymbol(state)).font(.caption2.weight(.medium))
          .foregroundStyle(
            attention ? Brand.attention : state == "running" ? Brand.blue : Brand.muted
          )
          .fixedSize(horizontal: false, vertical: true)
      }
      let description =
        [run["result"].text, run["progress"].text, item["objective"].text].first { !$0.isEmpty }
        ?? ""
      Text(description).font(.subheadline).foregroundStyle(Brand.muted).lineLimit(2)
        .multilineTextAlignment(.leading)
      if !run["next_step"].text.isEmpty {
        Text("下一步：" + run["next_step"].text).font(.caption).foregroundStyle(Brand.muted).lineLimit(
          2)
      } else if ["scheduled", "ready", "paused"].contains(state) {
        Label(taskSchedule(item["schedule"]), systemImage: "calendar").font(.caption)
          .foregroundStyle(Brand.muted)
      }
    }.frame(maxWidth: .infinity, alignment: .leading).padding(.vertical, 14)
      .overlay(alignment: .bottom) { Rectangle().fill(Brand.base).frame(height: 1) }

  }
}

func taskSymbol(_ state: String) -> String {
  switch state {
  case "blocked", "failed": return "exclamationmark.circle"
  case "running", "delivering", "ready": return "circle.dotted"
  case "succeeded": return "checkmark.circle"
  case "paused": return "pause.circle"
  case "expired", "cancelled": return "minus.circle"
  default: return "clock"
  }
}

#if DEBUG
@MainActor private func installExperienceFixture(_ board: TaskBoard) {
      guard !board.loaded else { return }
      var calendar = Calendar.current
      calendar.firstWeekday = 2
      let today = calendar.startOfDay(for: Date())
      func date(day: Int, hour: Int, minute: Int = 0) -> Date {
        calendar.date(
          bySettingHour: hour, minute: minute, second: 0,
          of: calendar.date(byAdding: .day, value: day, to: today)!)!
      }
      func task(
        _ id: String, _ title: String, _ state: String, _ status: String,
        at value: Date?, progress: String, next: String = ""
      ) -> JSON {
        .object([
          "id": .string(id), "title": .string(title),
          "objective": .string(progress), "state": .string(state), "kind": .string("task"),
          "for_user": .bool(value != nil),
          "source": .string("conversation"),
          "schedule": value.map {
            .object([
              "mode": .string("once"), "timezone": .string(TimeZone.current.identifier),
              "at": .string(ISO8601DateFormatter().string(from: $0)),
            ])
          } ?? .object(["mode": .string("now")]),
          "runs": .array([
            .object([
              "id": .string("run-\(id)"), "status": .string(status),
              "progress": .string(progress), "next_step": .string(next),
              "wait_reason": .string(status == "blocked" ? "user" : ""),
              "due_at": .number(value?.timeIntervalSince1970 ?? 0),
            ])
          ]),
        ])
      }
      board.items = [
        task(
          "hotel", "确认周五住哪家酒店", "active", "blocked", at: date(day: 0, hour: 9),
          progress: "两家酒店的位置和价格已经整理好。", next: "选一家后我来订房"),
        task(
          "cloud", "比较两家云服务方案", "active", "running", at: date(day: 0, hour: 11, minute: 30),
          progress: "正在核对带宽、价格和迁移成本。", next: "整理成一张决策表"),
        task(
          "walk", "傍晚出去走一圈", "active", "scheduled", at: date(day: 0, hour: 18),
          progress: "已避开最忙的时段。"),
        task(
          "reading", "整理下周阅读清单", "active", "scheduled", at: date(day: 1, hour: 10),
          progress: "从近期收藏里筛出真正想读的内容。"),
        task(
          "notes", "把零散想法收进一个笔记", "active", "scheduled", at: nil,
          progress: "没有明确时间，先留在待安排。"),
        task(
          "done", "更新周末出行清单", "succeeded", "succeeded", at: date(day: -1, hour: 16),
          progress: "清单已整理，缺少的物品已经补齐。"),
      ]
      board.suggestions = [
        .object([
          "id": .string("suggestion-1"),
          "proposal": .object([
            "title": .string("给下周留一个不看消息的下午"),
            "reason": .string("最近连续几天都有密集安排，也许需要一段完整时间。"),
          ]),
        ])
      ]
      board.loaded = true
}

struct PersonalExperiencePreview: View {
  let account: AccountService
  @StateObject private var client: AgentClient
  init(account: AccountService) {
    self.account = account
    _client = StateObject(wrappedValue: AgentClient(account: account, previewConnected: true))
  }
  var body: some View { ProductShell(account: account, client: client, previewMode: true) }
}

struct HomeExperiencePreview: View {
  let account: AccountService
  @StateObject private var board = TaskBoard()
  @StateObject private var client: AgentClient
  @State private var selected = ProductTab.today
  init(account: AccountService) {
    self.account = account
    _client = StateObject(wrappedValue: AgentClient(account: account, previewConnected: true))
  }
  var body: some View {
    NavigationStack {
      HomeScreen(
        account: account, client: client, board: board, selected: $selected,
        onAccount: {})
    }
    .onAppear {
      installExperienceFixture(board)
      if ProcessInfo.processInfo.arguments.contains("-HymioHomeEmpty") {
        board.items = []; board.suggestions = []
      } else if ProcessInfo.processInfo.arguments.contains("-HymioHomeManyDecisions"),
        case .object(let first) = board.items.first {
        let titles = ["确认周五住哪家酒店", "选一个周末出行方向", "确认下一周的空闲时间", "选定这次阅读的主题", "确认要保留的应用"]
        board.items = titles.enumerated().map { index, title in
          var value = first
          value["id"] = .string("decision-\(index)"); value["title"] = .string(title)
          return .object(value)
        }
      }
    }
  }
}
#endif

private struct AgentStatusSnapshot: Equatable {
  var approvals: [Approval] = []
  var working = false
  var awaitingReply = false
  init(_ model: Conversation) {
    approvals = model.approvals
    working = model.working
    awaitingReply = model.awaitingReply
  }
}

/// Streaming observation stays here; only status-bearing fields invalidate this overlay.
private struct ShellAgentStatus: View {
  let account: AccountService
  let client: AgentClient
  @ObservedObject var board: TaskBoard
  @Binding var selected: ProductTab
  @StateObject private var liveActivity = LiveActivityController()
  @State private var status = AgentStatusSnapshot(Conversation(events: []))
  @Environment(\.scenePhase) private var scene
  private func pendingApproval(at date: Date) -> Approval? {
    status.approvals.first {
      $0.status == "pending" && $0.expires > date.timeIntervalSince1970
    }
  }
  private func expiredApproval(at date: Date) -> Approval? {
    status.approvals.first {
      $0.status == "pending" && $0.expires <= date.timeIntervalSince1970
    }
  }
  var body: some View {
      TimelineView(.periodic(from: .now, by: 1)) { timeline in
        let approval = pendingApproval(at: timeline.date)
        let expired = expiredApproval(at: timeline.date) != nil
        Group {
          if selected != .chat, let approval {
            Button {
              selected = .chat
            } label: {
              HStack(spacing: 10) {
                Image(systemName: "hand.raised")
                  .font(.system(size: 16, weight: .medium))
                  .foregroundStyle(.secondary)
                VStack(alignment: .leading, spacing: 2) {
                  Text("需要你的确认").font(.caption.weight(.semibold))
                  Text(approval.title)
                    .font(.caption2).foregroundStyle(.secondary).lineLimit(1)
                }
                Spacer(minLength: 8)
                Image(systemName: "chevron.right")
                  .font(.caption.weight(.semibold)).foregroundStyle(.secondary)
              }
              .padding(.horizontal, 14)
              .frame(minHeight: 54)
              .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 18))
              .overlay(
                RoundedRectangle(cornerRadius: 18)
                  .stroke(Color(uiColor: .separator).opacity(0.24), lineWidth: 0.5)
              )
              .shadow(color: .black.opacity(0.12), radius: 14, y: 6)
            }
            .buttonStyle(.plain)
            .padding(.horizontal, 16)
            .padding(.bottom, 72)
            .accessibilityHint("打开对话处理授权")
          } else {
            Color.clear.frame(width: 0, height: 0)
          }
        }
        .task(id: "\(approval?.id ?? "")|\(expired)") {
          await liveActivity.sync(
            account: account, items: board.items, chatWorking: status.working,
            chatAwaiting: status.awaitingReply, chatApproval: approval?.title,
            expiredApproval: expired)
        }
      }
    .onReceive(client.$model.map(AgentStatusSnapshot.init).removeDuplicates()) {
      status = $0
    }
    .onChange(of: board.items) { _, items in
      Task {
        await liveActivity.sync(
          account: account, items: items, chatWorking: status.working,
          chatAwaiting: status.awaitingReply,
          chatApproval: pendingApproval(at: Date())?.title)
      }
    }
    .onChange(of: status) { _, _ in
      Task {
        await liveActivity.sync(
          account: account, items: board.items, chatWorking: status.working,
          chatAwaiting: status.awaitingReply,
          chatApproval: pendingApproval(at: Date())?.title)
      }
    }
    .onChange(of: scene) { _, phase in
      if phase == .background {
        Task {
          await liveActivity.sync(
            account: account, items: board.items, chatWorking: status.working,
            chatAwaiting: status.awaitingReply,
            chatApproval: pendingApproval(at: Date())?.title,
            leavingApp: true)
        }
      }
    }
  }
}
