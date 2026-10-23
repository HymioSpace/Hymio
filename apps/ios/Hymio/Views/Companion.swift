import SwiftUI

enum CompanionMood: Int {
  case idle = 0
  case working, replying, waiting, offline, greeting
}

struct Companion: View {
  var size: CGFloat = 36
  var mood: CompanionMood = .idle
  private var pose: Int { mood.rawValue }

  var body: some View {
    let cell = size
    Image("CompanionAtlas")
      .resizable().interpolation(.high)
      .frame(width: cell * 3, height: cell * 2)
      .offset(
        x: -CGFloat(pose % 3) * cell,
        y: -CGFloat(pose / 3) * cell
      )
      .frame(width: size, height: size, alignment: .topLeading).clipped()
      .frame(width: size, height: size)
      .accessibilityHidden(true)
  }
}
