import SwiftUI

struct MessageRow: View {
  let message: ChatMessage
  let tools: [String: JSON]
  var approvals: [Approval] = []
  @ObservedObject var account: AccountService
  @State private var expanded = false
  var body: some View {
    if message.role == "user" {
      HStack {
        Spacer(minLength: 45)
        Text(message.content).font(.body).lineSpacing(4).textSelection(.enabled)
          .padding(.horizontal, 16).padding(.vertical, 12)
          .background(Brand.userBubble, in: RoundedRectangle(cornerRadius: 20))
      }.accessibilityIdentifier("message.user")
    } else {
      HStack(alignment: .top, spacing: 9) {
        Companion(size: 34, mood: message.streaming ? .replying : .idle)
        VStack(alignment: .leading, spacing: 12) {
          if !message.content.isEmpty {
            MessageContent(content: message.content, account: account)
              .contextMenu {
                Button("复制回复", systemImage: "doc.on.doc") { UIPasteboard.general.string = message.content }
              }
          }
          if !message.calls.isEmpty {
            DisclosureGroup(isExpanded: $expanded) {
              ForEach(Array(message.calls.enumerated()), id: \.offset) { i, call in
                let tool = tools[String(message.id.dropFirst("assistant:".count)) + "-\(i)"]
                VStack(alignment: .leading, spacing: 8) {
                  HStack {
                    Label(toolName(call["name"].text), systemImage: "terminal")
                    Spacer()
                    ToolOutcomeLabel(outcome: toolOutcome(index: i))
                  }.font(.caption)
                  Text(call["arguments"].pretty).font(.system(.caption, design: .monospaced))
                    .textSelection(.enabled)
                  if let tool {
                    Text(tool.pretty).font(.system(.caption2, design: .monospaced)).textSelection(
                      .enabled)
                  }
                }.padding(12).background(Brand.mist, in: RoundedRectangle(cornerRadius: 12))
              }
            } label: {
              HStack {
                Label(message.calls.count == 1 ? toolName(message.calls[0]["name"].text) : "\(message.calls.count) 项工具操作", systemImage: "chevron.left.forwardslash.chevron.right")
                Spacer(minLength: 4)
                ToolOutcomeLabel(outcome: summaryOutcome)
              }.font(.caption).foregroundStyle(.secondary)
            }.tint(.secondary)
          }
        }.frame(maxWidth: .infinity, alignment: .leading)
      }.accessibilityIdentifier("message.assistant")
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
    if let result = tools[id]?["outcome"].text, !result.isEmpty, result != "running" { return result }
    if let approval = approvals.first(where: { $0.id == id }) {
      if approval.status == "pending" {
        return approval.expires <= Date().timeIntervalSince1970 ? "expired" : "awaiting_approval"
      }
      if approval.status == "denied" { return "denied" }
    }
    return tools[id]?["outcome"].text ?? "running"
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
          Image(uiImage: image).resizable().scaledToFit().frame(maxHeight: 240).clipShape(
            RoundedRectangle(cornerRadius: 14))
        }.buttonStyle(.plain).accessibilityLabel("放大截图")
      } else if failed {
        Button {
          retry += 1
        } label: {
          Label("图片未能加载，重试", systemImage: "arrow.clockwise").font(.caption)
        }
      } else {
        ProgressView().frame(height: 70).frame(maxWidth: .infinity)
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
        ScrollView([.horizontal, .vertical]) {
          if let image {
            Image(uiImage: image).resizable().scaledToFit().frame(width: max(350, image.size.width))
          }
        }
        .background(Brand.mist).navigationTitle("截图").navigationBarTitleDisplayMode(.inline)
        .toolbar { ToolbarItem(placement: .confirmationAction) { Button("完成") { show = false } } }
      }
    }
  }
}
