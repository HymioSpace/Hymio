import Foundation
import XCTest
@testable import HymioCore

final class StreamingPipelineTests: XCTestCase {
  func testInternalPayloadIsNotMaterializedButCursorAndOwnerRemain() throws {
    let data = Data("""
      {"v":2,"type":"event","user_id":"synthetic","event_seq":1,
      "event_type":"runtime.commit","occur_dt":"2026-01-01T00:00:00Z",
      "payload":{"private_state":"\(String(repeating: "x", count: 1_000_000))"}}
      """.utf8)
    let decoded = try IncomingFrame.decode(data)
    XCTAssertEqual(decoded.event?.payload, .null)
    var state = ConversationState()
    try state.append(try XCTUnwrap(decoded.event), user: "synthetic")
    XCTAssertEqual(state.cursor, 1)
    XCTAssertTrue(state.events.isEmpty)
    XCTAssertThrowsError(try state.append(try XCTUnwrap(decoded.event), user: "someone-else"))
  }

  func testSyntheticInternalFrameDecodeBenchmark() throws {
    let items = (0..<2000).map { ["key": "synthetic-\($0)", "text": String(repeating: "synthetic", count: 32)] }
    let data = try JSONSerialization.data(withJSONObject: [
      "v": 2, "type": "event", "user_id": "synthetic", "event_seq": 1,
      "event_type": "runtime.commit", "occur_dt": "2026-01-01T00:00:00Z", "payload": ["items": items],
    ])
    let before = ProcessInfo.processInfo.systemUptime
    for _ in 0..<3 {
      _ = try JSON.decode(data)
      _ = try JSONDecoder().decode(Event.self, from: data)
    }
    let middle = ProcessInfo.processInfo.systemUptime
    for _ in 0..<3 {
      let frame = try IncomingFrame.decode(data)
      XCTAssertEqual(frame.event?.payload, .null)
    }
    let after = ProcessInfo.processInfo.systemUptime
    print("STREAM_DECODE_BENCH bytes=\(data.count) old_ms=\((middle-before)*1000/3) envelope_ms=\((after-middle)*1000/3)")
  }

  func testDisplayAndSnapshotKeepTheirContents() throws {
    let frame = try IncomingFrame.decode(Data("""
      {"v":2,"type":"conversation.snapshot","checkpoint":3,"before_cursor":null,"has_more":false,
      "events":[{"user_id":"synthetic","event_seq":3,"event_type":"assistant.message",
      "payload":{"content":"Hello"},"occur_dt":"2026-01-01T00:00:00Z"}]}
      """.utf8))
    XCTAssertEqual(frame.snapshot?.first?.payload["content"].text, "Hello")
    XCTAssertEqual(frame.frame["checkpoint"].int, 3)
    XCTAssertNil(frame.event)
  }

  func testBatchedDeltasMatchOrderedIndividualProjection() {
    func delta(_ seq: Int, _ text: String, channel: String = "content", attempt: Int = 1) -> Event {
      Event(user_id: "synthetic", event_seq: seq, event_type: "assistant.delta", payload: .object([
        "step_id": .string("step"), "attempt": .number(Double(attempt)),
        "channel": .string(channel), "text": .string(text),
      ]))
    }
    let events = [delta(1, "Thinking", channel: "reasoning"), delta(2, "🦦"), delta(3, "你好"),
                  delta(4, "retry", attempt: 2), delta(5, " done", attempt: 2),
                  Event(user_id: "synthetic", event_seq: 6, event_type: "assistant.message",
                    payload: .object(["step_id": .string("step"), "content": .string("retry done")]))]
    var one = Conversation(events: [])
    for event in events { one.apply(event) }
    var batch = Conversation(events: [])
    batch.apply(events)
    XCTAssertEqual(batch.messages, one.messages)
    XCTAssertEqual(batch.turns, one.turns)
  }

  func testLargeCompletionDrainsWithoutReplayingVisiblePrefix() {
    var buffer = PresentationBuffer()
    let text = String(repeating: "🦦你好", count: 3000)
    buffer.set(text, now: 0)
    buffer.tick(0.2)
    let prefix = buffer.value
    XCTAssertFalse(prefix.isEmpty)
    buffer.complete(now: 0.2)
    for time in stride(from: 0.25, through: 0.7, by: 0.05) { buffer.tick(time) }
    XCTAssertFalse(buffer.pending)
    XCTAssertEqual(buffer.value, text)
    XCTAssertTrue(buffer.value.hasPrefix(prefix))
  }

  func testExtendedEmojiStillRevealsACompleteGrapheme() {
    var buffer = PresentationBuffer()
    buffer.set("👩", now: 0, immediate: true)
    buffer.set("👩‍💻", now: 1)
    buffer.complete(now: 1)
    buffer.tick(1.5)
    XCTAssertEqual(buffer.value, "👩‍💻")
    XCTAssertFalse(buffer.pending)
  }

  func testFinalCorrectionPreservesAlreadyVisiblePrefix() {
    var buffer = PresentationBuffer()
    buffer.set("Hello worl", now: 0, immediate: true)
    buffer.set("Hello world!", now: 1)
    XCTAssertEqual(buffer.value, "Hello worl")
    buffer.set("Hello work!", now: 1.1)
    XCTAssertEqual(buffer.value, "Hello wor")
  }
}

final class ProductErrorTests: XCTestCase {
  func testTransportAndCodeErrorsNeverBecomeProductCopy() {
    for raw in ["NSURLErrorDomain -1005", "The operation couldn’t be completed", "HTTP 503", "{" + "error: traceback" + "}"] {
      let shown = userFacingError(raw)
      XCTAssertFalse(shown.contains(raw))
      XCTAssertTrue(shown.contains("重试"))
    }
    XCTAssertTrue(userFacingError("expired", phase: "需要登录").contains("登录"))
  }
}
