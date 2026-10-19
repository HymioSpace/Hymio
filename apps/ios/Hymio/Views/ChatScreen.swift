import SwiftUI

struct ChatScreen: View {
  @ObservedObject var account: AccountService
  @ObservedObject var client: AgentClient
  @State private var draft = ""
  @State private var profile = false
  @State private var atBottom = true
  @State private var sendBusy = false
  @FocusState private var typing: Bool
  @Environment(\.accessibilityReduceMotion) private var reduceMotion
  @Namespace private var transitions
  @State private var sentCount = 0
  var body: some View {
    NavigationStack {
      ScrollViewReader { proxy in
        ScrollView {
          LazyVStack(alignment: .leading, spacing: 25) {
            if client.state.hasMore {
              Button(client.loadingHistory ? "正在加载…" : "更早的对话") {
                Task { await client.loadHistory() }
              }
              .font(.caption).foregroundStyle(.secondary).frame(maxWidth: .infinity).disabled(
                client.loadingHistory)
            }
            if client.model.messages.isEmpty {
              VStack(spacing: 18) {
                Companion(size: 116, animated: true)
                VStack(spacing: 10) {
                  Text("嗨，我在。").font(.system(.largeTitle, design: .rounded, weight: .medium))
                    .tracking(-1)
                  Text("想到什么，就和我说说。")
                    .font(.subheadline).foregroundStyle(.secondary)
                }
              }.frame(maxWidth: .infinity).padding(.top, 70).padding(.bottom, 90)
            }
            ForEach(client.model.messages) { message in
              MessageRow(message: message, tools: client.model.terminals, account: account).id(
                message.id)
            }
            ForEach(client.model.approvals.filter { $0.status == "pending" }) { approval in
              ApprovalCard(approval: approval, client: client)
            }
            if client.model.working && !client.model.messages.contains(where: \.streaming) {
              HStack(spacing: 10) {
                Companion(size: 30, animated: true)
                Text("正在继续处理…").font(.caption).foregroundStyle(.secondary)
              }.accessibilityIdentifier("chat.working")
            }
            if !client.model.failure.isEmpty {
              Label(client.model.failure, systemImage: "exclamationmark.circle").font(.footnote)
                .foregroundStyle(.secondary)
            }
            Color.clear.frame(height: 1).id("bottom").onAppear { atBottom = true }.onDisappear {
              atBottom = false
            }
          }.padding(.horizontal, 20).padding(.top, 22).padding(.bottom, 20)
            .animation(
              reduceMotion ? nil : .spring(duration: 0.32, bounce: 0.08),
              value: client.model.messages.count)
        }
        .scrollDismissesKeyboard(.interactively)
        .defaultScrollAnchor(.bottom, for: .initialOffset)
        .onChange(of: client.state.cursor) { _, _ in
          if atBottom && !client.loadingHistory { proxy.scrollTo("bottom", anchor: .bottom) }
        }
        .overlay(alignment: .bottomTrailing) {
          if !atBottom && !client.model.messages.isEmpty {
            Button {
              withAnimation { proxy.scrollTo("bottom", anchor: .bottom) }
            } label: {
              Image(systemName: "arrow.down").padding(12).background(.regularMaterial, in: Circle())
                .shadow(color: .black.opacity(0.05), radius: 8)
            }
            .padding(18).accessibilityLabel("最新消息")
          }
        }
      }
      .background(Brand.surface).foregroundStyle(Brand.ink)
      .navigationTitle("hymio").navigationBarTitleDisplayMode(.inline)
      .toolbar {
        ToolbarItem(placement: .principal) {
          VStack(spacing: 2) {
            Text("hymio").font(.system(.headline, design: .rounded)).tracking(-0.5)
            HStack(spacing: 4) {
              Circle().fill(client.connected ? Brand.blue : Color.gray).frame(width: 4, height: 4)
              Text(client.phase).font(.caption2).foregroundStyle(.secondary)
            }
          }.accessibilityElement(children: .combine)
        }
        ToolbarItem(placement: .topBarTrailing) {
          Button {
            typing = false
            profile = true
          } label: {
            Image(systemName: "person.crop.circle").font(.title3).foregroundStyle(Brand.ink)
          }.accessibilityLabel("我的账号")
            .matchedTransitionSource(id: "account", in: transitions)
        }
      }
      .safeAreaInset(edge: .bottom, spacing: 0) { composer }
      .sheet(isPresented: $profile) {
        if reduceMotion {
          AccountScreen(account: account, client: client).presentationDragIndicator(.visible)
        } else {
          AccountScreen(account: account, client: client)
            .navigationTransition(.zoom(sourceID: "account", in: transitions))
            .presentationDragIndicator(.visible)
        }
      }
      .sensoryFeedback(.selection, trigger: sentCount)
    }
  }
  private var composer: some View {
    VStack(spacing: 8) {
      if !client.connected && !client.state.pending.isEmpty {
        Text("消息已保存在本机，连接恢复后继续发送。")
          .font(.caption2).foregroundStyle(.secondary).frame(
            maxWidth: .infinity, alignment: .leading
          ).padding(.horizontal, 8)
      }
      if !client.error.isEmpty {
        HStack(alignment: .top) {
          Text(client.error).font(.caption).foregroundStyle(.secondary)
          Spacer()
          Button(client.phase == "需要登录" ? "重新登录" : "重连") {
            if client.phase == "需要登录" {
              Task {
                client.reset()
                await account.logout()
              }
            } else {
              client.reconnect()
            }
          }.font(.caption)
        }.padding(.horizontal, 8)
      }
      HStack(alignment: .bottom, spacing: 12) {
        TextField("接着说，我在听…", text: $draft, axis: .vertical)
          .lineLimit(1...6).padding(.vertical, 9).focused($typing).accessibilityIdentifier(
            "chat.input")
        Button {
          send()
        } label: {
          Image(systemName: "arrow.up").font(.system(size: 16, weight: .semibold)).foregroundStyle(
            Brand.surface
          ).symbolEffect(.bounce, value: reduceMotion ? 0 : sentCount)
            .frame(width: 36, height: 36).background(
              canSend ? Brand.ink : Color.secondary.opacity(0.18), in: Circle()
            )
            .frame(width: 44, height: 44)
        }.buttonStyle(GentlePress()).disabled(!canSend).accessibilityLabel("发送消息")
          .accessibilityIdentifier("chat.send")
      }
      .padding(7).padding(.leading, 12)
      .modifier(ComposerSurface())
    }.padding(.horizontal, 16).padding(.top, 9).padding(.bottom, 8)
  }
  private var canSend: Bool {
    client.connected && !sendBusy && !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
  }
  private func send() {
    let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
    guard canSend else { return }
    sendBusy = true
    Task {
      do {
        try await client.message(text)
        sentCount += 1
        if draft.trimmingCharacters(in: .whitespacesAndNewlines) == text { draft = "" }
      } catch { client.error = error.localizedDescription }
      sendBusy = false
    }
  }
}
struct ApprovalCard: View {
  let approval: Approval
  @ObservedObject var client: AgentClient
  var body: some View {
    TimelineView(.periodic(from: .now, by: 1)) { context in
      let expired = approval.expires <= context.date.timeIntervalSince1970
      let pending = client.state.pending.contains {
        $0.payload["invocation_id"].text == approval.id
      }
      VStack(alignment: .leading, spacing: 14) {
        Label(expired ? "这项授权已过期" : "这一步，需要你点头", systemImage: "hand.raised").font(
          .subheadline.weight(.medium))
        Text(approval.tool).font(.caption).foregroundStyle(.secondary)
        DisclosureGroup("操作详情") {
          Text(approval.arguments.pretty).font(.system(.caption, design: .monospaced))
            .textSelection(.enabled)
        }.font(.caption)
        if !expired {
          HStack {
            Button("拒绝") { Task { await client.decide(approval.id, false) } }.buttonStyle(.bordered)
            Spacer()
            Button(pending ? "已提交" : "允许这次") { Task { await client.decide(approval.id, true) } }
              .buttonStyle(.borderedProminent)
          }.disabled(!client.connected || pending)
        }
      }.padding(18).background(Brand.mist, in: RoundedRectangle(cornerRadius: 20)).padding(
        .leading, 39)
    }
  }
}
