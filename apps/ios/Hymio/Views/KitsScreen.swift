import SwiftUI
import WebKit
import os

@MainActor final class KitCatalogStore: ObservableObject {
  @Published var items: [JSON] = []
  @Published var loaded = false
  @Published var loading = false
  @Published var error = ""

  func load(_ account: AccountService) async {
    guard !loading else { return }
    loading = true
    defer { loading = false }
    do {
      let value = try await account.request("kits")
      let next = value["kits"].items
      if items != next { items = next }
      loaded = true
      error = ""
    } catch {
      self.error = "暂时无法读取应用。这些内容不会因此消失。"
    }
  }

  func install(_ item: JSON, account: AccountService) async -> Bool {
    guard !loading else { return false }
    loading = true
    defer { loading = false }
    do {
      _ = try await account.request(
        "kits/\(item["id"].text)/install", body: .object([:]))
      let value = try await account.request("kits")
      let next = value["kits"].items
      if items != next { items = next }
      loaded = true
      error = ""
      return true
    } catch {
      self.error = "暂时无法添加这个应用，请稍后再试。"
      return false
    }
  }
}

@MainActor final class KitEditorStore: ObservableObject {
  @Published var messages: [JSON] = []
  @Published var changes: [JSON] = []
  @Published var agentStatus = "not_started"
  @Published var agentResult = ""
  @Published var agentID = ""
  @Published var loading = true
  @Published var sending = false
  @Published var error = ""
  @Published var draft = ""

  init(preview: Bool = false) {
    guard preview else { return }
    loading = false
    agentStatus = "succeeded"
    messages = [
      .object([
        "author": .string("main_agent"),
        "content": .string("保留已有饮水记录，把首页重点放在今天的累计杯数。"),
      ]),
      .object([
        "author": .string("user"),
        "content": .string("再加一个按日期查看最近记录的方式，不要改变原来的字段。"),
      ]),
    ]
    changes = [
      .object([
        "revision": .number(2),
        "summary": .string("增加日期筛选，并优化键盘上方的添加入口"),
        "created_at": .number(Date().timeIntervalSince1970 - 900),
      ]),
      .object([
        "revision": .number(1),
        "summary": .string("完成饮水首页、空状态和 Python 数据结构"),
        "created_at": .number(Date().timeIntervalSince1970 - 86400),
      ]),
    ]
    agentResult = "日期筛选已经可用，原有记录保持不变。"
  }

  func load(_ account: AccountService, kitID: String) async {
    do {
      let value = try await account.request("kits/\(kitID)/editor")
      messages = value["messages"].items
      changes = value["changes"].items
      agentStatus = value["agent_status"].text
      agentResult = value["agent_result"].text
      agentID = value["coding_agent_id"].text
      loading = false
      error = ""
    } catch {
      if loading { self.error = "暂时无法读取编辑记录。" }
      loading = false
    }
  }

  func monitor(_ account: AccountService, kitID: String) async {
    while !Task.isCancelled {
      await load(account, kitID: kitID)
      let active = ["running", "waiting"].contains(agentStatus)
      do {
        try await Task.sleep(for: .seconds(active ? 1.5 : 5))
      } catch {
        return
      }
    }
  }

  func send(_ account: AccountService, kitID: String) async {
    let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !text.isEmpty, !sending else { return }
    sending = true
    error = ""
    defer { sending = false }
    do {
      _ = try await account.request(
        "kits/\(kitID)/editor/messages",
        body: .object(["content": .string(text)]),
        idempotencyKey: UUID().uuidString)
      draft = ""
      await load(account, kitID: kitID)
    } catch {
      self.error = "这次修改没有发出去，请稍后重试。"
    }
  }
}

private enum KitVisual {
  static func symbol(_ value: String) -> String {
    switch value {
    case "wallet": return "creditcard.fill"
    default: return "square.grid.2x2.fill"
    }
  }

  static func tint(_ value: String) -> Color {
    switch value {
    case "amber": return Brand.attention
    case "green": return Color.green
    case "rose": return Color.pink
    case "violet": return Color.purple
    default: return Brand.blue
    }
  }

  static func surface(_ value: String) -> Color {
    switch value {
    case "amber": return Brand.attentionSurface
    case "green": return Color.green.opacity(0.1)
    case "rose": return Color.pink.opacity(0.1)
    case "violet": return Color.purple.opacity(0.1)
    default: return Brand.softBlue
    }
  }
}

struct KitsScreen: View {
  @ObservedObject var account: AccountService
  let onAccount: () -> Void
  var showAccountButton = true
  @StateObject private var store = KitCatalogStore()
  @State private var installing = ""

  private var installed: [JSON] { store.items.filter { $0["installed"].flag } }
  private var available: [JSON] { store.items.filter { !$0["installed"].flag } }

  var body: some View {
    NavigationStack {
      ScrollView {
        LazyVStack(alignment: .leading, spacing: 28) {
          VStack(alignment: .leading, spacing: 9) {
            Text("让常用的事，顺手发生。")
              .font(.system(.title, design: .rounded, weight: .semibold)).tracking(-0.7)
            Text("打开就能用。也可以直接对 Hymio 说，让它在应用里继续做。")
              .font(.subheadline).foregroundStyle(Brand.muted).lineSpacing(4)
          }
          if !store.error.isEmpty {
            HStack(alignment: .top, spacing: 12) {
              Image(systemName: "wifi.exclamationmark").foregroundStyle(Brand.muted)
              Text(store.error).font(.footnote).foregroundStyle(Brand.muted)
              Spacer()
              Button("重试") { Task { await store.load(account) } }.font(.footnote)
            }
            .padding(15).background(Brand.mist, in: RoundedRectangle(cornerRadius: 14))
          }
          if store.loading && !store.loaded {
            VStack(spacing: 12) {
              ForEach(0..<2, id: \.self) { _ in
                RoundedRectangle(cornerRadius: 20).fill(Brand.mist).frame(height: 162)
              }
            }.accessibilityLabel("正在读取应用")
          } else if store.loaded {
            if installed.isEmpty {
              VStack(alignment: .leading, spacing: 9) {
                Text("还没有加入应用").font(.caption).foregroundStyle(Brand.muted)
                Text("从一个顺手的开始。")
                  .font(.title3.weight(.semibold)).foregroundStyle(Brand.ink)
                Text("加入后可以直接打开真实应用，也可以让 Hymio 在其中完成事情。")
                  .font(.subheadline).foregroundStyle(Brand.muted).lineSpacing(4)
              }
              .frame(maxWidth: .infinity, alignment: .leading).padding(22)
              .background(Brand.mist, in: RoundedRectangle(cornerRadius: 22))
            } else {
              appSection("我的应用", items: installed, installed: true)
            }
            if !available.isEmpty {
              appSection("还可以加入", items: available, installed: false)
            }
          }
        }
        .padding(.horizontal, 20).padding(.top, 16).padding(.bottom, 90)
        .frame(maxWidth: 680).frame(maxWidth: .infinity)
      }
      .background(Brand.surface)
      .navigationTitle("应用").navigationBarTitleDisplayMode(.inline)
      .toolbar {
        ToolbarItemGroup(placement: .topBarLeading) {
          if showAccountButton { AccountButton(account: account, action: onAccount) }
        }.accountUnframed()
      }
      .refreshable { await store.load(account) }
    }
    .task { await store.load(account) }
  }

  private func appSection(_ title: String, items: [JSON], installed: Bool) -> some View {
    VStack(alignment: .leading, spacing: 13) {
      HStack(spacing: 8) {
        Text(title).font(.subheadline.weight(.semibold))
        Text("\(items.count)").font(.caption).foregroundStyle(Brand.muted)
      }
      ForEach(items, id: \.self) { item in
        if installed {
          NavigationLink {
            KitAppScreen(account: account, item: item)
          } label: {
            KitCatalogCard(item: item, state: "打开")
          }
          .buttonStyle(GentlePress())
          .accessibilityIdentifier("kit.card." + item["id"].text)
        } else {
          Button {
            guard installing.isEmpty else { return }
            installing = item["id"].text
            Task {
              defer { installing = "" }
              _ = await store.install(item, account: account)
            }
          } label: {
            KitCatalogCard(
              item: item,
              state: installing == item["id"].text ? "正在添加…" : "添加")
          }
          .buttonStyle(GentlePress())
          .accessibilityIdentifier("kit.card." + item["id"].text)
          .disabled(!installing.isEmpty)
        }
      }
    }
  }
}

private struct KitCatalogCard: View {
  let item: JSON
  let state: String
  @Environment(\.dynamicTypeSize) private var typeSize

  var body: some View {
    Group {
      if typeSize.isAccessibilitySize {
        VStack(alignment: .leading, spacing: 13) {
          HStack(spacing: 12) {
            icon
            Text(item["category"].text).font(.caption).foregroundStyle(Brand.muted)
            Spacer()
          }
          Text(item["name"].text).font(.headline).foregroundStyle(Brand.ink)
          Text(item["tagline"].text).font(.subheadline).foregroundStyle(Brand.muted)
            .lineSpacing(3).multilineTextAlignment(.leading)
          preview
          stateLabel
        }
      } else {
        VStack(alignment: .leading, spacing: 14) {
          HStack(alignment: .top, spacing: 16) {
            icon
            VStack(alignment: .leading, spacing: 6) {
              HStack(spacing: 8) {
                Text(item["category"].text).font(.caption).foregroundStyle(Brand.muted)
                if item["installed"].flag {
                  Label("已加入", systemImage: "checkmark")
                    .font(.caption2).foregroundStyle(KitVisual.tint(item["accent"].text))
                }
              }
              Text(item["name"].text).font(.headline).foregroundStyle(Brand.ink)
              Text(item["tagline"].text).font(.subheadline).foregroundStyle(Brand.muted)
                .lineSpacing(3).multilineTextAlignment(.leading)
            }
            Spacer(minLength: 8)
            stateLabel
          }
          preview
        }
      }
    }
    .padding(18)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(Brand.surface, in: RoundedRectangle(cornerRadius: 20))
    .overlay { RoundedRectangle(cornerRadius: 20).stroke(Brand.line, lineWidth: 1) }
    .accessibilityElement(children: .combine)
    .accessibilityLabel("\(item["name"].text)，\(item["tagline"].text)，\(state)")
  }

  private var icon: some View {
    Image(systemName: KitVisual.symbol(item["icon"].text))
      .font(.system(size: 24, weight: .medium))
      .foregroundStyle(KitVisual.tint(item["accent"].text))
      .frame(width: 52, height: 52)
      .background(
        KitVisual.surface(item["accent"].text), in: RoundedRectangle(cornerRadius: 16)
      )
      .accessibilityHidden(true)
  }

  private var stateLabel: some View {
    Text(state)
      .font(.caption.weight(.medium))
      .foregroundStyle(item["installed"].flag ? Brand.blue : Brand.onAccent)
      .padding(.horizontal, 12).padding(.vertical, 7)
      .background(item["installed"].flag ? Brand.softBlue : Brand.blue, in: Capsule())
      .fixedSize(horizontal: false, vertical: true)
  }

  @ViewBuilder private var preview: some View {
    if item["preview"] != .null {
      VStack(alignment: .leading, spacing: 3) {
        Text(item["preview"]["label"].text)
          .font(.caption).foregroundStyle(KitVisual.tint(item["accent"].text))
        Text(item["preview"]["value"].text)
          .font(.system(.title2, design: .rounded, weight: .semibold))
          .foregroundStyle(Brand.ink)
        Text(
          item["preview"]["detail"].text
            + (item["preview"]["latest"].text.isEmpty
              ? "" : " · " + item["preview"]["latest"].text)
        ).font(.caption).foregroundStyle(Brand.muted)
      }
      .padding(.horizontal, 15).padding(.vertical, 12)
      .frame(maxWidth: .infinity, alignment: .leading)
      .background(
        KitVisual.surface(item["accent"].text).opacity(0.72),
        in: RoundedRectangle(cornerRadius: 14))
    }
  }
}

struct KitAppScreen: View {
  @ObservedObject var account: AccountService
  let item: JSON
  @State private var app: JSON = .null
  @State private var loading = true
  @State private var error = ""
  @State private var removeConfirm = false
  @State private var deleteConfirm = false
  @State private var editing = false
  @State private var removeError = ""
  @Environment(\.dismiss) private var dismiss

  var body: some View {
    Group {
      if loading {
        ProgressView("正在打开…").frame(maxWidth: .infinity, maxHeight: .infinity)
      } else if !error.isEmpty {
        VStack(spacing: 13) {
          Image(systemName: "exclamationmark.arrow.trianglehead.2.clockwise.rotate.90")
            .font(.title2).foregroundStyle(Brand.muted)
          Text(error).font(.subheadline).foregroundStyle(Brand.muted)
          Button("重新读取") { Task { await load() } }.buttonStyle(.bordered)
        }.frame(maxWidth: .infinity, maxHeight: .infinity)
      } else {
        KitWebView(
          html: app["html"].text,
          kitID: item["id"].text,
          account: account
        )
        .accessibilityIdentifier("kit.webview")
        .ignoresSafeArea(edges: .bottom)
      }
    }
    .background(Brand.surface)
    .navigationTitle(item["name"].text)
    .navigationBarTitleDisplayMode(.inline)
    .toolbar(.hidden, for: .tabBar)
    .toolbar {
      ToolbarItem(placement: .topBarTrailing) {
        Menu {
          if item["managed"].flag {
            Button {
              editing = true
            } label: {
              Label("编辑应用…", systemImage: "sparkles")
            }
          }
          Button("从应用页移除", role: .destructive) { removeConfirm = true }
          if item["managed"].flag {
            Button("永久删除应用和数据…", role: .destructive) { deleteConfirm = true }
          }
        } label: {
          Image(systemName: "ellipsis")
        }
        .accessibilityLabel("应用操作")
      }
    }
    .task { await load() }
    .sheet(isPresented: $editing, onDismiss: { Task { await load() } }) {
      KitEditorScreen(account: account, kitID: item["id"].text, name: item["name"].text)
    }
    .confirmationDialog(
      "移除“\(item["name"].text)”？已有记录会保留。",
      isPresented: $removeConfirm,
      titleVisibility: .visible
    ) {
      Button("移除应用", role: .destructive) { Task { await uninstall() } }
    } message: {
      if !removeError.isEmpty { Text(removeError) }
    }
    .confirmationDialog(
      "永久删除“\(item["name"].text)”？",
      isPresented: $deleteConfirm,
      titleVisibility: .visible
    ) {
      Button("删除应用和数据", role: .destructive) { Task { await delete() } }
    } message: {
      Text("应用代码和其中的记录都会删除，无法恢复。")
    }
  }

  private func load() async {
    loading = true
    error = ""
    do {
      app = try await account.request("kits/\(item["id"].text)/app")
    } catch {
      self.error = "暂时无法打开这个应用。已有记录仍会保留。"
    }
    loading = false
  }

  private func uninstall() async {
    removeError = ""
    do {
      _ = try await account.request(
        "kits/\(item["id"].text)/uninstall", body: .object([:]))
      dismiss()
    } catch {
      removeError = "暂时无法移除，请稍后重试。"
    }
  }

  private func delete() async {
    removeError = ""
    do {
      _ = try await account.request(
        "kits/\(item["id"].text)/delete",
        body: .object(["confirmation": .string("DELETE")]),
        idempotencyKey: "ios-delete:\(item["id"].text)")
      dismiss()
    } catch {
      removeError = "暂时无法删除，请稍后重试。"
    }
  }
}

private struct KitEditorScreen: View {
  @ObservedObject var account: AccountService
  let kitID: String
  let name: String
  @StateObject private var store = KitEditorStore()
  let preview: Bool
  @Environment(\.dismiss) private var dismiss

  init(account: AccountService, kitID: String, name: String, preview: Bool = false) {
    self.account = account
    self.kitID = kitID
    self.name = name
    self.preview = preview
    _store = StateObject(wrappedValue: KitEditorStore(preview: preview))
  }

  private var active: Bool {
    ["running", "waiting"].contains(store.agentStatus)
  }

  var body: some View {
    NavigationStack {
      ScrollView {
        LazyVStack(alignment: .leading, spacing: 18) {
          statusHeader
          if !store.agentID.isEmpty { AgentActivityView(account: account, agentID: store.agentID) }
          if !store.messages.isEmpty {
            sectionTitle("对话记录", detail: "你和 Hymio 的修改要求")
            ForEach(store.messages, id: \.self) { message in
              messageRow(message)
            }
          }
          if !store.agentResult.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
              Label("Hymio", systemImage: "sparkles")
                .font(.caption.weight(.semibold))
                .foregroundStyle(Brand.blue)
              Text(store.agentResult)
                .font(.subheadline)
                .foregroundStyle(Brand.ink)
                .lineSpacing(3)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(16)
            .background(Brand.softBlue, in: RoundedRectangle(cornerRadius: 18))
          }
          if !store.changes.isEmpty {
            sectionTitle("变更记录", detail: "每次发布都保留")
            ForEach(store.changes, id: \.self) { change in
              changeRow(change)
            }
          }
          if !store.error.isEmpty {
            Label(store.error, systemImage: "exclamationmark.circle")
              .font(.footnote)
              .foregroundStyle(Brand.muted)
          }
        }
        .padding(20)
      }
      .background(Brand.surface)
      .safeAreaInset(edge: .bottom) {
        HStack(alignment: .bottom, spacing: 10) {
          TextField("想让应用怎么变？", text: $store.draft, axis: .vertical)
            .lineLimit(1...4)
            .padding(.horizontal, 14)
            .padding(.vertical, 12)
            .background(Brand.mist, in: RoundedRectangle(cornerRadius: 18))
            .accessibilityIdentifier("kit.editor.input")
          Button {
            Task { await store.send(account, kitID: kitID) }
          } label: {
            if store.sending {
              ProgressView().frame(width: 42, height: 42)
            } else {
              Image(systemName: active ? "hourglass" : "arrow.up")
                .font(.system(size: 17, weight: .semibold))
                .frame(width: 42, height: 42)
            }
          }
          .buttonStyle(.plain)
          .foregroundStyle(Brand.onAccent)
          .background(Brand.blue, in: Circle())
          .disabled(
            store.sending || active
              || store.draft.trimmingCharacters(in: .whitespacesAndNewlines)
                .isEmpty)
          .opacity(active ? 0.55 : 1)
          .accessibilityLabel("发送修改要求")
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(.ultraThinMaterial)
      }
      .navigationTitle("编辑 \(name)")
      .navigationBarTitleDisplayMode(.inline)
      .toolbar {
        ToolbarItem(placement: .cancellationAction) {
          Button("完成") { dismiss() }
        }
      }
      .task {
        if !preview { await store.monitor(account, kitID: kitID) }
      }
    }
  }

  private var statusHeader: some View {
    HStack(spacing: 13) {
      Companion(size: 42, mood: active ? .working : .replying)
      VStack(alignment: .leading, spacing: 4) {
        Text(active ? "正在调整" : "随时可以继续改")
          .font(.headline)
          .foregroundStyle(Brand.ink)
        Text(
          active
            ? "Hymio 会检查页面和接口，完成后再发布。"
            : "说出想要的变化，现有记录会保留。"
        )
        .font(.caption)
        .foregroundStyle(Brand.muted)
      }
      Spacer()
      if store.loading { ProgressView().controlSize(.small) }
    }
    .padding(16)
    .background(Brand.softBlue, in: RoundedRectangle(cornerRadius: 20))
  }

  private func sectionTitle(_ title: String, detail: String) -> some View {
    HStack(alignment: .firstTextBaseline) {
      Text(title).font(.subheadline.weight(.semibold))
      Spacer()
      Text(detail).font(.caption2).foregroundStyle(Brand.muted)
    }
  }

  private func messageRow(_ message: JSON) -> some View {
    let fromMain = message["author"].text == "main_agent"
    return HStack(alignment: .top, spacing: 10) {
      Image(systemName: fromMain ? "sparkles" : "person.fill")
        .font(.caption)
        .foregroundStyle(fromMain ? Brand.blue : Brand.muted)
        .frame(width: 26, height: 26)
        .background(Brand.mist, in: Circle())
      VStack(alignment: .leading, spacing: 4) {
        Text(fromMain ? "由主对话发起" : "你")
          .font(.caption2)
          .foregroundStyle(Brand.muted)
        Text(message["content"].text)
          .font(.subheadline)
          .foregroundStyle(Brand.ink)
          .lineSpacing(2)
      }
      Spacer()
    }
    .frame(maxWidth: .infinity, alignment: .leading)
  }

  private func changeRow(_ change: JSON) -> some View {
    HStack(alignment: .top, spacing: 12) {
      Text("v\(change["revision"].int)")
        .font(.caption2.monospacedDigit().weight(.semibold))
        .foregroundStyle(Brand.blue)
        .padding(.horizontal, 8)
        .padding(.vertical, 5)
        .background(Brand.softBlue, in: Capsule())
      VStack(alignment: .leading, spacing: 4) {
        Text(change["summary"].text).font(.subheadline)
        Text(formatted(change["created_at"].double))
          .font(.caption2)
          .foregroundStyle(Brand.muted)
      }
      Spacer()
    }
    .padding(14)
    .background(Brand.surface, in: RoundedRectangle(cornerRadius: 16))
    .overlay(RoundedRectangle(cornerRadius: 16).stroke(Brand.line))
  }

  private func formatted(_ timestamp: Double) -> String {
    guard timestamp > 0 else { return "" }
    return Date(timeIntervalSince1970: timestamp).formatted(
      .dateTime.month().day().hour().minute())
  }
}

private struct KitWebView: UIViewRepresentable {
  let html: String
  let kitID: String
  @ObservedObject var account: AccountService

  func makeCoordinator() -> Coordinator {
    Coordinator(account: account, kitID: kitID)
  }

  func makeUIView(context: Context) -> WKWebView {
    let controller = WKUserContentController()
    controller.add(context.coordinator, name: "hymioKit")
    controller.addUserScript(
      WKUserScript(
        source: """
          const __hymioPending = new Map();
          let __hymioSequence = 0;
          window.__hymioResolve = function (result) {
            const pending = __hymioPending.get(result.id);
            if (!pending) return;
            __hymioPending.delete(result.id);
            result.ok
              ? pending.resolve(result.value)
              : pending.reject(new Error(result.value || "操作失败"));
          };
          window.HymioKit = {
            call(operation, arguments_) {
              return new Promise((resolve, reject) => {
                const id = `call-${++__hymioSequence}`;
                __hymioPending.set(id, { resolve, reject });
                window.webkit.messageHandlers.hymioKit.postMessage({
                  id,
                  operation,
                  arguments: arguments_ || {},
                });
              });
            },
          };
          """,
        injectionTime: .atDocumentStart,
        forMainFrameOnly: true
      )
    )
    let configuration = WKWebViewConfiguration()
    configuration.userContentController = controller
    configuration.defaultWebpagePreferences.allowsContentJavaScript = true
    configuration.preferences.javaScriptCanOpenWindowsAutomatically = false
    let webView = WKWebView(frame: .zero, configuration: configuration)
    webView.isOpaque = false
    webView.backgroundColor = .clear
    webView.scrollView.backgroundColor = .clear
    webView.allowsLinkPreview = false
    webView.navigationDelegate = context.coordinator
    context.coordinator.webView = webView
    context.coordinator.html = html
    webView.loadHTMLString(Self.sandboxed(html), baseURL: nil)
    return webView
  }

  func updateUIView(_ webView: WKWebView, context: Context) {
    guard context.coordinator.html != html else { return }
    context.coordinator.html = html
    webView.loadHTMLString(Self.sandboxed(html), baseURL: nil)
  }

  static func dismantleUIView(_ webView: WKWebView, coordinator: Coordinator) {
    webView.configuration.userContentController.removeScriptMessageHandler(forName: "hymioKit")
  }

  private static func sandboxed(_ source: String) -> String {
    let policy =
      "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; "
      + "script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; "
      + "font-src data:; connect-src 'none'; frame-src 'none'; media-src 'none'; "
      + "form-action 'none'; base-uri 'none'; navigate-to 'none'\">"
    let head = try! NSRegularExpression(
      pattern: #"<head(?:\s[^>]*)?>"#, options: .caseInsensitive)
    let html = try! NSRegularExpression(
      pattern: #"<html(?:\s[^>]*)?>"#, options: .caseInsensitive)
    let full = NSRange(source.startIndex..<source.endIndex, in: source)
    if let match = head.firstMatch(in: source, range: full),
      let range = Range(match.range, in: source)
    {
      var result = source
      result.insert(contentsOf: policy, at: range.upperBound)
      return result
    }
    if let match = html.firstMatch(in: source, range: full),
      let range = Range(match.range, in: source)
    {
      var result = source
      result.insert(contentsOf: "<head>" + policy + "</head>", at: range.upperBound)
      return result
    }
    return policy + source
  }

  @MainActor final class Coordinator: NSObject, WKScriptMessageHandler, WKNavigationDelegate {
    let account: AccountService
    let kitID: String
    weak var webView: WKWebView?
    var html = ""
    private let operationID = try! NSRegularExpression(
      pattern: #"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$"#)
    private let callID = try! NSRegularExpression(pattern: #"^call-[0-9]{1,12}$"#)

    init(account: AccountService, kitID: String) {
      self.account = account
      self.kitID = kitID
    }

    func userContentController(
      _ userContentController: WKUserContentController,
      didReceive message: WKScriptMessage
    ) {
      Logger(subsystem: "space.hymio.ios", category: "kit-bridge").debug(
        "Received Kit bridge callback")
      guard
        message.name == "hymioKit",
        let data = try? JSONSerialization.data(withJSONObject: message.body),
        let request = try? JSONDecoder().decode(JSON.self, from: data)
      else {
        Logger(subsystem: "space.hymio.ios", category: "kit-bridge").error(
          "Rejected malformed bridge message")
        return
      }
      let callID = request["id"].text
      let operation = request["operation"].text
      guard valid(callID, with: self.callID), valid(operation, with: operationID) else {
        Logger(subsystem: "space.hymio.ios", category: "kit-bridge").error(
          "Rejected invalid bridge operation")
        resolve(request["id"].text, error: "这个操作不可用")
        return
      }
      Task {
        do {
          Logger(subsystem: "space.hymio.ios", category: "kit-bridge").debug(
            "Forwarding Kit operation")
          let response = try await account.request(
            "kits/\(kitID)/actions/\(operation)",
            body: request["arguments"],
            idempotencyKey: "ios:\(kitID):\(callID)"
          )
          resolve(callID, value: response["result"])
        } catch {
          Logger(subsystem: "space.hymio.ios", category: "kit-bridge").error(
            "Kit operation did not complete")
          resolve(callID, error: "暂时无法完成这个操作")
        }
      }
    }

    private func resolve(_ id: String, value: JSON = .null, error: String = "") {
      var payload: [String: Any] = ["id": id, "ok": error.isEmpty]
      guard
        let valueData = try? JSONEncoder().encode(error.isEmpty ? value : .string(error)),
        let valueObject = try? JSONSerialization.jsonObject(with: valueData)
      else { return }
      payload["value"] = valueObject
      guard
        let data = try? JSONSerialization.data(withJSONObject: payload),
        let argument = String(data: data, encoding: .utf8)
      else { return }
      webView?.evaluateJavaScript("window.__hymioResolve(\(argument));") { _, _ in }
    }

    private func valid(_ value: String, with expression: NSRegularExpression) -> Bool {
      let range = NSRange(value.startIndex..<value.endIndex, in: value)
      return expression.firstMatch(in: value, range: range) != nil
    }

    func webView(
      _ webView: WKWebView,
      decidePolicyFor navigationAction: WKNavigationAction,
      decisionHandler: @escaping (WKNavigationActionPolicy) -> Void
    ) {
      decisionHandler(navigationAction.request.url?.scheme == "about" ? .allow : .cancel)
    }
  }
}

#if DEBUG
  struct KitEditorPreviewScreen: View {
    @StateObject private var account = AccountService()

    var body: some View {
      KitEditorScreen(
        account: account,
        kitID: "preview",
        name: "饮水记录",
        preview: true)
    }
  }

  struct KitAppPreviewScreen: View {
    @StateObject private var account = AccountService()
    private static let html = """
      <!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
      <style>
      :root{color-scheme:light;--surface:#fff;--ink:#202536;--muted:#687083;--line:#e6e8ee;--warm:#fff3dc;--blue:#425de8}
      *{box-sizing:border-box}body{margin:0;background:#f7f7f8;color:var(--ink);font-family:-apple-system,"PingFang SC"}
      main{padding:18px 16px 100px;max-width:720px;margin:auto}.hero,.panel{border:1px solid var(--line);border-radius:20px;background:var(--surface)}
      .hero{padding:22px;background:linear-gradient(135deg,var(--warm),var(--surface));border-color:#f0dfc1}
      .eyebrow{color:#8b5c24;font-size:13px;font-weight:600}h1{font-size:38px;letter-spacing:-1.5px;margin:7px 0 2px}.hero small{color:var(--muted)}
      .panel{margin-top:14px;padding:18px}.head{display:flex;justify-content:space-between;margin-bottom:8px}h2{font-size:17px;margin:0}.count{font-size:13px;color:var(--muted)}
      .entry{display:flex;justify-content:space-between;gap:14px;padding:14px 0;border-bottom:1px solid var(--line)}.entry:last-child{border:0}
      .entry strong,.entry small{display:block}.entry small{color:var(--muted);font-size:13px;margin-top:3px}.entry b{font-weight:600}
      .primary{position:fixed;left:20px;right:20px;bottom:max(18px,env(safe-area-inset-bottom));height:50px;border:0;border-radius:15px;color:white;background:var(--blue);font:600 17px -apple-system}
      </style></head><body><main><section class="hero"><div class="eyebrow">本月支出</div><h1>¥286.00</h1><small>4 笔记录</small></section>
      <section class="panel"><div class="head"><h2>最近记录</h2><span class="count">3</span></div>
      <div class="entry"><div><strong>和朋友吃午饭</strong><small>餐饮 · 10月24日</small></div><b>¥68.00</b></div>
      <div class="entry"><div><strong>地铁</strong><small>出行 · 10月24日</small></div><b>¥8.00</b></div>
      <div class="entry"><div><strong>一本想看很久的书</strong><small>学习 · 10月23日</small></div><b>¥54.00</b></div></section></main>
      <button class="primary">记一笔</button></body></html>
      """

    var body: some View {
      NavigationStack {
        KitWebView(html: Self.html, kitID: "preview", account: account)
          .navigationTitle("生活账本")
          .navigationBarTitleDisplayMode(.inline)
      }
    }
  }
#endif
