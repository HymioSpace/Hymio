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
  public init(type: String, payload: JSON) {
    self.type = type
    self.payload = payload
  }
}
public struct ConversationState: Codable, Sendable {
  public var events: [Event] = []
  public var cursor = 0
  public var before: Int?
  public var hasMore = false
  public var pending: [Command] = []
  public var clientID = "hymio-ios-" + UUID().uuidString
  public init() {}
  public mutating func snapshot(
    _ events: [Event], checkpoint: Int, before: Int?, hasMore: Bool, user: String
  ) throws {
    guard checkpoint >= 0,
      events.allSatisfy({ $0.user_id == user && $0.event_seq > 0 && $0.event_seq <= checkpoint })
    else { throw ProtocolFailure.invalidSnapshot }
    self.events = events.sorted { $0.id < $1.id }
    cursor = checkpoint
    self.before = before
    self.hasMore = hasMore
  }
  public mutating func append(_ event: Event, user: String) throws {
    guard event.user_id == user, event.event_seq > 0 else { throw ProtocolFailure.identity }
    if event.event_seq <= cursor { return }
    guard event.event_seq == cursor + 1 else { throw ProtocolFailure.gap }
    events.append(event)
    cursor = event.event_seq
  }
}
public enum ProtocolFailure: Error { case invalidSnapshot, identity, gap }
