import MarkdownUI
import SwiftUI

private struct WorkProcessTextKey: EnvironmentKey {
  static let defaultValue = false
}
extension EnvironmentValues {
  var workProcessText: Bool {
    get { self[WorkProcessTextKey.self] }
    set { self[WorkProcessTextKey.self] = newValue }
  }
}

struct MessageContent: View {
  let content: String
  @ObservedObject var account: AccountService
  var expands = true
  @Environment(\.workProcessText) private var workProcessText
  @State private var sharedFile: SharedAttachment?
  @State private var attachmentError = ""

  var body: some View {
    Markdown(content.trimmingCharacters(in: .whitespacesAndNewlines), baseURL: account.backend)
      .markdownTheme(
        Theme.hymio.text {
          FontSize(workProcessText ? 15 : 17)
          ForegroundColor(workProcessText ? Brand.muted : Brand.ink)
        }
      )
      .markdownImageProvider(ConversationImages(account: account))
      .markdownInlineImageProvider(ConversationInlineImages(account: account))
      .textSelection(.enabled)
      .tint(Brand.blue)
      .environment(
        \.openURL,
        OpenURLAction { url in
          if url.path.range(of: "^/attachments/[a-f0-9]{32}$", options: .regularExpression) != nil {
            Task {
              do {
                let target = try await account.downloadAttachment(url.path)
                sharedFile = SharedAttachment(url: target)
              } catch { attachmentError = "文件暂时无法打开，请重试。" }
            }
            return .handled
          }
          return ["https", "http", "mailto"].contains(url.scheme?.lowercased() ?? "")
            ? .systemAction : .discarded
        }
      )
      .frame(maxWidth: expands ? .infinity : nil, alignment: .leading)
      .sheet(item: $sharedFile) { file in
        AttachmentShare(url: file.url).onDisappear {
          try? FileManager.default.removeItem(at: file.url.deletingLastPathComponent())
        }
      }
      .alert(
        "文件暂不可用",
        isPresented: Binding(
          get: { !attachmentError.isEmpty }, set: { if !$0 { attachmentError = "" } })
      ) {
        Button("关闭", role: .cancel) { attachmentError = "" }
      } message: {
        Text(attachmentError)
      }
  }
}

private struct ConversationImages: ImageProvider {
  let account: AccountService
  @ViewBuilder func makeImage(url: URL?) -> some View {
    if let url, !url.path.isEmpty, url.path != "/" {
      ProtectedImage(source: url.absoluteString, account: account)
    }
  }
}

private struct ConversationInlineImages: InlineImageProvider {
  let account: AccountService
  func image(with url: URL, label: String) async throws -> Image {
    let data = try await account.image(url.absoluteString)
    guard let image = UIImage(data: data) else { throw ServiceError.message("图片格式无效") }
    return Image(uiImage: image)
  }
}

extension Theme {
  fileprivate static let hymio = Theme.gitHub
    .text {
      ForegroundColor(Brand.ink)
      FontSize(17)
    }
    .link { ForegroundColor(Brand.blue) }
    .heading1 { configuration in
      configuration.label.markdownTextStyle {
        FontWeight(.semibold)
        FontSize(.em(1.4))
      }
      .markdownMargin(top: 12, bottom: 8)
    }
    .heading2 { configuration in
      configuration.label.markdownTextStyle {
        FontWeight(.semibold)
        FontSize(.em(1.2))
      }
      .markdownMargin(top: 10, bottom: 6)
    }
    .heading3 { configuration in
      configuration.label.markdownTextStyle {
        FontWeight(.semibold)
        FontSize(.em(1.05))
      }
      .markdownMargin(top: 8, bottom: 6)
    }
    .codeBlock { configuration in
      VStack(alignment: .leading, spacing: 10) {
        HStack {
          Text(configuration.language ?? "代码").font(.caption).foregroundStyle(.secondary)
          Spacer()
          Button {
            UIPasteboard.general.string = configuration.content
          } label: {
            Label("复制", systemImage: "doc.on.doc").font(.caption)
          }.accessibilityLabel("复制代码")
        }
        ScrollView(.horizontal) {
          configuration.label
            .markdownTextStyle {
              FontFamilyVariant(.monospaced)
              FontSize(14)
            }
            .fixedSize(horizontal: true, vertical: false)
        }
      }.padding(14).background(Brand.mist, in: RoundedRectangle(cornerRadius: 14))
        .markdownMargin(top: 6, bottom: 12)
    }
    .blockquote { configuration in
      configuration.label
        .padding(.leading, 14)
        .overlay(alignment: .leading) {
          RoundedRectangle(cornerRadius: 2).fill(Brand.blue.opacity(0.4)).frame(width: 3)
        }
        .markdownMargin(top: 4, bottom: 10)
    }
    .table { configuration in
      ScrollView(.horizontal) { configuration.label.fixedSize(horizontal: true, vertical: false) }
        .markdownMargin(top: 6, bottom: 12)
    }
}

private struct SharedAttachment: Identifiable {
  let id = UUID()
  let url: URL
}
private struct AttachmentShare: UIViewControllerRepresentable {
  let url: URL
  func makeUIViewController(context: Context) -> UIActivityViewController {
    UIActivityViewController(activityItems: [url], applicationActivities: nil)
  }
  func updateUIViewController(_ controller: UIActivityViewController, context: Context) {}
}
