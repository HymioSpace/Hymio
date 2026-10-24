import Combine
import Foundation
import ImageIO
import Security
import UIKit

enum ImagePipeline {
  static let attachmentMaxEdge: CGFloat = 2048
  static let displayMaxEdge: CGFloat = 4096

  static func attachment(_ data: Data) -> Data? {
    guard let source = CGImageSourceCreateWithData(data as CFData, nil) else { return nil }
    return attachment(source: source)
  }

  static func attachment(_ image: UIImage) -> Data? {
    let edge = max(image.size.width, image.size.height)
    let scale = min(1, attachmentMaxEdge / max(edge, 1))
    let size = CGSize(width: image.size.width * scale, height: image.size.height * scale)
    let renderer = UIGraphicsImageRenderer(size: size)
    let resized = renderer.image { _ in
      image.draw(in: CGRect(origin: .zero, size: size))
    }
    return resized.jpegData(compressionQuality: 0.76)
  }

  static func display(_ data: Data, maxPixel: CGFloat = displayMaxEdge) -> UIImage? {
    guard let source = CGImageSourceCreateWithData(data as CFData, nil) else { return nil }
    let options: [CFString: Any] = [
      kCGImageSourceCreateThumbnailFromImageAlways: true,
      kCGImageSourceCreateThumbnailWithTransform: true,
      kCGImageSourceThumbnailMaxPixelSize: Int(maxPixel),
      kCGImageSourceShouldCacheImmediately: true,
    ]
    guard let image = CGImageSourceCreateThumbnailAtIndex(source, 0, options as CFDictionary)
    else { return nil }
    return UIImage(cgImage: image)
  }

  private static func attachment(source: CGImageSource) -> Data? {
    let options: [CFString: Any] = [
      kCGImageSourceCreateThumbnailFromImageAlways: true,
      kCGImageSourceCreateThumbnailWithTransform: true,
      kCGImageSourceThumbnailMaxPixelSize: Int(attachmentMaxEdge),
      kCGImageSourceShouldCacheImmediately: true,
    ]
    guard let image = CGImageSourceCreateThumbnailAtIndex(source, 0, options as CFDictionary)
    else { return nil }
    return UIImage(cgImage: image).jpegData(compressionQuality: 0.76)
  }
}

struct LoginSession: Codable {
  var access_token: String
  var refresh_token: String
  var expires_at: Double
  var user_id: String
  var name: String
  var oath_ws: String
  var oath_biz: String
  var displayName: String {
    let value = name.trimmingCharacters(in: .whitespacesAndNewlines)
    return value.isEmpty || UUID(uuidString: value) != nil
      || value.range(of: "^[a-fA-F0-9]{32}$", options: .regularExpression) != nil ? "我的账号" : value
  }
}
enum ServiceError: LocalizedError {
  case message(String)
  case unauthorized
  var errorDescription: String? {
    switch self {
    case .message(let s): return s
    case .unauthorized: return "登录已过期，请重新登录。"
    }
  }
}
struct SecureSession {
  private static var query: [String: Any] {
    [
      kSecClass as String: kSecClassGenericPassword,
      kSecAttrService as String: Bundle.main.bundleIdentifier ?? "Hymio",
      kSecAttrAccount as String:
        (Bundle.main.object(forInfoDictionaryKey: "HymioBackendURL") as? String ?? "unconfigured"),
    ]
  }
  static func load() throws -> LoginSession? {
    var q = query
    q[kSecReturnData as String] = true
    q[kSecMatchLimit as String] = kSecMatchLimitOne
    var item: CFTypeRef?
    let status = SecItemCopyMatching(q as CFDictionary, &item)
    if status == errSecItemNotFound { return nil }
    guard status == errSecSuccess, let data = item as? Data else {
      throw ServiceError.message("无法读取安全凭据（\(status)）")
    }
    return try JSONDecoder().decode(LoginSession.self, from: data)
  }
  static func save(_ value: LoginSession) throws {
    let data = try JSONEncoder().encode(value)
    let status = SecItemUpdate(
      query as CFDictionary, [kSecValueData as String: data] as CFDictionary)
    if status == errSecItemNotFound {
      var q = query
      q[kSecValueData as String] = data
      q[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
      let added = SecItemAdd(q as CFDictionary, nil)
      guard added == errSecSuccess else { throw ServiceError.message("无法安全保存登录信息（\(added)）") }
      return
    }
    guard status == errSecSuccess else { throw ServiceError.message("无法更新安全凭据（\(status)）") }
  }
  static func clear() { SecItemDelete(query as CFDictionary) }
}

@MainActor final class AccountService: ObservableObject {
  @Published var session: LoginSession?
  @Published var busy = false
  @Published var error = ""
  let backend: URL
  private var refreshTask: Task<LoginSession, Error>?
  private var generation = UUID()
  private let imageCache: NSCache<NSString, NSData> = {
    let cache = NSCache<NSString, NSData>()
    cache.countLimit = 64
    cache.totalCostLimit = 64 * 1024 * 1024
    return cache
  }()
  init() {
    let value = Bundle.main.object(forInfoDictionaryKey: "HymioBackendURL") as? String ?? ""
    backend = URL(string: value) ?? URL(string: "https://invalid.example")!
    do { session = try SecureSession.load() } catch { self.error = error.localizedDescription }
  }
  func validated(_ url: URL, socket: Bool = false) throws {
    #if DEBUG
      let schemes = socket ? ["ws", "wss"] : ["http", "https"]
    #else
      let schemes = socket ? ["wss"] : ["https"]
    #endif
    guard schemes.contains(url.scheme ?? ""), url.host != nil, url.user == nil, url.password == nil,
      !url.absoluteString.contains("invalid.example")
    else { throw ServiceError.message("服务尚未配置，请联系部署者。") }
  }
  func raw(_ path: String, body: JSON? = nil, token: String? = nil, timeout: Double = 25, idempotencyKey: String? = nil)
    async throws -> Data
  {
    guard let url = URL(string: path, relativeTo: backend.appendingPathComponent("/"))?.absoluteURL
    else { throw ServiceError.message("服务地址无效") }
    try validated(url)
    var req = URLRequest(url: url)
    req.timeoutInterval = timeout
    if let idempotencyKey { req.setValue(idempotencyKey, forHTTPHeaderField: "Idempotency-Key") }
    if let body {
      req.httpMethod = "POST"
      req.httpBody = try JSONEncoder().encode(body)
      req.setValue("application/json", forHTTPHeaderField: "Content-Type")
    }
    if let token { req.setValue("Bearer " + token, forHTTPHeaderField: "Authorization") }
    let (data, response) = try await NoRedirects.session.data(for: req)
    guard let response = response as? HTTPURLResponse else { throw ServiceError.message("服务响应无效") }
    if response.statusCode == 403,
      let failure = try? JSON.decode(data), failure["error"].text == "invalid_invitation"
    {
      throw ServiceError.message("邀请码不正确，请重新输入。")
    }
    if response.statusCode == 401 { throw ServiceError.unauthorized }
    guard (200..<300).contains(response.statusCode) else {
      let failure = try? JSON.decode(data)
      let code = failure?["error"].text ?? ""
      let conflicts = [
        "device_busy_or_requires_recovery":
          "上一次云端操作尚未结束。过期记录会自动核对，原操作不会重复执行。",
        "device_busy_or_outcome_unknown":
          "上一次云端操作结果未知。系统会先确认远端状态，请稍后重试。",
        "device_running_or_requires_recovery": "云电脑仍有一条执行记录，请稍后重试。",
        "device_unavailable": "云电脑暂时无法连接，原环境和文件仍会保留。",
        "provision_requires_recovery": "云电脑创建结果尚在核对，请稍后重试。",
      ]
      throw ServiceError.message(
        response.statusCode == 409
          ? conflicts[code] ?? "设备状态正在变化，请稍后重试。"
          : "服务暂不可用（\(response.statusCode)）")
    }
    return data
  }
  func login(username: String, password: String, signup: Bool, invitationCode: String = "") async {
    guard !busy else { return }
    busy = true
    error = ""
    defer { busy = false }
    do {
      let options = try JSON.decode(await raw("auth/options"))
      guard options["login_method"].text == "account" else {
        throw ServiceError.message("当前部署未启用账号登录，请联系部署者。")
      }
      let data = try await raw(
        "auth/account",
        body: .object([
          "action": .string(signup ? "signup" : "login"), "username": .string(username),
          "password": .string(password), "invitation_code": .string(signup ? invitationCode : ""),
        ]))
      var next = try JSONDecoder().decode(LoginSession.self, from: data)
      if next.displayName == "我的账号" { next.name = username }
      do { try SecureSession.save(next) } catch {
        _ = try? await raw("auth/logout", body: .object([:]), token: next.access_token)
        throw error
      }
      session = next
      generation = UUID()
    } catch ServiceError.unauthorized {
      error = "未能登录或创建账号，请检查用户名和密码。"
    } catch { self.error = error.localizedDescription }
  }
  func credential() async throws -> LoginSession {
    guard let current = session else { throw ServiceError.unauthorized }
    if current.expires_at > Date().timeIntervalSince1970 + 60 { return current }
    if let refreshTask { return try await refreshTask.value }
    let owner = generation
    let task = Task { () throws -> LoginSession in
      let data = try await self.raw(
        "auth/refresh", body: .object(["refresh_token": .string(current.refresh_token)]))
      var next = try JSONDecoder().decode(LoginSession.self, from: data)
      if next.displayName == "我的账号" { next.name = current.name }
      guard owner == self.generation else { throw CancellationError() }
      try SecureSession.save(next)
      self.session = next
      return next
    }
    refreshTask = task
    defer { refreshTask = nil }
    do { return try await task.value } catch ServiceError.unauthorized {
      error = "登录已过期，请重新登录。"
      throw ServiceError.unauthorized
    }
  }
  func request(_ path: String, body: JSON? = nil, timeout: Double = 25, idempotencyKey: String? = nil) async throws -> JSON {
    let s = try await credential()
    let owner = generation
    let data = try await raw(path, body: body, token: s.access_token, timeout: timeout, idempotencyKey: idempotencyKey)
    let value = try await Task.detached(priority: .userInitiated) {
      try JSON.decode(data)
    }.value
    guard owner == generation else { throw CancellationError() }
    return value
  }
  func logout() async {
    generation = UUID()
    refreshTask?.cancel()
    refreshTask = nil
    let old = session
    session = nil
    SecureSession.clear()
    if let old { _ = try? await raw("auth/logout", body: .object([:]), token: old.access_token) }
  }
  func upload(_ data: Data, name: String) async throws -> JSON {
    guard data.count <= 20 * 1024 * 1024 else { throw ServiceError.message("单个文件不能超过 20 MB") }
    let session = try await credential()
    let url = backend.appendingPathComponent("attachments")
    try validated(url)
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.httpBody = data
    request.timeoutInterval = 60
    request.setValue("Bearer " + session.access_token, forHTTPHeaderField: "Authorization")
    request.setValue(
      name.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed),
      forHTTPHeaderField: "X-File-Name")
    let (result, response) = try await NoRedirects.session.data(for: request)
    guard let response = response as? HTTPURLResponse, response.statusCode == 201 else {
      throw ServiceError.message("附件上传失败，请检查文件格式后重试。")
    }
    let value = try JSON.decode(result)
    if value["mime"].text.hasPrefix("image/"), !value["url"].text.isEmpty {
      imageCache.setObject(
        data as NSData, forKey: value["url"].text as NSString, cost: data.count)
    }
    return value
  }
  func downloadAttachment(_ path: String) async throws -> URL {
    guard path.range(of: "^/attachments/[a-f0-9]{32}$", options: .regularExpression) != nil else {
      throw ServiceError.message("文件地址无效")
    }
    let session = try await credential()
    let url = backend.appendingPathComponent(String(path.dropFirst()))
    try validated(url)
    var request = URLRequest(url: url)
    request.setValue("Bearer " + session.access_token, forHTTPHeaderField: "Authorization")
    request.timeoutInterval = 30
    let (data, response) = try await NoRedirects.session.data(for: request)
    guard let response = response as? HTTPURLResponse, response.statusCode == 200 else {
      throw ServiceError.message("文件暂不可用")
    }
    let header = response.value(forHTTPHeaderField: "Content-Disposition") ?? ""
    let encoded = header.components(separatedBy: "filename*=UTF-8''").last ?? "attachment"
    let name = URL(fileURLWithPath: encoded.removingPercentEncoding ?? "attachment")
      .lastPathComponent
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    let target = folder.appendingPathComponent(name.isEmpty ? "attachment" : name)
    try data.write(to: target, options: .atomic)
    return target
  }
  func image(_ source: String) async throws -> Data {
    guard let url = URL(string: source, relativeTo: backend)?.absoluteURL else {
      throw ServiceError.message("图片地址无效")
    }
    let protected = url.path.hasPrefix("/devices/media/") || url.path.hasPrefix("/attachments/")
    if protected {
      // Only the configured backend receives authentication, even if a model invents a host.
      let path = url.path
      guard
        path.range(of: "^/(?:devices/media|attachments)/[a-f0-9]{32}$", options: .regularExpression)
          != nil
      else { throw ServiceError.message("图片地址无效") }
      if let cached = imageCache.object(forKey: path as NSString) { return cached as Data }
      let s = try await credential()
      let data = try await raw(String(path.dropFirst()), token: s.access_token)
      if data.count <= 20 * 1024 * 1024 {
        imageCache.setObject(data as NSData, forKey: path as NSString, cost: data.count)
      }
      return data
    }
    guard url.scheme?.lowercased() == "https", url.user == nil, url.password == nil else {
      throw ServiceError.message("仅支持 HTTPS 图片或当前账号的截图附件")
    }
    var request = URLRequest(url: url)
    request.timeoutInterval = 20
    let (data, response) = try await NoRedirects.session.data(for: request)
    guard let response = response as? HTTPURLResponse, response.statusCode == 200,
      response.mimeType?.hasPrefix("image/") == true, data.count <= 20 * 1024 * 1024
    else { throw ServiceError.message("图片加载失败") }
    imageCache.setObject(data as NSData, forKey: source as NSString, cost: data.count)
    return data
  }
}
