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
  @Environment(\.accessibilityReduceMotion) private var reduceMotion

  var body: some View {
    VStack(alignment: .leading, spacing: 25) {
      if let user = turn.user { row(user) }
      if turn.foldable {
        VStack(alignment: .leading, spacing: 0) {
          Button {
            withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.18)) { expanded.toggle() }
          } label: {
            HStack(spacing: 9) {
              Image(systemName: "checkmark.circle").foregroundStyle(Brand.blue)
              Text(worked(Date())).fontWeight(.medium).foregroundStyle(Brand.ink)
              Text("工作过程").foregroundStyle(Brand.muted)
              Spacer(minLength: 4)
              Image(systemName: "chevron.right").font(.caption2.weight(.semibold))
                .rotationEffect(.degrees(expanded ? 90 : 0)).foregroundStyle(Brand.muted)
            }.font(.caption).padding(.horizontal, 14).frame(minHeight: 46)
              .contentShape(Rectangle())
          }.buttonStyle(.plain)
            .accessibilityIdentifier("trace.fold")
            .accessibilityValue(expanded ? "已展开" : "已收起")
            .accessibilityHint("展开或收起中间步骤，不影响最终回复")
          if expanded {
            Divider().padding(.horizontal, 14)
            VStack(alignment: .leading, spacing: 14) {
              ForEach(turn.activity) { row($0, compact: true) }
            }.padding(14)
          }
        }.background(Brand.mist.opacity(0.65), in: RoundedRectangle(cornerRadius: 16))
          .overlay(RoundedRectangle(cornerRadius: 16).stroke(Brand.line.opacity(0.8)))
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
      compact: compact
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
    return value.isEmpty ? "已工作" : "已工作 \(value)"
  }

  private func elapsed(_ now: Date) -> TimeInterval? {
    guard let latest = turn.latestAt else { return nil }
    return traceElapsed(turn, serverNow: latest.addingTimeInterval(now.timeIntervalSince(anchored)))
  }
}
