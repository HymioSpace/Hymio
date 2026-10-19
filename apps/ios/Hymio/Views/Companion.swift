import SwiftUI

struct Companion: View {
  var size: CGFloat = 36
  var animated = false
  @Environment(\.accessibilityReduceMotion) private var reduceMotion
  @Environment(\.scenePhase) private var scene
  private var moving: Bool { animated && !reduceMotion && scene == .active }

  var body: some View {
    TimelineView(.animation(minimumInterval: 1.0 / 24, paused: !moving)) { timeline in
      let time = moving ? timeline.date.timeIntervalSinceReferenceDate : 0
      Canvas { context, dimensions in
        let scale = dimensions.width / 60
        let cycle = time.truncatingRemainder(dividingBy: 6)
        let blink = moving && cycle > 5.65 && cycle < 5.82
        context.scaleBy(x: scale, y: scale)
        context.translateBy(x: 0, y: moving ? sin(time * 1.7) * 0.9 : 0)
        var outline = Path()
        outline.move(to: CGPoint(x: 16, y: 43))
        outline.addLine(to: CGPoint(x: 16, y: 25))
        outline.addCurve(
          to: CGPoint(x: 44, y: 25), control1: CGPoint(x: 16, y: 7), control2: CGPoint(x: 44, y: 7))
        outline.addLine(to: CGPoint(x: 44, y: 43))
        outline.addQuadCurve(to: CGPoint(x: 38, y: 49), control: CGPoint(x: 44, y: 49))
        outline.addLine(to: CGPoint(x: 22, y: 49))
        outline.addQuadCurve(to: CGPoint(x: 16, y: 43), control: CGPoint(x: 16, y: 49))
        context.fill(outline, with: .color(Brand.companionFill))
        context.stroke(
          outline, with: .color(Brand.ink), style: StrokeStyle(lineWidth: 1.3, lineCap: .round))
        var band = Path()
        band.move(to: CGPoint(x: 18, y: 42))
        band.addLine(to: CGPoint(x: 42, y: 47))
        context.stroke(
          band, with: .color(Brand.band), style: StrokeStyle(lineWidth: 3.2, lineCap: .round))
        for x in [25.0, 35.0] {
          context.fill(
            Path(ellipseIn: CGRect(x: x, y: blink ? 29 : 28, width: 2.4, height: blink ? 0.8 : 3)),
            with: .color(Brand.ink))
        }
        var details = Path()
        details.move(to: CGPoint(x: 27, y: 36))
        details.addQuadCurve(to: CGPoint(x: 34, y: 36), control: CGPoint(x: 30, y: 38.5))
        details.move(to: CGPoint(x: 16, y: 36))
        details.addQuadCurve(to: CGPoint(x: 9, y: 30), control: CGPoint(x: 7, y: 41))
        details.move(to: CGPoint(x: 44, y: 36))
        let hand = moving && cycle < 1.5 ? 37 + sin(time * 8) * 3 : 42
        details.addQuadCurve(to: CGPoint(x: 50, y: hand), control: CGPoint(x: 51, y: 35))
        details.move(to: CGPoint(x: 23, y: 50))
        details.addLine(to: CGPoint(x: 21, y: 53))
        details.move(to: CGPoint(x: 37, y: 50))
        details.addLine(to: CGPoint(x: 39, y: 53))
        context.stroke(
          details, with: .color(Brand.ink), style: StrokeStyle(lineWidth: 1.3, lineCap: .round))
      }
    }
    .frame(width: size, height: size)
    .accessibilityHidden(true)
  }
}
