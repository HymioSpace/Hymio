import SwiftUI

/// 一次工作：用户消息在上，过程收成一行，最终回复留在下面。
struct TraceRow: View {
  let turn: Turn
  let tools: [String: JSON]
  var approvals: [Approval] = []
  var onAction: (String) async throws -> Void = { _ in }
  @ObservedObject var account: AccountService
  @State private var expanded = false
  /// 最新一条事件到达的时刻。用它把客户端的墙上时钟折回服务端，再让秒针自己走。
  @State private var anchored = Date()

  var body: some View {
    VStack(alignment: .leading, spacing: 25) {
      if let user = turn.user { row(user) }
      if turn.foldable {
        DisclosureGroup(isExpanded: $expanded) {
          VStack(alignment: .leading, spacing: 25) {
            ForEach(turn.activity) { row($0) }
          }
          .padding(.leading, 14)
        } label: {
          Label {
            Text(worked(Date()))
          } icon: {
            Image(systemName: "chevron.right").font(.caption2)
          }
        }
        .tint(.secondary)
        .accessibilityIdentifier("trace.fold")
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

  private func row(_ message: ChatMessage) -> some View {
    MessageRow(
      message: message, tools: tools, approvals: approvals, onAction: onAction, account: account
    )
    .id(message.id)
  }

  private var live: some View {
    TimelineView(.periodic(from: .now, by: 1)) { context in
      Text(worked(context.date))
        .font(.caption).foregroundStyle(.secondary)
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityIdentifier("trace.live")
    }
  }

  private func worked(_ now: Date) -> String {
    let value = formatDuration(elapsed(now))
    return value.isEmpty ? "已工作" : "已工作 \(value)"
  }

  private func elapsed(_ now: Date) -> TimeInterval? {
    guard let latest = turn.latestAt else { return nil }
    return traceElapsed(turn, serverNow: latest.addingTimeInterval(now.timeIntervalSince(anchored)))
  }
}
