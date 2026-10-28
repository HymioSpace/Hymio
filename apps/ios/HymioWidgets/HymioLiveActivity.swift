import ActivityKit
import SwiftUI
import WidgetKit

struct HymioLiveActivity: Widget {
  var body: some WidgetConfiguration {
    ActivityConfiguration(for: HymioActivityAttributes.self) { context in
      HymioLockScreenActivity(state: context.state)
        .activityBackgroundTint(Color(red: 0.055, green: 0.09, blue: 0.20))
        .activitySystemActionForegroundColor(.white)
    } dynamicIsland: { context in
      DynamicIsland {
        DynamicIslandExpandedRegion(.leading) {
          ScarfMark(size: 35)
            .padding(.leading, 4)
        }
        DynamicIslandExpandedRegion(.center) {
          VStack(alignment: .leading, spacing: 3) {
            Text(context.state.title)
              .font(.headline.weight(.semibold))
              .lineLimit(1)
            Text(context.state.phase)
              .font(.caption)
              .foregroundStyle(.secondary)
              .lineLimit(1)
          }
        }
        DynamicIslandExpandedRegion(.trailing) {
          VStack(alignment: .trailing, spacing: 4) {
            StatusGlyph(status: context.state.status)
            ActivityClock(startedAt: context.state.startedAt)
              .font(.caption2.monospacedDigit().weight(.medium))
              .foregroundStyle(.secondary)
          }
        }
        DynamicIslandExpandedRegion(.bottom) {
          HStack(spacing: 8) {
            Image(systemName: "sparkles")
            Text(activityLine(context.state))
              .lineLimit(1)
            Spacer()
            Text("打开")
              .fontWeight(.semibold)
            Image(systemName: "arrow.up.right")
          }
          .font(.caption)
          .foregroundStyle(Color(red: 0.68, green: 0.76, blue: 1))
          .padding(.horizontal, 6)
          .padding(.top, 4)
        }
      } compactLeading: {
        CompactMark(state: context.state)
      } compactTrailing: {
        CompactTrailing(state: context.state)
      } minimal: {
        MinimalState(state: context.state)
      }
      .keylineTint(Color(red: 0.26, green: 0.36, blue: 0.91))
      .widgetURL(deepLink(context.state))
    }
  }

  private func activityLine(_ state: HymioActivityAttributes.ContentState) -> String {
    switch state.status {
    case "waiting": return "有一处需要你确认"
    case "completed": return "这项工作已经完成"
    case "failed": return "工作遇到了问题"
    default:
      return state.activeCount > 1 ? "\(state.activeCount) 项工作正在推进" : "正在替你推进"
    }
  }

  private func deepLink(_ state: HymioActivityAttributes.ContentState) -> URL? {
    state.taskID.isEmpty
      ? URL(string: "hymio://chat")
      : URL(string: "hymio://task/" + state.taskID)
  }
}

private struct HymioLockScreenActivity: View {
  let state: HymioActivityAttributes.ContentState

  var body: some View {
    HStack(spacing: 14) {
      ScarfMark(size: 48)
      VStack(alignment: .leading, spacing: 5) {
        HStack(alignment: .firstTextBaseline) {
          Text(state.title)
            .font(.headline.weight(.semibold))
            .lineLimit(1)
          Spacer(minLength: 8)
          ActivityClock(startedAt: state.startedAt)
            .font(.caption.monospacedDigit().weight(.medium))
            .opacity(0.76)
        }
        HStack(spacing: 7) {
          StatusGlyph(status: state.status)
          Text(state.phase)
            .font(.subheadline.weight(.medium))
            .lineLimit(1)
          Spacer(minLength: 5)
          if state.activeCount > 1 {
            Text("\(state.activeCount) 项")
              .font(.caption.weight(.semibold))
              .padding(.horizontal, 8)
              .padding(.vertical, 3)
              .background(.white.opacity(0.12), in: Capsule())
          }
        }
        ScarfStages(status: state.status)
      }
    }
    .foregroundStyle(.white)
    .padding(14)
    .accessibilityElement(children: .combine)
    .accessibilityLabel(
      "\(state.title)，\(state.phase)，\(state.activeCount > 1 ? "\(state.activeCount) 项工作" : "一项工作")"
    )
  }
}

private struct CompactMark: View {
  let state: HymioActivityAttributes.ContentState

  var body: some View {
    Image(systemName: state.status == "waiting" ? "hand.raised.fill" : "water.waves")
      .font(.system(size: 16, weight: .semibold))
      .foregroundStyle(Color(red: 0.63, green: 0.72, blue: 1))
      .accessibilityLabel(state.status == "waiting" ? "等待你确认" : "Hymio 正在处理")
  }
}

private struct CompactTrailing: View {
  let state: HymioActivityAttributes.ContentState

  var body: some View {
    if state.activeCount > 1 {
      Text("\(state.activeCount)")
        .font(.system(size: 15, weight: .bold, design: .rounded))
        .monospacedDigit()
    } else {
      StatusGlyph(status: state.status)
    }
  }
}

private struct MinimalState: View {
  let state: HymioActivityAttributes.ContentState

  var body: some View {
    Image(systemName: state.status == "waiting" ? "hand.raised.fill" : "water.waves")
      .font(.system(size: 13, weight: .bold))
      .foregroundStyle(Color(red: 0.65, green: 0.74, blue: 1))
      .accessibilityLabel(state.status == "waiting" ? "等待确认" : "正在处理")
  }
}

private struct StatusGlyph: View {
  let status: String

  var body: some View {
    Image(systemName: symbol)
      .font(.caption.weight(.semibold))
      .foregroundStyle(color)
      .accessibilityLabel(label)
  }

  private var symbol: String {
    switch status {
    case "waiting": return "hand.raised.fill"
    case "completed": return "checkmark.circle.fill"
    case "failed": return "exclamationmark.circle.fill"
    default: return "circle.dotted"
    }
  }
  private var label: String {
    switch status {
    case "waiting": return "等待确认"
    case "completed": return "已完成"
    case "failed": return "遇到问题"
    default: return "正在处理"
    }
  }
  private var color: Color {
    switch status {
    case "waiting": return Color(red: 1, green: 0.76, blue: 0.42)
    case "failed": return Color(red: 1, green: 0.55, blue: 0.58)
    default: return Color(red: 0.58, green: 0.90, blue: 0.78)
    }
  }
}

private struct ActivityClock: View {
  let startedAt: Int

  var body: some View {
    let start = Date(timeIntervalSince1970: TimeInterval(startedAt))
    let end = Date(timeIntervalSince1970: TimeInterval(startedAt) + 8 * 3600)
    Text(
      timerInterval: start...end,
      countsDown: false,
      showsHours: true
    )
  }
}

private struct ScarfMark: View {
  let size: CGFloat

  var body: some View {
    ZStack {
      Circle()
        .fill(
          LinearGradient(
            colors: [
              Color(red: 0.33, green: 0.47, blue: 1),
              Color(red: 0.16, green: 0.28, blue: 0.76),
            ],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
          ))
      Circle()
        .fill(.white.opacity(0.12))
        .frame(width: size * 0.86, height: size * 0.86)
      Image("HymioActivityOtter")
        .resizable()
        .scaledToFit()
        .frame(width: size * 0.78, height: size * 0.78)
        .offset(y: size * 0.05)
    }
    .frame(width: size, height: size)
    .overlay(Circle().stroke(.white.opacity(0.16), lineWidth: 1))
    .accessibilityHidden(true)
  }
}

private struct ScarfStages: View {
  let status: String

  var body: some View {
    HStack(spacing: 5) {
      ForEach(0..<3, id: \.self) { index in
        Capsule()
          .fill(index < filled ? accent : .white.opacity(0.12))
          .frame(height: 3)
        }
    }
    .accessibilityHidden(true)
  }

  private var filled: Int {
    switch status {
    case "waiting": return 2
    case "completed", "failed": return 3
    default: return 1
    }
  }
  private var accent: Color { Color(red: 0.58, green: 0.72, blue: 1) }
}
