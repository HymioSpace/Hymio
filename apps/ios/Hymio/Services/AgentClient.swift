import Combine
import Foundation
import UIKit

@MainActor final class AgentClient: ObservableObject {
  @Published private(set) var state = ConversationState()
  @Published private(set) var phase = "未连接"
  @Published var error = ""
  @Published var devices: [JSON] = []
  @Published private(set) var devicesLoading = false
  @Published private(set) var devicesError = ""
  private var devicesRequest = UUID()
  @Published var loadingHistory = false
  @Published private(set) var model = Conversation(events: [])
  private var cache: ConversationCache?
  private var loop: Task<Void, Never>?
  private var socket: URLSessionWebSocketTask?
  private var sent: Set<String> = []
  private var generation = UUID()
  private var owner = ""
  private var sourceDevice = ""
  private var ready = false
  private let account: AccountService
  init(account: AccountService) { self.account = account }
  var connected: Bool { ready }
  var user: String { account.session?.user_id ?? "" }
  var installationID: String {
    let key = "hymio.installation"
    if let old = UserDefaults.standard.string(forKey: key) { return old }
    let value = UUID().uuidString
    UserDefaults.standard.set(value, forKey: key)
    return value
  }
  func activate() {
    guard account.session != nil, loop == nil else { return }
    let token = UUID()
    generation = token
    loop = Task { [weak self] in await self?.run(token) }
  }
  func suspend() {
    generation = UUID()
    loop?.cancel()
    loop = nil
    ready = false
    socket?.cancel(with: .goingAway, reason: nil)
    socket = nil
    phase = "已暂停连接"
  }
  func reset() {
    suspend()
    try? cache?.clear()
    cache = nil
    owner = ""
    state = ConversationState()
    model = Conversation(events: [])
    devices = []
    devicesRequest = UUID()
    devicesLoading = false
    devicesError = ""
    sourceDevice = ""
    error = ""
  }
  func reconnect() {
    suspend()
    activate()
  }
  private func commit(_ next: ConversationState) throws {
    guard let cache else { throw ServiceError.message("消息存储未准备好") }
    try cache.save(next)
    state = next
    model = Conversation(events: next.events)
  }
  private func run(_ token: UUID) async {
    var attempts = 0
    while !Task.isCancelled && token == generation {
      var heartbeat: Task<Void, Never>?
      do {
        let s = try await account.credential()
        guard token == generation else { return }
        let key = account.backend.absoluteString + "|" + s.user_id
        if owner != key {
          let disk = try ConversationCache(backend: account.backend.absoluteString, user: s.user_id)
          cache = disk
          let restored = try disk.load()
          owner = key
          state = restored
          model = Conversation(events: restored.events)
        }
        phase = attempts == 0 ? "正在连接" : "重新连接中"
        guard let endpoint = URL(string: s.oath_ws) else { throw ServiceError.message("聊天地址无效") }
        try account.validated(endpoint, socket: true)
        let ws = URLSession.shared.webSocketTask(with: endpoint)
        socket = ws
        sent = []
        ready = false
        ws.resume()
        try await send(
          Command(
            type: "agent.attach",
            payload: .object([
              "credential": .string(s.access_token), "user_id": .string(s.user_id),
              "client_id": .string(state.clientID), "history_limit": .number(10),
            ])), socket: ws)
        heartbeat = Task { [weak self, weak ws] in
          while !Task.isCancelled {
            try? await Task.sleep(for: .seconds(20))
            guard !Task.isCancelled, let self, let ws, token == self.generation else { return }
            if Date().timeIntervalSince1970 > s.expires_at - 45 {
              ws.cancel(with: .goingAway, reason: nil)
              return
            }
            ws.sendPing { failure in if failure != nil { ws.cancel(with: .goingAway, reason: nil) }
            }
            if self.ready {
              try? await self.send(Command(type: "agent.status", payload: .object([:])), socket: ws)
              guard token == self.generation, !self.sourceDevice.isEmpty else { continue }
              _ = try? await self.account.request(
                "devices/\(self.sourceDevice)/heartbeat", body: .object([:]))
            }
          }
        }
        // A receive timeout also covers attachment/snapshot stalls, not just TCP failures.
        while !Task.isCancelled && token == generation {
          let message = try await receive(ws)
          guard token == generation else { return }
          let data: Data
          switch message {
          case .string(let text): data = Data(text.utf8)
          case .data(let bytes): data = bytes
          @unknown default: continue
          }
          let frame = try JSON.decode(data)
          try await consume(frame, raw: data, socket: ws)
          if ready { attempts = 0 }
        }
      } catch is CancellationError {
        heartbeat?.cancel()
        return
      } catch {
        guard token == generation else {
          heartbeat?.cancel()
          return
        }
        self.error = error.localizedDescription
        phase = "重新连接中"
        ready = false
        socket?.cancel(with: .goingAway, reason: nil)
        if case ServiceError.unauthorized = error {
          phase = "需要登录"
          heartbeat?.cancel()
          break
        }
      }
      heartbeat?.cancel()
      attempts += 1
      try? await Task.sleep(for: .seconds(min(pow(2, Double(min(attempts, 5))), 30)))
    }
    if token == generation { loop = nil }
  }
  private func receive(_ ws: URLSessionWebSocketTask) async throws
    -> URLSessionWebSocketTask.Message
  {
    try await withThrowingTaskGroup(of: URLSessionWebSocketTask.Message.self) { group in
      group.addTask { try await ws.receive() }
      group.addTask {
        try await Task.sleep(for: .seconds(55))
        ws.cancel(with: .goingAway, reason: nil)
        throw ServiceError.message("连接超时，正在恢复。")
      }
      defer { group.cancelAll() }
      return try await group.next()!
    }
  }
  private func send(_ command: Command, socket: URLSessionWebSocketTask) async throws {
    try await socket.send(.string(String(decoding: JSONEncoder().encode(command), as: UTF8.self)))
  }
  private func consume(_ f: JSON, raw: Data, socket ws: URLSessionWebSocketTask) async throws {
    guard f["v"].int == 2 else { throw ServiceError.message("聊天协议版本不匹配") }
    switch f["type"].text {
    case "ack":
      if !f["user_id"].text.isEmpty && f["user_id"].text != user { throw ProtocolFailure.identity }
      var next = state
      next.pending.removeAll { $0.id == f["id"].text }
      try commit(next)
    case "conversation.snapshot":
      let events = try JSONDecoder().decode([Event].self, from: JSONEncoder().encode(f["events"]))
      var next = state
      try next.snapshot(
        events, checkpoint: f["checkpoint"].int,
        before: f["before_cursor"] == .null ? nil : f["before_cursor"].int,
        hasMore: f["has_more"].flag, user: user)
      try commit(next)
      try await ack(ws)
    case "event":
      let event = try JSONDecoder().decode(Event.self, from: raw)
      do {
        var next = state
        try next.append(event, user: user)
        try commit(next)
      } catch ProtocolFailure.gap {
        var next = state
        next.clientID = "hymio-ios-" + UUID().uuidString
        try commit(next)
        throw ProtocolFailure.gap
      }
      try await ack(ws)
    case "offline.start":
      guard f["after_cursor"].int <= state.cursor else {
        var next = state
        next.clientID = "hymio-ios-" + UUID().uuidString
        try commit(next)
        throw ProtocolFailure.gap
      }
      phase = "正在同步进展"
    case "offline.end":
      ready = true
      phase = "随时在这里"
      error = ""
      try await ack(ws)
      try await flush(ws)
      Task { await register() }
    case "error":
      if ["unauthorized", "auth_failed"].contains(f["code"].text) {
        throw ServiceError.unauthorized
      }
      if state.pending.contains(where: { $0.id == f["id"].text }) {
        error = f["message"].text
        return
      }
      throw ServiceError.message(f["message"].text.isEmpty ? "聊天服务暂不可用" : f["message"].text)
    default: break
    }
  }
  private func ack(_ ws: URLSessionWebSocketTask) async throws {
    try await send(
      Command(type: "event.ack", payload: .object(["cursor": .number(Double(state.cursor))])),
      socket: ws)
  }
  private func flush(_ ws: URLSessionWebSocketTask) async throws {
    for cmd in state.pending where !sent.contains(cmd.id) {
      try await send(cmd, socket: ws)
      sent.insert(cmd.id)
    }
  }
  func command(_ type: String, _ payload: [String: JSON]) async throws {
    guard ready, let socket else { throw ServiceError.message("连接恢复后再发送，草稿会保留。") }
    var next = state
    next.pending.append(Command(type: type, payload: .object(payload)))
    try commit(next)
    do { try await flush(socket) } catch {
      // Once persisted, reconnect owns delivery of this command ID.
      self.error = "消息已保存，正在恢复连接。"
      ready = false
      phase = "重新连接中"
      socket.cancel(with: .goingAway, reason: nil)
    }
  }
  func message(_ text: String) async throws {
    try await command(
      "user.message",
      [
        "content": .string(text),
        "user_context": .object([
          "locale": .string(Locale.current.identifier),
          "time_zone": .string(TimeZone.current.identifier),
          "source_device_id": .string(sourceDevice), "client_id": .string(state.clientID),
          "received_event_seq": .number(Double(state.cursor)),
        ]),
      ])
  }
  func decide(_ id: String, _ approved: Bool) async {
    do {
      try await command(
        "permission.decide",
        ["invocation_id": .string(id), "status": .string(approved ? "approved" : "denied")])
    } catch { self.error = error.localizedDescription }
  }
  func loadHistory() async {
    guard !loadingHistory, state.hasMore, let before = state.before else { return }
    loadingHistory = true
    let token = generation
    defer { loadingHistory = false }
    do {
      let s = try await account.credential()
      let data = try await account.raw(
        "oath-biz/conversation_history?before=\(before)&limit=10", token: s.access_token)
      guard token == generation else { return }
      let page = try JSON.decode(data)
      let older = try JSONDecoder().decode([Event].self, from: JSONEncoder().encode(page["events"]))
      guard older.allSatisfy({ $0.user_id == user && $0.id <= state.cursor }) else {
        throw ProtocolFailure.identity
      }
      var next = state
      var merged = Dictionary(uniqueKeysWithValues: older.map { ($0.id, $0) })
      for event in state.events { merged[event.id] = event }
      next.events = merged.values.sorted { $0.id < $1.id }
      next.before = page["before_cursor"] == .null ? nil : page["before_cursor"].int
      next.hasMore = page["has_more"].flag
      try commit(next)
    } catch { self.error = error.localizedDescription }
  }
  func register() async {
    let token = generation
    do {
      let value = try await account.request(
        "devices/register",
        body: .object(["installation_id": .string(installationID), "kind": .string("ios")]))
      guard token == generation else { return }
      sourceDevice = value["device_id"].text
      _ = try? await account.request("devices/\(sourceDevice)/heartbeat", body: .object([:]))
      _ = try? await account.request("devices/ensure", body: .object([:]), timeout: 130)
    } catch { /* Device preparation does not block conversation. */  }
  }
  func loadDevices() async {
    let requestedUser = user
    guard !requestedUser.isEmpty else { return }
    let request = UUID()
    devicesRequest = request
    devicesLoading = true
    devicesError = ""
    defer { if request == devicesRequest { devicesLoading = false } }
    do {
      let result = try await account.request("devices")["devices"].items
      guard request == devicesRequest, requestedUser == user else { return }
      devices = result
    } catch {
      guard request == devicesRequest, requestedUser == user, !Task.isCancelled else { return }
      devicesError = "设备暂时无法读取，对话仍可继续。"
    }
  }
}
