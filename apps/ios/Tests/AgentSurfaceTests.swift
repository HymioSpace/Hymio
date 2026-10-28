import XCTest

@testable import HymioCore

final class AgentSurfaceTests: XCTestCase {
  func testSharedCatalogFixtures() throws {
    let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
      .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
    let fixtures = try JSON.decode(
      Data(contentsOf: root.appendingPathComponent("packages/protocol/fixtures/agent-ui.json")))
    for item in fixtures.items {
      XCTAssertEqual(AgentSurface.valid(item["spec"]), item["valid"].flag, item["name"].text)
    }
    XCTAssertFalse(
      AgentSurface.parts("~~~text\n```hymio-ui\n{}\n```\n~~~", streaming: false).contains(
        where: \.isUI))
  }
  func testStableMarkdownWaitsForClosedBlocks() {
    let text = "First paragraph.\n\n```swift\nlet value = 1\n\n"
    let parts = AgentSurface.stableMarkdown(text)
    XCTAssertEqual(parts.stable, "First paragraph.\n\n")
    XCTAssertTrue(parts.tail.hasPrefix("```swift"))
  }
  func testUnicodeBufferAndFinalDrain() {
    var b = PresentationBuffer()
    b.set("🦦你好👨‍👩‍👧‍👦", now: 0)
    b.tick(0.04)
    XCTAssertEqual(b.value, "")
    b.tick(0.15)
    XCTAssertEqual(b.value, "🦦")
    b.complete(now: 0.15)
    b.tick(0.7)
    XCTAssertEqual(b.value, "🦦你好👨‍👩‍👧‍👦")
    b.set("改写", now: 1)
    XCTAssertEqual(b.value, "")
    b.set("历史", now: 2, immediate: true)
    XCTAssertEqual(b.value, "历史")
    XCTAssertFalse(b.pending)
  }
  func testNoAccumulatedCreditAfterStall() {
    var b = PresentationBuffer()
    b.set("a", now: 0)
    b.tick(0.2)
    b.tick(100)
    b.set("abcdefghijklmno", now: 100.001)
    b.tick(100.002)
    XCTAssertEqual(b.value, "a")
  }
  func testAppendedUnicodeClustersAndLongStreamDrain() {
    for parts in [["e", "́", "好"], ["👨", "‍👩", "‍👧‍👦"], ["🇨", "🇳", "🇺", "🇸"]] {
      var buffer = PresentationBuffer()
      var text = ""
      for part in parts {
        text += part
        buffer.set(text, now: 0, immediate: true)
        XCTAssertEqual(buffer.value, text)
      }
      let final = text + String(repeating: "中文🦦", count: 10000)
      buffer.set(final, now: 1)
      buffer.tick(1.1)
      XCTAssertTrue(buffer.value.hasPrefix(text))
      buffer.complete(now: 1.1)
      buffer.tick(1.6)
      XCTAssertEqual(buffer.value, final)
      XCTAssertFalse(buffer.pending)
    }
  }
  func testAdaptiveJitterPacingKeepsContinuityAndFinalContent() {
    let intervals = [0.04, 0.08, 0.36, 0.04, 0.16, 0.28]
    var events: [(Double, String)] = []
    var at = 0.0
    for index in 0..<60 {
      at += intervals[index % intervals.count]
      events.append((at, String(repeating: "字", count: (index + 1) * 8)))
    }
    var b = PresentationBuffer()
    var event = 0
    var shown = 0
    var last: Double?
    var gaps: [Double] = []
    var completed = false
    for frame in 0...Int((at + 0.6) / 0.016) {
      let now = Double(frame) * 0.016
      while event < events.count && events[event].0 <= now {
        b.set(events[event].1, now: now)
        event += 1
      }
      if event == events.count && !completed {
        b.complete(now: now)
        completed = true
      }
      b.tick(now)
      if b.value.count > shown {
        if let previous = last { gaps.append(now - previous) }
        last = now
        shown = b.value.count
      }
    }
    XCTAssertEqual(b.value, events.last?.1)
    XCTAssertFalse(b.pending)
    XCTAssertLessThanOrEqual(gaps.max() ?? 1, 0.18)
    print("JITTER_TRACE max_gap_ms=\((gaps.max() ?? 0) * 1000)")
  }
  func testPartialPatchKeepsLastFrame() {
    let source = """
      {"op":"add","path":"/root","value":"card"}
      {"op":"add","path":"/elements/card","value":{"type":"Card","props":{"title":"Hello"},"children":["text"]}}
      """
    let partial = AgentSurface.parse(source + "\n{\"op\":", complete: false)
    XCTAssertEqual(partial.spec?["root"].text, "card")
    XCTAssertFalse(partial.error)
    XCTAssertTrue(AgentSurface.parse(source + "\n{\"op\":", complete: true).error)
    XCTAssertTrue(
      AgentSurface.parse(
        source
          + "\n{\"op\":\"add\",\"path\":\"/elements/card\",\"value\":{\"type\":\"Script\",\"props\":{}}}",
        complete: true
      ).error)
    XCTAssertTrue(AgentSurface.parse(String(repeating: "x", count: 65537), complete: false).error)
  }
  func testCycleAndActionContract() throws {
    let cyclic = try JSON.decode(
      Data(
        "{\"root\":\"card\",\"elements\":{\"card\":{\"type\":\"Card\",\"props\":{},\"children\":[\"card\"]}}}"
          .utf8))
    XCTAssertFalse(AgentSurface.valid(cyclic))
    XCTAssertEqual(
      AgentSurface.prompt("Plan {{duration}} {{unknown}}", values: ["duration": "30 minutes"]),
      "Plan 30 minutes")
    let parts = AgentSurface.parts("Hello\n```hymio-ui\n{}\n```\nDone", streaming: false)
    XCTAssertEqual(parts.map(\.isUI), [false, true, false])
  }
  func testQuickRepliesStayHiddenAndAreBounded() {
    let result = AgentSurface.proseAndQuickReplies(
      "先这样。\n\n```hymio-quick\n[\"先停下吧\",\"我改变主意了\",\"换个方向\",\"第四句\"]\n```")
    XCTAssertEqual(result.content, "先这样。")
    XCTAssertEqual(result.suggestions, ["先停下吧", "我改变主意了", "换个方向"])
    XCTAssertEqual(
      AgentSurface.proseAndQuickReplies("答案\n```hymio-quick\n[\"未完成\"").content,
      "答案")
  }
}
