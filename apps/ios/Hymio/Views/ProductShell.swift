import Combine
import CryptoKit
import SwiftUI

@MainActor final class TaskBoard: ObservableObject {
  @Published var items: [JSON] = []
  @Published var suggestions: [JSON] = []
  @Published var loaded = false
  @Published var error = ""
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
    baseline = UserDefaults.standard.dictionary(forKey: key) as? [String: String]
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
  var changes: [JSON] {
    guard let baseline else {
      return Array(
        items.filter { ["succeeded", "blocked", "failed"].contains(taskStatus($0)) }.prefix(2))
    }
    return items.filter { baseline[$0["id"].text] != fingerprint($0) }
  }
  func markSeen(_ item: JSON) {
    guard loaded, !item["id"].text.isEmpty else { return }
    let stamp = fingerprint(item)
    guard baseline?[item["id"].text] != stamp else { return }
    var values = baseline ?? [:]
    values[item["id"].text] = stamp
    baseline = values
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
      suggestions = result["suggestions"].items
      let next = result["tasks"].items
      if items != next { items = next }
      loaded = true
      error = ""
    } catch is CancellationError {
    } catch { if user == account.session?.user_id { self.error = "暂时无法读取进展。" } }
  }
}

enum ProductTab: Hashable { case today, chat, tasks, moments, kits }

struct ProductShell: View {
  @ObservedObject var account: AccountService
  @ObservedObject var client: AgentClient
  @EnvironmentObject private var notifications: PushNotificationManager
  @StateObject private var board = TaskBoard()
  @StateObject private var liveActivity = LiveActivityController()
  @State private var selected: ProductTab = .today
  @State private var notificationTask: JSON?
  @State private var showAccount = false
  @Environment(\.scenePhase) private var scene
  private func pendingApproval(at date: Date) -> Approval? {
    client.model.approvals.first {
      $0.status == "pending" && $0.expires > date.timeIntervalSince1970
    }
  }
  private func expiredApproval(at date: Date) -> Approval? {
    client.model.approvals.first {
      $0.status == "pending" && $0.expires <= date.timeIntervalSince1970
    }
  }
  var body: some View {
    TabView(selection: $selected) {
      Tab("此刻", systemImage: "house.fill", value: ProductTab.today) {
        HomeScreen(
          account: account, client: client, board: board, selected: $selected,
          onAccount: { showAccount = true })
      }
      Tab("对话", systemImage: "bubble.left.and.bubble.right.fill", value: ProductTab.chat) {
        ChatScreen(account: account, client: client, onAccount: { showAccount = true })
      }
      Tab("任务", systemImage: "checklist", value: ProductTab.tasks) {
        NavigationStack {
          TasksScreen(account: account, board: board, onAccount: { showAccount = true })
            .navigationDestination(item: $notificationTask) { item in
              TaskDetailScreen(
                account: account, taskID: item["id"].text, initial: item
              )
            }
        }
      }
      Tab("记忆", systemImage: "book.closed.fill", value: ProductTab.moments) {
        ContextScreen(account: account, onAccount: { showAccount = true })
      }
      Tab("应用", systemImage: "square.grid.2x2.fill", value: ProductTab.kits) {
        KitsScreen(account: account, onAccount: { showAccount = true })
      }
    }
    .toolbarBackground(.ultraThinMaterial, for: .tabBar)
    .task(id: scene) {
      board.bind(account)
      guard scene == .active else { return }
      while !Task.isCancelled {
        await board.refresh(account)
        do { try await Task.sleep(for: .seconds(15)) } catch { return }
      }
    }
    .onChange(of: selected) { _, _ in Task { await board.refresh(account) } }
    .onChange(of: notifications.destination) { _, destination in
      open(destination)
    }
    .onAppear { open(notifications.destination) }
    .onChange(of: board.items) { _, items in
      Task {
        await liveActivity.sync(
          account: account, items: items, chatWorking: client.model.working,
          chatAwaiting: client.model.awaitingReply,
          chatApproval: pendingApproval(at: Date())?.title)
      }
    }
    .onChange(of: client.model.working) { _, _ in
      Task {
        await liveActivity.sync(
          account: account, items: board.items, chatWorking: client.model.working,
          chatAwaiting: client.model.awaitingReply,
          chatApproval: pendingApproval(at: Date())?.title)
      }
    }
    .onChange(of: client.model.approvals) { _, _ in
      Task {
        await liveActivity.sync(
          account: account, items: board.items, chatWorking: client.model.working,
          chatAwaiting: client.model.awaitingReply,
          chatApproval: pendingApproval(at: Date())?.title)
      }
    }
    .onChange(of: scene) { _, phase in
      if phase == .background {
        Task {
          await liveActivity.sync(
            account: account, items: board.items, chatWorking: client.model.working,
            chatAwaiting: client.model.awaitingReply,
            chatApproval: pendingApproval(at: Date())?.title,
            leavingApp: true)
        }
      }
    }
    .overlay(alignment: .bottom) {
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
            account: account, items: board.items, chatWorking: client.model.working,
            chatAwaiting: client.model.awaitingReply, chatApproval: approval?.title,
            expiredApproval: expired)
        }
      }
    }
    .sheet(isPresented: $showAccount) {
      AccountScreen(account: account, client: client)
    }
  }

  private func open(_ destination: AppDestination?) {
    guard let destination else { return }
    switch destination {
    case .task(let id):
      selected = .tasks
      notificationTask = .object(["id": .string(id)])
    case .chat:
      selected = .chat
    }
    notifications.consume(destination)
  }
}

struct HomeScreen: View {
  @ObservedObject var account: AccountService
  @ObservedObject var client: AgentClient
  @ObservedObject var board: TaskBoard
  @Binding var selected: ProductTab
  let onAccount: () -> Void
  @State private var openedTask: JSON?
  private var attention: [JSON] {
    board.changes.filter { ["blocked", "failed"].contains(taskStatus($0)) }
  }
  private var ongoing: [JSON] {
    board.items.filter { ["running", "ready", "delivering"].contains(taskStatus($0)) }
  }
  private var firstVisit: Bool {
    board.loaded && board.items.isEmpty && client.connected && client.model.messages.isEmpty
  }
  // Each module owns its content. Memory and Kit can join this feed without changing its shell.
  private enum Module: String, Identifiable {
    case attention, updates, ongoing, upcoming
    var id: String { rawValue }
    var title: String {
      switch self {
      case .attention: return "需要你确认"
      case .updates: return "最近进展"
      case .ongoing: return "正在推进"
      case .upcoming: return "接下来的安排"
      }
    }
    var symbol: String {
      switch self {
      case .attention: return "hand.raised"
      case .updates: return "sparkle"
      case .ongoing: return "circle.dotted"
      case .upcoming: return "calendar"
      }
    }
  }
  private var modules: [(kind: Module, items: [JSON])] {
    let updates = board.changes.filter {
      !attention.contains($0) && !ongoing.contains($0)
        && !["scheduled", "paused", "cancelled", "expired"].contains(taskStatus($0))
    }
    let upcoming = board.items.filter { taskStatus($0) == "scheduled" }
    return [
      (.attention, attention), (.ongoing, ongoing),
      (.updates, updates), (.upcoming, upcoming),
    ]
    .filter { !$0.1.isEmpty }
  }
  var body: some View {
    NavigationStack {
      ScrollView {
        VStack(alignment: .leading, spacing: 28) {
          VStack(alignment: .leading, spacing: 7) {
            Text(Date.now.formatted(.dateTime.month().day().weekday(.wide)))
              .font(.caption).foregroundStyle(Brand.muted)
            Text(firstVisit ? "嗨，我是 Hymio。" : "此刻")
              .font(.title2.weight(.semibold))
            if !client.connected {
              Text("正在连接，已有进展仍可查看。")
                .font(.subheadline).foregroundStyle(Brand.muted)
            }
          }.padding(.top, 12)
          if !board.suggestions.isEmpty {
            homeSection("可能值得做", symbol: "lightbulb", tint: Brand.muted, count: board.suggestions.count) {
              ForEach(Array(board.suggestions.prefix(3)), id: \.self) { item in
                VStack(alignment: .leading, spacing: 10) {
                  Text(item["proposal"]["title"].text).font(.subheadline.weight(.medium))
                  Text(item["proposal"]["reason"].text).font(.caption).foregroundStyle(Brand.muted).lineLimit(3)
                  HStack(spacing: 20) {
                    Button("交给 Hymio") { Task { await handleSuggestion(item, accept: true) } }
                    Button("暂不需要") { Task { await handleSuggestion(item, accept: false) } }.foregroundStyle(Brand.muted)
                  }.font(.subheadline).frame(minHeight: 44)
                }.padding(.vertical, 10)
              }
            }
          }
          ForEach(modules, id: \.kind) { module in
            homeSection(
              module.kind == .updates && board.hasBaseline ? "新的进展" : module.kind.title,
              symbol: module.kind.symbol,
              tint: module.kind == .attention
                ? Brand.attention : module.kind == .ongoing ? Brand.blue : Brand.muted,
              count: module.kind == .ongoing ? nil : module.items.count
            ) {
              ForEach(Array(module.items.prefix(3)), id: \.self) { item in taskLink(item) }
            }
          }
          if !board.error.isEmpty {
            HStack {
              Label(board.error, systemImage: "wifi.exclamationmark").font(.footnote)
                .foregroundStyle(Brand.muted)
              Spacer()
              Button("重试") { Task { await board.refresh(account) } }.font(.footnote).frame(
                minHeight: 44)
            }
          } else if !board.loaded {
            HStack(spacing: 10) {
              ProgressView().controlSize(.small)
              Text("正在整理最新进展…").font(.footnote).foregroundStyle(Brand.muted)
            }
            .padding(.vertical, 20)
          } else if modules.isEmpty && !client.connected && client.model.messages.isEmpty
            && board.items.isEmpty
          {
            Label("正在接回你的内容…", systemImage: "arrow.trianglehead.2.clockwise")
              .font(.subheadline).foregroundStyle(Brand.muted).padding(.vertical, 24)
          } else if modules.isEmpty {
            VStack(alignment: .leading, spacing: 16) {
              Label(firstVisit ? "初次见面" : "此刻", systemImage: firstVisit ? "sparkle" : "sun.horizon")
                .font(.caption).foregroundStyle(Brand.muted)
              Text(firstVisit ? "一件小事，就能开始。" : "暂时没有新的进展。")
                .font(.title3.weight(.semibold)).foregroundStyle(Brand.ink)
              Text(
                firstVisit
                  ? "理清一个想法、做一份计划，或把眼前的事交代给我。我们慢慢来。"
                  : "有了新结果，或有需要你确认的事，会在这里汇合。现在可以安心做自己的事。"
              )
              .font(.subheadline).foregroundStyle(Brand.muted).lineSpacing(5)
              if firstVisit {
                Button {
                  selected = .chat
                } label: {
                  HStack {
                    Text("和 Hymio 说说")
                    Spacer()
                    Image(systemName: "arrow.right")
                  }.font(.subheadline.weight(.semibold)).padding(.horizontal, 16)
                }.buttonStyle(PrimaryAction()).padding(.top, 8)
                  .accessibilityIdentifier("home.chat")
              } else if !board.items.isEmpty {
                Button {
                  selected = .tasks
                } label: {
                  Label("查看所有安排", systemImage: "arrow.up.right")
                    .font(.subheadline).frame(minHeight: 44)
                }.foregroundStyle(Brand.blue)
              }
            }.frame(maxWidth: .infinity, alignment: .leading).padding(24)
              .background(Brand.mist, in: RoundedRectangle(cornerRadius: 24))
          }

        }.padding(.horizontal, 22).padding(.bottom, 28).frame(maxWidth: 680)
          .frame(maxWidth: .infinity)
      }.background(Brand.surface).toolbarBackground(.ultraThinMaterial, for: .navigationBar).navigationTitle("此刻").navigationBarTitleDisplayMode(.inline)
        .toolbar {
          ToolbarItemGroup(placement: .topBarLeading) {
            AccountButton(account: account, action: onAccount)
          }.accountUnframed()
        }
        .refreshable { await board.refresh(account) }
        .navigationDestination(item: $openedTask) { item in
          TaskDetailScreen(
            account: account, taskID: item["id"].text, initial: item,
            onViewed: { board.markSeen($0) })
        }
    }
  }
  private func taskLink(_ item: JSON) -> some View {
    Button {
      openedTask = item
    } label: {
      TaskSummaryCard(item: item)
    }
    .buttonStyle(GentlePress())
  }
  private func homeSection<Content: View>(
    _ title: String, symbol: String, tint: Color, count: Int?, @ViewBuilder content: () -> Content
  ) -> some View {
    VStack(alignment: .leading, spacing: 12) {
      HStack(spacing: 9) {
        Circle().fill(tint).frame(width: 6, height: 6).accessibilityHidden(true)
        Text(title).font(.subheadline.weight(.semibold)).foregroundStyle(Brand.ink)
          .layoutPriority(1)
        if let count {
          Text("\(count)").font(.caption2.monospacedDigit()).foregroundStyle(Brand.muted)
        }
        Spacer(minLength: 0)
      }
      .accessibilityElement(children: .combine)
      .accessibilityAddTraits(.isHeader)
      content()
    }
  }
  private func handleSuggestion(_ item: JSON, accept: Bool) async {
    do {
      _ = try await account.request("tasks", body: .object([
        "action": .string(accept ? "accept_suggestion" : "dismiss_suggestion"),
        "suggestion_id": .string(item["id"].text)]))
      await board.refresh(account)
    } catch { board.error = "这次操作未完成，请重试。" }
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
