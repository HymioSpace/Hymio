import XCTest

@testable import HymioCore

final class ConversationTests: XCTestCase {
  func testAssistantReactionAttachesToUserMessage() {
    let model = Conversation(events: [
      event(1, "user.message", ["content": .string("done")]),
      event(
        2, "message.reaction.changed",
        [
          "target": .string("user:1"), "actor": .string("assistant"), "emoji": .string("🎉"),
        ]),
    ])
    XCTAssertEqual(model.messages.count, 1)
    XCTAssertEqual(model.messages[0].reactions["assistant"], "🎉")
  }

  private func event(_ id: Int, _ type: String, _ fields: [String: JSON], user: String = "alice")
    -> Event
  {
    Event(user_id: user, event_seq: id, event_type: type, payload: .object(fields))
  }
  func testSnapshotThenContinuousReplayRejectsGapAndOtherUser() throws {
    var state = ConversationState()
    let older = event(20, "user.message", ["content": .string("hello")])
    try state.snapshot([older], checkpoint: 100, before: 20, hasMore: true, user: "alice")
    let next = event(101, "assistant.message", ["step_id": .string("s"), "content": .string("hi")])
    try state.append(next, user: "alice")
    try state.append(next, user: "alice")
    XCTAssertEqual(state.events.count, 2)
    XCTAssertThrowsError(try state.append(event(103, "user.message", [:]), user: "alice"))
    XCTAssertThrowsError(
      try state.append(event(102, "user.message", [:], user: "bob"), user: "alice"))
    XCTAssertEqual(state.cursor, 101)
  }
  func testRetryAttemptAndTerminalReplaceStream() {
    let model = Conversation(events: [
      event(
        1, "assistant.delta",
        [
          "step_id": .string("s"), "channel": .string("content"), "text": .string("discard"),
          "attempt": .number(0),
        ]),
      event(
        2, "assistant.delta",
        [
          "step_id": .string("s"), "channel": .string("content"), "text": .string("new"),
          "attempt": .number(1),
        ]),
      event(3, "assistant.message", ["step_id": .string("s"), "content": .string("final")]),
      event(
        4, "assistant.delta",
        [
          "step_id": .string("s"), "channel": .string("content"), "text": .string("late"),
          "attempt": .number(1),
        ]),
    ])
    XCTAssertEqual(model.messages.count, 1)
    XCTAssertEqual(model.messages[0].content, "final")
    XCTAssertFalse(model.messages[0].streaming)
  }
  func testFinalMessageAttachesHiddenQuickReplies() {
    let content = "先这样。\n\n```hymio-quick\n[\"先停下吧\",\"换个方向\"]\n```"
    let model = Conversation(events: [
      event(1, "assistant.message", ["step_id": .string("s"), "content": .string(content)])
    ])
    XCTAssertEqual(model.messages[0].content, "先这样。")
    XCTAssertEqual(model.messages[0].suggestions, ["先停下吧", "换个方向"])
  }
  func testCacheAccountIsolationAndPendingCommandSurvivesRestart() throws {
    let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    defer { try? FileManager.default.removeItem(at: root) }
    let a = try ConversationCache(backend: "https://example.test", user: "alice", root: root)
    let b = try ConversationCache(backend: "https://example.test", user: "bob", root: root)
    var state = ConversationState()
    state.pending = [
      Command(type: "user.message", payload: .object(["content": .string("persist")]))
    ]
    try a.save(state)
    XCTAssertEqual(try a.load().pending.first?.id, state.pending.first?.id)
    XCTAssertTrue(try b.load().pending.isEmpty)
    try a.clear()
    XCTAssertTrue(try a.load().pending.isEmpty)
  }
  func testApprovalCanResolveWhileOtherToolsContinue() {
    let model = Conversation(events: [
      event(
        1, "permission.requested",
        ["invocation_id": .string("a"), "tool": .string("bash"), "expires_at": .number(999)]),
      event(2, "tool.terminal", ["invocation_id": .string("b"), "outcome": .string("succeeded")]),
      event(
        3, "permission.resolved", ["invocation_id": .string("a"), "status": .string("denied")]),
    ])
    XCTAssertEqual(model.approvals[0].status, "denied")
    XCTAssertEqual(model.terminals["b"]?["outcome"].text, "succeeded")
  }
  func testOptimisticOutboxAndReasoning() throws {
    let command = Command(type: "user.message", payload: .object(["content": .string("hello")]))
    let pending = Conversation(events: [], pending: [command], accepted: [command.id])
    XCTAssertEqual(pending.messages.first?.delivery, "accepted")
    XCTAssertTrue(pending.awaitingReply)
    let delta = event(
      1, "assistant.delta",
      ["step_id": .string("s"), "channel": .string("reasoning"), "text": .string("checking")])
    var model = Conversation(events: [delta])
    XCTAssertEqual(model.messages.first?.reasoning, "checking")
    XCTAssertTrue(model.messages.first?.thinking == true)
    model.apply(
      event(
        2, "assistant.message",
        ["step_id": .string("s"), "content": .string("done"), "reasoning": .string("checked")]))
    XCTAssertFalse(model.messages.first?.thinking == true)
    XCTAssertEqual(model.messages.first?.reasoning, "checked")
  }
  func testInternalEventsAdvanceCursorWithoutCachingPayload() throws {
    var state = ConversationState()
    try state.append(event(1, "runtime.commit", ["private": .string("large state")]), user: "alice")
    XCTAssertEqual(state.cursor, 1)
    XCTAssertTrue(state.events.isEmpty)
    try state.append(
      event(
        2, "assistant.delta",
        ["step_id": .string("s"), "channel": .string("content"), "text": .string("one")]),
      user: "alice")
    try state.append(
      event(
        3, "assistant.delta",
        ["step_id": .string("s"), "channel": .string("content"), "text": .string("two")]),
      user: "alice")
    XCTAssertEqual(state.events.count, 1)
    XCTAssertEqual(Conversation(events: state.events).messages.first?.content, "onetwo")
    XCTAssertThrowsError(try state.append(event(5, "user.message", [:]), user: "alice"))
  }

  func testFailedSendKeepsItsPositionBeforeLaterReminder() {
    var pending = Command(type: "user.message", payload: .object(["content": .string("hello")]))
    pending.createdAt = "2026-01-01T01:00:00Z"
    let later = Event(
      user_id: "alice", event_seq: 9, event_type: "assistant.message",
      payload: .object(["step_id": .string("reminder"), "content": .string("提醒")]),
      occur_dt: "2026-01-01T02:00:00Z")
    let model = Conversation(events: [later], pending: [pending], rejected: [pending.id])
    XCTAssertEqual(model.messages.map(\.id), ["local:\(pending.id)", "assistant:reminder"])
    XCTAssertEqual(model.messages.first?.delivery, "failed")
    XCTAssertEqual(model.messages.last?.eventSeq, 9)
  }

  func testUnreadBoundarySurvivesSnapshotReplacingReplay() throws {
    var state = ConversationState()
    let reply = Event(
      user_id: "alice", event_seq: 20, event_type: "assistant.message",
      payload: .object(["step_id": .string("s"), "content": .string("reminder")]))
    try state.snapshot([reply], checkpoint: 22, before: nil, hasMore: false, user: "alice")
    state.finishReplay(after: 10)
    XCTAssertEqual(state.unreadAfter, 10)
    XCTAssertEqual(state.unreadThrough, 22)
    let restored = try JSONDecoder().decode(
      ConversationState.self, from: JSONEncoder().encode(state))
    XCTAssertEqual(restored.unreadAfter, 10)
    var fresh = ConversationState()
    try fresh.snapshot([reply], checkpoint: 22, before: nil, hasMore: false, user: "alice")
    fresh.finishReplay(after: nil)
    XCTAssertNil(fresh.unreadAfter)
  }

}
