import SwiftUI

enum Brand {
  static let attention = adaptive(0x9A641E, dark: 0xF0C384)
  static let attentionSurface = adaptive(0xFFF5E7, dark: 0x392E21)
  static let ink = adaptive(0x202536, dark: 0xEFF1F7)
  static let blue = adaptive(0x425DE8, dark: 0xA2B0FF)
  static let muted = adaptive(0x626B7D, dark: 0xA7AFC1)
  static let mist = adaptive(0xF6F7FA, dark: 0x202530)
  static let surface = Color(uiColor: .systemBackground)
  static let paper = adaptive(0xF8F6F0, dark: 0x26252A)
  static let paperLine = adaptive(0xEAE4D8, dark: 0x3C3940)
  static let notePaper = adaptive(0xFFF1CF, dark: 0x3A3121)
  static let noteLine = adaptive(0xA47B31, dark: 0xC6A35E)
  static let softBlue = adaptive(0xF2F5FF, dark: 0x242A3E)
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
  @Environment(\.accessibilityReduceTransparency) private var opaque
  @Environment(\.colorSchemeContrast) private var contrast
  func body(content: Content) -> some View {
    if #available(iOS 26, *), !opaque, contrast != .increased {
      content.glassEffect(.regular, in: RoundedRectangle(cornerRadius: 28))
    } else {
      content.background(Brand.mist, in: RoundedRectangle(cornerRadius: 28))
        .overlay(RoundedRectangle(cornerRadius: 28).stroke(.secondary.opacity(0.2), lineWidth: 1))
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
        .background(Brand.softBlue, in: Circle())
        .overlay(Circle().stroke(Brand.blue.opacity(0.14), lineWidth: 1))
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
