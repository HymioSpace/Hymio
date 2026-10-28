import ActivityKit
import SwiftUI

struct LiveActivityPreviewScreen: View {
  @State private var activity: Activity<HymioActivityAttributes>?
  @State private var result = ""

  var body: some View {
    VStack(spacing: 22) {
      Companion(size: 104, mood: .working)
      VStack(spacing: 8) {
        Text("实时活动预览").font(.system(.title, design: .rounded, weight: .semibold))
        Text("启动后回到主屏幕，查看锁屏、灵动岛和展开状态。")
          .font(.subheadline)
          .foregroundStyle(.secondary)
          .multilineTextAlignment(.center)
      }
      Button(activity == nil ? "开始预览" : "结束预览") {
        Task { await toggle() }
      }
      .buttonStyle(PrimaryAction())
      if !result.isEmpty {
        Text(result).font(.footnote).foregroundStyle(.secondary)
      }
      Spacer()
    }
    .padding(28)
  }

  private func toggle() async {
    if let activity {
      await activity.end(nil, dismissalPolicy: .immediate)
      self.activity = nil
      result = ""
      return
    }
    let now = Int(Date().timeIntervalSince1970)
    do {
      activity = try Activity.request(
        attributes: HymioActivityAttributes(aggregateID: "preview"),
        content: ActivityContent(
          state: .init(
            title: "整理周末出游路线",
            phase: "正在比较交通和开放时间",
            status: "working",
            activeCount: 2,
            startedAt: now,
            updatedAt: now,
            taskID: ""
          ),
          staleDate: Date().addingTimeInterval(8 * 3600)
        ),
        pushType: nil
      )
      result = "预览已启动"
    } catch {
      result = "无法启动：\(error.localizedDescription)"
    }
  }
}
