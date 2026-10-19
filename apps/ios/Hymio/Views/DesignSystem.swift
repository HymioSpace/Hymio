import SwiftUI

enum Brand {
  static let ink = adaptive(0x172033, dark: 0xEFF2FA)
  static let blue = adaptive(0x425DE8, dark: 0x9AABFF)
  static let muted = adaptive(0x606A7A, dark: 0xA4ABBA)
  static let mist = adaptive(0xF4F5F9, dark: 0x1D202A)
  static let surface = Color(uiColor: .systemBackground)
  static let companionFill = adaptive(0xFFFFFF, dark: 0x272B38)
  static let userBubble = adaptive(0xF0F2FB, dark: 0x242B43)
  static let band = Color(red: 0.29, green: 0.42, blue: 0.98)

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
