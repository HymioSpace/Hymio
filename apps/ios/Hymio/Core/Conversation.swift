import Foundation

public struct ChatMessage: Identifiable {
  public var id: String
  public var role: String
  public var content: String
  public var time: String
  public var streaming = false
  public var attempt = 0
  public var calls: [JSON] = []
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
  public init(events: [Event]) {
    var indices: [String: Int] = [:]
    for e in events {
      let p = e.payload
      let step = p["step_id"].text
      switch e.event_type {
      case "user.message":
        messages.append(
          ChatMessage(
            id: "user:\(e.id)", role: "user", content: p["content"].text, time: e.occur_dt))
        working = true
        failure = ""
      case "assistant.delta" where p["channel"].text == "content" && !step.isEmpty:
        if indices[step] == nil {
          indices[step] = messages.count
          messages.append(
            ChatMessage(
              id: "assistant:\(step)", role: "assistant", content: "", time: e.occur_dt,
              streaming: true, attempt: p["attempt"].int))
        }
        let i = indices[step]!
        guard messages[i].streaming else { continue }
        if p["attempt"].int > messages[i].attempt {
          messages[i].content = ""
          messages[i].attempt = p["attempt"].int
        }
        if p["attempt"].int == messages[i].attempt { messages[i].content += p["text"].text }
      case "assistant.message":
        let key = step.isEmpty ? String(e.id) : step
        if indices[key] == nil {
          indices[key] = messages.count
          messages.append(
            ChatMessage(id: "assistant:\(key)", role: "assistant", content: "", time: e.occur_dt))
        }
        let i = indices[key]!
        messages[i].content = p["content"].text
        messages[i].streaming = false
        messages[i].calls = p["tool_calls"].items
        if messages[i].calls.isEmpty { working = false }
      case "tool.terminal": terminals[p["invocation_id"].text] = p
      case "permission.requested":
        approvals.append(
          Approval(
            id: p["invocation_id"].text, tool: p["tool"].text, arguments: p["arguments"],
            status: "pending", expires: p["expires_at"].double))
      case "permission.resolved":
        if let i = approvals.firstIndex(where: { $0.id == p["invocation_id"].text }) {
          approvals[i].status = p["status"].text
        }
      case "step.status":
        let status = p["status"].text
        working = ["running", "queued"].contains(status)
        if ["failed", "paused", "cancelled"].contains(status) {
          if let i = indices[step] { messages[i].streaming = false }
          failure = p["error"].text
        }
      default: break
      }
    }
    messages.removeAll { $0.content.isEmpty && $0.calls.isEmpty && !$0.streaming }
  }
}
