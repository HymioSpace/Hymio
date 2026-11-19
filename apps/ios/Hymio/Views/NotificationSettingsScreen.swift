import SwiftUI
import UIKit
import UserNotifications

struct NotificationSettingsScreen: View {
  @ObservedObject var account: AccountService
  @StateObject private var notifications = PushNotificationManager.shared

  var body: some View {
    List {
      Section {
        HStack(alignment: .top, spacing: 14) {
          Image(systemName: statusSymbol)
            .font(.title2)
            .foregroundStyle(statusColor)
            .frame(width: 34, height: 34)
            .accessibilityHidden(true)
          VStack(alignment: .leading, spacing: 5) {
            Text(statusTitle).font(.headline)
            Text(statusDetail).font(.caption).foregroundStyle(.secondary)
          }
        }
        Button(authorizationButton) {
          Task {
            if notifications.authorization == .notDetermined {
              _ = await notifications.requestAuthorization()
            } else {
              openSettings()
            }
          }
        }
        if !notifications.configured {
          Label("服务端尚未配置 APNs；设置会保存，但暂时不会送达。", systemImage: "server.rack")
            .font(.caption)
            .foregroundStyle(.secondary)
        }
      } footer: {
        Text("通知由任务状态或 Agent 的 notify_user 调用产生。这里只决定哪些提醒送达，不会改写通知正文。")
      }

      Section {
        preference(
          "后台工作开始", key: "start_enabled", value: $notifications.preferences.startEnabled,
          symbol: "play.circle")
        preference(
          "任务完成", key: "completion_enabled", value: $notifications.preferences.completionEnabled,
          symbol: "checkmark.circle")
        preference(
          "需要确认或遇到问题", key: "attention_enabled",
          value: $notifications.preferences.attentionEnabled, symbol: "hand.raised")
        preference(
          "对话回复已准备好", key: "reply_enabled", value: $notifications.preferences.replyEnabled,
          symbol: "bubble.left")
        preference(
          "在锁屏显示标题与摘要", key: "show_details", value: $notifications.preferences.showDetails,
          symbol: "text.quote")
      } header: {
        Text("提醒类型")
      } footer: {
        Text("Agent 调用 notify_user 时只能选择以上类型并提供摘要；服务器会按这里的选择拦掉关闭的类型。任务开始、完成和需确认由任务流程生成，不靠 Agent 猜。关闭锁屏详情后，系统通知只显示“Hymio”。")
      }

      Section {
        preference(
          "显示进行中的实时活动", key: "live_activity_enabled",
          value: $notifications.preferences.liveActivityEnabled, symbol: "waveform.path")
      } footer: {
        Text("实时活动会合并正在进行的任务，最长保留 8 小时；结束后最多再显示 15 分钟。")
      }

      if !notifications.error.isEmpty {
        Section {
          Text(notifications.error).font(.footnote).foregroundStyle(.secondary)
        }
      }
    }
    .navigationTitle("通知与实时活动")
    .navigationBarTitleDisplayMode(.inline)
    .task { await notifications.bind(account) }
    .refreshable { await notifications.load(account) }
  }

  private func preference(
    _ title: String, key: String, value: Binding<Bool>, symbol: String
  ) -> some View {
    Toggle(isOn: Binding(
      get: { value.wrappedValue },
      set: { next in Task { await notifications.update(account, key: key, value: next) } }
    )) {
      Label(title, systemImage: symbol)
    }
    .tint(Brand.blue)
  }

  private var statusSymbol: String {
    switch notifications.authorization {
    case .authorized, .provisional, .ephemeral: return "bell.badge.fill"
    case .denied: return "bell.slash.fill"
    default: return "bell"
    }
  }

  private var statusColor: Color {
    switch notifications.authorization {
    case .authorized, .provisional, .ephemeral: return Brand.blue
    case .denied: return Brand.attention
    default: return Brand.muted
    }
  }

  private var statusTitle: String {
    switch notifications.authorization {
    case .authorized, .provisional, .ephemeral:
      return notifications.deviceRegistered ? "通知已就绪" : "通知已允许"
    case .denied: return "通知已关闭"
    default: return "还没有开启通知"
    }
  }

  private var statusDetail: String {
    switch notifications.authorization {
    case .authorized, .provisional, .ephemeral:
      return notifications.deviceRegistered
        ? "后台工作完成或需要你时，会在这里提醒。"
        : "正在登记这台 iPhone，请稍候。"
    case .denied:
      return "可前往系统设置重新允许 Hymio 通知。"
    default:
      return "开启后，离开 App 也能收到重要进展。"
    }
  }

  private var authorizationButton: String {
    notifications.authorization == .notDetermined ? "开启通知" : "打开系统设置"
  }

  private func openSettings() {
    guard let url = URL(string: UIApplication.openSettingsURLString) else { return }
    UIApplication.shared.open(url)
  }
}
