import Foundation

public struct ChatMessage: Identifiable, Equatable {
  public var id: String
  public var role: String
  public var content: String
  public var rawContent = ""
  public var suggestions: [String] = []
  public var time: String
  public var streaming = false
  public var attempt = 0
  /// step.status 里的 trace_id：同一条 trace 的多个 step 属于同一次工作。
  public var trace = ""
  public var calls: [JSON] = []
  public var reasoning = ""
  public var thinking = false
  public var eventSeq = 0
  public var delivery: String?
  public var reactions: [String: String] = [:]
}
public struct ApprovalTarget: Equatable {
  public var kind: String
  public var id: String
  public var label: String
}
public struct Approval: Identifiable, Equatable {
  public var id: String
  public var tool: String
  public var arguments: JSON
  public var status: String
  public var expires: Double
  public var title: String
  public var summary: String
  public var risk: String
  public var effects: [String]
  public var target: ApprovalTarget
  public var scopeOptions: [String]
  public var actionDigest: String
  public var decidedAt: Double?
  public var decidedBy: String
  public var decisionChannel: String
  public var reason: String
}
public struct Conversation {
  public var messages: [ChatMessage] = []
  public var approvals: [Approval] = []
  public var terminals: [String: JSON] = [:]
  public var working = false
  public var failure = ""
  public var pauseNotice = ""
  private var indices: [String: Int] = [:]
  /// step_id -> trace_id。step.status 先于该step 的任何输出到达，所以这里总是来得及。
  private var traces: [String: String] = [:]
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
      if message.delivery != "failed" {
        failure = ""
        pauseNotice = ""
      }
      let sentAt = TurnClock.date(message.time)
      let position =
        messages.firstIndex {
          guard let sentAt, let other = TurnClock.date($0.time) else { return false }
          return other > sentAt
        } ?? messages.endIndex
      messages.insert(message, at: position)
    }
    rebuildIndices()
  }
  /// 一次工作为单位的消息序列，界面按它来折叠过程。
  public var turns: [Turn] { buildTurns(messages, paused: !pauseNotice.isEmpty) }
  public var awaitingReply: Bool {
    messages.last?.role == "user" && messages.last?.delivery != "failed" && failure.isEmpty
      && pauseNotice.isEmpty
  }
  /// Coalesce only adjacent deltas. A terminal, retry or side event preserves ordering.
  public mutating func apply(_ events: [Event]) {
    var delta: Event?
    var text: [String] = []
    func matching(_ a: Event, _ b: Event) -> Bool {
      a.event_type == "assistant.delta" && b.event_type == a.event_type
        && a.payload["step_id"] == b.payload["step_id"]
        && a.payload["channel"] == b.payload["channel"]
        && a.payload["attempt"] == b.payload["attempt"]
    }
    for event in events {
      if let old = delta, matching(old, event) {
        text.append(event.payload["text"].text)
        continue
      }
      if var old = delta, case .object(var payload) = old.payload {
        payload["text"] = .string(text.joined())
        old.payload = .object(payload)
        apply(old)
      }
      delta = nil
      text = []
      if event.event_type == "assistant.delta" {
        delta = event
        text = [event.payload["text"].text]
      } else { apply(event) }
    }
    if var old = delta, case .object(var payload) = old.payload {
      payload["text"] = .string(text.joined())
      old.payload = .object(payload)
      apply(old)
    }
  }

  public mutating func apply(_ e: Event) {
    let p = e.payload
    let step = p["step_id"].text
    switch e.event_type {
    case "message.reaction.changed":
      if let i = messages.firstIndex(where: { $0.id == p["target"].text }) {
        messages[i].reactions[p["actor"].text] = p["emoji"].text.isEmpty ? nil : p["emoji"].text
      }
    case "user.message":
      pauseNotice = ""
      let id = p["user_context"]["hymio_message_id"].text
      if !id.isEmpty {
        messages.removeAll { $0.id == "local:\(id)" }
        rebuildIndices()
      }
      messages.append(
        ChatMessage(
          id: "user:\(e.id)", role: "user", content: p["content"].text, time: e.occur_dt,
          eventSeq: e.event_seq))
      working = true
      failure = ""
    case "assistant.delta"
    where ["content", "reasoning"].contains(p["channel"].text) && !step.isEmpty:
      if indices[step] == nil {
        indices[step] = messages.count
        messages.append(
          ChatMessage(
            id: "assistant:\(step)", role: "assistant", content: "", time: e.occur_dt,
            streaming: true, attempt: p["attempt"].int, trace: traces[step] ?? "",
            eventSeq: e.event_seq))
      }
      let i = indices[step]!
      guard messages[i].streaming else { return }
      let attempt = p["attempt"].int
      if attempt > messages[i].attempt {
        messages[i].rawContent = ""
        messages[i].content = ""
        messages[i].reasoning = ""
        messages[i].attempt = attempt
      }
      guard attempt == messages[i].attempt else { return }
      if p["channel"].text == "reasoning" {
        messages[i].reasoning += p["text"].text
        messages[i].thinking = true
      } else {
        messages[i].rawContent += p["text"].text
        messages[i].content = AgentSurface.proseAndQuickReplies(messages[i].rawContent).content
        messages[i].thinking = false
      }
      working = true
    case "assistant.message":
      let key = step.isEmpty ? String(e.id) : step
      if indices[key] == nil {
        indices[key] = messages.count
        messages.append(
          ChatMessage(
            id: "assistant:\(key)", role: "assistant", content: "", time: e.occur_dt,
            trace: traces[key] ?? ""))
      }
      let i = indices[key]!
      messages[i].eventSeq = e.event_seq
      messages[i].rawContent = p["content"].text
      let parsed = AgentSurface.proseAndQuickReplies(messages[i].rawContent)
      messages[i].content = parsed.content
      messages[i].suggestions = parsed.suggestions
      if p["reasoning"] != .null { messages[i].reasoning = p["reasoning"].text }
      messages[i].streaming = false
      messages[i].thinking = false
      messages[i].calls = p["tool_calls"].items
      if messages[i].calls.isEmpty { working = false }
    case "tool.terminal": terminals[p["invocation_id"].text] = p
    case "permission.requested":
      let target = p["target"]
      let description = p["arguments"]["description"].text.trimmingCharacters(
        in: .whitespacesAndNewlines)
      let approval = Approval(
        id: p["invocation_id"].text, tool: p["tool"].text, arguments: p["arguments"],
        status: "pending", expires: p["expires_at"].double,
        title: p["title"].text.isEmpty
          ? (description.isEmpty ? "允许执行操作？" : description) : p["title"].text,
        summary: p["summary"].text, risk: p["risk"].text.isEmpty ? "medium" : p["risk"].text,
        effects: p["effects"].items.map(\.text),
        target: ApprovalTarget(
          kind: target["kind"].text, id: target["id"].text, label: target["label"].text),
        scopeOptions: p["scope_options"].items.map(\.text).filter {
          ["once", "run", "exact_rule"].contains($0)
        },
        actionDigest: p["action_digest"].text, decidedAt: nil, decidedBy: "",
        decisionChannel: "", reason: "")
      if let i = approvals.firstIndex(where: { $0.id == approval.id }) {
        approvals[i] = approval
      } else {
        approvals.append(approval)
      }
    case "permission.resolved":
      if let i = approvals.firstIndex(where: { $0.id == p["invocation_id"].text }) {
        approvals[i].status = p["status"].text
        approvals[i].decidedAt = p["decided_at"].double
        approvals[i].decidedBy = p["client_id"].text
        approvals[i].decisionChannel = p["channel"].text
        approvals[i].reason = p["reason"].text
      }
    case "agent.paused" where p["reason"].text == "tool_only_budget":
      working = false
      pauseNotice = "本轮自动处理额度已用完，进展已保留。"
    case "agent.resumed":
      pauseNotice = ""
    case "step.status":
      let status = p["status"].text
      if !step.isEmpty, !p["trace_id"].text.isEmpty {
        traces[step] = p["trace_id"].text
        if let i = indices[step] { messages[i].trace = p["trace_id"].text }
      }
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
