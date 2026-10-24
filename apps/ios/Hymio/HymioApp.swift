import SwiftUI

@main struct HymioApp: App {
  @StateObject private var account: AccountService
  @StateObject private var client: AgentClient
  @Environment(\.scenePhase) private var scene
  init() {
    let service = AccountService()
    _account = StateObject(wrappedValue: service)
    _client = StateObject(wrappedValue: AgentClient(account: service))
  }
  var body: some Scene {
    WindowGroup {
      Group {
        #if DEBUG
          if ProcessInfo.processInfo.arguments.contains("-HymioContextPreview") {
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
            ProductShell(account: account, client: client).id(account.session?.user_id)
          } else {
            LoginScreen(account: account)
          }
        #else
          if account.session != nil {
            ProductShell(account: account, client: client).id(account.session?.user_id)
          } else {
            LoginScreen(account: account)
          }
        #endif
      }
      .tint(Brand.blue)
      .onChange(of: account.session?.user_id) { _, value in
        if value == nil { client.reset() } else { client.activate() }
      }
      .onChange(of: scene) { _, phase in
        if phase == .active { client.activate() } else if phase == .background { client.suspend() }
      }
      .task { client.activate() }
    }
  }
}
