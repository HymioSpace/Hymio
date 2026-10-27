import Combine
import Foundation
import HealthKit
import UIKit

enum DeviceInstallation {
  private static let key = "hymio.connector.installation"

  static var id: String {
    if let value = UserDefaults.standard.string(forKey: key) { return value }
    let value = UUID().uuidString
    UserDefaults.standard.set(value, forKey: key)
    return value
  }
}

@MainActor
final class HealthEventSync: ObservableObject {
  @Published private(set) var monitoring = false
  @Published private(set) var message = ""

  private static let pendingKey = "hymio.health.background.pending_at"
  private let account: AccountService
  private let healthStore = HKHealthStore()
  private let installation = DeviceInstallation.id
  private let types: [HKQuantityType] = [
    HKQuantityType(.stepCount), HKQuantityType(.activeEnergyBurned),
  ]
  private var observers: [HKObserverQuery] = []
  private var connectionID: String?
  private var activeUserID = ""
  private var activationInFlight = false
  private var generation = UUID()
  private var manualGeneration: UUID?
  private var syncTask: Task<Void, Never>?
  private var backgroundTask = UIBackgroundTaskIdentifier.invalid

  init(account: AccountService) {
    self.account = account
  }

  /// Observer queries must be recreated after every launch. A recent catch-up
  /// upload also covers changes accumulated while the app was not running.
  func activate() async {
    guard !activationInFlight else { return }
    activationInFlight = true
    defer {
      activationInFlight = false
      if (account.session?.user_id ?? "") != activeUserID {
        Task { await activate() }
      }
    }
    guard let userID = account.session?.user_id else {
      stop(clearPending: true)
      activeUserID = ""
      return
    }
    if activeUserID != userID { stop(clearPending: true) }
    activeUserID = userID
    let cached = UserDefaults.standard.string(forKey: connectionKey(userID))
    if let cached, !cached.isEmpty {
      connectionID = cached
      await registerIfNeeded()
    }

    do {
      let value = try await account.request("connectors")
      guard account.session?.user_id == userID, activeUserID == userID else { return }
      guard
        let row = value["connections"].items.first(where: {
          $0["provider"].text == "apple_health"
            && $0["device_id"].text == installation
            && ($0["enabled"].flag || $0["enabled"].double > 0)
            && !["paused", "disconnected"].contains($0["state"].text)
        })
      else {
        stop(clearPending: true)
        return
      }
      connectionID = row["id"].text
      UserDefaults.standard.set(connectionID, forKey: connectionKey(userID))
      await registerIfNeeded()

      let lastSuccess = row["last_success"].double
      let stale = lastSuccess <= 0 || Date().timeIntervalSince1970 - lastSuccess > 15 * 60
      if pendingAt > 0 || stale {
        markPending()
        scheduleSync(background: UIApplication.shared.applicationState != .active)
      }
    } catch is CancellationError {
      return
    } catch {
      guard account.session?.user_id == userID, activeUserID == userID else { return }
      message = "后台健康同步稍后会重试。"
    }
  }

  /// The caller has already obtained explicit in-app and HealthKit consent.
  func enable(connectionID: String) async throws {
    guard let userID = account.session?.user_id else { throw ServiceError.unauthorized }
    if activeUserID != userID { stop(clearPending: true) }
    activeUserID = userID
    self.connectionID = connectionID
    UserDefaults.standard.set(connectionID, forKey: connectionKey(userID))
    await registerIfNeeded()
    try await syncNow(connectionID: connectionID)
  }

  func syncNow(connectionID: String) async throws {
    let epoch = generation
    if let syncTask { await syncTask.value }
    guard epoch == generation else { throw CancellationError() }
    guard manualGeneration == nil else { throw ServiceError.message("正在同步健康数据，请稍候。") }
    manualGeneration = epoch
    defer { if manualGeneration == epoch { manualGeneration = nil } }
    guard account.session != nil else { throw ServiceError.unauthorized }
    self.connectionID = connectionID
    markPending()
    let startedAt = pendingAt
    do {
      try await upload(connectionID: connectionID)
      guard epoch == generation else { throw CancellationError() }
      clearPending(through: startedAt)
      if monitoring { message = "" }
      if pendingAt > startedAt {
        Task {
          guard generation == epoch else { return }
          scheduleSync(background: UIApplication.shared.applicationState != .active)
        }
      }
    } catch {
      guard epoch == generation else { throw CancellationError() }
      message = "本次健康同步未完成；变化已标记，将在下次同步时重试。"
      throw error
    }
  }

  func stop(clearPending: Bool) {
    generation = UUID()
    manualGeneration = nil
    syncTask?.cancel()
    syncTask = nil
    for query in observers { healthStore.stop(query) }
    observers.removeAll()
    for type in types {
      healthStore.disableBackgroundDelivery(for: type) { _, _ in }
    }
    monitoring = false
    connectionID = nil
    if clearPending {
      UserDefaults.standard.removeObject(forKey: pendingKey)
      if !activeUserID.isEmpty {
        UserDefaults.standard.removeObject(forKey: connectionKey(activeUserID))
      }
    }
    endBackgroundTask()
  }

  private var pendingKey: String { Self.pendingKey + "." + activeUserID }

  private var pendingAt: Double {
    UserDefaults.standard.double(forKey: pendingKey)
  }

  private func markPending() {
    UserDefaults.standard.set(Date().timeIntervalSince1970, forKey: pendingKey)
  }

  private func clearPending(through startedAt: Double) {
    if pendingAt <= startedAt {
      UserDefaults.standard.removeObject(forKey: pendingKey)
    }
  }

  private func connectionKey(_ userID: String) -> String {
    "hymio.health.background.connection." + userID
  }

  private func registerIfNeeded() async {
    guard
      observers.count < types.count, connectionID != nil, HKHealthStore.isHealthDataAvailable()
    else { return }
    let epoch = generation
    for query in observers { healthStore.stop(query) }
    observers.removeAll()
    var failures: [String] = []
    for type in types {
      do {
        try await enableBackgroundDelivery(type)
        guard epoch == generation else { return }
      } catch {
        guard epoch == generation else { return }
        failures.append(error.localizedDescription)
        continue
      }
      let query = HKObserverQuery(sampleType: type, predicate: nil) {
        [weak self] _, completion, error in
        guard error == nil else {
          completion()
          return
        }
        Task { @MainActor [weak self] in
          if self?.generation == epoch { self?.eventReceived() }
          completion()
        }
      }
      observers.append(query)
      healthStore.execute(query)
    }
    monitoring = observers.count == types.count
    message =
      failures.isEmpty
      ? "" : "后台健康事件暂未启用；手动同步仍可使用，请检查 HealthKit 签名与系统权限。"
  }

  private func enableBackgroundDelivery(_ type: HKQuantityType) async throws {
    try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
      healthStore.enableBackgroundDelivery(for: type, frequency: .hourly) { success, error in
        if let error {
          continuation.resume(throwing: error)
        } else if success {
          continuation.resume()
        } else {
          continuation.resume(
            throwing: ServiceError.message("HealthKit Background Delivery 不可用"))
        }
      }
    }
  }

  private func eventReceived() {
    markPending()
    scheduleSync(background: UIApplication.shared.applicationState != .active)
  }

  private func scheduleSync(background: Bool) {
    guard syncTask == nil, manualGeneration == nil, connectionID != nil, account.session != nil else { return }
    if background {
      backgroundTask = UIApplication.shared.beginBackgroundTask(
        withName: "Hymio Health Event Sync"
      ) { [weak self] in
        Task { @MainActor in self?.endBackgroundTask() }
      }
    }
    let epoch = generation
    let startedAt = pendingAt
    syncTask = Task { @MainActor [weak self] in
      guard let self, let connectionID = self.connectionID else { return }
      do {
        try await self.upload(connectionID: connectionID)
        guard self.generation == epoch else { return }
        self.clearPending(through: startedAt)
        if self.monitoring { self.message = "" }
        self.syncTask = nil
        self.endBackgroundTask()
        if self.pendingAt > startedAt {
          self.scheduleSync(background: background)
        }
      } catch is CancellationError {
        guard self.generation == epoch else { return }
        self.syncTask = nil
        self.endBackgroundTask()
      } catch {
        guard self.generation == epoch else { return }
        self.message = "健康变化已记录；本次上传失败，将在下次同步时重试。"
        self.syncTask = nil
        self.endBackgroundTask()
      }
    }
  }

  private func upload(connectionID: String) async throws {
    guard let userID = account.session?.user_id, userID == activeUserID else {
      throw ServiceError.unauthorized
    }
    var payload = try await HealthSnapshot.payload(store: healthStore)
    try Task.checkCancellation()
    guard account.session?.user_id == userID, activeUserID == userID,
      self.connectionID == connectionID else { throw CancellationError() }
    payload["device_id"] = .string(installation)
    payload["consent"] = .bool(true)
    _ = try await account.request(
      "connectors/" + connectionID + "/ingest",
      body: .object(payload),
      timeout: 30
    )
  }

  private func endBackgroundTask() {
    if backgroundTask != .invalid {
      UIApplication.shared.endBackgroundTask(backgroundTask)
      backgroundTask = .invalid
    }
  }
}

private enum HealthSnapshot {
  static func payload(store: HKHealthStore) async throws -> [String: JSON] {
    let capturedAt = Date()
    var items: [JSON] = []
    let calendar = Calendar.current
    let today = calendar.startOfDay(for: Date())
    let formatter = DateFormatter()
    formatter.calendar = calendar
    formatter.dateFormat = "yyyy-MM-dd"
    formatter.locale = Locale(identifier: "en_US_POSIX")
    for offset in -6...0 {
      let start = calendar.date(byAdding: .day, value: offset, to: today)!
      let end = calendar.date(byAdding: .day, value: 1, to: start)!
      let steps = try await sum(
        HKQuantityType(.stepCount), unit: .count(), start: start, end: end, store: store)
      let energy = try await sum(
        HKQuantityType(.activeEnergyBurned), unit: .kilocalorie(), start: start, end: end,
        store: store)
      if steps == nil && energy == nil { continue }
      let day = formatter.string(from: start)
      items.append(
        .object([
          "external_id": .string("daily:" + day), "kind": .string("health_daily"),
          "day": .string(day), "title": .string(day + " 每日活动"),
          "steps": steps.map(JSON.number) ?? .null,
          "active_kcal": energy.map { .number(($0 * 10).rounded() / 10) } ?? .null,
        ]))
    }
    return ["items": .array(items), "captured_at": .number(capturedAt.timeIntervalSince1970)]
  }

  private static func sum(
    _ type: HKQuantityType, unit: HKUnit, start: Date, end: Date, store: HKHealthStore
  ) async throws -> Double? {
    try await withCheckedThrowingContinuation { continuation in
      let query = HKStatisticsQuery(
        quantityType: type,
        quantitySamplePredicate: HKQuery.predicateForSamples(withStart: start, end: end),
        options: .cumulativeSum
      ) { _, result, error in
        if let error, (error as? HKError)?.code != .errorNoData {
          continuation.resume(throwing: error)
        } else {
          continuation.resume(returning: result?.sumQuantity()?.doubleValue(for: unit))
        }
      }
      store.execute(query)
    }
  }
}
