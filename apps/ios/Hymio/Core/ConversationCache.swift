import CryptoKit
import Foundation

public struct ConversationCache {
  private let url: URL
  public init(backend: String, user: String, root: URL? = nil) throws {
    let base =
      root
      ?? FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
      .appendingPathComponent("Conversations", isDirectory: true)
    try FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)
    let key = SHA256.hash(data: Data((backend + "|" + user).utf8)).map {
      String(format: "%02x", $0)
    }.joined()
    url = base.appendingPathComponent(key + ".json")
    var directory = base
    var values = URLResourceValues()
    values.isExcludedFromBackup = true
    try directory.setResourceValues(values)
  }
  public func load() throws -> ConversationState {
    guard FileManager.default.fileExists(atPath: url.path) else { return ConversationState() }
    return try JSONDecoder().decode(ConversationState.self, from: Data(contentsOf: url))
  }
  public func save(_ state: ConversationState) throws {
    #if os(iOS)
      try JSONEncoder().encode(state).write(
        to: url, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
    #else
      try JSONEncoder().encode(state).write(to: url, options: .atomic)
    #endif
  }
  public func clear() throws {
    if FileManager.default.fileExists(atPath: url.path) {
      try FileManager.default.removeItem(at: url)
    }
  }
}
