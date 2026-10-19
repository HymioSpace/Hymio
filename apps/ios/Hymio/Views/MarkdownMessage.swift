import MarkdownUI
import SwiftUI

struct MessageContent: View {
  let content: String
  @ObservedObject var account: AccountService

  var body: some View {
    Markdown(content.trimmingCharacters(in: .whitespacesAndNewlines), baseURL: account.backend)
      .markdownTheme(.hymio)
      .markdownImageProvider(ConversationImages(account: account))
      .markdownInlineImageProvider(ConversationInlineImages(account: account))
      .textSelection(.enabled)
      .tint(Brand.blue)
      .environment(
        \.openURL,
        OpenURLAction { url in
          ["https", "http", "mailto"].contains(url.scheme?.lowercased() ?? "")
            ? .systemAction : .discarded
        }
      )
      .frame(maxWidth: .infinity, alignment: .leading)
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
