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
        if account.session != nil {
          ChatScreen(account: account, client: client)
        } else {
          LoginScreen(account: account)
        }
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
