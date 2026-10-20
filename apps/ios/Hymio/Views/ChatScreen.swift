import PhotosUI
import SwiftUI
import UIKit
import UniformTypeIdentifiers

struct ChatScreen: View {
  @ObservedObject var account: AccountService
  @ObservedObject var client: AgentClient
  @State private var draft = ""
  @State private var attachments: [JSON] = []
  @State private var selectedPhotos: [PhotosPickerItem] = []
  @State private var uploading = false
  @State private var filesOpen = false
  @State private var cameraOpen = false
  @State private var profile = false
  @State private var tracePage = false
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
              MessageRow(
                message: message, tools: client.model.terminals, approvals: client.model.approvals,
                onAction: {
                  try await client.message($0)
                }, account: account
              ).id(message.id)

            }
            ForEach(client.model.approvals.filter { $0.status == "pending" }) { approval in
              ApprovalCard(approval: approval, client: client)
            }
            if (client.model.working || client.model.awaitingReply)
              && !client.model.messages.contains(where: \.streaming)
            {
              HStack(spacing: 10) {
                ProgressView().controlSize(.small)
                Text(client.model.awaitingReply ? "正在等候回复…" : "正在继续处理…").font(.caption)
                  .foregroundStyle(.secondary)
              }.accessibilityIdentifier("chat.working")
            }
            if !client.model.failure.isEmpty {
              Label(client.model.failure, systemImage: "exclamationmark.circle").font(.footnote)
                .foregroundStyle(.secondary)
            }
            if !client.model.pauseNotice.isEmpty {
              Label(client.model.pauseNotice, systemImage: "pause.circle")
                .font(.footnote).foregroundStyle(.secondary)
            }
            Color.clear.frame(height: 1).id("bottom").onAppear { atBottom = true }.onDisappear {
              atBottom = false
            }
          }.padding(.horizontal, 20).padding(.top, 22).padding(.bottom, 20)
            .animation(
              reduceMotion ? nil : .spring(duration: 0.32, bounce: 0.08),
              value: client.model.messages.count)
        }
        .contentShape(Rectangle())
        .simultaneousGesture(TapGesture().onEnded { typing = false })
        .scrollDismissesKeyboard(.interactively)
        .defaultScrollAnchor(.bottom)
        .onChange(of: client.model.messages.count) { _, _ in
          if client.model.messages.last?.role == "assistant" && typing { typing = false }
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
      .navigationDestination(isPresented: $tracePage) {
        TraceScreen(account: account, client: client)
      }
      .toolbar {
        ToolbarItem(placement: .topBarLeading) {
          Button {
            typing = false
            tracePage = true
          } label: {
            Image(systemName: "waveform.path.ecg").font(.body)
          }
          .accessibilityLabel("工作观察")
        }
        ToolbarItem(placement: .principal) {
          VStack(spacing: 2) {
            Text("hymio").font(.system(.headline, design: .rounded)).tracking(-0.5)
            HStack(spacing: 5) {
              if client.connected
                && (client.model.working || client.model.awaitingReply
                  || client.model.messages.contains(where: \.streaming))
              {
                Companion(size: 24, animated: true, mood: .working)
              }
              ConnectionStatus(
                text: client.connected && (client.model.working || client.model.awaitingReply)
                  ? "正在处理" : client.phase, connected: client.connected)
            }
          }.accessibilityElement(children: .combine)
        }
        ToolbarItem(placement: .topBarTrailing) {
          Button {
            typing = false
            profile = true
          } label: {
            Image(systemName: "ellipsis").font(.body).frame(width: 30, height: 30).contentShape(
              Rectangle())
          }.buttonStyle(.plain).accessibilityLabel("我的账号")
            .matchedTransitionSource(id: "account", in: transitions)
        }
      }
      .onChange(of: selectedPhotos) { _, photos in
        guard !photos.isEmpty else { return }
        uploading = true
        Task {
          defer {
            uploading = false
            selectedPhotos = []
          }
          do {
            for photo in photos {
              if let data = try await photo.loadTransferable(type: Data.self) {
                guard let image = UIImage(data: data),
                  let jpeg = image.jpegData(compressionQuality: 0.9)
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
            guard urls.count + attachments.count <= 8 else {
              throw ServiceError.message("每条消息最多添加 8 个附件")
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
          uploading = true
          Task {
            defer { uploading = false }
            do {
              guard let data = image.jpegData(compressionQuality: 0.9) else { return }
              let value = try await account.upload(data, name: "camera.jpg")
              attachments.append(value)
            } catch { client.error = error.localizedDescription }
          }
        }.ignoresSafeArea()
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
        HStack(alignment: .bottom, spacing: 8) {
          Menu {
            PhotosPicker(
              selection: $selectedPhotos, maxSelectionCount: max(1, 8 - attachments.count),
              matching: .images
            ) {
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
            PasteButton(supportedContentTypes: [.image]) { providers in pasteImages(providers) }
          } label: {
            Image(systemName: "plus").font(.system(size: 19, weight: .regular)).foregroundStyle(
              Brand.muted
            ).frame(width: 44, height: 44)
          }.disabled(uploading || attachments.count >= 8).accessibilityLabel("添加附件")
          TextField("接着说，我在听…", text: $draft, axis: .vertical)
            .lineLimit(1...6).padding(.vertical, 9).focused($typing).accessibilityIdentifier(
              "chat.input")
          Button {
            send()
          } label: {
            Image(systemName: "arrow.up").font(.system(size: 16, weight: .semibold))
              .foregroundStyle(
                Brand.onAccent
              ).symbolEffect(.bounce, value: reduceMotion ? 0 : sentCount)
              .frame(width: 36, height: 36).background(
                canSend ? Brand.blue : Color.secondary.opacity(0.18), in: Circle()
              )
              .frame(width: 44, height: 44)
          }.buttonStyle(GentlePress()).disabled(!canSend).accessibilityLabel("发送消息")
            .accessibilityIdentifier("chat.send")
        }
      }
      .padding(8)
      .modifier(ComposerSurface())
    }.padding(.horizontal, 16).padding(.top, 9).padding(.bottom, 8)
  }
  private func pasteImages(_ providers: [NSItemProvider]) {
    let images = providers.filter { $0.canLoadObject(ofClass: UIImage.self) }
    guard !images.isEmpty else { return }
    guard !uploading else {
      client.error = "附件正在上传，完成后可继续粘贴。"
      return
    }
    guard images.count + attachments.count <= 8 else {
      client.error = "每条消息最多添加 8 个附件"
      return
    }
    uploading = true
    Task {
      defer { uploading = false }
      do {
        for provider in images {
          let image: UIImage = try await withCheckedThrowingContinuation { continuation in
            _ = provider.loadObject(ofClass: UIImage.self) { object, error in
              if let error {
                continuation.resume(throwing: error)
              } else if let image = object as? UIImage {
                continuation.resume(returning: image)
              } else {
                continuation.resume(throwing: ServiceError.message("无法读取剪贴板图片"))
              }
            }
          }
          guard let data = image.jpegData(compressionQuality: 0.9) else {
            throw ServiceError.message("无法读取剪贴板图片")
          }
          let value = try await account.upload(data, name: "screenshot.jpg")
          attachments.append(value)
        }
      } catch { client.error = error.localizedDescription }
    }
  }
  private var canSend: Bool {
    client.connected && !sendBusy && !uploading
      && (!draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !attachments.isEmpty)
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
        if let data = try? await account.image(file["url"].text) { image = UIImage(data: data) }
      }
  }
}
