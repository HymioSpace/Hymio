import SwiftUI

/// 一次探索：用户消息在上，过程收成一行，最终回复留在下面。
struct TraceRow: View, Equatable {
  static func == (lhs: Self, rhs: Self) -> Bool {
    lhs.turn == rhs.turn && lhs.tools == rhs.tools && lhs.approvals == rhs.approvals
      && lhs.account === rhs.account
  }
  let turn: Turn
  let tools: [String: JSON]
  var approvals: [Approval] = []
  var onOpenTrace: (Turn) -> Void = { _ in }
  var onAction: (String) async throws -> Void = { _ in }
  var onRetry: (String) -> Void = { _ in }
  var onDiscard: (String) -> Void = { _ in }
  @ObservedObject var account: AccountService
  /// 最新一条事件到达的时刻。用它把客户端的墙上时钟折回服务端，再让秒针自己走。
  @State private var anchored = Date()

  var body: some View {
    VStack(alignment: .leading, spacing: 8) {
      if let user = turn.user { row(user) }
      if turn.foldable {
        Button {
          Haptics.selection()
          onOpenTrace(turn)
        } label: {
          HStack(spacing: 9) {
            Image(systemName: "checkmark").font(.caption2).foregroundStyle(Brand.muted)
            Text(worked(Date())).foregroundStyle(Brand.muted)
            Spacer(minLength: 4)
            Text("查看探索").font(.caption2).foregroundStyle(Brand.muted)
            Image(systemName: "arrow.up.right").font(.caption2.weight(.semibold))
              .foregroundStyle(Brand.muted)
          }
          .font(.caption).frame(minHeight: 44).contentShape(Rectangle())
        }.buttonStyle(.plain)
          .accessibilityIdentifier("trace.fold")
          .accessibilityHint("打开探索面板，不改变当前对话位置")
      } else {
        if !turn.activity.isEmpty { live }
        ForEach(turn.activity) { row($0) }
      }
      if let final = turn.final { row(final) }
      ForEach(turn.trailing) { row($0) }
    }
    .onAppear { anchored = Date() }
    .onChange(of: turn.latestAt) { _, _ in anchored = Date() }
  }

  private func row(_ message: ChatMessage, compact: Bool = false) -> some View {
    MessageRow(
      message: message, tools: tools, approvals: approvals, onAction: onAction, account: account,
      compact: compact, showsTime: message.id == turn.user?.id || message.id == turn.final?.id,
      onRetry: onRetry, onDiscard: onDiscard
    )
    .id(message.id)
  }

  private var live: some View {
    TimelineView(.periodic(from: .now, by: 1)) { context in
      Label(worked(context.date), systemImage: "circle.dotted")
        .font(.caption).foregroundStyle(.secondary)
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityIdentifier("trace.live")
    }
  }

  private func worked(_ now: Date) -> String {
    let value = formatDuration(elapsed(now))
    return value.isEmpty ? "探索中" : "已探索 \(value)"
  }

  private func elapsed(_ now: Date) -> TimeInterval? {
    guard let latest = turn.latestAt else { return nil }
    return traceElapsed(turn, serverNow: latest.addingTimeInterval(now.timeIntervalSince(anchored)))
  }
}

struct TraceActivityPanel: View {
  let turn: Turn
  let tools: [String: JSON]
  var approvals: [Approval] = []
  @ObservedObject var account: AccountService
  var onAction: (String) async throws -> Void = { _ in }
  var onRetry: (String) -> Void = { _ in }
  var onDiscard: (String) -> Void = { _ in }
  @Environment(\.dismiss) private var dismiss

  private var messages: [ChatMessage] {
    [turn.user].compactMap { $0 } + turn.activity + [turn.final].compactMap { $0 }
      + turn.trailing
  }

  var body: some View {
    NavigationStack {
      ScrollView {
        LazyVStack(alignment: .leading, spacing: 14) {
          VStack(alignment: .leading, spacing: 5) {
            Text("这一次探索").font(.title3.weight(.semibold)).foregroundStyle(Brand.ink)
            Text("过程放在独立面板里，不会推动正在阅读的消息。")
              .font(.caption).foregroundStyle(Brand.muted)
          }
          .frame(maxWidth: .infinity, alignment: .leading)
          .padding(16)
          .background(Brand.softBlue, in: RoundedRectangle(cornerRadius: 16))

          ForEach(messages) { message in
            MessageRow(
              message: message, tools: tools, approvals: approvals, onAction: onAction,
              account: account, compact: false, showsTime: true,
              onRetry: onRetry, onDiscard: onDiscard)
          }

          if !turn.trace.isEmpty {
            NavigationLink {
              TraceRecordScreen(traceID: turn.trace, account: account)
            } label: {
              HStack {
                Label("查看完整执行记录", systemImage: "point.3.connected.trianglepath.dotted")
                Spacer()
                Image(systemName: "chevron.right").font(.caption)
              }
              .font(.subheadline.weight(.medium))
              .foregroundStyle(Brand.blue)
              .padding(16)
              .background(Brand.raised, in: RoundedRectangle(cornerRadius: 14))
            }.buttonStyle(.plain)
          }
        }
        .padding(18)
      }
      .background(Brand.surface)
      .navigationTitle("探索过程")
      .navigationBarTitleDisplayMode(.inline)
      .toolbar {
        ToolbarItem(placement: .confirmationAction) {
          Button("完成") { dismiss() }
        }
      }
    }
  }
}

#if DEBUG
struct TracePanelExperiencePreview: View {
  @State private var presented = true
  private let account = AccountService()

  private var turn: Turn {
    Turn(
      id: "preview-turn",
      trace: "preview-trace",
      user: ChatMessage(
        id: "preview-user", role: "user", content: "帮我核对今天的安排。",
        time: "2026-11-19T08:00:00Z"),
      final: ChatMessage(
        id: "preview-final", role: "assistant", content: "安排已经核对好，下午两点前没有冲突。",
        time: "2026-11-19T08:00:04Z"),
      activity: [
        ChatMessage(
          id: "assistant:preview-step", role: "assistant",
          content: "我先看一下今天的日历与任务，再核对时间冲突。",
          time: "2026-11-19T08:00:02Z"),
      ],
      trailing: [],
      startedAt: TurnClock.date("2026-11-19T08:00:00Z"),
      latestAt: TurnClock.date("2026-11-19T08:00:04Z"),
      endedAt: TurnClock.date("2026-11-19T08:00:04Z"),
      settled: true)
  }

  var body: some View {
    Color.clear
      .sheet(isPresented: $presented) {
        TraceActivityPanel(turn: turn, tools: [:], account: account)
          .presentationDetents([.medium, .large])
          .presentationDragIndicator(.visible)
      }
  }
}
#endif
