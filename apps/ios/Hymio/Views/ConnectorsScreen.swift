import Combine
import EventKit
import HealthKit
import SafariServices
import SwiftUI

private let connectorLabels = [
  "ready": "已连接", "syncing": "同步中", "queued": "等待同步", "waiting_device": "等待手机同步",
  "authorization_required": "需要授权", "paused": "已暂停", "retrying": "稍后重试", "disconnected": "已断开",
]
private func sourceSymbol(_ id: String) -> String {
  [
    "gmail": "envelope", "dida": "checkmark", "apple_calendar": "calendar",
    "apple_health": "heart.fill",
  ][id] ?? "link"
}
private func sourceTint(_ id: String) -> Color {
  id == "gmail" ? .orange : id == "apple_health" ? .pink : Brand.blue
}
private struct SourceMark: View {
  let id: String
  var size: CGFloat = 54
  var body: some View {
    Group {
      if id == "gmail" || id == "dida" {
        Image(id == "gmail" ? "GmailBrand" : "DidaBrand").resizable().scaledToFit().padding(
          size * 0.17)
      } else if id == "apple_calendar" {
        VStack(spacing: 1) {
          Text("日历").font(.system(size: size * 0.16, weight: .medium)).foregroundStyle(
            .red.opacity(0.85))
          Text(String(Calendar.current.component(.day, from: Date()))).font(
            .system(size: size * 0.48, weight: .light)
          ).tracking(-1.5).foregroundStyle(Brand.ink)
        }
      } else {
        Image(systemName: "heart.fill").resizable().scaledToFit().padding(size * 0.22)
          .foregroundStyle(
            LinearGradient(
              colors: [
                Color(red: 1, green: 0.37, blue: 0.6), Color(red: 1, green: 0.12, blue: 0.3),
              ], startPoint: .top, endPoint: .bottom))
      }
    }.frame(width: size, height: size).background(
      Brand.surface, in: RoundedRectangle(cornerRadius: size * 0.28)
    )
    .overlay(RoundedRectangle(cornerRadius: size * 0.28).stroke(Brand.line.opacity(0.5)))
    .shadow(color: sourceTint(id).opacity(0.065), radius: 9, y: 4)
  }
}
@MainActor private final class ConnectionsModel: ObservableObject {
  @Published var providers: [JSON] = []
  @Published var connections: [JSON] = []
  @Published var error = ""
  @Published var busy = false
  let account: AccountService
  let preview: Bool
  init(account: AccountService, preview: Bool) {
    self.account = account
    self.preview = preview
  }
  func load() async {
    if preview {
      providers = [
        .object([
          "id": .string("gmail"), "name": .string("Gmail"), "summary": .string("让邮件里的安排和线索，有迹可循。"),
          "transport": .string("oauth"), "configured": .bool(true),
          "permissions": .array([.string("读取最近收件箱及后续变化"), .string("不发送、修改或删除邮件")]),
        ]),
        .object([
          "id": .string("dida"), "name": .string("滴答清单"), "summary": .string("把清单里的待办，带进日常对话。"),
          "transport": .string("oauth"), "configured": .bool(true),
          "permissions": .array([.string("读取项目和任务"), .string("不修改或完成任务")]),
        ]),
        .object([
          "id": .string("apple_calendar"), "name": .string("Apple 日历"),
          "summary": .string("知道你的安排，留出合适的空隙。"), "transport": .string("device"),
          "configured": .bool(true),
          "permissions": .array([.string("只读取你选择的日历"), .string("过去 7 天至未来 30 天")]),
        ]),
        .object([
          "id": .string("apple_health"), "name": .string("Apple 健康"),
          "summary": .string("从步数与活动量，了解生活的节奏。"), "transport": .string("device"),
          "configured": .bool(true),
          "permissions": .array([.string("每日步数与活动能量"), .string("不读取其他健康样本")]),
        ]),
      ]
      return
    }
    do {
      let value = try await account.request("connectors")
      providers = value["providers"].items
      connections = value["connections"].items
      error = ""
    } catch { self.error = "暂时无法读取连接，请稍后重试。" }
  }
  func perform(_ operation: () async throws -> Void) async {
    guard !busy, !preview else { return }
    busy = true
    error = ""
    defer { busy = false }
    do {
      try await operation()
      await load()
    } catch { self.error = error.localizedDescription }
  }
}

struct ConnectorsScreen: View {
  @StateObject private var model: ConnectionsModel
  init(account: AccountService, preview: Bool = false) {
    _model = StateObject(wrappedValue: ConnectionsModel(account: account, preview: preview))
  }
  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 26) {
        VStack(alignment: .leading, spacing: 10) {
          Text("连接你的日常").font(.system(.title, design: .rounded, weight: .semibold)).tracking(-0.8)
          Text("把邮件、计划与生活节奏，\n带进同一段对话。").font(.subheadline).foregroundStyle(Brand.muted)
            .lineSpacing(4)
        }.padding(.top, 8)
        if !model.error.isEmpty {
          VStack(alignment: .leading, spacing: 8) {
            Text(model.error).font(.footnote).foregroundStyle(.secondary)
            Button("重新读取") { Task { await model.load() } }
          }
        }
        VStack(alignment: .leading, spacing: 13) {
          sectionTitle("云端服务", caption: "账号授权后，由云端同步新的变化。")
          ForEach(model.providers.filter { $0["transport"].text == "oauth" }, id: \.self) {
            provider in
            NavigationLink {
              ConnectorDetail(provider: provider, model: model)
            } label: {
              if provider["id"].text == "gmail" { gmailCard(provider) } else { cloudRow(provider) }
            }.buttonStyle(.plain).accessibilityIdentifier("connector.\(provider["id"].text)")
          }
        }
        VStack(alignment: .leading, spacing: 13) {
          sectionTitle("来自 iPhone", caption: "权限留在设备上，分享哪些由你选择。")
          LazyVGrid(
            columns: [GridItem(.flexible(), spacing: 12), GridItem(.flexible(), spacing: 12)],
            spacing: 12
          ) {
            ForEach(model.providers.filter { $0["transport"].text == "device" }, id: \.self) {
              provider in
              NavigationLink {
                ConnectorDetail(provider: provider, model: model)
              } label: {
                deviceCard(provider)
              }
              .buttonStyle(.plain).accessibilityIdentifier("connector.\(provider["id"].text)")
            }
          }
        }
        if model.providers.isEmpty && model.error.isEmpty {
          ProgressView().frame(maxWidth: .infinity)
        }
        HStack(alignment: .top, spacing: 10) {
          Image(systemName: "lock.shield").font(.subheadline).padding(.top, 2)
          Text("每个来源单独授权。\nHymio 只读这些来源，不会修改外部数据。").font(.caption).lineSpacing(4)
        }.foregroundStyle(Brand.muted).padding(15).frame(maxWidth: .infinity, alignment: .leading)
          .background(Brand.mist.opacity(0.7), in: RoundedRectangle(cornerRadius: 16))
      }.padding(.horizontal, 20).padding(.bottom, 28)
    }.background(Brand.surface).navigationTitle("连接来源").navigationBarTitleDisplayMode(.inline)
      .task {
        await model.load()
        while !Task.isCancelled && !model.preview {
          do { try await Task.sleep(for: .seconds(15)) } catch { return }
          await model.load()
        }
      }
  }
  private func sectionTitle(_ title: String, caption: String) -> some View {
    VStack(alignment: .leading, spacing: 6) {
      Text(title).font(.subheadline.weight(.semibold)).foregroundStyle(Brand.ink)
      Text(caption).font(.caption).foregroundStyle(Brand.muted)
    }
  }
  private func connection(_ provider: JSON) -> JSON? {
    model.connections.first {
      $0["provider"] == provider["id"] && $0["state"].text != "disconnected"
    }
  }
  private func status(_ provider: JSON) -> String {
    if let connection = connection(provider) {
      return connectorLabels[connection["state"].text] ?? "检查连接"
    }
    return !provider["configured"].flag
      ? "待配置" : provider["transport"].text == "device" ? "iPhone 授权" : "连接"
  }
  private func badge(_ provider: JSON) -> some View {
    let ready = connection(provider)?["state"].text == "ready"
    return HStack(spacing: 4) {
      if ready { Circle().fill(Color.green.opacity(0.75)).frame(width: 5, height: 5) }
      Text(status(provider)).font(.system(size: 11, weight: .medium))
      if connection(provider) == nil && provider["configured"].flag {
        Image(systemName: "chevron.right").font(.system(size: 8, weight: .semibold))
      }
    }.foregroundStyle(ready ? Color.green : Brand.blue.opacity(0.8)).padding(.horizontal, 9)
      .padding(.vertical, 6)
      .background(ready ? Color.green.opacity(0.07) : Brand.blue.opacity(0.065), in: Capsule())
  }
  private func gmailCard(_ provider: JSON) -> some View {
    VStack(alignment: .leading, spacing: 16) {
      HStack(spacing: 13) {
        SourceMark(id: "gmail", size: 54)
        VStack(alignment: .leading, spacing: 5) {
          Text("Gmail").font(.headline).foregroundStyle(Brand.ink)
          Text(connection(provider)?["name"].text ?? "邮件里的安排与线索").font(.caption).foregroundStyle(
            Brand.muted)
        }
        Spacer(minLength: 4)
        badge(provider)
      }
      Text(provider["summary"].text).font(.footnote).foregroundStyle(Brand.muted).lineSpacing(3)
      HStack {
        Label(
          connection(provider).map { "\($0["item_count"].int) 条来源记录" } ?? "由你授权，只读同步",
          systemImage: "tray")
        Spacer()
        Image(systemName: "arrow.up.right").foregroundStyle(Brand.blue.opacity(0.75))
      }.font(.caption).foregroundStyle(Brand.muted).padding(.top, 12)
        .overlay(alignment: .top) { Rectangle().fill(Brand.blue.opacity(0.07)).frame(height: 1) }
    }.padding(18).background(
      LinearGradient(
        colors: [Brand.surface, Brand.blue.opacity(0.035)], startPoint: .topLeading,
        endPoint: .bottomTrailing), in: RoundedRectangle(cornerRadius: 22)
    )
    .overlay(RoundedRectangle(cornerRadius: 22).stroke(Brand.blue.opacity(0.11)))
    .shadow(color: Brand.blue.opacity(0.035), radius: 12, y: 5)
  }
  private func cloudRow(_ provider: JSON) -> some View {
    HStack(spacing: 13) {
      SourceMark(id: provider["id"].text, size: 50)
      VStack(alignment: .leading, spacing: 6) {
        Text(provider["name"].text).font(.subheadline.weight(.semibold)).foregroundStyle(Brand.ink)
        Text("任务与清单，随时接续").font(.caption).foregroundStyle(Brand.muted)
      }
      Spacer(minLength: 4)
      badge(provider)
    }.padding(17).background(Brand.surface, in: RoundedRectangle(cornerRadius: 21))
      .overlay(RoundedRectangle(cornerRadius: 21).stroke(Brand.line.opacity(0.7)))
      .shadow(color: .black.opacity(0.025), radius: 10, y: 4)
  }
  private func deviceCard(_ provider: JSON) -> some View {
    VStack(alignment: .leading, spacing: 12) {
      SourceMark(id: provider["id"].text, size: 48)
      VStack(alignment: .leading, spacing: 6) {
        Text(provider["id"].text == "apple_health" ? "健康" : "日历").font(
          .subheadline.weight(.semibold)
        ).foregroundStyle(Brand.ink)
        Text(provider["id"].text == "apple_health" ? "每日步数与活动量，\n了解生活的节奏。" : "读懂安排，\n留出合适的空隙。")
          .font(.caption).foregroundStyle(Brand.muted).lineSpacing(3).fixedSize(
            horizontal: false, vertical: true)
      }
      Spacer(minLength: 0)
      badge(provider)
    }.frame(maxWidth: .infinity, minHeight: 164, alignment: .topLeading).padding(16)
      .background(Brand.surface, in: RoundedRectangle(cornerRadius: 21))
      .overlay(RoundedRectangle(cornerRadius: 21).stroke(Brand.line.opacity(0.65)))
      .shadow(color: .black.opacity(0.025), radius: 10, y: 4)
  }
}

private struct ConnectorOAuth: Identifiable {
  let id = UUID()
  let url: URL
}
private struct ConnectorDetail: View {
  let provider: JSON
  @ObservedObject var model: ConnectionsModel
  @EnvironmentObject private var healthSync: HealthEventSync
  @StateObject private var device = DeviceSourceCollector()
  @State private var consent = false
  @State private var browser: ConnectorOAuth?
  @State private var calendarPicker = false
  @State private var selectedCalendars: Set<String> = []
  @State private var disconnect: JSON?
  private var id: String { provider["id"].text }
  private var ownConnections: [JSON] { model.connections.filter { $0["provider"].text == id } }
  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 24) {
        HStack(alignment: .center, spacing: 17) {
          SourceMark(id: id, size: 72)
          VStack(alignment: .leading, spacing: 7) {
            Text(provider["name"].text).font(.title2.weight(.semibold)).tracking(-0.6)
            Text(provider["summary"].text).font(.footnote).foregroundStyle(Brand.muted).lineSpacing(
              3)
          }
        }.padding(.top, 16).padding(.bottom, 3)
        HStack(spacing: 8) {
          Label(
            provider["transport"].text == "device" ? "来自 iPhone" : "云端同步",
            systemImage: provider["transport"].text == "device" ? "iphone" : "cloud")
          Label(id == "apple_health" ? "每日汇总" : "只读访问", systemImage: "checkmark.shield")
        }.font(.caption).foregroundStyle(Brand.muted)
          .labelStyle(.titleAndIcon)
        VStack(alignment: .leading, spacing: 0) {
          HStack {
            Text("分享的范围").font(.subheadline.weight(.semibold)).foregroundStyle(Brand.ink)
            Spacer()
            Text("只读").font(.caption).foregroundStyle(Brand.muted)
          }.padding(.bottom, 6)
          if id == "apple_health" {
            permissionRow("每日步数", caption: "最近 7 天的每日汇总", symbol: "figure.walk", color: Brand.blue)
            Divider().overlay(Brand.line.opacity(0.4)).padding(.leading, 48)
            permissionRow("活动能量", caption: "每日活动消耗，单位为千卡", symbol: "flame.fill", color: .orange)
          } else if id == "apple_calendar" {
            permissionRow(
              "你选择的日历", caption: "过去 7 天至未来 30 天的安排", symbol: "calendar", color: Brand.blue)
            Divider().padding(.leading, 48)
            permissionRow("只保留必要信息", caption: "不读取参与者、备注或位置", symbol: "lock", color: Brand.muted)
          } else {
            ForEach(Array(provider["permissions"].items.enumerated()), id: \.offset) {
              index, permission in
              permissionRow(
                permission.text, caption: index == 0 ? "仅用于你的个人助手" : "连接不会授予外部写入权限",
                symbol: index == 0 ? "tray" : "lock", color: index == 0 ? Brand.blue : Brand.muted)
            }
          }
        }.padding(18).background(Brand.surface, in: RoundedRectangle(cornerRadius: 22))
          .overlay(RoundedRectangle(cornerRadius: 22).stroke(Brand.line.opacity(0.7)))
          .shadow(color: .black.opacity(0.025), radius: 10, y: 4)
        if id == "apple_health" || id == "apple_calendar" {
          Label(
            id == "apple_health" ? "仅分享每日汇总，不读取其他健康样本。" : "Apple 要求完整日历权限才能读取，Hymio 仅只读所选日历。",
            systemImage: "info.circle"
          )
          .font(.caption).foregroundStyle(Brand.muted).lineSpacing(4)
        }
        ForEach(ownConnections, id: \.self) { connection in
          VStack(alignment: .leading, spacing: 12) {
            HStack {
              Text(connection["name"].text).font(.subheadline.weight(.medium))
              Spacer()
              Text(connectorLabels[connection["state"].text] ?? "检查连接").font(.caption)
                .foregroundStyle(Brand.blue)
            }
            Text(
              connection["last_success"].double > 0
                ? "最近同步 "
                  + Date(timeIntervalSince1970: connection["last_success"].double).formatted(
                    .dateTime.month().day().hour().minute()) : "尚未完成首次同步"
            ).font(.caption).foregroundStyle(Brand.muted)
            Text(
              "\(connection["item_count"].int) 条来源记录 · \(connection["pending_count"].int) 条待写入记忆"
            ).font(.caption).foregroundStyle(Brand.muted)
            if id == "apple_health", let latest = connection["runs"].items.first,
              latest["status"].text == "succeeded", latest["received"].int == 0
            {
              Text("本次未读取到健康汇总，可能没有数据或读取范围受限。这不表示活动量为零。").font(.caption).foregroundStyle(
                Brand.muted)
            }
            if id == "apple_health", healthSync.monitoring {
              Label("健康变化事件同步已开启", systemImage: "bolt.heart")
                .font(.caption).foregroundStyle(Brand.muted)
            }
            if id == "apple_health", !healthSync.message.isEmpty {
              Text(healthSync.message).font(.caption).foregroundStyle(Brand.muted)
            }
            if connection["pending_count"].int > 0 {
              Text("来源已接收，正在写入记忆；暂不可用时会保留进度重试。").font(.caption).foregroundStyle(Brand.muted)
            }
            if connection["state"].text != "disconnected" {
              HStack(spacing: 20) {
                if connection["state"].text == "paused" {
                  Button("恢复") { action(connection, "resume") }
                } else {
                  Button("立即同步") { Task { await sync(connection) } }.disabled(
                    !consent || model.busy)
                  Button("暂停") { action(connection, "pause") }
                }
                Spacer()
                Button("断开", role: .destructive) { disconnect = connection }
              }.font(.footnote).frame(minHeight: 44)
            }
            if !connection["runs"].items.isEmpty {
              DisclosureGroup("最近同步记录") {
                ForEach(connection["runs"].items, id: \.self) { run in
                  Text(
                    Date(timeIntervalSince1970: run["started_at"].double).formatted(
                      .dateTime.hour().minute()) + " · "
                      + (run["status"].text == "succeeded"
                        ? "已接收 \(run["received"].int) 条" : "未完成，保留进度")
                  )
                  .font(.caption).foregroundStyle(Brand.muted).frame(
                    maxWidth: .infinity, alignment: .leading
                  ).padding(.vertical, 4)
                }
              }.font(.caption).tint(Brand.muted)
            }
          }.padding(18).background(Brand.mist.opacity(0.5), in: RoundedRectangle(cornerRadius: 20))
        }
        if !provider["configured"].flag {
          Label("此部署尚未配置服务授权，请联系部署者。", systemImage: "info.circle").font(.footnote).foregroundStyle(
            Brand.muted)
        } else {
          Toggle(isOn: $consent) {
            VStack(alignment: .leading, spacing: 6) {
              Text("同步至 Hymio").font(.footnote.weight(.semibold)).foregroundStyle(Brand.ink)
              Text("保存为个人上下文，供助手及配置的 AI 模型使用。").font(.caption).foregroundStyle(Brand.muted)
                .lineSpacing(3)
            }
          }.tint(Brand.blue).padding(16)
            .background(Brand.mist.opacity(0.5), in: RoundedRectangle(cornerRadius: 18))
            .accessibilityIdentifier("connector.consent")
          Button {
            Task { await connect() }
          } label: {
            HStack {
              if model.busy { ProgressView().tint(.white) }
              Text("连接 \(provider["name"].text)").font(.subheadline.weight(.semibold))
              Spacer()
              Image(systemName: "arrow.up.right")
            }.padding(17).foregroundStyle(.white).background(
              Brand.blue, in: RoundedRectangle(cornerRadius: 16))
          }.buttonStyle(.plain).disabled(!consent || model.busy || model.preview).opacity(
            consent ? 1 : 0.45)
        }
        if !model.error.isEmpty { Text(model.error).font(.footnote).foregroundStyle(.secondary) }
        Text(
          id == "apple_health"
            ? "健康数据变化后，由 iOS 调度后台同步；系统会控制频率，不保证实时。可随时暂停或断开，已导入记录会保留。"
            : provider["transport"].text == "device"
              ? "仅在你主动同步时读取。可随时暂停或断开，已导入记录会保留。"
              : "可随时暂停或断开。断开后移除授权凭据，已导入记录会保留。"
        ).font(.caption).foregroundStyle(
          Brand.muted
        ).lineSpacing(4)
      }.padding(22)
    }.background(Brand.surface).navigationBarTitleDisplayMode(.inline)
      .sheet(item: $browser, onDismiss: { Task { await model.load() } }) { flow in
        ConnectorBrowser(url: flow.url) { browser = nil }
      }
      .sheet(isPresented: $calendarPicker) {
        NavigationStack {
          List(device.calendars, id: \.calendarIdentifier) { calendar in
            Toggle(
              calendar.title,
              isOn: Binding(
                get: { selectedCalendars.contains(calendar.calendarIdentifier) },
                set: {
                  if $0 {
                    selectedCalendars.insert(calendar.calendarIdentifier)
                  } else {
                    selectedCalendars.remove(calendar.calendarIdentifier)
                  }
                }))
          }.navigationTitle("选择要同步的日历").toolbar {
            ToolbarItem(placement: .cancellationAction) { Button("取消") { calendarPicker = false } }
            ToolbarItem(placement: .confirmationAction) {
              Button("同步") {
                calendarPicker = false
                Task { await finishCalendar() }
              }.disabled(selectedCalendars.isEmpty)
            }
          }
        }
      }
      .confirmationDialog(
        "断开连接？已导入记录会保留。",
        isPresented: Binding(get: { disconnect != nil }, set: { if !$0 { disconnect = nil } })
      ) {
        Button("断开连接", role: .destructive) {
          if let connection = disconnect { action(connection, "disconnect") }
          disconnect = nil
        }
      }
  }
  private func permissionRow(_ title: String, caption: String, symbol: String, color: Color)
    -> some View
  {
    HStack(alignment: .center, spacing: 12) {
      Image(systemName: symbol).font(.subheadline).foregroundStyle(color)
        .frame(width: 36, height: 36).background(
          color.opacity(0.065), in: RoundedRectangle(cornerRadius: 12))
      VStack(alignment: .leading, spacing: 5) {
        Text(title).font(.footnote.weight(.medium)).foregroundStyle(Brand.ink)
        Text(caption).font(.caption).foregroundStyle(Brand.muted).lineSpacing(2)
      }
      Spacer(minLength: 0)
    }.padding(.vertical, 13)
  }
  private func action(_ connection: JSON, _ action: String) {
    Task {
      await model.perform {
        let result = try await model.account.request(
          "connectors/" + connection["id"].text, body: .object(["action": .string(action)]))
        if result["revocation"].text == "not_confirmed" {
          model.error = "已停止同步；服务端撤权未确认，可在服务账号设置中移除授权。"
        }
      }
      if id == "apple_health" {
        if action == "resume" {
          await healthSync.activate()
        } else {
          healthSync.stop(clearPending: true)
        }
      }
    }
  }
  private func existing() -> JSON? {
    ownConnections.first {
      $0["state"].text != "disconnected"
        && (provider["transport"].text == "oauth" || $0["device_id"].text == device.installation)
    }
  }
  private func create() async throws -> JSON {
    if let value = existing() { return value }
    return try await model.account.request(
      "connectors",
      body: .object([
        "provider": .string(id), "device_id": .string(device.installation),
        "platform": .string("ios"), "consent": .bool(true),
      ]))
  }
  private func connect() async {
    if id == "apple_calendar" {
      await model.perform {
        try await device.calendarPermission()
        selectedCalendars = []
        calendarPicker = true
      }
    } else if id == "apple_health" {
      await model.perform {
        try await device.healthPermission()
        let row = try await create()
        try await healthSync.enable(connectionID: row["id"].text)
      }
    } else {
      await model.perform {
        let row = try await create()
        let value = try await model.account.request(
          "connectors/" + row["id"].text + "/authorize", body: .object([:]))
        guard let url = URL(string: value["url"].text), url.scheme == "https",
          ["accounts.google.com", "dida365.com"].contains(url.host ?? "")
        else { throw ServiceError.message("授权地址无效") }
        browser = ConnectorOAuth(url: url)
      }
    }
  }
  private func sync(_ connection: JSON) async {
    if provider["transport"].text == "oauth" {
      action(connection, "sync")
    } else if connection["device_id"].text != device.installation {
      model.error = "此来源由另一台 iPhone 同步。请在那台手机上操作。"
    } else if id == "apple_health" {
      await model.perform {
        try await healthSync.syncNow(connectionID: connection["id"].text)
      }
    } else {
      await connect()
    }
  }
  private func finishCalendar() async {
    await model.perform {
      let row = try await create()
      try await upload(row, try await device.calendar(ids: selectedCalendars))
    }
  }
  private func upload(_ connection: JSON, _ payload: [String: JSON]) async throws {
    var body = payload
    body["device_id"] = .string(device.installation)
    body["consent"] = .bool(true)
    _ = try await model.account.request(
      "connectors/" + connection["id"].text + "/ingest", body: .object(body))
  }
}

@MainActor private final class DeviceSourceCollector: ObservableObject {
  private let eventStore = EKEventStore()
  private let healthStore = HKHealthStore()
  @Published var calendars: [EKCalendar] = []
  var installation: String { DeviceInstallation.id }
  func calendarPermission() async throws {
    guard try await eventStore.requestFullAccessToEvents() else {
      throw ServiceError.message("日历权限未开启，可到系统设置中更改。")
    }
    calendars = eventStore.calendars(for: .event)
  }
  func calendar(ids: Set<String>) async throws -> [String: JSON] {
    return try await Task.detached(priority: .userInitiated) {
      let eventStore = EKEventStore()
      let calendars = eventStore.calendars(for: .event)
      let now = Date()
      let cal = Calendar.current
      let start = cal.date(byAdding: .day, value: -7, to: now)!
      let end = cal.date(byAdding: .day, value: 30, to: now)!
      let selected = calendars.filter { ids.contains($0.calendarIdentifier) }
      guard !selected.isEmpty else { throw ServiceError.message("请至少选择一个日历。") }
      let events = eventStore.events(
        matching: eventStore.predicateForEvents(withStart: start, end: end, calendars: selected))
      guard events.count <= 250 else {
        throw ServiceError.message("此时间范围超过 250 条日程。请减少所选日历后重试；本次未上传，也不会删除旧记录。")
      }
      let formatter = ISO8601DateFormatter()
      let items = events.map { event in
        JSON.object([
          "external_id": .string(
            (event.eventIdentifier ?? event.calendarItemIdentifier) + ":"
              + formatter.string(from: event.startDate)), "kind": .string("calendar_event"),
          "title": .string(String((event.title ?? "日程").prefix(300))),
          "calendar_id": .string(event.calendar.calendarIdentifier),
          "start": .string(formatter.string(from: event.startDate)),
          "end": .string(formatter.string(from: event.endDate)), "all_day": .bool(event.isAllDay),
        ])
      }
      return [
        "captured_at": .number(now.timeIntervalSince1970),
        "items": .array(items), "complete": .bool(true),
        "window": .object([
          "start": .string(formatter.string(from: start)),
          "end": .string(formatter.string(from: end)),
          "calendars": .array(ids.sorted().map(JSON.string)),
        ]),
      ]
    }.value
  }
  func healthPermission() async throws {
    guard HKHealthStore.isHealthDataAvailable() else { throw ServiceError.message("这台设备不支持健康数据。") }
    let types: Set<HKObjectType> = [
      HKQuantityType(.stepCount), HKQuantityType(.activeEnergyBurned),
    ]
    try await healthStore.requestAuthorization(toShare: [], read: types)
    // HealthKit intentionally does not reveal whether read permission was granted.
  }
}

private struct ConnectorBrowser: UIViewControllerRepresentable {
  let url: URL
  let onClose: () -> Void
  func makeCoordinator() -> Coordinator { Coordinator(onClose) }
  func makeUIViewController(context: Context) -> SFSafariViewController {
    let view = SFSafariViewController(url: url)
    view.delegate = context.coordinator
    return view
  }
  func updateUIViewController(_ controller: SFSafariViewController, context: Context) {}
  final class Coordinator: NSObject, SFSafariViewControllerDelegate {
    let close: () -> Void
    init(_ close: @escaping () -> Void) { self.close = close }
    func safariViewControllerDidFinish(_ controller: SFSafariViewController) { close() }
  }
}
