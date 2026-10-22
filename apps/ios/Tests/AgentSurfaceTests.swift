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
