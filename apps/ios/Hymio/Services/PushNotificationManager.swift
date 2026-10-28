import Combine
import ActivityKit
import SwiftUI
import UIKit
import UserNotifications

enum AppDestination: Equatable {
  case task(String)
  case chat

  init?(route: String) {
    if route.hasPrefix("task:") {
      let id = String(route.dropFirst(5))
      guard !id.isEmpty else { return nil }
      self = .task(id)
    } else if route == "chat" {
      self = .chat
    } else {
      return nil
    }
  }

  init?(url: URL) {
    guard url.scheme == "hymio" else { return nil }
    if url.host == "task" {
      let id = url.pathComponents.dropFirst().joined(separator: "/")
      guard !id.isEmpty else { return nil }
      self = .task(id)
    } else if url.host == "chat" {
      self = .chat
    } else {
      return nil
    }
  }
}

struct PushPreferences: Equatable {
  var startEnabled = true
  var completionEnabled = true
  var attentionEnabled = true
  var replyEnabled = true
  var showDetails = false
  var liveActivityEnabled = true

  init() {}

  init(_ value: JSON) {
    let preferences = value["preferences"]
    startEnabled = preferences["start_enabled"].flag
    completionEnabled = preferences["completion_enabled"].flag
    attentionEnabled = preferences["attention_enabled"].flag
    replyEnabled = preferences["reply_enabled"].flag
    showDetails = preferences["show_details"].flag
    liveActivityEnabled = preferences["live_activity_enabled"].flag
  }

  func body(_ key: String, _ value: Bool) -> [String: JSON] {
    ["action": .string("preferences"), key: .bool(value)]
  }
}

@MainActor
final class PushNotificationManager: NSObject, ObservableObject {
  static let shared = PushNotificationManager()

  @Published private(set) var authorization: UNAuthorizationStatus = .notDetermined
  @Published private(set) var configured = false
  @Published private(set) var deviceRegistered = false
  @Published private(set) var error = ""
  @Published var preferences = PushPreferences()
  @Published private(set) var destination: AppDestination?

  private weak var account: AccountService?
  private var token = ""
  private var refreshing = false

  var installationID: String {
    let key = "hymio.push-installation"
    if let value = UserDefaults.standard.string(forKey: key) { return value }
    let value = UUID().uuidString
    UserDefaults.standard.set(value, forKey: key)
    return value
  }

  var systemDenied: Bool {
    authorization == .denied
  }

  func bind(_ account: AccountService) async {
    guard account.session != nil else { return }
    self.account = account
    await refreshSystemStatus()
    await load(account)
    if authorization == .authorized || authorization == .provisional || authorization == .ephemeral {
      UIApplication.shared.registerForRemoteNotifications()
    }
    if let token = deviceTokenFromDefaults() {
      await register(account, token: token)
    }
  }

  func detach() async {
    if let account, !token.isEmpty {
      _ = try? await account.request(
        "notifications",
        body: .object([
          "action": .string("unregister"), "installation_id": .string(installationID),
        ]))
    }
    account = nil
    token = ""
    deviceRegistered = false
    destination = nil
    for activity in Activity<HymioActivityAttributes>.activities {
      await activity.end(nil, dismissalPolicy: .immediate)
    }
  }

  func requestAuthorization() async -> Bool {
    do {
      let granted = try await UNUserNotificationCenter.current().requestAuthorization(options: [
        .alert, .sound, .badge,
      ])
      await refreshSystemStatus()
      if granted {
        UIApplication.shared.registerForRemoteNotifications()
        return true
      }
      error = "通知未开启。你仍可在系统设置中允许 Hymio 通知。"
    } catch {
      self.error = "无法请求通知权限：\(error.localizedDescription)"
    }
    return false
  }

  func requestForBackgroundWork(_ account: AccountService) async {
    self.account = account
    await refreshSystemStatus()
    guard authorization == .notDetermined else { return }
    _ = await requestAuthorization()
  }

  func refreshSystemStatus() async {
    let settings = await UNUserNotificationCenter.current().notificationSettings()
    authorization = settings.authorizationStatus
  }

  func load(_ account: AccountService) async {
    guard !refreshing else { return }
    refreshing = true
    defer { refreshing = false }
    do {
      let value = try await account.request("notifications")
      apply(value)
      error = ""
    } catch {
      self.error = "暂时无法读取通知设置。"
    }
  }

  func update(_ account: AccountService, key: String, value: Bool) async {
    let previous = preferences
    switch key {
    case "start_enabled": preferences.startEnabled = value
    case "completion_enabled": preferences.completionEnabled = value
    case "attention_enabled": preferences.attentionEnabled = value
    case "reply_enabled": preferences.replyEnabled = value
    case "show_details": preferences.showDetails = value
    case "live_activity_enabled":
      preferences.liveActivityEnabled = value
      UserDefaults.standard.set(value, forKey: "hymio.live-activity-enabled")
    default: return
    }
    UserDefaults.standard.set(preferences.showDetails, forKey: "hymio.push-show-details")
    do {
      let result = try await account.request(
        "notifications", body: .object(preferences.body(key, value)))
      apply(result)
      error = ""
    } catch {
      preferences = previous
      self.error = "设置没有保存，请稍后再试。"
    }
  }

  func updatePresence(_ account: AccountService, active: Bool) async {
    self.account = account
    _ = try? await account.request(
      "notifications",
      body: .object([
        "action": .string("presence"), "installation_id": .string(installationID),
        "active": .bool(active),
      ]))
  }

  func registerLiveActivity(
    _ account: AccountService, activityID: String, token: String, state: String = "working",
    summary: String = "", taskID: String = ""
  ) async {
    self.account = account
    _ = try? await account.request(
      "notifications",
      body: .object([
        "action": .string("live_activity_register"),
        "installation_id": .string(installationID),
        "activity_id": .string(activityID),
        "token": .string(token),
        "environment": .string(environment),
        "state": .string(state),
        "summary": .string(summary),
        "task_id": .string(taskID),
      ]))
  }

  func unregisterLiveActivity(_ account: AccountService, activityID: String) async {
    _ = try? await account.request(
      "notifications",
      body: .object([
        "action": .string("live_activity_unregister"),
        "activity_id": .string(activityID),
      ]))
  }

  func received(token data: Data) {
    let value = data.map { String(format: "%02x", $0) }.joined()
    guard value.count >= 64 else { return }
    token = value
    UserDefaults.standard.set(value, forKey: tokenKey)
    guard let account else { return }
    Task { await register(account, token: value) }
  }

  func open(route: String) {
    guard let destination = AppDestination(route: route) else { return }
    self.destination = destination
  }

  func open(url: URL) {
    guard let destination = AppDestination(url: url) else { return }
    self.destination = destination
  }

  func registrationFailed(_ error: Error) {
    deviceRegistered = false
    self.error = "无法登记通知：\(error.localizedDescription)"
  }

  func consume(_ destination: AppDestination) {
    if self.destination == destination { self.destination = nil }
  }

  private var environment: String {
    #if DEBUG
      "sandbox"
    #else
      "production"
    #endif
  }

  private var tokenKey: String {
    "hymio.apns-token."
      + (Bundle.main.bundleIdentifier ?? "Hymio")
      + "."
      + environment
      + "."
      + installationID
  }

  private func deviceTokenFromDefaults() -> String? {
    UserDefaults.standard.string(forKey: tokenKey)
  }

  private func register(_ account: AccountService, token: String) async {
    guard !token.isEmpty else { return }
    do {
      _ = try await account.request(
        "notifications",
        body: .object([
          "action": .string("register"),
          "installation_id": .string(installationID),
          "token": .string(token),
          "environment": .string(environment),
          "locale": .string(Locale.current.identifier),
          "timezone": .string(TimeZone.current.identifier),
          "app_version": .string(
            Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String
              ?? ""),
        ]))
      deviceRegistered = true
      error = ""
    } catch {
      deviceRegistered = false
      self.error = "通知服务暂时无法登记，请稍后再试。"
    }
  }

  private func apply(_ value: JSON) {
    configured = value["configured"].flag
    preferences = PushPreferences(value)
    UserDefaults.standard.set(
      preferences.showDetails, forKey: "hymio.push-show-details")
    UserDefaults.standard.set(
      preferences.liveActivityEnabled, forKey: "hymio.live-activity-enabled")
  }
}

final class HymioAppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {
  func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
  ) -> Bool {
    let center = UNUserNotificationCenter.current()
    center.delegate = self
    center.setNotificationCategories([
      UNNotificationCategory(
        identifier: "HYMIO_TASK", actions: [], intentIdentifiers: [], options: [])
    ])
    return true
  }

  func application(
    _ application: UIApplication,
    didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data
  ) {
    Task { @MainActor in PushNotificationManager.shared.received(token: deviceToken) }
  }

  func application(
    _ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error
  ) {
    Task { @MainActor in
      PushNotificationManager.shared.registrationFailed(error)
    }
  }

  func userNotificationCenter(
    _ center: UNUserNotificationCenter,
    willPresent notification: UNNotification,
    withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
  ) {
    completionHandler([])
  }

  func userNotificationCenter(
    _ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse,
    withCompletionHandler completionHandler: @escaping () -> Void
  ) {
    let route = response.notification.request.content.userInfo["route"] as? String ?? "chat"
    Task { @MainActor in PushNotificationManager.shared.open(route: route) }
    completionHandler()
  }
}
