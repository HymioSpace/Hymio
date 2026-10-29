import SwiftUI

private struct StableMarkdown: View, Equatable {
  let content: String
  let account: AccountService
  static func == (lhs: Self, rhs: Self) -> Bool {
    lhs.content == rhs.content && lhs.account === rhs.account
  }
  var body: some View { MessageContent(content: content, account: account) }
}

@MainActor
private final class ProsePresenter: ObservableObject {
  struct Frame: Equatable {
    var text: String
    var pending: Bool
  }
  @Published private(set) var frame: Frame
  private var buffer = PresentationBuffer()
  private var task: Task<Void, Never>?
  init(source: String, immediate: Bool) {
    buffer.set(source, now: ProcessInfo.processInfo.systemUptime, immediate: immediate)
    frame = Frame(text: buffer.value, pending: buffer.pending)
    startTicker()
  }
  func receive(_ source: String, immediate: Bool, complete: Bool = false) {
    buffer.set(source, now: ProcessInfo.processInfo.systemUptime, immediate: immediate)
    if complete { buffer.complete(now: ProcessInfo.processInfo.systemUptime) }
    publish()
    if immediate {
      task?.cancel()
      task = nil
    } else {
      startTicker()
    }
  }
  private func startTicker() {
    guard task == nil, buffer.pending else { return }
    task = Task { [weak self] in
      while !Task.isCancelled {
        do { try await Task.sleep(for: .milliseconds(33)) } catch { return }
        guard let self else { return }
        self.buffer.tick(ProcessInfo.processInfo.systemUptime)
        self.publish()
        if !self.buffer.pending {
          self.task = nil
          return
        }
      }
    }
  }
  private func publish() {
    let next = Frame(text: buffer.value, pending: buffer.pending)
    if frame != next { frame = next }
  }
  deinit { task?.cancel() }
}

struct BufferedProse: View {
  let source: String
  let streaming: Bool
  var plain = false
  @ObservedObject var account: AccountService
  @Environment(\.accessibilityReduceMotion) private var reduceMotion
  @Environment(\.scenePhase) private var scene
  @State private var copyGeneration = 0
  @State private var copied = false
  @StateObject private var presentation: ProsePresenter
  init(source: String, streaming: Bool, account: AccountService, plain: Bool = false) {
    self.plain = plain
    self.source = source
    self.streaming = streaming
    self.account = account
    _presentation = StateObject(wrappedValue: ProsePresenter(source: source, immediate: !streaming))
  }
  var body: some View {
    let frame = presentation.frame
    Group {
      if plain {
        Text(frame.text).font(.callout).foregroundStyle(.secondary).textSelection(.enabled)
          .multilineTextAlignment(.leading).frame(maxWidth: .infinity, alignment: .leading)
      } else {
        let parts = AgentSurface.stableMarkdown(frame.text)
        VStack(alignment: .leading, spacing: 8) {
          if !parts.stable.isEmpty {
            StableMarkdown(content: parts.stable, account: account).equatable()
          }
          if !parts.tail.isEmpty {
            if frame.pending || streaming {
              Text(
                (try? AttributedString(
                  markdown: parts.tail,
                  options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)))
                  ?? AttributedString(parts.tail)
              )
              .font(.body).lineSpacing(4).textSelection(.disabled)
              .frame(maxWidth: .infinity, alignment: .leading)
            } else {
              StableMarkdown(content: parts.tail, account: account).equatable()
            }
          }
        }.frame(minHeight: 24, alignment: .topLeading)
      }
    }
    .contextMenu {
      Button("复制回复", systemImage: "doc.on.doc") {
        UIPasteboard.general.string = source
        copied = true
        copyGeneration += 1
      }
    }
    .overlay(alignment: .bottomTrailing) {
      if copied {
        Label("已复制", systemImage: "checkmark").font(.caption)
          .padding(8).background(Brand.raised, in: Capsule())
          .accessibilityLabel("回复已复制")
      }
    }
    .task(id: copyGeneration) {
      guard copyGeneration > 0 else { return }
      do { try await Task.sleep(for: .milliseconds(2500)) } catch { return }
      copied = false
    }
    .onChange(of: source, initial: true) { _, value in
      presentation.receive(
        value, immediate: reduceMotion || (!streaming && frame.text == value),
        complete: !streaming)
    }
    .onChange(of: streaming) { _, value in
      presentation.receive(source, immediate: reduceMotion, complete: !value)
    }
    .onDisappear { presentation.receive(source, immediate: true) }
    .onChange(of: scene) { _, phase in
      if phase == .active { presentation.receive(source, immediate: true) }
    }
    .onChange(of: reduceMotion) { _, value in
      if value { presentation.receive(source, immediate: true) }
    }
    .environment(
      \.openURL,
      OpenURLAction {
        ["https", "http", "mailto"].contains($0.scheme?.lowercased() ?? "")
          ? .systemAction : .discarded
      })
  }
}

struct ProgressiveMessageContent: View {
  let content: String
  let streaming: Bool
  @ObservedObject var account: AccountService
  let onAction: (String) async throws -> Void
  var body: some View {
    VStack(alignment: .leading, spacing: 12) {
      ForEach(AgentSurface.parts(content, streaming: streaming)) { part in
        if part.isUI {
          AgentSurfaceView(source: part.source, complete: part.complete, onAction: onAction)
        } else {
          BufferedProse(source: part.source, streaming: streaming, account: account)
        }
      }
    }
  }
}

struct AgentSurfaceView: View {
  let source: String
  let complete: Bool
  let onAction: (String) async throws -> Void
  @Environment(\.accessibilityReduceMotion) private var reduceMotion
  @State private var values: [String: String] = [:]
  @State private var sending = false
  @State private var failure = ""
  var parsed: AgentSurface.Parsed { AgentSurface.parse(source, complete: complete) }
  var body: some View {
    let result = parsed
    VStack(alignment: .leading, spacing: 10) {
      Label(complete ? "为你整理" : "正在构建", systemImage: "sparkles")
        .font(.caption2).foregroundStyle(.secondary)
      if let spec = result.spec {
        node(spec["root"].text, spec: spec, depth: 0)
      } else if !complete {
        RoundedRectangle(cornerRadius: 12).fill(Brand.mist).frame(height: 50).overlay {
          ProgressView().controlSize(.small)
        }
      }
      if result.error || (complete && result.spec == nil) {
        Label("部分内容未能展示，你可以继续提问。", systemImage: "exclamationmark.circle")
          .font(.caption).foregroundStyle(.secondary)
      }
      if !failure.isEmpty { Text(failure).font(.caption).foregroundStyle(.secondary) }
    }.padding(.vertical, 8).frame(maxWidth: .infinity, alignment: .leading)
      .animation(reduceMotion ? nil : .easeOut(duration: 0.24), value: result.spec)
      .accessibilityElement(children: .contain)
      .accessibilityIdentifier("message.surface")
  }
  private func node(_ id: String, spec: JSON, depth: Int) -> AnyView {
    guard depth <= 12 else { return AnyView(EmptyView()) }
    let element = spec["elements"][id]
    let props = element["props"]
    let children = element["children"].items.map(\.text)
    if element == .null {
      return AnyView(
        Group {
          if !complete { RoundedRectangle(cornerRadius: 8).fill(Brand.mist).frame(height: 36) }
        })
    }
    let items = ForEach(children, id: \.self) { child in
      node(child, spec: spec, depth: depth + 1)
        .transition(reduceMotion ? .identity : .opacity.combined(with: .offset(y: 5)))
    }
    switch element["type"].text {
    case "Card":
      return AnyView(
        VStack(alignment: .leading, spacing: 18) {
          if !props["title"].text.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
              Text(props["title"].text).font(.title3.weight(.semibold))
              if !props["subtitle"].text.isEmpty {
                Text(props["subtitle"].text).font(.subheadline).foregroundStyle(.secondary)
              }
            }
          }
          items
        }.padding(20).frame(maxWidth: .infinity, alignment: .leading)
          .background(Brand.mist.opacity(0.55), in: RoundedRectangle(cornerRadius: 22))
          .overlay { RoundedRectangle(cornerRadius: 22).stroke(Brand.line, lineWidth: 1) })
    case "Column":
      return AnyView(
        VStack(alignment: .leading, spacing: 16) { items }.frame(
          maxWidth: .infinity, alignment: .leading))
    case "Row":
      return AnyView(
        ViewThatFits(in: .horizontal) {
          HStack(alignment: .top, spacing: 12) { items }
          VStack(alignment: .leading, spacing: 12) { items }
        })
    case "Text":
      return AnyView(
        Text(props["text"].text).font(.body).foregroundStyle(
          props["tone"].text == "muted" ? Brand.muted : Brand.ink
        ).textSelection(.enabled))
    case "Metric":
      return AnyView(
        VStack(alignment: .leading, spacing: 6) {
          Text(props["label"].text).font(.caption).foregroundStyle(.secondary)
          Text(props["value"].text).font(.system(.title, design: .rounded, weight: .medium))
            .contentTransition(.numericText())
          if !props["detail"].text.isEmpty {
            Text(props["detail"].text).font(.caption2).foregroundStyle(.secondary)
          }
        }.padding(15).frame(maxWidth: .infinity, alignment: .leading).background(
          Brand.userBubble, in: RoundedRectangle(cornerRadius: 14)))
    case "Badge":
      return AnyView(
        Text(props["text"].text).font(.caption2.weight(.medium)).foregroundStyle(Brand.blue)
          .padding(.horizontal, 8).padding(.vertical, 5).background(
            Brand.userBubble, in: RoundedRectangle(cornerRadius: 7)))
    case "Input":
      return AnyView(
        VStack(alignment: .leading, spacing: 8) {
          Text(props["label"].text).font(.caption).foregroundStyle(.secondary)
          TextField(
            props["placeholder"].text,
            text: Binding(
              get: { values[id] ?? props["value"].text },
              set: { values[id] = String($0.prefix(2000)) })
          )
          .padding(12).background(Brand.surface, in: RoundedRectangle(cornerRadius: 12))
          .accessibilityIdentifier("surface.input.\(id)")
        })
    case "Choice":
      return AnyView(
        VStack(alignment: .leading, spacing: 8) {
          Text(props["label"].text).font(.caption).foregroundStyle(.secondary)
          ForEach(props["options"].items, id: \.self) { option in
            let selected = (values[id] ?? props["value"].text) == option.text
            Button {
              values[id] = option.text
            } label: {
              HStack {
                Text(option.text)
                Spacer()
                Image(systemName: selected ? "checkmark.circle.fill" : "circle")
              }
              .font(.subheadline).padding(12).background(
                selected ? Brand.userBubble : Brand.surface, in: RoundedRectangle(cornerRadius: 11))
            }.buttonStyle(.plain).accessibilityAddTraits(selected ? .isSelected : [])
              .accessibilityIdentifier("surface.choice.\(id).\(option.text)")
          }
        })
    case "Button":
      return AnyView(
        Button {
          guard !sending else { return }
          var bindings = values
          if case .object(let nodes) = spec["elements"] {
            for (key, n) in nodes
            where ["Input", "Choice"].contains(n["type"].text) && bindings[key] == nil {
              bindings[key] = n["props"]["value"].text
            }
          }
          if let regex = try? NSRegularExpression(pattern: "\\{\\{([A-Za-z0-9_-]{1,64})\\}\\}") {
            let template = props["prompt"].text
            let matches = regex.matches(
              in: template, range: NSRange(template.startIndex..., in: template))
            guard
              matches.allSatisfy({ match in
                guard let range = Range(match.range(at: 1), in: template) else { return false }
                return bindings[String(template[range])] != nil
              })
            else {
              failure = "选项仍在准备，请稍后再试。"
              return
            }
          }
          let prompt = AgentSurface.prompt(props["prompt"].text, values: bindings)
          guard !prompt.isEmpty else { return }
          sending = true
          failure = ""
          Task {
            defer { sending = false }
            do { try await onAction(prompt) } catch { failure = "未能发送，请重试。" }
          }
        } label: {
          HStack {
            Text(props["label"].text.isEmpty ? "继续" : props["label"].text)
            if sending { ProgressView() } else { Image(systemName: "arrow.up.right") }
          }.font(.subheadline.weight(.medium)).foregroundStyle(Brand.onAccent).padding(14)
        }.buttonStyle(.borderedProminent).tint(Brand.blue).disabled(
          sending || props["prompt"].text.isEmpty
        )
        .accessibilityIdentifier("surface.action.\(id)"))
    default: return AnyView(EmptyView())
    }
  }
}

#if DEBUG
  /// Deterministic local stream; no account, network or private conversation data.
  struct StreamingPerformancePreview: View {
    let account: AccountService
    @State private var messages: [ChatMessage] = []
    @State private var status = "Streaming synthetic Markdown"
    @State private var replay = 0
    private var isDemo: Bool { ProcessInfo.processInfo.arguments.contains("-HymioRevealDemo") }
    private var answer: String {
      if isDemo {
        return
          "好，这一段已经补上了。\n\n**时间、地点和价格**会保留在同一份安排里。新到的文字逐渐清晰，已读过的内容保持不动。中英文、数字 07:52 和 🦦 都使用同一套排版。\n\n你可以继续补充，我会接着整理。"
      }
      return
        String(repeating: "A small step, clearly explained. 中文和 🦦 stay intact. ", count: 10)
        + "\n\n## Next steps\n\n- Keep the answer in place.\n- Preserve the final frame.\n\n```swift\nlet reply = \"Hello\"\n```\n\nDone."
    }
    var body: some View {
      VStack {
        Text(status).font(.caption).accessibilityIdentifier("stream.preview.status")
        if isDemo {
          Button("重播渐显") {
            messages = []
            replay += 1
          }.frame(minHeight: 44)
        }
        ScrollView {
          LazyVStack(alignment: .leading, spacing: 18) {
            ForEach(buildTurns(messages)) { turn in
              TraceRow(turn: turn, tools: [:], account: account).equatable()
            }
          }.padding(18)
        }.defaultScrollAnchor(.bottom)
          .defaultScrollAnchor(.bottom, for: .sizeChanges)
      }.background(Brand.surface)
        .task(id: replay) {
          let clock = StreamFrameProbe()
          clock.start()
          for index in 0..<(isDemo ? 0 : 12) {
            messages.append(
              ChatMessage(
                id: "history-\(index)", role: "assistant",
                content:
                  "A completed reply with **stable Markdown**.\n\nNothing here should animate again.",
                time: "2026-01-01T00:00:00Z"))
          }
          messages.append(
            ChatMessage(
              id: "question", role: "user",
              content: isDemo ? "继续整理。" : "![preview](hymio-preview:one)\n可以了",
              time: "2026-01-01T00:00:01Z"))
          var reply = ChatMessage(
            id: "reply", role: "assistant", content: "", time: "2026-01-01T00:00:02Z")
          reply.streaming = true
          messages.append(reply)
          let characters = Array(answer)
          let jitterDemo = ProcessInfo.processInfo.arguments.contains("-HymioJitterDemo")
          let cadence = [40, 80, 360, 40, 160, 280]
          let step = jitterDemo ? 8 : (isDemo ? 4 : 8)
          var packet = 0
          for count in stride(from: step, through: characters.count + step - 1, by: step) {
            guard !Task.isCancelled else {
              clock.stop()
              return
            }
            messages[messages.count - 1].content = String(
              characters.prefix(min(count, characters.count)))
            let delay = jitterDemo ? cadence[packet % cadence.count] : (isDemo ? 70 : 40)
            packet += 1
            try? await Task.sleep(for: .milliseconds(delay))
          }
          messages[messages.count - 1].streaming = false
          do { try await Task.sleep(for: .seconds(8)) } catch {
            clock.stop()
            return
          }
          let result = clock.stop()
          status = "Complete · \(result)"
          let url = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("stream-preview-metrics.txt")
          try? status.write(to: url, atomically: true, encoding: .utf8)
        }
    }
  }

  struct ActualChatPerformancePreview: View {
    let account: AccountService
    @StateObject private var client: AgentClient
    @State private var complete = false
    init(account: AccountService) {
      self.account = account
      _client = StateObject(wrappedValue: AgentClient(account: account, previewConnected: true))
    }
    var body: some View {
      ChatScreen(account: account, client: client, onAccount: {})
        .overlay(alignment: .topTrailing) {
          if complete { Text("验收完成").font(.caption2).padding(6).background(Brand.base).accessibilityIdentifier("chat.stress.complete") }
        }
        .task { @MainActor in
          var seq = 0
          @MainActor func emit(_ type: String, _ body: [String: JSON]) {
            seq += 1
            client.injectSynthetic(Event(user_id: "synthetic", event_seq: seq, event_type: type,
              payload: .object(body), occur_dt: "2026-01-01T00:00:00Z"))
          }
          for i in 0..<16 {
            emit("user.message", ["content": .string("整理第 \(i + 1) 件事")])
            emit("assistant.message", ["step_id": .string("history-\(i)"), "content": .string("已整理好。保留清楚的结果与下一步。")])
          }
          emit("user.message", ["content": .string("继续整理，给我最终结果。")])
          let clock = StreamFrameProbe(); clock.start()
          let answer = String(repeating: "文字逐渐到达，已读内容留在原位。中英文 09:58 与 🦦 保持完整。", count: 18) + "\n\n最终结果已整理好。"
          let characters = Array(answer)
          for index in stride(from: 0, to: characters.count, by: 10) {
            guard !Task.isCancelled else { clock.stop(); return }
            emit("assistant.delta", ["step_id": .string("live"), "channel": .string("content"), "attempt": .number(0),
              "text": .string(String(characters[index..<min(index + 10, characters.count)]))])
            try? await Task.sleep(for: .milliseconds(index % 70 == 0 ? 180 : 50))
          }
          emit("assistant.message", ["step_id": .string("live"), "content": .string(answer)])
          try? await Task.sleep(for: .seconds(8))
          let metrics = clock.stop()
          let path = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("actual-chat-metrics.txt")
          try? metrics.write(to: path, atomically: true, encoding: .utf8)
          complete = true
        }
    }
  }

  @MainActor final class StreamFrameProbe: NSObject {
    private var link: CADisplayLink?
    private var previous = 0.0
    private var frames = 0
    private var stalls = 0
    private var maxGap = 0.0
    func start() {
      link = CADisplayLink(target: self, selector: #selector(frame(_:)))
      link?.add(to: .main, forMode: .common)
    }
    @objc private func frame(_ sender: CADisplayLink) {
      if previous > 0 {
        let gap = sender.timestamp - previous
        maxGap = max(maxGap, gap)
        if gap > 0.05 { stalls += 1 }
      }
      previous = sender.timestamp
      frames += 1
    }
    @discardableResult func stop() -> String {
      link?.invalidate()
      link = nil
      return "\(frames) frames, \(stalls) gaps >50ms, max \(Int(maxGap * 1000))ms"
    }
  }
#endif
