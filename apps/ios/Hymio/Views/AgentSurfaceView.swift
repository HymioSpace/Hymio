import SwiftUI

@available(iOS 18.0, *)
private struct StreamingFadeRenderer: TextRenderer {
  var animatableData: Double = 0

  func draw(layout: Text.Layout, in context: inout GraphicsContext) {
    let total = layout.reduce(0) { count, line in
      count + line.reduce(0) { $0 + $1.characterIndices.count }
    }
    var index = 0
    for line in layout {
      for run in line {
        for slice in run {
          let length = max(1, slice.characterIndices.count)
          let distance = max(0, total - index - length)
          let settled = min(1, Double(distance) / 18)
          context.opacity = 0.04 + settled * 0.96
          let lift = distance < 7 ? CGFloat(7 - distance) * 0.55 : 0
          context.translateBy(x: 0, y: lift)
          context.draw(slice)
          context.translateBy(x: 0, y: -lift)
          index += length
        }
      }
    }
  }
}

private struct StreamingInlineText: View {
  let value: AttributedString
  let animate: Bool

  var body: some View {
    if animate, #available(iOS 18.0, *) {
      Text(value).textRenderer(StreamingFadeRenderer())
    } else {
      Text(value)
    }
  }
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
  func receive(_ source: String, immediate: Bool) {
    buffer.set(source, now: ProcessInfo.processInfo.systemUptime, immediate: immediate)
    publish()
    startTicker()
  }
  private func startTicker() {
    guard task == nil else { return }
    task = Task { [weak self] in
      while !Task.isCancelled {
        let delay = self?.buffer.pending == true ? 32 : 160
        do { try await Task.sleep(for: .milliseconds(delay)) } catch { return }
        guard let self else { return }
        self.buffer.tick(ProcessInfo.processInfo.systemUptime)
        self.publish()
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
      } else if frame.pending || streaming {
        let parts = AgentSurface.stableMarkdown(frame.text)
        VStack(alignment: .leading, spacing: 8) {
          if !parts.stable.isEmpty { MessageContent(content: parts.stable, account: account) }
          if !parts.tail.isEmpty {
            StreamingInlineText(
              value: (try? AttributedString(
                markdown: parts.tail,
                options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)))
                ?? AttributedString(parts.tail),
              animate: !reduceMotion
            )
            .font(.body).lineSpacing(4).textSelection(.enabled).frame(
              maxWidth: .infinity, alignment: .leading)
          }
        }.frame(minHeight: 24, alignment: .topLeading)
      } else {
        MessageContent(content: frame.text, account: account)
      }
    }
    .contextMenu {
      Button("复制回复", systemImage: "doc.on.doc") { UIPasteboard.general.string = source }
    }
    .overlay(alignment: .bottomTrailing) {
      if frame.pending && !reduceMotion {
        LinearGradient(
          colors: [.clear, Brand.surface.opacity(0.85)], startPoint: .leading, endPoint: .trailing
        )
        .frame(width: 28, height: 22).allowsHitTesting(false).accessibilityHidden(true)
      }
    }
    .task(id: source) {
      presentation.receive(source, immediate: reduceMotion || (!streaming && frame.text == source))
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
