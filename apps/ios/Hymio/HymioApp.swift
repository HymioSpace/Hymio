import SwiftUI

@main struct HymioApp: App {
  @UIApplicationDelegateAdaptor(HymioAppDelegate.self) private var appDelegate
  @StateObject private var account: AccountService
  @StateObject private var client: AgentClient
  @StateObject private var healthSync: HealthEventSync
  @StateObject private var notifications = PushNotificationManager.shared
  @Environment(\.scenePhase) private var scene
  init() {
    let service = AccountService()
    _account = StateObject(wrappedValue: service)
    _client = StateObject(wrappedValue: AgentClient(account: service))
    _healthSync = StateObject(wrappedValue: HealthEventSync(account: service))
  }
  var body: some Scene {
    WindowGroup {
      Group {
        #if DEBUG
          if ProcessInfo.processInfo.arguments.contains("-HymioApprovalPreview") {
            ApprovalPreviewScreen()
              .preferredColorScheme(
                ProcessInfo.processInfo.arguments.contains("-HymioApprovalDarkPreview") ? .dark : nil
              )
              .environment(
                \.dynamicTypeSize,
                ProcessInfo.processInfo.arguments.contains("-HymioApprovalLargePreview")
                  ? .accessibility3 : .large
              )
          } else if ProcessInfo.processInfo.arguments.contains("-HymioExperiencePreview") {
            PersonalExperiencePreview(account: account)
          } else if ProcessInfo.processInfo.arguments.contains("-HymioTaskStorePreview") {
            TaskStoreValidationPreview()
          } else if ProcessInfo.processInfo.arguments.contains("-HymioArtworkPreview") {
            ArtworkAlignmentPreview()
          } else if ProcessInfo.processInfo.arguments.contains("-HymioHomePreview") {
            HomeExperiencePreview(account: account)
              .preferredColorScheme(ProcessInfo.processInfo.arguments.contains("-HymioHomeDarkPreview") ? .dark : nil)
              .environment(\.dynamicTypeSize, ProcessInfo.processInfo.arguments.contains("-HymioHomeLargePreview") ? .accessibility3 : .large)
          } else if ProcessInfo.processInfo.arguments.contains("-HymioCalendarPreview") {
            CalendarWorkspacePreview(account: account)
          } else if ProcessInfo.processInfo.arguments.contains("-HymioTaskPreview") {
            TaskExperiencePreview(account: account)
          } else if ProcessInfo.processInfo.arguments.contains("-HymioConnectorsPreview") {
            NavigationStack { ConnectorsScreen(account: account, preview: true) }
          } else if ProcessInfo.processInfo.arguments.contains("-HymioBubblePreview") {
            ChatBubblePreview(account: account)
              .preferredColorScheme(ProcessInfo.processInfo.arguments.contains("-HymioBubbleDarkPreview") ? .dark : nil)
              .environment(\.dynamicTypeSize, ProcessInfo.processInfo.arguments.contains("-HymioBubbleLargePreview") ? .accessibility3 : .large)
          } else if ProcessInfo.processInfo.arguments.contains("-HymioActualChatPreview") {
            ActualChatPerformancePreview(account: account)
          } else if ProcessInfo.processInfo.arguments.contains("-HymioStreamingPreview") {
            StreamingPerformancePreview(account: account)
          } else if ProcessInfo.processInfo.arguments.contains("-HymioKitAppPreview") {
            KitAppPreviewScreen()
          } else if ProcessInfo.processInfo.arguments.contains("-HymioKitEditorPreview") {
            KitEditorPreviewScreen()
          } else if ProcessInfo.processInfo.arguments.contains("-HymioLiveActivityPreview") {
            LiveActivityPreviewScreen()
          } else if ProcessInfo.processInfo.arguments.contains("-HymioContextPreview") {
            ContextPreviewScreen(
              account: account.session == nil ? nil : account,
              empty: ProcessInfo.processInfo.arguments.contains("-HymioContextEmptyPreview")
            )
            .environment(
              \.dynamicTypeSize,
              ProcessInfo.processInfo.arguments.contains("-HymioContextLargeTextPreview")
                ? .accessibility3 : .large
            )
            .preferredColorScheme(
              ProcessInfo.processInfo.arguments.contains("-HymioContextDarkPreview") ? .dark : nil)
          } else if account.session != nil {
            ProductShell(account: account, client: client).equatable().id(account.session?.user_id)
          } else {
            LoginScreen(account: account)
          }
        #else
          if account.session != nil {
            ProductShell(account: account, client: client).equatable().id(account.session?.user_id)
          } else {
            LoginScreen(account: account)
          }
        #endif
      }
      .environmentObject(healthSync)
      .environmentObject(notifications)
      .tint(Brand.blue)
      .monospacedDigit()
      .onChange(of: account.session?.user_id) { _, value in
        if value == nil {
          client.reset()
          healthSync.stop(clearPending: true)
        } else {
          client.activate()
          Task { await healthSync.activate() }
          Task { await notifications.bind(account) }
        }
      }
      .onChange(of: scene) { _, phase in
        if phase == .active {
          client.activate()
          Task { await healthSync.activate() }
          Task { await notifications.updatePresence(account, active: true) }
        } else if phase == .background {
          client.enterBackground()
          Task { await notifications.updatePresence(account, active: false) }
        }
      }
      .task {
        client.activate()
        await healthSync.activate()
        await notifications.bind(account)
      }
      .onOpenURL { notifications.open(url: $0) }
    }
  }
}
