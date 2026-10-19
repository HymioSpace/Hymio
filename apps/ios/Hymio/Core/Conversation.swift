import Foundation

public struct ChatMessage: Identifiable {
  public var id: String
  public var role: String
  public var content: String
  public var time: String
  public var streaming = false
  public var attempt = 0
  public var calls: [JSON] = []
  public var reasoning = ""
  public var thinking = false
  public var delivery: String?
}
public struct Approval: Identifiable {
  public var id: String
  public var tool: String
  public var arguments: JSON
  public var status: String
  public var expires: Double
}
public struct Conversation {
  public var messages: [ChatMessage] = []
  public var approvals: [Approval] = []
  public var terminals: [String: JSON] = [:]
  public var working = false
  public var failure = ""
  private var indices: [String: Int] = [:]
  public init(
    events: [Event], pending: [Command] = [], accepted: Set<String> = [], rejected: Set<String> = []
  ) {
    for event in events { apply(event) }
    let echoed = Set(
      events.filter { $0.event_type == "user.message" }.map {
        $0.payload["user_context"]["hymio_message_id"].text
      })
    for command in pending where command.type == "user.message" && !echoed.contains(command.id) {
      var message = ChatMessage(
        id: "local:\(command.id)", role: "user", content: command.payload["content"].text,
        time: command.createdAt ?? "")
      message.delivery =
        rejected.contains(command.id)
        ? "failed" : accepted.contains(command.id) ? "accepted" : "queued"
      if message.delivery != "failed" { failure = "" }
      messages.append(message)
    }
  }
  public var awaitingReply: Bool {
    messages.last?.role == "user" && messages.last?.delivery != "failed" && failure.isEmpty
  }
  public mutating func apply(_ e: Event) {
    let p = e.payload
    let step = p["step_id"].text
    switch e.event_type {
    case "user.message":
      let id = p["user_context"]["hymio_message_id"].text
      if !id.isEmpty {
        messages.removeAll { $0.id == "local:\(id)" }
        rebuildIndices()
      }
      messages.append(
        ChatMessage(id: "user:\(e.id)", role: "user", content: p["content"].text, time: e.occur_dt))
      working = true
      failure = ""
    case "assistant.delta"
    where ["content", "reasoning"].contains(p["channel"].text) && !step.isEmpty:
      if indices[step] == nil {
        indices[step] = messages.count
        messages.append(
          ChatMessage(
            id: "assistant:\(step)", role: "assistant", content: "", time: e.occur_dt,
            streaming: true, attempt: p["attempt"].int))
      }
      let i = indices[step]!
      guard messages[i].streaming else { return }
      let attempt = p["attempt"].int
      if attempt > messages[i].attempt {
        messages[i].content = ""
        messages[i].reasoning = ""
        messages[i].attempt = attempt
      }
      guard attempt == messages[i].attempt else { return }
      if p["channel"].text == "reasoning" {
        messages[i].reasoning += p["text"].text
        messages[i].thinking = true
      } else {
        messages[i].content += p["text"].text
        messages[i].thinking = false
      }
      working = true
    case "assistant.message":
      let key = step.isEmpty ? String(e.id) : step
      if indices[key] == nil {
        indices[key] = messages.count
        messages.append(
          ChatMessage(id: "assistant:\(key)", role: "assistant", content: "", time: e.occur_dt))
      }
      let i = indices[key]!
      messages[i].content = p["content"].text
      if p["reasoning"] != .null { messages[i].reasoning = p["reasoning"].text }
      messages[i].streaming = false
      messages[i].thinking = false
      messages[i].calls = p["tool_calls"].items
      if messages[i].calls.isEmpty { working = false }
    case "tool.terminal": terminals[p["invocation_id"].text] = p
    case "permission.requested":
      let approval = Approval(
        id: p["invocation_id"].text, tool: p["tool"].text, arguments: p["arguments"],
        status: "pending", expires: p["expires_at"].double)
      if let i = approvals.firstIndex(where: { $0.id == approval.id }) {
        approvals[i] = approval
      } else {
        approvals.append(approval)
      }
    case "permission.resolved":
      if let i = approvals.firstIndex(where: { $0.id == p["invocation_id"].text }) {
        approvals[i].status = p["status"].text
      }
    case "step.status":
      let status = p["status"].text
      working = ["prepared", "running", "queued"].contains(status)
      if ["completed", "failed", "paused", "cancelled"].contains(status), let i = indices[step] {
        messages[i].streaming = false
        messages[i].thinking = false
      }
      if ["failed", "paused", "cancelled"].contains(status) {
        failure = p["error"].text
      } else {
        failure = ""
      }
    default: break
    }
  }
  private mutating func rebuildIndices() {
    indices = [:]
    for (i, m) in messages.enumerated() where m.id.hasPrefix("assistant:") {
      indices[String(m.id.dropFirst(10))] = i
    }
  }
}
