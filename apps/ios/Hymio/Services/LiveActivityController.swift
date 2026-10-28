import ActivityKit
import Foundation

@MainActor
final class LiveActivityController: ObservableObject {
  private var activity: Activity<HymioActivityAttributes>?
  private var tokenTask: Task<Void, Never>?
  private var finishing: Task<Void, Never>?

  init() {
    activity = Activity<HymioActivityAttributes>.activities.first
  }

  private var enabled: Bool {
    let key = "hymio.live-activity-enabled"
    return UserDefaults.standard.object(forKey: key) as? Bool ?? true
  }

  private var showDetails: Bool {
    UserDefaults.standard.bool(forKey: "hymio.push-show-details")
  }

  func sync(
    account: AccountService, items: [JSON], chatWorking: Bool, chatAwaiting: Bool,
    leavingApp: Bool = false
  ) async {
    if let activity, activity.activityState != .active {
      tokenTask?.cancel()
      tokenTask = nil
      self.activity = nil
    }
    if !enabled || !ActivityAuthorizationInfo().areActivitiesEnabled {
      if activity != nil { await finish(account: account) }
      return
    }
    let runs = items.compactMap { item -> (JSON, JSON)? in
      guard item["state"].text == "active", let run = item["runs"].items.first else {
        return nil
      }
      return (item, run)
    }
    let active = runs.filter {
      ["running", "ready", "delivering"].contains($0.1["status"].text)
    }
    let waiting = runs.filter { $0.1["status"].text == "blocked" }
    let working = chatWorking || chatAwaiting || !active.isEmpty
    guard working || !waiting.isEmpty || activity != nil else { return }
    if activity == nil {
      guard leavingApp, working || !waiting.isEmpty else { return }
      let now = Int(Date().timeIntervalSince1970)
      let first = active.first ?? waiting.first
      let title =
        showDetails && !(first?.0["title"].text.isEmpty ?? true)
        ? first!.0["title"].text : "Hymio"
      let phase =
        !waiting.isEmpty ? "等待你确认"
        : chatWorking || chatAwaiting ? "正在整理和推进"
        : active.first?.1["phase"].text.nonEmpty ?? "正在处理"
      let state = HymioActivityAttributes.ContentState(
        title: title,
        phase: String(phase.prefix(72)),
        status: !waiting.isEmpty ? "waiting" : "working",
        activeCount: max(active.count, chatWorking || chatAwaiting ? 1 : 0),
        startedAt: now,
        updatedAt: now,
        taskID: active.first?.0["id"].text ?? waiting.first?.0["id"].text ?? ""
      )
      do {
        let next = try Activity.request(
          attributes: HymioActivityAttributes(
            aggregateID: "hymio-" + account.session!.user_id),
          content: ActivityContent(state: state, staleDate: Date().addingTimeInterval(8 * 3600)),
          pushType: .token
        )
        activity = next
        observeToken(next, account: account)
      } catch {
        activity = nil
      }
      return
    }
    finishing?.cancel()
    finishing = nil
    let now = Int(Date().timeIntervalSince1970)
    let current = activity?.content.state
    if working || !waiting.isEmpty {
      let first = active.first ?? waiting.first
      let title =
        showDetails && !(first?.0["title"].text.isEmpty ?? true)
        ? first!.0["title"].text : "Hymio"
      let phase =
        !waiting.isEmpty ? "等待你确认"
        : chatWorking || chatAwaiting ? "正在整理和推进"
        : active.first?.1["phase"].text.nonEmpty ?? "正在处理"
      let next = HymioActivityAttributes.ContentState(
        title: title,
        phase: String(phase.prefix(72)),
        status: !waiting.isEmpty ? "waiting" : "working",
        activeCount: max(active.count, chatWorking || chatAwaiting ? 1 : 0),
        startedAt: current?.startedAt ?? now,
        updatedAt: now,
        taskID: active.first?.0["id"].text ?? waiting.first?.0["id"].text ?? ""
      )
      guard next != current else { return }
      await activity?.update(
        ActivityContent(state: next, staleDate: Date().addingTimeInterval(8 * 3600)))
    } else if let current {
      finishing = Task { [weak self] in
        try? await Task.sleep(for: .seconds(2))
        guard !Task.isCancelled else { return }
        let done = HymioActivityAttributes.ContentState(
          title: current.title,
          phase: "已完成",
          status: "completed",
          activeCount: 0,
          startedAt: current.startedAt,
          updatedAt: Int(Date().timeIntervalSince1970),
          taskID: current.taskID
        )
        await self?.activity?.update(ActivityContent(state: done, staleDate: nil))
        await self?.finish(account: account)
      }
    }
  }

  private func finish(account: AccountService) async {
    guard let activity else { return }
    let state = activity.content.state
    let done = HymioActivityAttributes.ContentState(
      title: state.title,
      phase: "已完成",
      status: "completed",
      activeCount: 0,
      startedAt: state.startedAt,
      updatedAt: Int(Date().timeIntervalSince1970),
      taskID: state.taskID
    )
    await activity.end(
      ActivityContent(state: done, staleDate: nil),
      dismissalPolicy: .after(Date().addingTimeInterval(15 * 60))
    )
    await PushNotificationManager.shared.unregisterLiveActivity(
      account, activityID: activity.id)
    tokenTask?.cancel()
    tokenTask = nil
    self.activity = nil
  }

  private func observeToken(_ activity: Activity<HymioActivityAttributes>, account: AccountService) {
    tokenTask?.cancel()
    tokenTask = Task { [weak self] in
      for await token in activity.pushTokenUpdates {
        let value = token.map { String(format: "%02x", $0) }.joined()
        await PushNotificationManager.shared.registerLiveActivity(
          account,
          activityID: activity.id,
          token: value,
          state: activity.content.state.status,
          summary: activity.content.state.title,
          taskID: ""
        )
        guard self != nil else { return }
      }
    }
  }
}

private extension String {
  var nonEmpty: String? { isEmpty ? nil : self }
}
