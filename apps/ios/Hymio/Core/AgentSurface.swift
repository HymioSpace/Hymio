import Foundation

public struct SurfacePart: Identifiable {
  public let id: Int
  public let isUI: Bool
  public let source: String
  public let complete: Bool
}
public enum AgentSurface {
  public static func proseAndQuickReplies(_ source: String) -> (
    content: String, suggestions: [String]
  ) {
    if !source.contains("```hymio-quick") {
      return (source.trimmingCharacters(in: .whitespacesAndNewlines), [])
    }
    var output: [String] = []
    var block: [String]?
    var suggestions: [String] = []
    var otherFence = ""
    for line in source.components(separatedBy: "\n") {
      let trimmed = line.trimmingCharacters(in: .whitespaces)
      if block != nil {
        if trimmed == "```" {
          if let data = block?.joined(separator: "\n").data(using: .utf8),
            let values = try? JSONDecoder().decode([String].self, from: data)
          {
            for value in values {
              let text = value.trimmingCharacters(in: .whitespacesAndNewlines)
              if !text.isEmpty, text.utf16.count <= 40, !suggestions.contains(text) {
                suggestions.append(text)
                if suggestions.count == 3 { break }
              }
            }
          }
          block = nil
        } else {
          block?.append(line)
        }
        continue
      }
      if otherFence.isEmpty && trimmed == "```hymio-quick" {
        block = []
        continue
      }
      if trimmed.hasPrefix("```") || trimmed.hasPrefix("~~~") {
        let marker = String(trimmed.prefix(while: { $0 == trimmed.first }))
        if otherFence.isEmpty {
          otherFence = marker
        } else if trimmed == otherFence {
          otherFence = ""
        }
      }
      output.append(line)
    }
    return (
      output.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines),
      Array(suggestions.prefix(3))
    )
  }

  public static func parts(_ source: String, streaming: Bool) -> [SurfacePart] {
    var result: [SurfacePart] = []
    var lines: [String] = []
    var inside = false
    var otherFence = ""
    func flush(_ ui: Bool, _ complete: Bool) {
      if !lines.isEmpty || ui {
        result.append(
          SurfacePart(
            id: result.count, isUI: ui, source: lines.joined(separator: "\n"), complete: complete))
      }
      lines = []
    }
    for line in source.components(separatedBy: "\n") {
      let trimmed = line.trimmingCharacters(in: .whitespaces)
      if !inside && otherFence.isEmpty && trimmed == "```hymio-ui" {
        flush(false, true)
        inside = true
        continue
      }
      if inside {
        if trimmed == "```" {
          flush(true, true)
          inside = false
        } else {
          lines.append(line)
        }
      } else {
        if trimmed.hasPrefix("```") || trimmed.hasPrefix("~~~") {
          let marker = String(trimmed.prefix(while: { $0 == trimmed.first }))
          if otherFence.isEmpty {
            otherFence = marker
          } else if marker.first == otherFence.first && marker.count >= otherFence.count
            && trimmed == marker
          {
            otherFence = ""
          }
        }
        lines.append(line)
      }
    }
    if streaming && !inside, let last = lines.last {
      let trimmed = last.trimmingCharacters(in: .whitespaces)
      if trimmed.hasPrefix("`") && "```hymio-ui".hasPrefix(trimmed) { lines.removeLast() }
    }
    flush(inside, !streaming)
    return result
  }
  public static func stableMarkdown(_ text: String) -> (stable: String, tail: String) {
    var fence = ""
    var boundary = text.startIndex
    for line in text.split(separator: "\n", omittingEmptySubsequences: false) {
      let trimmed = line.trimmingCharacters(in: .whitespaces)
      if trimmed.hasPrefix("```") || trimmed.hasPrefix("~~~") {
        let marker = String(trimmed.prefix(while: { $0 == trimmed.first }))
        if fence.isEmpty {
          fence = marker
        } else if marker.first == fence.first && marker.count >= fence.count && trimmed == marker {
          fence = ""
        }
      }
      if trimmed.isEmpty && fence.isEmpty && line.endIndex < text.endIndex {
        boundary = text.index(after: line.endIndex)
      }
    }
    return (String(text[..<boundary]), String(text[boundary...]))
  }
  public struct Parsed {
    public var spec: JSON?
    public var error: Bool
  }
  static let fields = [
    "Card": ["title", "subtitle"], "Column": [], "Row": [], "Text": ["text", "tone"],
    "Metric": ["label", "value", "detail"], "Badge": ["text"],
    "Input": ["label", "placeholder", "value"],
    "Choice": ["label", "options", "value"], "Button": ["label", "prompt"],
  ]
  static func identifier(_ id: String) -> Bool {
    !["__proto__", "constructor", "prototype"].contains(id)
      && id.range(of: "^[A-Za-z0-9_-]{1,64}$", options: .regularExpression) != nil
  }
  public static func valid(_ spec: JSON) -> Bool {
    guard identifier(spec["root"].text), case .object(let nodes) = spec["elements"],
      nodes.count <= 64
    else { return false }
    var references: Set<String> = []
    for (id, node) in nodes {
      guard identifier(id), let allowed = fields[node["type"].text],
        case .object(let props) = node["props"]
      else { return false }
      for (key, value) in props {
        guard allowed.contains(key) else { return false }
        if key == "options" {
          guard case .array(let options) = value else { return false }
          guard options.count <= 12,
            options.allSatisfy({
              if case .string(let s) = $0 { return s.utf16.count <= 200 }
              return false
            })
          else { return false }
        } else {
          guard case .string(let s) = value, s.utf16.count <= 2000 else { return false }
        }
      }
      if node["children"] != .null {
        guard case .array(let children) = node["children"], children.count <= 64 else {
          return false
        }
        for child in children {
          guard identifier(child.text), references.insert(child.text).inserted else { return false }
        }
      }
    }
    func visit(_ id: String, _ path: Set<String>, _ depth: Int) -> Bool {
      guard depth <= 12, !path.contains(id) else { return false }
      guard let node = nodes[id] else { return true }
      return node["children"].items.allSatisfy { visit($0.text, path.union([id]), depth + 1) }
    }
    return nodes.keys.allSatisfy { visit($0, [], 0) }
  }
  public static func parse(_ source: String, complete: Bool) -> Parsed {
    guard source.utf8.count <= 65536 else { return Parsed(error: true) }
    var root = ""
    var elements: [String: JSON] = [:]
    var result = Parsed(error: false)
    let lines = source.components(separatedBy: "\n")
    for (index, line) in lines.enumerated() where !line.trimmingCharacters(in: .whitespaces).isEmpty
    {
      do {
        let value = try JSON.decode(Data(line.utf8))
        var nextRoot = root
        var nextElements = elements
        if value["root"] != .null && value["elements"] != .null {
          nextRoot = value["root"].text
          guard case .object(let e) = value["elements"] else { throw ParseError.invalid }
          nextElements = e
        } else {
          let op = value["op"].text
          let path = value["path"].text
          guard ["add", "replace", "remove"].contains(op) else { throw ParseError.invalid }
          if path == "/root" && op != "remove" {
            nextRoot = value["value"].text
          } else {
            guard path.hasPrefix("/elements/") else { throw ParseError.invalid }
            let id = String(path.dropFirst(10))
            guard identifier(id) else { throw ParseError.invalid }
            if op == "remove" {
              nextElements.removeValue(forKey: id)
            } else {
              nextElements[id] = value["value"]
            }
          }
        }
        let candidate = JSON.object([
          "root": .string(nextRoot.isEmpty ? "pending" : nextRoot),
          "elements": .object(nextElements),
        ])
        guard valid(candidate) else { throw ParseError.invalid }
        root = nextRoot
        elements = nextElements
        if !root.isEmpty && elements[root] != nil { result.spec = candidate }
      } catch { if complete || index < lines.count - 1 { result.error = true } }
    }
    return result
  }
  enum ParseError: Error { case invalid }
  public static func prompt(_ template: String, values: [String: String]) -> String {
    var value = template
    if let regex = try? NSRegularExpression(pattern: "\\{\\{([A-Za-z0-9_-]{1,64})\\}\\}") {
      let matches = regex.matches(
        in: template, range: NSRange(template.startIndex..., in: template))
      for match in matches.reversed() {
        if let id = Range(match.range(at: 1), in: template),
          let range = Range(match.range, in: value)
        {
          value.replaceSubrange(range, with: values[String(template[id])] ?? "")
        }
      }
    }
    return String(value.trimmingCharacters(in: .whitespacesAndNewlines).prefix(8000))
  }
}

public struct PresentationBuffer {
  private var source = "", characters: [Character] = []
  private var shown = 0
  private var start: Double = 0, previous: Double = 0, credit: Double = 0
  private var finishBy: Double?
  private var lastArrival: Double?
  private var inputRate = 0.0, gap = 0.08, jitter = 0.0, speed = 0.0
  public private(set) var value = ""
  public init() {}
  public mutating func set(_ text: String, now: Double, immediate: Bool = false) {
    if text != source {
      let appending = text.utf8.starts(with: source.utf8)
      let oldCount = appending ? characters.count : 0
      if source.isEmpty && !text.isEmpty {
        start = now
        previous = now
      }
      if !appending {
        lastArrival = nil
        inputRate = 0
        speed = 0
        jitter = 0
        gap = 0.08
        // A final correction preserves the already visible common prefix.
        let next = Array(text)
        let shared = zip(characters, next).prefix { $0 == $1 }.count
        shown = min(shown, shared)
        value = String(next.prefix(shown))
        characters = next
        start = now
        previous = now
        credit = 0
      } else {
        // A delta may extend the final grapheme (combining mark, flag or ZWJ).
        let last = characters.popLast().map(String.init) ?? ""
        let offset = source.utf8.count - last.utf8.count
        let utf8Index = text.utf8.index(text.utf8.startIndex, offsetBy: offset)
        let cut = String.Index(utf8Index, within: text) ?? text.startIndex
        let prefix = characters.count
        let tail = Array(text[cut...])
        characters.append(contentsOf: tail)
        if shown > prefix {
          shown = prefix + min(1, tail.count)
          value = String(text[..<cut]) + (tail.first.map(String.init) ?? "")
        }
      }
      let added = characters.count - oldCount
      if added > 0 {
        let interval = lastArrival.map { now - $0 } ?? 0
        if interval > 0 && interval < 1.5 {
          let sample = min(4000, Double(added) / max(0.008, interval))
          if inputRate == 0 {
            inputRate = sample
            gap = interval
          } else {
            inputRate += 0.25 * (sample - inputRate)
            jitter += 0.2 * (abs(interval - gap) - jitter)
            gap += 0.2 * (interval - gap)
          }
        }
        if interval >= 1.5 && interval < 5 {
          inputRate = Double(added) / interval
          gap = min(interval, 1.5)
          jitter = 0
        } else if interval >= 5 {
          inputRate = 0
          speed = 0
          jitter = 0
          gap = 0.08
          start = now
          previous = now
        }
        lastArrival = now
      }
      source = text
      finishBy = nil
    }
    if immediate {
      shown = characters.count
      value = source
      credit = 0
      finishBy = nil
    }
  }
  /// Server completion drains a backlog promptly, without replaying its visible prefix.
  public mutating func complete(now: Double) {
    if pending && finishBy == nil { finishBy = now + 0.45 }
  }
  public mutating func tick(_ now: Double) {
    let elapsed = min(0.1, max(0, now - previous))
    previous = now
    guard now - start >= 0.14 else { return }
    guard pending else {
      credit = 0
      return
    }
    let backlog = characters.count - shown
    let input = inputRate > 0 ? inputRate : min(54, max(8, Double(backlog) / 0.3))
    let reserve = min(0.24, max(0.1, gap * 0.5 + jitter * 1.5))
    let desired = input * (reserve + gap * 0.5)
    var goal = max(input * 0.25, input + (Double(backlog) - desired) / 0.35, 1)
    goal = min(goal, input * 1.8 + 12)
    if Double(backlog) > max(256, input * 1.5) { goal = max(goal, Double(backlog) / 0.65) }
    speed = speed > 0 ? speed + (goal - speed) * (1 - exp(-elapsed / 0.16)) : goal
    var rate = speed
    let silence = lastArrival.map { now - $0 } ?? 0
    if silence > max(0.3, gap * 1.5) {
      rate = max(rate, Double(backlog) / max(0.016, 0.9 - silence))
    }
    if let finishBy {
      if now >= finishBy {
        value = source
        shown = characters.count
        credit = 0
        return
      }
      rate = max(rate, Double(backlog) / max(0.025, finishBy - now))
    }
    credit += elapsed * rate
    let amount = Int(credit)
    let next = min(characters.count, shown + amount)
    if next > shown { value.append(contentsOf: String(characters[shown..<next])) }
    shown = next
    credit -= Double(amount)
  }
  public var pending: Bool { shown < characters.count }
}
