import SwiftUI

struct MessageRow: View {
  let message: ChatMessage
  let tools: [String: JSON]
  var approvals: [Approval] = []
  var onAction: (String) async throws -> Void = { _ in }
  @ObservedObject var account: AccountService
  var compact = false
  var onRetry: (String) -> Void = { _ in }
  var onDiscard: (String) -> Void = { _ in }
  private var reasoningOnly: Bool {
    !message.reasoning.isEmpty && message.content.isEmpty && message.calls.isEmpty
  }
  @State private var expanded = false
  @Environment(\.accessibilityReduceMotion) private var reduceMotion
  var body: some View {
    if message.role == "user" {
      HStack {
        Spacer(minLength: 45)
        VStack(alignment: .trailing, spacing: 5) {
          UserMessageContent(content: message.content, account: account)
            .padding(.horizontal, 14).padding(.vertical, 12)
            .background(Brand.userBubble, in: RoundedRectangle(cornerRadius: 20))
          if message.delivery == "failed" {
            HStack(spacing: 16) {
              Label("未发送", systemImage: "exclamationmark.circle").foregroundStyle(.secondary)
              Button("重试") { onRetry(message.id) }
              Button("移除", role: .destructive) { onDiscard(message.id) }
            }.font(.caption).frame(minHeight: 44)
          } else if let delivery = message.delivery {
            Text(["queued": "正在发送…", "accepted": "已送达", "failed": "发送失败，可重试"][delivery] ?? "")
              .font(.caption).foregroundStyle(.secondary)
          }
        }
      }.accessibilityIdentifier("message.user")
    } else {
      HStack(alignment: .top, spacing: 0) {
        VStack(alignment: .leading, spacing: 12) {
          if !message.reasoning.isEmpty {
            DisclosureGroup {
              BufferedProse(
                source: message.reasoning, streaming: message.streaming, account: account,
                plain: true
              )
              .multilineTextAlignment(.leading)
              .frame(maxWidth: .infinity, alignment: .leading)
              .padding(.top, 8)
            } label: {
              HStack(spacing: 7) {
                Image(systemName: "brain").symbolEffect(
                  .pulse, isActive: message.thinking && !reduceMotion)
                Text(message.thinking ? "正在思考…" : "思考过程")
              }.font(.caption).foregroundStyle(.secondary)
            }.tint(Brand.muted)
              .frame(minHeight: 44, alignment: .leading)
              .accessibilityIdentifier("message.reasoning")
          }
          if message.streaming && message.content.isEmpty && message.reasoning.isEmpty {
            HStack(spacing: 8) {
              ProgressView().controlSize(.small)
              Text("正在准备回复…").font(.caption).foregroundStyle(.secondary)
            }
          }
          if !message.content.isEmpty {
            ProgressiveMessageContent(
              content: message.content, streaming: message.streaming, account: account,
              onAction: onAction
            )

          }
          if !message.calls.isEmpty {
            DisclosureGroup(isExpanded: $expanded) {
              VStack(alignment: .leading, spacing: 8) {
                ForEach(Array(message.calls.enumerated()), id: \.offset) { i, call in
                  let tool = tools[String(message.id.dropFirst("assistant:".count)) + "-\(i)"]
                  VStack(alignment: .leading, spacing: 8) {
                    HStack {
                      Label(toolName(call["name"].text), systemImage: toolIcon(call["name"].text))
                      Spacer()
                      ToolOutcomeLabel(outcome: toolOutcome(index: i))
                    }.font(.caption)
                    Text(call["arguments"].pretty).font(.system(.caption, design: .monospaced))
                      .textSelection(.enabled)
                    if let tool {
                      Text(tool.pretty).font(.system(.caption2, design: .monospaced)).textSelection(
                        .enabled)
                    }
                  }.padding(12).background(Brand.surface, in: RoundedRectangle(cornerRadius: 12))
                    .overlay(RoundedRectangle(cornerRadius: 12).stroke(Brand.line))
                }
              }.padding(.top, 8)
            } label: {
              HStack {
                Label(
                  message.calls.count == 1
                    ? toolName(message.calls[0]["name"].text) : "\(message.calls.count) 项工具操作",
                  systemImage: "chevron.left.forwardslash.chevron.right")
                Spacer(minLength: 4)
                ToolOutcomeLabel(outcome: summaryOutcome)
              }.font(.caption).foregroundStyle(.secondary)
            }.tint(.secondary)
          }
        }.frame(maxWidth: .infinity, alignment: .leading)
      }
      .padding(compact || reasoningOnly ? 0 : 16)
      .background {
        if !compact && !message.content.isEmpty {
          RoundedRectangle(cornerRadius: 18).fill(Brand.mist.opacity(0.7))
        }
      }
      .accessibilityElement(children: .contain).accessibilityIdentifier("message.assistant")
    }
  }
  private var summaryOutcome: String {
    let outcomes = message.calls.indices.map { toolOutcome(index: $0) }
    if outcomes.contains("running") { return "running" }
    if outcomes.contains("awaiting_approval") { return "awaiting_approval" }
    return outcomes.first(where: { $0 != "succeeded" }) ?? "succeeded"
  }
  private func toolOutcome(index: Int) -> String {
    let id = String(message.id.dropFirst("assistant:".count)) + "-\(index)"
    if let result = tools[id]?["outcome"].text, !result.isEmpty, result != "running" {
      return result
    }
    if let approval = approvals.first(where: { $0.id == id }) {
      if approval.status == "pending" {
        return approval.expires <= Date().timeIntervalSince1970 ? "expired" : "awaiting_approval"
      }
      if approval.status == "denied" { return "denied" }
    }
    return tools[id]?["outcome"].text ?? "running"
  }
  private func toolIcon(_ name: String) -> String {
    [
      "browser": "globe", "computer": "desktopcomputer", "devices": "laptopcomputer",
      "skill": "book.closed",
    ][name] ?? "terminal"
  }
  private func toolName(_ value: String) -> String {
    [
      "bash": "执行命令", "devices": "查看设备", "device_command": "查询执行结果", "computer": "操作电脑",
      "browser": "浏览网页", "skill": "使用技能",
    ][value] ?? value
  }
}
struct ProtectedImage: View {
  let source: String
  var thumbnail = false
  @ObservedObject var account: AccountService
  @State private var image: UIImage?
  @State private var failed = false
  @State private var retry = 0
  @State private var show = false
  var body: some View {
    Group {
      if let image {
        Button {
          show = true
        } label: {
          Group {
            if thumbnail {
              Image(uiImage: image).resizable().scaledToFill().frame(width: 80, height: 80)
            } else {
              Image(uiImage: image).resizable().scaledToFit().frame(maxHeight: 240)
            }
          }.clipShape(RoundedRectangle(cornerRadius: thumbnail ? 12 : 14))
        }.buttonStyle(.plain).accessibilityLabel("查看完整图片")
      } else if failed {
        Button {
          retry += 1
        } label: {
          Label("图片未能加载，重试", systemImage: "arrow.clockwise").font(.caption)
        }
      } else {
        ProgressView().frame(width: thumbnail ? 80 : nil, height: 80)
      }
    }
    .task(id: source + "\(retry)") {
      failed = false
      do {
        let data = try await account.image(source)
        guard let decoded = UIImage(data: data) else { throw ServiceError.message("图片格式无效") }
        image = decoded
      } catch { if !Task.isCancelled { failed = true } }
    }
    .sheet(isPresented: $show) {
      NavigationStack {
        GeometryReader { geometry in
          ScrollView {
            if let image {
              Image(uiImage: image).resizable().scaledToFit()
                .frame(width: geometry.size.width)
                .frame(minHeight: geometry.size.height)
            }
          }
        }
        .background(Brand.surface).navigationTitle("图片预览").navigationBarTitleDisplayMode(.inline)
        .toolbar { ToolbarItem(placement: .confirmationAction) { Button("完成") { show = false } } }
      }
    }
  }
}

private struct UserMessageContent: View {
  let content: String
  @ObservedObject var account: AccountService
  private var extracted: (text: String, images: [String]) {
    let pattern = #"!\[[^\]]*\]\((/attachments/[a-f0-9]{32})\)"#
    guard let regex = try? NSRegularExpression(pattern: pattern) else { return (content, []) }
    let range = NSRange(content.startIndex..., in: content)
    let matches = regex.matches(in: content, range: range)
    let images = matches.compactMap { match in
      Range(match.range(at: 1), in: content).map { String(content[$0]) }
    }
    let text = regex.stringByReplacingMatches(in: content, range: range, withTemplate: "")
      .trimmingCharacters(in: .whitespacesAndNewlines)
    return (text, images)
  }
  var body: some View {
    let parts = extracted
    VStack(alignment: .leading, spacing: 10) {
      if !parts.images.isEmpty {
        ScrollView(.horizontal, showsIndicators: false) {
          HStack(spacing: 8) {
            ForEach(Array(parts.images.enumerated()), id: \.offset) { _, source in
              ProtectedImage(source: source, thumbnail: true, account: account)
            }
          }
        }.frame(height: 80)
      }
      if !parts.text.isEmpty {
        MessageContent(content: parts.text, account: account)
          .multilineTextAlignment(.leading)
      }
    }.frame(maxWidth: .infinity, alignment: .leading)
  }
}
