import Foundation

/// 一次工作。对齐 Oath 的 trace：用户发话开新 trace，只要上一步还在产出工具调用就续同一条，
/// 直到某一步给出没有工具调用的最终回复，这条 trace 才结束。
public struct Turn: Identifiable, Equatable {
  public var id: String
  public var trace: String
  /// 用户那条消息，留在折叠块上方。
  public var user: ChatMessage?
  /// 最终回复：始终展开。
  public var final: ChatMessage?
  /// 全部思考、最终回复之前的正文和工具调用，收进折叠块。
  public var activity: [ChatMessage]
  /// 最终回复之后仍在流式的内容，保持展开。
  public var trailing: [ChatMessage]
  public var startedAt: Date?
  /// 这条 trace 最新一条事件的服务端时间，客户端拿它对齐自己的时钟。
  public var latestAt: Date?
  public var endedAt: Date?
  /// 这条 trace 可以收起了。
  public var settled: Bool

  public var foldable: Bool { settled && !activity.isEmpty }
  public var invocationIDs: [String] {
    (activity + trailing + [final].compactMap { $0 }).flatMap { message in
      let step = String(message.id.dropFirst("assistant:".count))
      return message.calls.indices.map { step + "-\($0)" }
    }
  }
}

enum TurnClock {
  private static let dates: NSCache<NSString, NSDate> = {
    let cache = NSCache<NSString, NSDate>()
    cache.countLimit = 4096
    return cache
  }()
  static let fractional: ISO8601DateFormatter = {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return formatter
  }()
  static let plain: ISO8601DateFormatter = {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime]
    return formatter
  }()
  /// occur_dt 是 RFC 3339 UTC，微秒以下精度。截到毫秒再解析，稳过任何 formatter。
  static func date(_ value: String) -> Date? {
    guard !value.isEmpty else { return nil }
    if let cached = dates.object(forKey: value as NSString) { return cached as Date }
    if let parsed = fractional.date(from: value) ?? plain.date(from: value) {
      dates.setObject(parsed as NSDate, forKey: value as NSString)
      return parsed
    }
    guard let dot = value.firstIndex(of: ".") else { return nil }
    let head = String(value[value.startIndex..<dot])
    let tail = value[value.index(after: dot)...].prefix(3)
    return fractional.date(from: "\(head).\(tail)")
  }
}

private func isFinal(_ message: ChatMessage) -> Bool {
  message.role == "assistant" && message.calls.isEmpty && !message.streaming
}

/// 按 trace 切分消息。缺 trace_id 的老消息退回「用户消息即分界」，免得整段历史塌成一条。
public func buildTurns(_ messages: [ChatMessage], paused: Bool = false) -> [Turn] {
  struct Draft {
    var trace = ""
    var items: [ChatMessage] = []
  }
  var drafts: [Draft] = []
  var byTrace: [String: Int] = [:]
  for message in messages {
    let trace = message.trace
    // 同一条 trace 的事件即使被后开的 trace 打断过，也还归回原来那次工作。
    if !trace.isEmpty, let index = byTrace[trace],
      !(drafts[index].items.last.map {
        isFinal($0) && message.role == "assistant" && message.id != $0.id
      } ?? false)
    {
      drafts[index].items.append(message)
      continue
    }
    let closed =
      drafts.last?.items.last.map {
        isFinal($0) && message.role == "assistant" && message.id != $0.id
      } ?? false
    if drafts.isEmpty || message.role == "user" || closed
      || (!trace.isEmpty && !drafts[drafts.count - 1].trace.isEmpty)
    {
      drafts.append(Draft(trace: trace, items: [message]))
    } else {
      drafts[drafts.count - 1].items.append(message)
    }
    if !trace.isEmpty {
      drafts[drafts.count - 1].trace = trace
      byTrace[trace] = drafts.count - 1
    }
  }
  return drafts.enumerated().map { index, draft in
    let items = draft.items
    var finalAt = -1
    var i = items.count - 1
    while i >= 0 {
      if isFinal(items[i])
        || (items[i].streaming && items[i].calls.isEmpty && !items[i].content.isEmpty)
      {
        finalAt = i
        break
      }
      i -= 1
    }
    let streaming = items.contains { $0.streaming }
    let last = items.last
    // 没有最终回复的 trace，只有在它后面又开了新 trace、且自己不再流式时才算结束。
    let settled =
      (paused && index == drafts.count - 1 && !streaming)
      || (finalAt >= 0
        ? finalAt == items.count - 1 && !streaming : index < drafts.count - 1 && !streaming)
    let head = finalAt < 0 ? items.count : finalAt
    var final: ChatMessage? = finalAt >= 0 ? items[finalAt] : nil
    var activity = items[0..<head].filter { $0.role == "assistant" }
    if var answer = final, !answer.streaming,
      !answer.reasoning.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    {
      var reasoning = answer
      reasoning.id += ":reasoning"
      reasoning.content = ""
      reasoning.thinking = false
      activity.append(reasoning)
      answer.reasoning = ""
      answer.thinking = false
      final = answer.content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? nil : answer
    }
    return Turn(
      id: items[0].id,
      trace: draft.trace,
      user: items.first { $0.role == "user" },
      final: final,
      activity: activity,
      trailing: finalAt < 0 ? [] : Array(items[(finalAt + 1)...]),
      startedAt: TurnClock.date(items[0].time),
      latestAt: last.flatMap { TurnClock.date($0.time) },
      endedAt: settled ? last.flatMap { TurnClock.date($0.time) } : nil,
      settled: settled)
  }
}

/// 进行中的 trace 用服务端时钟口径的现在估算；已结束的用两端时间戳的精确值。
public func traceElapsed(_ turn: Turn, serverNow: Date) -> TimeInterval? {
  guard let start = turn.startedAt else { return nil }
  if let end = turn.endedAt { return max(0, end.timeIntervalSince(start)) }
  return serverNow > start ? serverNow.timeIntervalSince(start) : nil
}

public func formatDuration(_ elapsed: TimeInterval?) -> String {
  guard let elapsed else { return "" }
  let seconds = max(1, Int(elapsed.rounded()))
  if seconds < 60 { return "\(seconds) 秒" }
  if seconds < 3600 {
    let rest = seconds % 60
    return rest > 0 ? "\(seconds / 60) 分 \(rest) 秒" : "\(seconds / 60) 分"
  }
  let rest = (seconds % 3600) / 60
  return rest > 0 ? "\(seconds / 3600) 小时 \(rest) 分" : "\(seconds / 3600) 小时"
}
