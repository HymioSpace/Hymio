import SwiftUI

enum Brand {
  static let attention = adaptive(0x9A641E, dark: 0xF0C384)
  static let attentionSurface = adaptive(0xFFF5E7, dark: 0x392E21)
  static let ink = adaptive(0x202536, dark: 0xEFF1F7)
  static let blue = adaptive(0x425DE8, dark: 0xA2B0FF)
  static let muted = adaptive(0x626B7D, dark: 0xA7AFC1)
  static let mist = base
  static let canvas = adaptive(0xF0F2F4, dark: 0x0F1215)
  static let base = adaptive(0xF5F7F9, dark: 0x13161A)
  static let surface = adaptive(0xFAFCFE, dark: 0x181B1E)
  static let raised = adaptive(0xFEFFFF, dark: 0x1C2023)
  static let paper = adaptive(0xF8F6F0, dark: 0x26252A)
  static let paperLine = adaptive(0xEAE4D8, dark: 0x3C3940)
  static let notePaper = adaptive(0xFFF1CF, dark: 0x3A3121)
  static let noteLine = adaptive(0xA47B31, dark: 0xC6A35E)
  static let softBlue = adaptive(0xF2F5FF, dark: 0x242A3E)
  static let assistantBubble = adaptive(0xF0F3F8, dark: 0x222A35)
  static let userBubble = adaptive(0xEEF1FF, dark: 0x28314A)
  static let onAccent = adaptive(0xFFFFFF, dark: 0x18214A)
  static let line = adaptive(0xE6E8EF, dark: 0x353B4B)

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

struct ComposerSurface: ViewModifier {
  @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
  var focused = false
  func body(content: Content) -> some View {
    content
      .background {
        RoundedRectangle(cornerRadius: 28)
          .fill(reduceTransparency ? AnyShapeStyle(Brand.raised) : AnyShapeStyle(.regularMaterial))
      }
      .overlay { RoundedRectangle(cornerRadius: 28).strokeBorder(Brand.line.opacity(0.6), lineWidth: 0.5) }
      .shadow(color: Brand.blue.opacity(focused ? 0.16 : 0), radius: 3)
      .shadow(color: Brand.blue.opacity(focused ? 0.09 : 0), radius: 8)
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
      .background(Brand.blue, in: RoundedRectangle(cornerRadius: 14))
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

struct AccountButton: View {
  @ObservedObject var account: AccountService
  let action: () -> Void

  var body: some View {
    Button(action: action) {
      Companion(size: 31, mood: .greeting)
        .padding(5)
        .frame(width: 44, height: 44)
    }
    .buttonStyle(AccountAvatarStyle())
    .contentShape(Circle())
    .accessibilityLabel("账号与设置")
    .accessibilityHint("打开个人资料、设备和偏好设置")
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
