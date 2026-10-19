import SwiftUI

enum CompanionMood: Int {
  case idle = 0, working, replying, waiting, offline, greeting
}

struct Companion: View {
  var size: CGFloat = 36
  var animated = false
  var mood: CompanionMood = .idle
  @Environment(\.accessibilityReduceMotion) private var reduceMotion
  @Environment(\.scenePhase) private var scene
  @State private var greeting = false
  private var moving: Bool { animated && !reduceMotion && scene == .active && mood != .offline }
  private var pose: Int { greeting ? CompanionMood.greeting.rawValue : mood.rawValue }

  var body: some View {
    TimelineView(.animation(minimumInterval: 1.0 / 24, paused: !moving)) { timeline in
      let time = moving ? timeline.date.timeIntervalSinceReferenceDate : 0
      let cell = size
      Image("CompanionAtlas")
        .resizable().interpolation(.high)
        .frame(width: cell * 3, height: cell * 2)
        .offset(x: -CGFloat(pose % 3) * cell,
                y: -CGFloat(pose / 3) * cell)
        .frame(width: size, height: size, alignment: .topLeading).clipped()
        .offset(y: moving ? sin(time * 1.3) * 1.5 : 0)
    }.frame(width: size, height: size)
      .onTapGesture { if animated { greeting = true } }
      .task(id: greeting) {
        guard greeting else { return }
        try? await Task.sleep(for: .milliseconds(1200)); greeting = false
      }.accessibilityHidden(true)
  }
}
