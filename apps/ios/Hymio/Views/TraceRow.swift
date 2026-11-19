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
  var onExpansionChange: (Turn, Bool) -> Void = { _, _ in }
  var onAction: (String) async throws -> Void = { _ in }
  var onRetry: (String) -> Void = { _ in }
  var onDiscard: (String) -> Void = { _ in }
  @ObservedObject var account: AccountService
  /// 最新一条事件到达的时刻。用它把客户端的墙上时钟折回服务端，再让秒针自己走。
  @State private var anchored = Date()
  @State private var expanded = false
  @Environment(\.accessibilityReduceMotion) private var reduceMotion

  var body: some View {
    VStack(alignment: .leading, spacing: 8) {
      if let user = turn.user { row(user) }
      if turn.foldable {
        Button {
          Haptics.selection()
          let next = !expanded
          withAnimation(reduceMotion ? nil : .snappy(duration: 0.28, extraBounce: 0)) {
            expanded = next
          }
          onExpansionChange(turn, next)
        } label: {
          HStack(spacing: 9) {
            Image(systemName: "checkmark").font(.caption2).foregroundStyle(Brand.muted)
            Text(worked(Date())).foregroundStyle(Brand.muted)
            Spacer(minLength: 4)
            Text(expanded ? "收起" : "查看探索").font(.caption2).foregroundStyle(Brand.muted)
            Image(systemName: "chevron.down").font(.caption2.weight(.semibold))
              .foregroundStyle(Brand.muted)
              .rotationEffect(.degrees(expanded ? 180 : 0))
          }
          .font(.caption).padding(.horizontal, expanded ? 12 : 0).frame(minHeight: 44)
          .contentShape(Rectangle())
        }.buttonStyle(.plain)
          .accessibilityIdentifier("trace.fold")
          .accessibilityValue(expanded ? "已展开" : "已收起")
          .accessibilityHint("直接在对话中展开或收起探索过程")
        if expanded {
          VStack(alignment: .leading, spacing: 10) {
            ForEach(turn.activity) { activity in
              TraceActivityStep(message: activity)
            }
          }
          .padding(12)
          .background(Brand.mist.opacity(0.55), in: RoundedRectangle(cornerRadius: 14))
          .overlay(RoundedRectangle(cornerRadius: 14).strokeBorder(Brand.line, lineWidth: 0.6))
          .transition(.opacity.combined(with: .move(edge: .top)))
          .accessibilityIdentifier("trace.activity")
        }
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

private struct TraceActivityStep: View {
  let message: ChatMessage

  private var text: String {
    let content = message.content.trimmingCharacters(in: .whitespacesAndNewlines)
    if !content.isEmpty { return content }
    let reasoning = message.reasoning.trimmingCharacters(in: .whitespacesAndNewlines)
    if !reasoning.isEmpty { return reasoning }
    guard let call = message.calls.first else { return "继续处理" }
    let name = call["name"].text.lowercased()
    if name.contains("calendar") { return "检查相关日程" }
    if name.contains("task") { return "核对任务进展" }
    if name.contains("browser") || name.contains("web") { return "查看相关网页" }
    if name.contains("computer") || name.contains("bash") { return "操作相关应用" }
    if name.contains("recall") || name.contains("remember") || name.contains("context") {
      return "查看相关记忆"
    }
    return "继续处理下一步"
  }

  var body: some View {
    HStack(alignment: .top, spacing: 10) {
      Image(systemName: "sparkle")
        .font(.system(size: 12, weight: .semibold))
        .foregroundStyle(Brand.blue)
        .frame(width: 18, height: 20)
      Text(text)
        .font(.subheadline)
        .foregroundStyle(Brand.ink)
        .lineSpacing(3)
        .frame(maxWidth: .infinity, alignment: .leading)
        .textSelection(.enabled)
    }
    .padding(.vertical, 2)
  }
}

#if DEBUG
struct TraceInlineExperiencePreview: View {
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
    NavigationStack {
      ScrollView {
        VStack(alignment: .leading, spacing: 20) {
          Text("先看一段已经结束的对话。")
            .font(.subheadline).foregroundStyle(Brand.muted)
          TraceRow(turn: turn, tools: [:], account: account)
          HStack {
            Spacer()
            Text("你可以继续问下一件事。")
              .font(.body)
              .padding(.horizontal, 15).padding(.vertical, 11)
              .background(Brand.userBubble, in: RoundedRectangle(cornerRadius: 18))
          }
          Spacer(minLength: 240)
        }.padding(18)
      }
      .background(Brand.surface)
      .navigationTitle("对话")
      .navigationBarTitleDisplayMode(.inline)
    }
  }
}
#endif
