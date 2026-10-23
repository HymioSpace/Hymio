import Foundation

public enum JSON: Codable, Hashable, Sendable {
  case string(String)
  case number(Double)
  case bool(Bool)
  case object([String: JSON])
  case array([JSON])
  case null
  public init(from decoder: Decoder) throws {
    let c = try decoder.singleValueContainer()
    if c.decodeNil() {
      self = .null
    } else if let v = try? c.decode(Bool.self) {
      self = .bool(v)
    } else if let v = try? c.decode(Double.self) {
      self = .number(v)
    } else if let v = try? c.decode(String.self) {
      self = .string(v)
    } else if let v = try? c.decode([String: JSON].self) {
      self = .object(v)
    } else {
      self = .array(try c.decode([JSON].self))
    }
  }
  public func encode(to encoder: Encoder) throws {
    var c = encoder.singleValueContainer()
    switch self {
    case .string(let v): try c.encode(v)
    case .number(let v): try c.encode(v)
    case .bool(let v): try c.encode(v)
    case .object(let v): try c.encode(v)
    case .array(let v): try c.encode(v)
    case .null: try c.encodeNil()
    }
  }
  public subscript(_ key: String) -> JSON {
    if case .object(let v) = self { return v[key] ?? .null }
    return .null
  }
  public var text: String {
    if case .string(let v) = self { return v }
    return ""
  }
  public var int: Int {
    if case .number(let v) = self, v.isFinite, v >= 0, v < Double(Int.max) { return Int(v) }
    return 0
  }
  public var double: Double {
    if case .number(let v) = self { return v }
    return 0
  }
  public var flag: Bool {
    if case .bool(let v) = self { return v }
    return false
  }
  public var items: [JSON] {
    if case .array(let v) = self { return v }
    return []
  }
  public var pretty: String {
    let e = JSONEncoder()
    e.outputFormatting = [.prettyPrinted, .sortedKeys]
    return (try? String(data: e.encode(self), encoding: .utf8)) ?? ""
  }
  public static func decode(_ data: Data) throws -> JSON {
    try JSONDecoder().decode(JSON.self, from: data)
  }
}

public struct Event: Codable, Identifiable, Equatable, Sendable {
  public var user_id: String
  public var event_seq: Int
  public var event_type: String
  public var payload: JSON
  public var occur_dt: String
  public var id: Int { event_seq }
  public init(
    user_id: String, event_seq: Int, event_type: String, payload: JSON, occur_dt: String = ""
  ) {
    self.user_id = user_id
    self.event_seq = event_seq
    self.event_type = event_type
    self.payload = payload
    self.occur_dt = occur_dt
  }
}
public struct Command: Codable, Identifiable, Sendable {
  public var v = 2
  public var id = UUID().uuidString
  public var type: String
  public var payload: JSON
  public var createdAt: String?
  public init(type: String, payload: JSON) {
    self.type = type
    self.payload = payload
    self.createdAt = Date().ISO8601Format()
  }
}
public struct ConversationState: Codable, Sendable {
  public var events: [Event] = []
  public var cursor = 0
  public var before: Int?
  public var hasMore = false
  public var pending: [Command] = []
  public var accepted: Set<String>?
  public var rejected: Set<String>?
  public var unreadAfter: Int?
  public var unreadThrough: Int?
  public var clientID = "hymio-ios-" + UUID().uuidString
  public init() {}
  public mutating func finishReplay(after: Int?) {
    guard let after, after > 0,
      events.contains(where: {
        $0.event_seq > after && $0.event_seq <= cursor && $0.event_type == "assistant.message"
          && !$0.payload["content"].text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
          && $0.payload["tool_calls"].items.isEmpty
      })
    else { return }
    unreadAfter = min(unreadAfter ?? after, after)
    unreadThrough = cursor
  }
  public mutating func snapshot(
    _ events: [Event], checkpoint: Int, before: Int?, hasMore: Bool, user: String
  ) throws {
    guard checkpoint >= 0,
      events.allSatisfy({ $0.user_id == user && $0.event_seq > 0 && $0.event_seq <= checkpoint })
    else { throw ProtocolFailure.invalidSnapshot }
    self.events = events.filter(Self.isDisplayEvent).sorted { $0.id < $1.id }
    reconcile()
    cursor = checkpoint
    self.before = before
    self.hasMore = hasMore
  }
  public mutating func append(_ event: Event, user: String) throws {
    guard event.user_id == user, event.event_seq > 0 else { throw ProtocolFailure.identity }
    if event.event_seq <= cursor { return }
    guard event.event_seq == cursor + 1 else { throw ProtocolFailure.gap }
    if Self.isDisplayEvent(event) {
      let step = event.payload["step_id"].text
      if event.event_type == "assistant.message" {
        events.removeAll {
          $0.event_type == "assistant.delta" && $0.payload["step_id"].text == step
        }
      }
      if event.event_type == "assistant.delta",
        let i = events.lastIndex(where: {
          $0.event_type == "assistant.delta" && $0.payload["step_id"].text == step
            && $0.payload["channel"] == event.payload["channel"]
            && $0.payload["attempt"] == event.payload["attempt"]
        }), case .object(var payload) = event.payload
      {
        payload["text"] = .string(events[i].payload["text"].text + event.payload["text"].text)
        events.remove(at: i)
        var combined = event
        combined.payload = .object(payload)
        events.append(combined)
      } else {
        events.append(event)
      }
      if event.event_type == "user.message" { reconcile() }
    }
    cursor = event.event_seq
  }
  public static func isDisplayEvent(_ event: Event) -> Bool {
    [
      "user.message", "assistant.delta", "assistant.message", "tool.terminal",
      "permission.requested", "permission.resolved", "step.status", "message.reaction.changed",
    ].contains(event.event_type)
  }
  public mutating func reconcile() {
    let ids = Set(
      events.filter { $0.event_type == "user.message" }.map {
        $0.payload["user_context"]["hymio_message_id"].text
      }.filter { !$0.isEmpty })
    pending.removeAll { ids.contains($0.id) }
    accepted = accepted?.subtracting(ids)
    rejected = rejected?.subtracting(ids)
  }
}
public enum ProtocolFailure: Error { case invalidSnapshot, identity, gap }
