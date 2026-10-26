import XCTest

@testable import HymioCore

final class TurnsTests: XCTestCase {
  private let start = "2026-01-01T00:00:00.000000Z"
  private func event(
    _ id: Int, _ type: String, _ fields: [String: JSON], at: String? = nil
  ) -> Event {
    Event(
      user_id: "alice", event_seq: id, event_type: type, payload: .object(fields),
      occur_dt: at ?? start)
  }
  private func stamp(_ seconds: Double) -> String {
    ISO8601DateFormatter().string(from: Date(timeIntervalSince1970: 1_767_225_600 + seconds))
      .replacingOccurrences(of: "Z", with: ".000000Z")
  }
  private func step(
    _ id: Int, _ stepId: String, _ status: String, _ trace: String, at: String? = nil
  )
    -> Event
  {
    event(
      id, "step.status",
      ["step_id": .string(stepId), "status": .string(status), "trace_id": .string(trace)],
      at: at)
  }
  private func call(
    _ id: Int, _ stepId: String, _ content: String, _ calls: [JSON], at: String? = nil
  )
    -> Event
  {
    event(
      id, "assistant.message",
      ["step_id": .string(stepId), "content": .string(content), "tool_calls": .array(calls)],
      at: at)
  }

  func testTraceCollapsesEverythingBeforeItsFinalMessage() {
    let model = Conversation(events: [
      event(1, "user.message", ["content": .string("跑个命令")], at: stamp(0)),
      step(2, "s1", "prepared", "t1", at: stamp(0)),
      call(3, "s1", "我先看看", [.object(["name": .string("bash")])], at: stamp(1)),
      step(4, "s1", "completed", "t1", at: stamp(2)),
      step(5, "s2", "prepared", "t1", at: stamp(2)),
      call(6, "s2", "好了", [], at: stamp(40)),
      step(7, "s2", "completed", "t1", at: stamp(40)),
    ])
    let turns = model.turns
    XCTAssertEqual(turns.count, 1)
    let turn = turns[0]
    XCTAssertEqual(turn.user?.content, "跑个命令")
    XCTAssertEqual(turn.activity.map(\.id), ["assistant:s1"])
    XCTAssertEqual(turn.final?.id, "assistant:s2")
    XCTAssertTrue(turn.settled)
    XCTAssertTrue(turn.foldable)
    XCTAssertEqual(traceElapsed(turn, serverNow: Date()), 40)
    XCTAssertEqual(formatDuration(traceElapsed(turn, serverNow: Date())), "40 秒")
  }

  func testFinalReasoningBelongsToWorkWithoutChangingStoredMessages() {
    for content in ["最终答案", ""] {
      var original = ChatMessage(id: "final", role: "assistant", content: content, time: start)
      original.reasoning = "核对结果"
      let turn = buildTurns([original])[0]
      XCTAssertTrue(turn.foldable)
      XCTAssertEqual(turn.activity.count, 1)
      XCTAssertEqual(turn.activity[0].reasoning, "核对结果")
      XCTAssertEqual(turn.activity[0].content, "")
      XCTAssertNotEqual(turn.activity[0].id, turn.final?.id)
      XCTAssertEqual(turn.final?.content ?? "", content)
      XCTAssertEqual(turn.final?.reasoning ?? "", "")
      XCTAssertEqual(turn.final == nil, content.isEmpty)
      XCTAssertEqual(original.reasoning, "核对结果")
      original.streaming = true
      let live = buildTurns([original])[0]
      XCTAssertFalse(live.foldable)
      let visible = content.isEmpty ? live.activity.first : live.final
      XCTAssertEqual(visible?.content, content)
      XCTAssertEqual(visible?.reasoning, "核对结果")
    }
  }

  func testStreamingAnswerKeepsItsSlotOnCompletion() {
    let user = ChatMessage(id: "user", role: "user", content: "Question", time: start)
    var answer = ChatMessage(id: "answer", role: "assistant", content: "Partial reply", time: start)
    answer.streaming = true
    let live = buildTurns([user, answer])[0]
    XCTAssertEqual(live.final?.id, "answer")
    XCTAssertTrue(live.activity.isEmpty)
    XCTAssertFalse(live.settled)
    answer.streaming = false
    let finished = buildTurns([user, answer])[0]
    XCTAssertEqual(live.id, finished.id)
    XCTAssertEqual(live.final?.id, finished.final?.id)
    XCTAssertTrue(finished.settled)
  }

  func testProactiveReplyPreservesPreviousFinalAnswer() {
    for trace in ["new", "t1", ""] {
      let model = Conversation(events: [
        event(1, "user.message", ["content": .string("你好")]),
        step(2, "s1", "prepared", "t1"),
        call(3, "s1", "之前的答案", []),
        step(4, "s2", "prepared", trace),
        call(5, "s2", "提醒到了", []),
      ])
      XCTAssertEqual(model.turns.count, 2)
      XCTAssertEqual(model.turns[0].trace, "t1")
      XCTAssertEqual(model.turns[0].final?.content, "之前的答案")
      XCTAssertEqual(model.turns[1].final?.content, "提醒到了")
      XCTAssertTrue(model.turns[1].activity.isEmpty)
    }
  }

  func testSnapshotStatusAfterMessageRestoresTrace() {
    let model = Conversation(events: [
      event(1, "user.message", ["content": .string("你好")]),
      call(2, "s1", "答案", []), step(3, "s1", "completed", "t1"),
      call(4, "s2", "提醒", []), step(5, "s2", "completed", "t2"),
    ])
    XCTAssertEqual(model.messages.filter { $0.role == "assistant" }.map(\.trace), ["t1", "t2"])
    XCTAssertEqual(model.turns.count, 2)
    XCTAssertEqual(model.turns[0].final?.content, "答案")
  }

  func testToolCallsNeverEndTheTrace() {
    let model = Conversation(events: [
      event(1, "user.message", ["content": .string("查一下")]),
      step(2, "s1", "prepared", "t1"),
      call(3, "s1", "我先查", [.object(["name": .string("bash")])]),
    ])
    XCTAssertEqual(model.turns.count, 1)
    XCTAssertNil(model.turns[0].final)
    XCTAssertFalse(model.turns[0].settled)
    XCTAssertEqual(model.turns[0].activity.count, 1)
  }

  func testLateTraceEventsReturnToTheirOriginalTurn() {
    // 老 trace 的工具步骤还在跑时用户插了一句话；新 trace 先跑完，老 trace 的最终回复后到。
    let model = Conversation(events: [
      event(1, "user.message", ["content": .string("先查这个")]),
      step(2, "s1", "prepared", "t1"),
      call(3, "s1", "先查", [.object(["name": .string("bash")])]),
      event(4, "user.message", ["content": .string("算了，换个方向")]),
      step(5, "s2", "prepared", "t2"),
      call(6, "s2", "换个方向", [.object(["name": .string("browser")])]),
      step(7, "s3", "prepared", "t2"),
      call(8, "s3", "都办完了", []),
      step(9, "s4", "prepared", "t1"),
      call(10, "s4", "先查那条也完了", []),
    ])
    XCTAssertEqual(model.turns.count, 2)
    XCTAssertEqual(model.turns[0].user?.content, "先查这个")
    XCTAssertEqual(model.turns[0].activity.map(\.id), ["assistant:s1"])
    XCTAssertEqual(model.turns[0].final?.id, "assistant:s4")
    XCTAssertTrue(model.turns[0].settled)
    XCTAssertEqual(model.turns[1].user?.content, "算了，换个方向")
    XCTAssertEqual(model.turns[1].activity.map(\.id), ["assistant:s2"])
    XCTAssertEqual(model.turns[1].final?.id, "assistant:s3")
    XCTAssertTrue(model.turns[1].settled)
  }

  func testHistoryWithoutTraceIdsSplitsOnUserMessages() {
    let model = Conversation(events: [
      event(1, "user.message", ["content": .string("一")]),
      call(2, "s1", "", [.object(["name": .string("bash")])]),
      call(3, "s2", "好", []),
      event(4, "user.message", ["content": .string("二")]),
      call(5, "s3", "在", []),
    ])
    XCTAssertEqual(model.turns.count, 2)
    XCTAssertTrue(model.turns[0].settled)
    XCTAssertTrue(model.turns[1].settled)
  }

  func testTraceAbandonedByTheNextUserMessageStillCollapses() {
    let model = Conversation(events: [
      event(1, "user.message", ["content": .string("一")]),
      step(2, "s1", "prepared", "t1"),
      call(3, "s1", "", [.object(["name": .string("bash")])]),
      event(4, "user.message", ["content": .string("二")]),
      call(5, "s2", "在", []),
    ])
    XCTAssertEqual(model.turns.count, 2)
    XCTAssertTrue(model.turns[0].settled)
    XCTAssertNil(model.turns[0].final)
    XCTAssertEqual(model.turns[0].activity.count, 1)
  }

  func testTraceWithNothingAfterTheUserMessageStaysOpen() {
    let model = Conversation(events: [event(1, "user.message", ["content": .string("在吗")])])
    XCTAssertEqual(model.turns.count, 1)
    XCTAssertFalse(model.turns[0].settled)
    XCTAssertTrue(model.turns[0].activity.isEmpty)
    XCTAssertNil(model.turns[0].endedAt)
  }

  func testElapsedFallsBackToServerClockWhileRunning() {
    let begin = Date(timeIntervalSince1970: 1_767_225_600)
    let model = Conversation(events: [
      event(1, "user.message", ["content": .string("跑起来")], at: stamp(0)),
      step(2, "s1", "prepared", "t1", at: stamp(4)),
      call(3, "s1", "", [.object(["name": .string("bash")])], at: stamp(4)),
    ])
    let turn = model.turns[0]
    XCTAssertNil(turn.endedAt)
    XCTAssertEqual(traceElapsed(turn, serverNow: begin.addingTimeInterval(9)), 9)
    XCTAssertNil(traceElapsed(turn, serverNow: begin))
  }

  func testDurationsReadTheWayAPersonWouldSayThem() {
    XCTAssertEqual(formatDuration(0.9), "1 秒")
    XCTAssertEqual(formatDuration(43), "43 秒")
    XCTAssertEqual(formatDuration(163), "2 分 43 秒")
    XCTAssertEqual(formatDuration(120), "2 分")
    XCTAssertEqual(formatDuration(7_260), "2 小时 1 分")
    XCTAssertEqual(formatDuration(nil), "")
  }
}
