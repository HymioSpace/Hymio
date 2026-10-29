import PhotosUI
import SwiftUI
import UIKit
import UniformTypeIdentifiers

private enum AttachmentLimits {
  static let maxCount = 12
}

struct ChatScreen: View {
  @ObservedObject var account: AccountService
  @ObservedObject var client: AgentClient
  let onAccount: () -> Void
  @State private var draft = ""
  @State private var attachments: [JSON] = []
  @State private var selectedPhotos: [PhotosPickerItem] = []
  @State private var uploading = false
  @State private var filesOpen = false
  @State private var cameraOpen = false
  @State private var photosOpen = false
  @State private var following = true
  @State private var positioned = false
  @State private var atBottom = true
  @State private var sendBusy = false
  @FocusState private var typing: Bool
  @Environment(\.accessibilityReduceMotion) private var reduceMotion
  @State private var sentCount = 0
  @State private var followTask: Task<Void, Never>?
  private var visibleTurns: [Turn] {
    if client.turns.isEmpty, !client.model.messages.isEmpty {
      return client.model.turns
    }
    return client.turns
  }
  var body: some View {
    NavigationStack {
      ScrollViewReader { proxy in
        ScrollView {
          LazyVStack(alignment: .leading, spacing: 18) {
            if client.state.hasMore {
              Button(client.loadingHistory ? "正在加载…" : "更早的对话") {
                let first = client.turns.first?.id
                Task {
                  await client.loadHistory()
                  if let first { proxy.scrollTo(first, anchor: .top) }
                }
              }
              .font(.caption).foregroundStyle(.secondary).frame(maxWidth: .infinity).disabled(
                client.loadingHistory)
            }
            if client.model.messages.isEmpty {
              VStack(spacing: 18) {
                Companion(size: 116)
                VStack(spacing: 10) {
                  Text("嗨，我在。").font(.system(.largeTitle, design: .rounded, weight: .medium))
                    .tracking(-1)
                  Text("想到什么，就和我说说。")
                    .font(.subheadline).foregroundStyle(.secondary)
                }
              }.frame(maxWidth: .infinity).padding(.top, 70).padding(.bottom, 90)
            }
            ForEach(visibleTurns) { turn in
              if let unread = client.unread, unread.turnID == turn.id {
                HStack(spacing: 12) {
                  Rectangle().fill(Brand.line).frame(height: 1)
                  Button("\(unread.count) 条未读消息") { client.markRead() }
                    .font(.caption).foregroundStyle(.secondary).fixedSize().frame(minHeight: 44)
                  Rectangle().fill(Brand.line).frame(height: 1)
                }.accessibilityHint("点击标记为已读")
              }
              TraceRow(
                turn: turn,
                tools: Dictionary(
                  uniqueKeysWithValues: turn.invocationIDs.compactMap { id in
                    client.model.terminals[id].map { (id, $0) }
                  }), approvals: client.model.approvals,
                onAction: {
                  try await client.message($0)
                }, onRetry: { client.retryDelivery($0) },
                onDiscard: { client.discardDelivery($0) },
                account: account
              ).equatable().id(turn.id)
            }
            ForEach(client.model.approvals.filter { $0.status == "pending" }) { approval in
              ApprovalCard(approval: approval, client: client, account: account)
            }
            TimelineView(.periodic(from: .now, by: 2)) { timeline in
              if (client.model.working || client.model.awaitingReply)
                && !client.model.messages.contains(where: \.streaming)
                && CompactionNotice.active(in: client.state.events, at: timeline.date) == nil
              {
                HStack(spacing: 10) {
                  ProgressView().controlSize(.small)
                  Text(client.model.awaitingReply ? "正在探索…" : "继续探索中…").font(.caption)
                    .foregroundStyle(.secondary)
                }.accessibilityIdentifier("chat.working")
              }
            }
            if !client.model.failure.isEmpty {
              Label(userFacingError(client.model.failure), systemImage: "exclamationmark.circle").font(.footnote)
                .foregroundStyle(.secondary)
            }
            if !client.model.pauseNotice.isEmpty {
              VStack(alignment: .leading, spacing: 8) {
                Label(client.model.pauseNotice, systemImage: "pause.circle")
                  .font(.footnote).foregroundStyle(.secondary)
                Button(sendBusy ? "正在继续…" : "继续处理") {
                  guard !sendBusy else { return }
                  sendBusy = true
                  Task {
                    defer { sendBusy = false }
                    do { try await client.message("继续处理") } catch {
                      client.error = error.localizedDescription
                    }
                  }
                }.buttonStyle(.borderedProminent).frame(minHeight: 44)
                  .fixedSize(horizontal: false, vertical: true)
                  .disabled(sendBusy || uploading || !client.connected)
                  .accessibilityIdentifier("chat.continue")
              }
            }
            Color.clear.frame(height: 1).id("bottom")
          }.padding(.horizontal, 18).padding(.top, 16).padding(.bottom, 14)
            .frame(maxWidth: 760).frame(maxWidth: .infinity)
        }
        .contentShape(Rectangle())
        .simultaneousGesture(TapGesture().onEnded { typing = false })
        .scrollDismissesKeyboard(.interactively)
        .defaultScrollAnchor(.bottom, for: .initialOffset)
        .onScrollGeometryChange(for: Bool.self) { geometry in
          geometry.contentSize.height - geometry.visibleRect.maxY < 12
        } action: { _, near in
          atBottom = near
        }
        .onScrollPhaseChange { _, phase in
          if phase == .interacting {
            following = false
            followTask?.cancel()
            followTask = nil
          }
          if phase == .idle && atBottom { following = true }
        }
        .onScrollGeometryChange(for: CGFloat.self) {
          $0.contentSize.height
        } action: { before, after in
          if after > before + 0.5 && following && !client.loadingHistory && positioned {
            scheduleFollow(proxy)
          }
        }
        .onChange(of: client.model.messages.count) { _, _ in
          if client.model.messages.last?.role == "user" {
            following = true
            scheduleFollow(proxy)
          } else if !positioned && !client.model.messages.isEmpty {
            proxy.scrollTo("bottom", anchor: .bottom)
          }
          positioned = !client.model.messages.isEmpty
        }
        .overlay(alignment: .bottomTrailing) {
          if client.model.approvals.contains(where: { $0.status == "pending" }) {
            TimelineView(.periodic(from: .now, by: 1)) { timeline in
              let pending = pendingApprovalCount(at: timeline.date)
              if !atBottom && !client.model.messages.isEmpty {
                Button {
                  following = true
                  atBottom = true
                  withAnimation(reduceMotion ? nil : .easeOut(duration: 0.2)) {
                    proxy.scrollTo("bottom", anchor: .bottom)
                  }
                  Task { @MainActor in
                    try? await Task.sleep(for: .milliseconds(180))
                    proxy.scrollTo("bottom", anchor: .bottom)
                    atBottom = true
                  }
                } label: {
                  if pending > 0 {
                    Label("\(pending) 个待确认", systemImage: "hand.raised")
                      .font(.caption.weight(.medium))
                      .foregroundStyle(.secondary)
                      .padding(.horizontal, 12)
                      .padding(.vertical, 10)
                      .background(.regularMaterial, in: Capsule())
                      .shadow(color: .black.opacity(0.05), radius: 8)
                  } else {
                    Image(systemName: "arrow.down").padding(12)
                      .background(.regularMaterial, in: Circle())
                      .shadow(color: .black.opacity(0.05), radius: 8)
                  }
                }
                .padding(18)
                .accessibilityLabel(pending > 0 ? "\(pending) 个操作等待确认" : "最新消息")
              }
            }
          } else if !atBottom && !client.model.messages.isEmpty {
            Button {
              following = true
              atBottom = true
              withAnimation(reduceMotion ? nil : .easeOut(duration: 0.2)) {
                proxy.scrollTo("bottom", anchor: .bottom)
              }
              Task { @MainActor in
                try? await Task.sleep(for: .milliseconds(180))
                proxy.scrollTo("bottom", anchor: .bottom)
                atBottom = true
              }
            } label: {
              Image(systemName: "arrow.down").padding(12).background(.regularMaterial, in: Circle())
                .shadow(color: .black.opacity(0.05), radius: 8)
            }
            .padding(18).accessibilityLabel("最新消息")
          }
        }
      }
      .background(Brand.surface).foregroundStyle(Brand.ink)
      .toolbarBackground(.regularMaterial, for: .navigationBar)
      .toolbarBackground(.visible, for: .navigationBar)
      .navigationTitle("hymio").navigationBarTitleDisplayMode(.inline)
      .toolbar {
        ToolbarItemGroup(placement: .topBarLeading) {
          AccountButton(account: account, action: onAccount)
        }.accountUnframed()
        ToolbarItem(placement: .principal) {
          VStack(spacing: 2) {
            Text("hymio").font(.system(.headline, design: .rounded)).tracking(-0.5)
            HStack(spacing: 5) {
              if client.connected
                && (client.model.working || client.model.awaitingReply
                  || client.model.messages.contains(where: \.streaming))
              {
                Companion(size: 24, mood: .working)
              }
              ConnectionStatus(
                text: client.connected && (client.model.working || client.model.awaitingReply)
                  ? "探索中" : client.phase, connected: client.connected)
            }
          }.accessibilityElement(children: .combine)
        }
      }
      .onChange(of: selectedPhotos) { _, photos in
        guard !photos.isEmpty else { return }
        guard photos.count + attachments.count <= AttachmentLimits.maxCount else {
          selectedPhotos = []
          client.error = "每条消息最多添加 \(AttachmentLimits.maxCount) 个附件"
          return
        }
        uploading = true
        Task {
          defer {
            uploading = false
            selectedPhotos = []
          }
          do {
            for photo in photos {
              if let data = try await photo.loadTransferable(type: Data.self) {
                guard
                  let jpeg = try await Task.detached(
                    priority: .userInitiated,
                    operation: {
                      ImagePipeline.attachment(data)
                    }
                  ).value
                else {
                  throw ServiceError.message("照片格式无法读取")
                }
                let value = try await account.upload(jpeg, name: "photo.jpg")
                attachments.append(value)
              }
            }
          } catch { client.error = error.localizedDescription }
        }
      }
      .fileImporter(
        isPresented: $filesOpen, allowedContentTypes: [.item], allowsMultipleSelection: true
      ) { result in
        uploading = true
        Task {
          defer { uploading = false }
          do {
            let urls = try result.get()
            guard urls.count + attachments.count <= AttachmentLimits.maxCount else {
              throw ServiceError.message("每条消息最多添加 \(AttachmentLimits.maxCount) 个附件")
            }
            for url in urls {
              let access = url.startAccessingSecurityScopedResource()
              defer { if access { url.stopAccessingSecurityScopedResource() } }
              let data = try await Task.detached {
                try Data(contentsOf: url, options: .mappedIfSafe)
              }.value
              let value = try await account.upload(data, name: url.lastPathComponent)
              attachments.append(value)
            }
          } catch { client.error = error.localizedDescription }
        }
      }
      .sheet(isPresented: $cameraOpen) {
        CameraCapture { image in
          cameraOpen = false
          guard let image else { return }
          guard attachments.count < AttachmentLimits.maxCount else {
            client.error = "每条消息最多添加 \(AttachmentLimits.maxCount) 个附件"
            return
          }
          uploading = true
          Task {
            defer { uploading = false }
            do {
              guard
                let data = try await Task.detached(
                  priority: .userInitiated,
                  operation: {
                    ImagePipeline.attachment(image)
                  }
                ).value
              else { throw ServiceError.message("照片格式无法读取") }
              let value = try await account.upload(data, name: "camera.jpg")
              attachments.append(value)
            } catch { client.error = error.localizedDescription }
          }
        }.ignoresSafeArea()
      }
      .modifier(
        PhotoLibraryPickerModifier(
          isPresented: $photosOpen,
          selection: $selectedPhotos,
          maxSelectionCount: max(1, AttachmentLimits.maxCount - attachments.count)
        )
      )
      .safeAreaInset(edge: .bottom, spacing: 0) { composer }
      .sensoryFeedback(.selection, trigger: sentCount)
      .onDisappear {
        followTask?.cancel()
        followTask = nil
      }
    }
  }

  private func scheduleFollow(_ proxy: ScrollViewProxy) {
    guard followTask == nil else { return }
    followTask = Task { @MainActor in
      try? await Task.sleep(for: .milliseconds(100))
      guard !Task.isCancelled else { return }
      followTask = nil
      guard following, !client.loadingHistory else { return }
      var transaction = Transaction(); transaction.disablesAnimations = true
      withTransaction(transaction) { proxy.scrollTo("bottom", anchor: .bottom) }
      atBottom = true
    }
  }

  private var composer: some View {
    VStack(spacing: 8) {
      CompactionNotice(events: client.state.events)
      if !client.connected && !client.state.pending.isEmpty {
        Text("消息已保存在本机，连接恢复后继续发送。")
          .font(.caption2).foregroundStyle(.secondary).frame(
            maxWidth: .infinity, alignment: .leading
          ).padding(.horizontal, 8)
      }
      if !client.error.isEmpty && (client.connected || ["需要登录", "消息大小超限", "已在其他设备连接"].contains(client.phase)) {
        HStack(alignment: .top) {
          Text(userFacingError(client.error, phase: client.phase)).font(.caption).foregroundStyle(.secondary)
          Spacer()
          Button(client.phase == "需要登录" ? "重新登录" : "重连") {
            if client.phase == "需要登录" {
              Task {
                client.reset()
                await account.logout()
              }
            } else {
              client.retryDelivery()
            }
          }.font(.caption)
        }.padding(.horizontal, 8)
      }
      VStack(alignment: .leading, spacing: 8) {
        if !attachments.isEmpty || uploading {
          ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 10) {
              ForEach(attachments.indices, id: \.self) { index in
                ComposerAttachment(file: attachments[index], account: account, disabled: uploading)
                {
                  attachments.remove(at: index)
                }
              }
              if uploading {
                HStack(spacing: 8) {
                  ProgressView().controlSize(.small)
                  Text("正在添加…").font(.caption).foregroundStyle(.secondary)
                }
                .padding(.horizontal, 12).frame(height: 64)
              }
            }.padding(.horizontal, 4).padding(.top, 4)
          }
        }
        if !quickReplies.isEmpty {
          ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 7) {
              ForEach(quickReplies, id: \.self) { reply in
                Button {
                  sendQuick(reply)
                } label: {
                  Text(reply).font(.caption).foregroundStyle(Brand.muted)
                    .padding(.horizontal, 12).frame(minHeight: 34)
                    .background(Brand.surface.opacity(0.82), in: Capsule())
                    .overlay { Capsule().stroke(Brand.muted.opacity(0.18), lineWidth: 0.5) }
                }.buttonStyle(.plain).disabled(!client.connected || sendBusy || uploading)
                  .accessibilityHint("立即发送这条消息")
              }
            }.padding(.horizontal, 4)
          }
        }
        TextField("接着说，我在听…", text: $draft, axis: .vertical)
          .lineLimit(1...6).padding(.vertical, 6).padding(.horizontal, 8).focused($typing)
          .accessibilityIdentifier(
            "chat.input")
        HStack(alignment: .bottom, spacing: 8) {
          Menu {
            Button {
              photosOpen = true
            } label: {
              Label("照片图库", systemImage: "photo.on.rectangle")
            }
            if UIImagePickerController.isSourceTypeAvailable(.camera) {
              Button {
                cameraOpen = true
              } label: {
                Label("拍照", systemImage: "camera")
              }
            }
            Button {
              filesOpen = true
            } label: {
              Label("选择文件", systemImage: "doc")
            }
          } label: {
            Image(systemName: "plus").font(.system(size: 19, weight: .regular)).foregroundStyle(
              Brand.muted
            ).frame(width: 44, height: 44)
          }.disabled(uploading || attachments.count >= AttachmentLimits.maxCount)
            .accessibilityLabel("添加附件")
          Spacer(minLength: 8)
          Button {
            send()
          } label: {
            Image(systemName: "arrow.up").font(.system(size: 16, weight: .semibold))
              .foregroundStyle(
                Brand.onAccent
              )
              .frame(width: 36, height: 36).background(
                canSend ? Brand.blue : Color.secondary.opacity(0.18), in: Circle()
              )
              .frame(width: 44, height: 44)
          }.buttonStyle(GentlePress()).disabled(!canSend).accessibilityLabel("发送消息")
            .accessibilityIdentifier("chat.send")
        }
      }
      .padding(8)
      .modifier(ComposerSurface(focused: typing))
    }.padding(.horizontal, 16).padding(.top, 9).padding(.bottom, 8)
  }
  private func pendingApprovalCount(at date: Date) -> Int {
    client.model.approvals.filter {
      $0.status == "pending" && $0.expires > date.timeIntervalSince1970
    }.count
  }
  private var canSend: Bool {
    client.connected && !sendBusy && !uploading
      && (!draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !attachments.isEmpty)
  }
  private var quickReplies: [String] {
    guard !client.model.working, !client.model.awaitingReply,
      let last = client.model.messages.last, last.role == "assistant", !last.streaming
    else { return [] }
    return last.suggestions
  }
  private func sendQuick(_ text: String) {
    let value = text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard client.connected, !sendBusy, !uploading, !value.isEmpty else { return }
    sendBusy = true
    atBottom = true
    following = true
    Task {
      do {
        try await client.message(value)
        sentCount += 1
      } catch { client.error = error.localizedDescription }
      sendBusy = false
    }
  }
  private func send() {
    let originalDraft = draft
    let sentAttachments = attachments
    let links = sentAttachments.map { file in
      let name = file["name"].text.replacingOccurrences(of: "[", with: "").replacingOccurrences(
        of: "]", with: "")
      return (file["mime"].text.hasPrefix("image/") ? "!" : "") + "[" + name + "]("
        + file["url"].text + ")"
    }.joined(separator: "\n")
    let text = [draft.trimmingCharacters(in: .whitespacesAndNewlines), links].filter { !$0.isEmpty }
      .joined(separator: "\n\n")
    guard canSend else { return }
    sendBusy = true
    draft = ""
    attachments = []
    atBottom = true
    following = true
    Task {
      do {
        try await client.message(
          text, attachmentIds: sentAttachments.map { $0["attachment_id"].text })
        sentCount += 1

      } catch {
        if draft.isEmpty {
          draft = originalDraft
          attachments = sentAttachments
        }
        client.error = error.localizedDescription
      }
      sendBusy = false
    }
  }
}
struct ApprovalCard: View {
  let approval: Approval
  @ObservedObject var client: AgentClient
  @ObservedObject var account: AccountService
  var body: some View {
    ApprovalCardView(
      approval: approval,
      connected: client.connected,
      pending: client.state.pending.contains {
        $0.payload["invocation_id"].text == approval.id
      },
      onDecision: { approved, scope in
        try await client.decide(
          approval.id, approved, scope: scope, actionDigest: approval.actionDigest)
        if approved && scope == "exact_rule" {
          do {
            _ = try await account.request(
              "settings/tool-authorization/rules",
              body: .object([
                "tool": .string(approval.tool),
                "arguments": approval.arguments,
              ]))
            return "已允许，并加入始终允许"
          } catch {
            return "已允许；长期规则未保存"
          }
        }
        return approved ? "已允许" : "已拒绝"
      }
    )
  }
}

struct ApprovalCardView: View {
  let approval: Approval
  let connected: Bool
  let pending: Bool
  let onDecision: (_ approved: Bool, _ scope: String) async throws -> String
  @State private var scope = "once"
  @State private var hidden = false
  @State private var receipt = ""
  @State private var detailsExpanded = false
  @State private var error = ""
  @Environment(\.accessibilityReduceMotion) private var reduceMotion

  var body: some View {
    TimelineView(.periodic(from: .now, by: 1)) { context in
      if hidden {
        if !receipt.isEmpty {
          Label(receipt, systemImage: receipt.hasPrefix("已拒绝") ? "xmark" : "checkmark")
            .font(.caption.weight(.medium))
            .foregroundStyle(.secondary)
            .frame(maxWidth: .infinity, minHeight: 32, alignment: .leading)
            .transition(.opacity)
        }
      } else if approval.expires > context.date.timeIntervalSince1970 {
        VStack(alignment: .leading, spacing: 0) {
          HStack(alignment: .firstTextBaseline, spacing: 7) {
            Image(systemName: toolSymbol)
              .font(.caption.weight(.medium))
              .foregroundStyle(.secondary)
              .accessibilityHidden(true)
            Text(displayTitle)
              .font(.headline)
              .foregroundStyle(.primary)
              .lineLimit(2)
            Spacer(minLength: 8)
            if let warningLabel {
              Text(warningLabel)
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize()
            }
          }
          if !approval.summary.isEmpty {
            Text(approval.summary)
              .font(.subheadline)
              .foregroundStyle(.secondary)
              .padding(.top, 4)
          }

          if !cardPreview.isEmpty {
            HStack(alignment: .top, spacing: 6) {
              Text(approval.tool == "bash" ? "$" : "›").foregroundStyle(.secondary)
              Text(cardPreview)
                .foregroundStyle(.primary)
                .lineLimit(3)
                .textSelection(.enabled)
            }
            .font(.system(size: 13, weight: .regular, design: .monospaced))
            .padding(.horizontal, 10)
            .padding(.vertical, 9)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
              Color(uiColor: .secondarySystemFill),
              in: RoundedRectangle(cornerRadius: 8, style: .continuous)
            )
            .padding(.top, 10)
          }

          ViewThatFits(in: .horizontal) {
            HStack(alignment: .center, spacing: 8) {
              metadataText(context.date)
              Spacer(minLength: 8)
              detailsButton
            }
            VStack(alignment: .leading, spacing: 0) {
              metadataText(context.date)
              detailsButton
            }
          }
          .padding(.top, 2)

          if detailsExpanded {
            Text(approval.arguments.pretty)
              .font(.system(.caption, design: .monospaced))
              .textSelection(.enabled)
              .frame(maxWidth: .infinity, alignment: .leading)
              .padding(10)
              .background(
                Color(uiColor: .secondarySystemFill),
                in: RoundedRectangle(cornerRadius: 8, style: .continuous)
              )
              .padding(.bottom, 4)
          }

          if options.count > 1 && scope != "once" {
            Text(scopeDescription)
              .font(.caption)
              .foregroundStyle(.secondary)
              .padding(.bottom, 2)
          }
          ViewThatFits(in: .horizontal) {
            HStack(spacing: 8) {
              scopeMenu
              Spacer(minLength: 8)
              decisionButtons
            }
            VStack(alignment: .leading, spacing: 2) {
              scopeMenu
              decisionButtons
            }
          }
          .disabled(!connected || pending)
          if !error.isEmpty {
            Text(error).font(.caption).foregroundStyle(.secondary)
          }
        }
        .padding(.horizontal, 15)
        .padding(.top, 14)
        .padding(.bottom, 10)
        .background(
          Brand.raised,
          in: RoundedRectangle(cornerRadius: 14, style: .continuous)
        )
        .overlay(
          RoundedRectangle(cornerRadius: 14, style: .continuous)
            .stroke(Color(uiColor: .separator).opacity(0.34), lineWidth: 0.5)
        )
      }
    }
    .animation(reduceMotion ? nil : .easeOut(duration: 0.16), value: hidden)
  }

  private var options: [String] {
    let value = approval.scopeOptions.filter { ["once", "run", "exact_rule"].contains($0) }
    return value.isEmpty ? ["once"] : value
  }
  private var displayTitle: String {
    let title = approval.title.trimmingCharacters(in: .whitespacesAndNewlines)
    let description = approval.arguments["description"].text.trimmingCharacters(
      in: .whitespacesAndNewlines)
    if !description.isEmpty,
      title.isEmpty || title == approval.tool || title == "允许运行 \(approval.tool)？"
        || title == "Allow \(approval.tool)?"
    {
      return description
    }
    return title.isEmpty ? "允许执行操作？" : title
  }
  private var warningLabel: String? {
    approval.tier == "critical" ? "每次确认" : nil
  }
  private var toolSymbol: String {
    [
      "browser": "globe",
      "computer": "desktopcomputer",
      "kit_call": "square.grid.2x2",
      "bash": "terminal",
    ][approval.tool] ?? "terminal"
  }
  private var cardPreview: String {
    let value =
      approval.tool == "bash"
      ? approval.arguments["command"].text
      : approval.tool == "browser"
        ? [
          approval.arguments["url"].text, approval.arguments["selector"].text,
          approval.arguments["action"].text,
        ].first { !$0.isEmpty } ?? ""
        : approval.tool == "computer"
          ? approval.arguments["action"].text
          : approval.arguments["operation"].text
    return String(value.prefix(180))
  }
  private var scopeDescription: String {
    switch scope {
    case "run": return "仅限相同操作，直到本轮任务结束"
    case "exact_rule": return "仅限相同操作，以后自动允许，可在设置中撤销"
    default: return ""
    }
  }
  private func metadata(_ now: Date) -> [String] {
    [
      approval.target.label,
      expiryLabel(approval.expires - now.timeIntervalSince1970),
    ].compactMap { $0 }.filter { !$0.isEmpty }
  }
  private func metadataText(_ now: Date) -> some View {
    Text(metadata(now).joined(separator: " · "))
      .font(.caption)
      .foregroundStyle(.secondary)
      .fixedSize(horizontal: false, vertical: true)
  }
  private var detailsButton: some View {
    Button {
      withAnimation(reduceMotion ? nil : .easeOut(duration: 0.16)) {
        detailsExpanded.toggle()
      }
    } label: {
      HStack(spacing: 3) {
        Text("详情")
        Image(systemName: "chevron.down")
          .font(.system(size: 9, weight: .semibold))
          .rotationEffect(.degrees(detailsExpanded ? 180 : 0))
      }
      .font(.caption)
      .foregroundStyle(.secondary)
      .frame(minHeight: 44)
      .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
    .accessibilityLabel(detailsExpanded ? "收起操作详情" : "展开操作详情")
  }
  @ViewBuilder private var scopeMenu: some View {
    if options.count > 1 {
      Menu {
        ForEach(options, id: \.self) { option in
          Button(scopeLabel(option)) { scope = option }
        }
      } label: {
        HStack(spacing: 4) {
          Text(scopeLabel(scope)).foregroundStyle(.secondary)
          Image(systemName: "chevron.down")
            .font(.caption2.weight(.semibold))
            .foregroundStyle(.secondary)
        }
        .font(.footnote.weight(.medium))
        .frame(minHeight: 44)
      }
      .tint(.secondary)
      .disabled(pending)
    }
  }
  private var decisionButtons: some View {
    HStack(spacing: 8) {
      Spacer(minLength: 0)
      Button("拒绝") {
        submit(false)
      }
      .buttonStyle(.borderless)
      .foregroundStyle(.secondary)
      .frame(minHeight: 44)
      Button {
        submit(true)
      } label: {
        Text(approval.tier == "critical" ? "仅允许一次" : "允许")
          .foregroundStyle(Brand.surface)
      }
      .buttonStyle(.borderedProminent)
      .tint(Brand.ink)
      .frame(minHeight: 44)
    }
  }
  private func submit(_ approved: Bool) {
    guard !hidden else { return }
    error = ""
    receipt = approved ? "已允许" : "已拒绝"
    withAnimation(reduceMotion ? nil : .easeOut(duration: 0.16)) {
      hidden = true
    }
    Task {
      do {
        let result = try await onDecision(approved, scope)
        receipt = result
        do { try await Task.sleep(for: .seconds(1.8)) } catch { return }
        withAnimation(reduceMotion ? nil : .easeOut(duration: 0.16)) {
          receipt = ""
        }
      } catch {
        receipt = ""
        self.error = error.localizedDescription
        withAnimation(reduceMotion ? nil : .easeOut(duration: 0.16)) {
          hidden = false
        }
      }
    }
  }
  private func expiryLabel(_ seconds: TimeInterval) -> String {
    let value = max(0, Int(ceil(seconds)))
    return value < 60 ? "\(value) 秒后失效" : "\(Int(ceil(Double(value) / 60))) 分钟后失效"
  }
  private func scopeLabel(_ value: String) -> String {
    ["once": "仅这次", "run": "此任务期间", "exact_rule": "始终允许"][value] ?? value
  }
}

#if DEBUG
struct ApprovalPreviewScreen: View {
  private let approval = Approval(
    id: "approval-preview",
    tool: "bash",
    arguments: .object([
      "command": .string("pnpm add -D vitest"),
      "description": .string("安装测试依赖"),
    ]),
    status: "pending",
    expires: Date().addingTimeInterval(300).timeIntervalSince1970,
    title: "安装测试依赖",
    summary: "为当前项目添加此开发依赖。",
    risk: "high",
    tier: "write",
    effects: ["execute", "local_access"],
    target: ApprovalTarget(kind: "device", id: "mac-mini", label: "Mac mini"),
    scopeOptions: ["once", "run", "exact_rule"],
    actionDigest: String(repeating: "0", count: 64),
    decidedAt: nil,
    decidedBy: "",
    decisionChannel: "",
    reason: ""
  )

  var body: some View {
    NavigationStack {
      ScrollView {
        VStack(alignment: .leading, spacing: 14) {
          Text("我已检查项目结构，准备运行测试。")
            .font(.body)
          ApprovalCardView(
            approval: approval,
            connected: true,
            pending: false,
            onDecision: { approved, _ in
              approved ? "已允许" : "已拒绝"
            }
          )
        }
        .padding(20)
      }
      .background(Color(uiColor: .systemBackground))
      .navigationTitle("对话")
      .navigationBarTitleDisplayMode(.inline)
    }
  }
}
#endif

private struct CameraCapture: UIViewControllerRepresentable {
  let completion: (UIImage?) -> Void
  func makeCoordinator() -> Coordinator { Coordinator(completion) }
  func makeUIViewController(context: Context) -> UIImagePickerController {
    let picker = UIImagePickerController()
    picker.sourceType = .camera
    picker.delegate = context.coordinator
    return picker
  }
  func updateUIViewController(_ uiViewController: UIImagePickerController, context: Context) {}
  final class Coordinator: NSObject, UINavigationControllerDelegate, UIImagePickerControllerDelegate
  {
    let completion: (UIImage?) -> Void
    init(_ completion: @escaping (UIImage?) -> Void) { self.completion = completion }
    func imagePickerController(
      _ picker: UIImagePickerController,
      didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]
    ) { completion(info[.originalImage] as? UIImage) }
    func imagePickerControllerDidCancel(_ picker: UIImagePickerController) { completion(nil) }
  }
}

private struct PhotoLibraryPickerModifier: ViewModifier {
  @Binding var isPresented: Bool
  @Binding var selection: [PhotosPickerItem]
  let maxSelectionCount: Int

  func body(content: Content) -> some View {
    content.photosPicker(
      isPresented: $isPresented,
      selection: $selection,
      maxSelectionCount: maxSelectionCount,
      matching: .images
    )
  }
}

private struct ComposerAttachment: View {
  let file: JSON
  @ObservedObject var account: AccountService
  let disabled: Bool
  let remove: () -> Void
  @State private var image: UIImage?
  private var isImage: Bool { file["mime"].text.hasPrefix("image/") }
  var body: some View {
    HStack(spacing: 10) {
      Group {
        if let image {
          Image(uiImage: image).resizable().scaledToFill()
        } else {
          Image(
            systemName: isImage
              ? "photo" : file["mime"].text.hasPrefix("audio/") ? "waveform" : "doc.text"
          )
          .font(.system(size: 20, weight: .light)).foregroundStyle(Brand.muted)
        }
      }.frame(width: 48, height: 48).background(Brand.mist).clipShape(
        RoundedRectangle(cornerRadius: 9))
      if !isImage {
        VStack(alignment: .leading, spacing: 5) {
          Text(file["name"].text).font(.caption.weight(.medium)).lineLimit(1)
          Text(ByteCountFormatter.string(fromByteCount: Int64(file["size"].int), countStyle: .file))
            .font(.caption2).foregroundStyle(.secondary)
        }.frame(width: 104, alignment: .leading).padding(.trailing, 12)
      }
    }.padding(8)
      .background(Brand.surface, in: RoundedRectangle(cornerRadius: 14))
      .overlay {
        RoundedRectangle(cornerRadius: 14).strokeBorder(Brand.muted.opacity(0.16), lineWidth: 0.5)
      }
      .overlay(alignment: .topTrailing) {
        Button(action: remove) {
          Image(systemName: "xmark").font(.system(size: 8, weight: .bold))
            .foregroundStyle(Brand.ink).frame(width: 20, height: 20)
            .background(Brand.surface, in: Circle())
            .overlay { Circle().strokeBorder(Brand.muted.opacity(0.15), lineWidth: 0.5) }
            .frame(width: 44, height: 44)
        }.buttonStyle(.plain).disabled(disabled).accessibilityLabel("移除 " + file["name"].text)
      }
      .task(id: file["attachment_id"].text) {
        guard isImage else { return }
        if let data = try? await account.image(file["url"].text),
          let decoded = await Task.detached(
            priority: .userInitiated,
            operation: {
              ImagePipeline.display(data, maxPixel: 480)
            }
          ).value
        {
          image = decoded
        }
      }
  }
}

private struct CompactionNotice: View {
  let events: [Event]
  var body: some View {
    TimelineView(.periodic(from: .now, by: 2)) { timeline in
      if Self.active(in: events, at: timeline.date) != nil {
        HStack(spacing: 8) {
          ProgressView().controlSize(.mini)
          Text("我整理一下前面的内容，马上继续").font(.caption)
          Spacer(minLength: 0)
        }
        .foregroundStyle(.secondary)
        .frame(minHeight: 36)
        .padding(.horizontal, 8)
        .accessibilityIdentifier("chat.compaction")
      }
    }
  }

  static func active(in events: [Event], at now: Date) -> Event? {
    var finished = Set<String>()
    for event in events.reversed() where event.event_type == "context.compaction" {
      let payload = event.payload
      let status = payload["status"].text
      let compression = payload["compression_id"].text
      if ["ready", "applied", "failed", "skipped"].contains(status), !compression.isEmpty {
        finished.insert(compression)
        continue
      }
      guard status == "started", payload["mode"].text == "sync" else { continue }
      if !compression.isEmpty && finished.contains(compression) { continue }
      guard
        let at = ISO8601DateFormatter().date(
          from: event.occur_dt.replacingOccurrences(
            of: #"\.\d+(?=Z|[+-]\d\d:\d\d$)"#, with: "", options: .regularExpression)),
        now.timeIntervalSince(at) >= 0,
        now.timeIntervalSince(at) <= 300
      else { continue }
      return event
    }
    return nil
  }
}
