import SwiftUI

enum Brand {
  static let primary = adaptive(0x425DE8, dark: 0xB8C3FF)
  static let onPrimary = adaptive(0xFFFFFF, dark: 0x06257B)
  static let primaryContainer = adaptive(0xDDE1FF, dark: 0x2947B9)
  static let onPrimaryContainer = adaptive(0x09185C, dark: 0xDDE1FF)
  static let secondary = adaptive(0x5B5D72, dark: 0xC4C5DD)
  static let secondaryContainer = adaptive(0xE0E1F9, dark: 0x434559)
  static let onSecondaryContainer = adaptive(0x181A2C, dark: 0xE0E1F9)
  static let tertiary = adaptive(0x76546D, dark: 0xE6BAD8)
  static let tertiaryContainer = adaptive(0xFFD7F3, dark: 0x5C3D55)
  static let onTertiaryContainer = adaptive(0x2C1229, dark: 0xFFD7F3)
  static let error = adaptive(0xBA1A1A, dark: 0xFFB4AB)
  static let onError = adaptive(0xFFFFFF, dark: 0x690005)
  static let errorContainer = adaptive(0xFFDAD6, dark: 0x93000A)

  static let surface = adaptive(0xF9F9FF, dark: 0x111318)
  static let surfaceDim = adaptive(0xDAD9E0, dark: 0x111318)
  static let surfaceBright = adaptive(0xF9F9FF, dark: 0x37393E)
  static let surfaceLowest = adaptive(0xFFFFFF, dark: 0x0C0E13)
  static let surfaceLow = adaptive(0xF3F3FA, dark: 0x191C20)
  static let surfaceContainer = adaptive(0xEDEDF4, dark: 0x1D2024)
  static let surfaceHigh = adaptive(0xE7E8EF, dark: 0x282A2F)
  static let surfaceHighest = adaptive(0xE1E2E9, dark: 0x33353A)
  static let ink = adaptive(0x1B1B21, dark: 0xE4E1E9)
  static let muted = adaptive(0x45464F, dark: 0xC6C5D0)
  static let outline = adaptive(0x757780, dark: 0x90909A)
  static let line = adaptive(0xC6C6D0, dark: 0x45464F)

  static let blue = primary
  static let onAccent = onPrimary
  static let canvas = surface
  static let base = surface
  static let raised = surfaceLow
  static let mist = surfaceContainer
  static let softBlue = primaryContainer
  static let assistantBubble = surfaceHigh
  static let userBubble = primaryContainer
  static let attention = adaptive(0x7A5900, dark: 0xF4C95D)
  static let attentionSurface = adaptive(0xFFF2CC, dark: 0x3E3210)
  static let paper = adaptive(0xFFF8F1, dark: 0x2D211D)
  static let paperLine = adaptive(0xE8D9CE, dark: 0x58443B)
  static let notePaper = adaptive(0xFFF2CB, dark: 0x3E3210)
  static let noteLine = adaptive(0x9A6B00, dark: 0xF4C95D)

  private static func adaptive(_ light: UInt32, dark: UInt32) -> Color {
    Color(
      uiColor: UIColor { traits in
        let hex = traits.userInterfaceStyle == .dark ? dark : light
        return UIColor(
          red: CGFloat((hex >> 16) & 255) / 255,
          green: CGFloat((hex >> 8) & 255) / 255,
          blue: CGFloat(hex & 255) / 255, alpha: 1)
      })
  }
}

enum MaterialShape {
  static let extraSmall: CGFloat = 8
  static let small: CGFloat = 12
  static let medium: CGFloat = 16
  static let large: CGFloat = 20
  static let extraLarge: CGFloat = 28
  static let full: CGFloat = 999
}

enum MaterialSpacing {
  static let xs: CGFloat = 4
  static let sm: CGFloat = 8
  static let md: CGFloat = 12
  static let lg: CGFloat = 16
  static let xl: CGFloat = 24
  static let xxl: CGFloat = 32
}

struct MaterialCardSurface: ViewModifier {
  var elevated = false
  func body(content: Content) -> some View {
    content
      .background(
        elevated ? Brand.surfaceLow : Brand.surfaceLow,
        in: RoundedRectangle(cornerRadius: MaterialShape.small)
      )
      .overlay(
        RoundedRectangle(cornerRadius: MaterialShape.small)
          .strokeBorder(Brand.line, lineWidth: 0.75)
      )
  }
}

extension View {
  func materialCard(elevated: Bool = false) -> some View {
    modifier(MaterialCardSurface(elevated: elevated))
  }
}

struct ComposerSurface: ViewModifier {
  @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
  var focused = false
  func body(content: Content) -> some View {
    content
      .background {
        RoundedRectangle(cornerRadius: MaterialShape.extraLarge)
          .fill(reduceTransparency ? AnyShapeStyle(Brand.surfaceHigh) : AnyShapeStyle(Brand.surfaceHigh.opacity(0.96)))
      }
      .overlay {
        RoundedRectangle(cornerRadius: MaterialShape.extraLarge)
          .strokeBorder(focused ? Brand.primary : Brand.line, lineWidth: focused ? 2 : 1)
      }
      .animation(.easeOut(duration: 0.12), value: focused)
  }
}

/// Available only for existing interactive surfaces; these constants do not create gestures.
enum InteractionSpring {
  static let drag = Animation.interpolatingSpring(mass: 1, stiffness: 1200, damping: 80)
  static let like = Animation.interpolatingSpring(mass: 1, stiffness: 380, damping: 18)
}

struct CopyFeedbackButton: View {
  let content: String
  @State private var copied = false
  @State private var generation = 0
  var body: some View {
    Button {
      UIPasteboard.general.string = content
      copied = true
      generation += 1
    } label: {
      Label(copied ? "已复制" : "复制", systemImage: copied ? "checkmark" : "doc.on.doc")
        .labelStyle(.iconOnly)
        .font(.system(size: 12, weight: .medium))
        .frame(width: 28, height: 28)
        .contentShape(Rectangle())
    }
    .accessibilityLabel(copied ? "已复制代码" : "复制代码")
    .task(id: generation) {
      guard generation > 0 else { return }
      do { try await Task.sleep(for: .milliseconds(2500)) } catch { return }
      copied = false
    }
  }
}

struct GentlePress: ButtonStyle {
  @Environment(\.accessibilityReduceMotion) private var reduceMotion
  func makeBody(configuration: Configuration) -> some View {
    configuration.label
      .opacity(configuration.isPressed ? 0.85 : 1)
      .scaleEffect(configuration.isPressed && !reduceMotion ? 0.97 : 1)
      .animation(
        reduceMotion ? nil : .spring(duration: 0.24, bounce: 0.15), value: configuration.isPressed)
  }
}

struct PrimaryAction: ButtonStyle {
  @Environment(\.isEnabled) private var enabled
  func makeBody(configuration: Configuration) -> some View {
    configuration.label
      .frame(maxWidth: .infinity, minHeight: 48)
      .foregroundStyle(Brand.onAccent)
      .background(Brand.blue, in: Capsule())
      .opacity(!enabled ? 0.45 : configuration.isPressed ? 0.85 : 1)
  }
}

struct ConnectionStatus: View {
  let text: String
  let connected: Bool
  var body: some View {
    HStack(spacing: 5) {
      Circle().fill(connected ? Brand.blue : Brand.muted).frame(width: 4, height: 4)
      Text(text).font(.caption2).foregroundStyle(Brand.muted)
    }.accessibilityElement(children: .combine)
  }
}

struct HymioNowMark: View {
  var size: CGFloat = 24

  var body: some View {
    ZStack {
      Circle()
        .fill(
          LinearGradient(
            colors: [Brand.blue.opacity(0.16), Brand.softBlue],
            startPoint: .topLeading, endPoint: .bottomTrailing))
      Circle()
        .trim(from: 0.08, to: 0.82)
        .stroke(Brand.blue.opacity(0.55), style: StrokeStyle(lineWidth: 1.2, lineCap: .round))
        .rotationEffect(.degrees(-90))
        .padding(2.5)
      Image(systemName: "sparkles")
        .font(.system(size: size * 0.42, weight: .semibold))
        .foregroundStyle(Brand.blue)
    }
    .frame(width: size, height: size)
    .accessibilityHidden(true)
  }
}

struct HymioProfileMark: View {
  let initial: String
  var size: CGFloat = 28

  var body: some View {
    ZStack {
      RoundedRectangle(cornerRadius: size * 0.33, style: .continuous)
        .fill(
          LinearGradient(
            colors: [Brand.ink, Brand.blue],
            startPoint: .topLeading, endPoint: .bottomTrailing))
      RoundedRectangle(cornerRadius: size * 0.22, style: .continuous)
        .stroke(Color.white.opacity(0.34), lineWidth: 0.7)
        .padding(size * 0.12)
      Text(initial)
        .font(.system(size: size * 0.42, weight: .bold, design: .rounded))
        .foregroundStyle(.white)
      Circle()
        .fill(Brand.noteLine)
        .frame(width: size * 0.18, height: size * 0.18)
        .overlay(Circle().stroke(Brand.raised, lineWidth: 1))
        .offset(x: size * 0.38, y: -size * 0.38)
    }
    .frame(width: size, height: size)
    .accessibilityHidden(true)
  }
}

struct AccountButton: View {
  @ObservedObject var account: AccountService
  let action: () -> Void

  var body: some View {
    Button(action: { Haptics.selection(); action() }) {
      HymioProfileMark(
        initial: {
          let name = account.session?.displayName.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
          return name.isEmpty ? "H" : String(name.prefix(1)).uppercased()
        }(),
        size: 31)
      .frame(width: 44, height: 44)
    }
    .buttonStyle(AccountAvatarStyle())
    .contentShape(Rectangle())
    .accessibilityLabel("我的")
    .accessibilityHint("打开任务、记忆、连接服务和设置")
  }
}

private struct AccountAvatarStyle: ButtonStyle {
  @Environment(\.accessibilityReduceMotion) private var reduceMotion

  func makeBody(configuration: Configuration) -> some View {
    configuration.label
      .scaleEffect(configuration.isPressed && !reduceMotion ? 0.94 : 1)
      .opacity(configuration.isPressed ? 0.8 : 1)
      .animation(
        reduceMotion ? nil : .easeOut(duration: 0.14),
        value: configuration.isPressed)
  }
}

extension ToolbarContent {
  @ToolbarContentBuilder func accountUnframed() -> some ToolbarContent {
    if #available(iOS 26.0, *) {
      self.sharedBackgroundVisibility(.hidden)
    } else {
      self
    }
  }
}

struct ToolOutcomeLabel: View {
  let outcome: String
  private var label: String {
    [
      "running": "执行中", "succeeded": "已完成", "failed": "失败", "denied": "已拒绝",
      "awaiting_approval": "等待授权", "expired": "授权已过期", "timeout": "超时",
      "timed_out": "超时", "outcome_unknown": "结果待确认",
    ][outcome] ?? outcome
  }
  var body: some View { Text(label).font(.caption).foregroundStyle(Brand.muted) }
}

@MainActor enum Haptics {
  static func selection() { UISelectionFeedbackGenerator().selectionChanged() }
  static func success() { UINotificationFeedbackGenerator().notificationOccurred(.success) }
}

struct AddActionButton: View {
  let title: String
  let action: () -> Void
  var body: some View {
    Button { Haptics.selection(); action() } label: {
      Image(systemName: "plus").font(.system(size: 17, weight: .regular))
        .frame(width: 36, height: 36).foregroundStyle(Brand.ink)
        .background(.regularMaterial, in: Circle())
        .overlay(Circle().strokeBorder(Brand.line, lineWidth: 0.7))
        .frame(width: 44, height: 44)
        .contentShape(Rectangle())
    }.buttonStyle(.plain).accessibilityLabel(title)
  }
}

/// One locally bundled artwork atlas; no remote image fetches during navigation.
struct FeatureArtwork: View {
  enum Kind { case notebook, health, calendar, mail, chat, archive
    // Optical centers in the source artwork; its six subjects are not on a uniform grid.
    var center: CGPoint {
      switch self {
      case .notebook: CGPoint(x: 317, y: 310)
      case .health: CGPoint(x: 770, y: 315)
      case .calendar: CGPoint(x: 1230, y: 310)
      case .mail: CGPoint(x: 318, y: 715)
      case .chat: CGPoint(x: 780, y: 715)
      case .archive: CGPoint(x: 1225, y: 715)
      }
    }
  }
  let kind: Kind
  var size: CGFloat = 72
  var body: some View {
    let center = kind.center
    let scale = size / 480
    Image("FeatureArtwork").resizable()
      .frame(width: 1536 * scale, height: 1024 * scale)
      .offset(x: -(center.x - 240) * scale, y: -(center.y - 240) * scale)
      .frame(width: size, height: size, alignment: .topLeading)
      .clipped().clipShape(RoundedRectangle(cornerRadius: size * 0.24))
      .accessibilityHidden(true)
  }
}

/// Measure both columns first, then give each the same row height.
struct EqualHeightColumns: Layout {
  var spacing: CGFloat = 12
  func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
    let gaps = spacing * CGFloat(max(0, subviews.count - 1))
    let width = proposal.width ?? subviews.reduce(gaps) { $0 + $1.sizeThatFits(.unspecified).width }
    let column = max(0, width - gaps) / CGFloat(max(1, subviews.count))
    let height = subviews.map { $0.sizeThatFits(ProposedViewSize(width: column, height: nil)).height }.max() ?? 0
    return CGSize(width: width, height: height)
  }
  func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
    let column = max(0, bounds.width - spacing * CGFloat(max(0, subviews.count - 1))) / CGFloat(max(1, subviews.count))
    for (index, view) in subviews.enumerated() {
      view.place(at: CGPoint(x: bounds.minX + CGFloat(index) * (column + spacing), y: bounds.minY),
        anchor: .topLeading, proposal: ProposedViewSize(width: column, height: bounds.height))
    }
  }
}

#if DEBUG
struct ArtworkAlignmentPreview: View {
  private let kinds: [(FeatureArtwork.Kind, String)] = [(.notebook, "Notebook"), (.health, "Health"),
    (.calendar, "Calendar"), (.mail, "Mail"), (.chat, "Chat"), (.archive, "Archive")]
  var body: some View {
    NavigationStack {
      LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 28) {
        ForEach(kinds.indices, id: \.self) { index in
          VStack(spacing: 8) {
            FeatureArtwork(kind: kinds[index].0, size: 112)
              .overlay(RoundedRectangle(cornerRadius: 22).stroke(Brand.line))
            Text(kinds[index].1).font(.caption)
          }
        }
      }.padding(24).navigationTitle("Artwork alignment")
    }
  }
}
#endif
