import SwiftUI

/// 一次探索：用户消息在上，过程收成一行，最终回复留在下面。
struct TraceRow: View {
  let turn: Turn
  let tools: [String: JSON]
  var approvals: [Approval] = []
  var onAction: (String) async throws -> Void = { _ in }
  var onRetry: (String) -> Void = { _ in }
  var onDiscard: (String) -> Void = { _ in }
  @ObservedObject var account: AccountService
  @State private var expanded = false
  /// 最新一条事件到达的时刻。用它把客户端的墙上时钟折回服务端，再让秒针自己走。
  @State private var anchored = Date()
  @Environment(\.accessibilityReduceMotion) private var reduceMotion

  var body: some View {
    VStack(alignment: .leading, spacing: 8) {
      if let user = turn.user { row(user) }
      if turn.foldable {
        VStack(alignment: .leading, spacing: 0) {
          Button {
            withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.18)) { expanded.toggle() }
          } label: {
            HStack(spacing: 9) {
              Image(systemName: "checkmark").font(.caption2).foregroundStyle(Brand.muted)
              Text(worked(Date())).foregroundStyle(Brand.muted)

              Spacer(minLength: 4)
              Image(systemName: "chevron.right").font(.caption2.weight(.semibold))
                .rotationEffect(.degrees(expanded ? 90 : 0)).foregroundStyle(Brand.muted)
            }.font(.caption).padding(.horizontal, expanded ? 12 : 0).frame(minHeight: 44)
              .contentShape(Rectangle())
          }.buttonStyle(.plain)
            .accessibilityIdentifier("trace.fold")
            .accessibilityValue(expanded ? "已展开" : "已收起")
            .accessibilityHint("展开或收起中间步骤，不影响最终回复")
          if expanded {
            Divider().padding(.horizontal, 14)
            VStack(alignment: .leading, spacing: 8) {
              ForEach(turn.activity) { row($0, compact: true) }
              if !turn.trace.isEmpty {
                NavigationLink {
                  TraceRecordScreen(traceID: turn.trace, account: account)
                } label: {
                  Label("查看探索详情", systemImage: "arrow.up.right")
                    .font(.caption).foregroundStyle(Brand.muted).frame(minHeight: 44)
                }
              }
            }.padding(10)
          }
        }.background(
          expanded ? Brand.mist.opacity(0.5) : Color.clear, in: RoundedRectangle(cornerRadius: 14)
        )
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(expanded ? Brand.line : Color.clear))
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
