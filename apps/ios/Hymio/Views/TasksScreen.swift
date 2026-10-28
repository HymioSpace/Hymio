import SwiftUI

func taskStatus(_ item: JSON) -> String {
  item["state"].text == "active"
    ? (item["runs"].items.first?["status"].text ?? "scheduled") : item["state"].text
}
func taskLabel(_ state: String) -> String {
  [
    "scheduled": "已安排", "delivering": "正在送达", "ready": "等已安排", "running": "进行中", "blocked": "需要关注",
    "succeeded": "已完成", "failed": "未完成", "expired": "已过期", "cancelled": "已取消", "paused": "已暂停",
  ][state] ?? state
}
func taskDate(_ stamp: Double) -> String {
  Date(timeIntervalSince1970: stamp).formatted(.dateTime.month(.abbreviated).day().hour().minute())
}
private func taskTimestamp(_ text: String) -> Date? {
  let parser = ISO8601DateFormatter()
  parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
  return parser.date(from: text) ?? ISO8601DateFormatter().date(from: text)
}
func taskSchedule(_ value: JSON) -> String {
  switch value["mode"].text {
  case "daily": return "每天 \(value["time"].text)"
  case "weekly":
    return
      "每周\(["一","二","三","四","五","六","日"][max(0,min(6,value["weekday"].int))]) \(value["time"].text)"
  case "once":
    return taskTimestamp(value["at"].text)?.formatted(date: .abbreviated, time: .shortened)
      ?? "等待时间确认"
  default: return "即刻开始"
  }
}

struct TasksScreen: View {
  @ObservedObject var account: AccountService
  @ObservedObject var board: TaskBoard
  let onAccount: () -> Void
  @State private var filter = 0
  @State private var agenda = false
  @State private var creating = false
  private let groups: [(String, [String])] = [
    ("需要你看看", ["blocked", "failed"]),
    ("Hymio 正在做", ["running", "ready", "delivering"]),
    ("等时间开始", ["scheduled", "paused"]),
    ("已结束", ["succeeded", "expired", "cancelled"]),
  ]
  private func visible(_ states: [String]) -> [JSON] {
    board.items.filter { item in
      let state = taskStatus(item)
      let included =
        filter == 0
        ? !["succeeded", "expired", "cancelled"].contains(state)
        : filter == 1
          ? ["scheduled", "paused"].contains(state)
          : ["succeeded", "expired", "cancelled"].contains(state)
      return included && states.contains(state)
    }
  }
  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 24) {
        VStack(alignment: .leading, spacing: 8) {
          Text("交给 Hymio 的事").font(.system(.title, design: .rounded, weight: .semibold)).tracking(
            -0.7)
          Text("进展、下一步，还有带回来的结果。").font(.subheadline).foregroundStyle(Brand.muted)
        }.padding(.top, 16)
        Picker("筛选任务", selection: $filter) {
          Text("未完成").tag(0)
          Text("已安排").tag(1)
          Text("已结束").tag(2)
        }.pickerStyle(.segmented)
        if !board.error.isEmpty {
          HStack {
            Text(board.error).font(.footnote).foregroundStyle(Brand.muted)
            Spacer()
            Button("重试") { Task { await board.refresh(account) } }.frame(minHeight: 44)
          }
        } else if !board.loaded {
          ProgressView("正在读取任务…").font(.footnote).frame(maxWidth: .infinity).padding(.vertical, 40)
        } else if groups.allSatisfy({ visible($0.1).isEmpty }) {
          VStack(spacing: 16) {
            Companion(size: 80)
            Text(filter == 2 ? "暂无已结束任务" : "还没有任务").font(.headline)
            Text("在对话里交代，或在这里安排。")
              .font(.subheadline).foregroundStyle(Brand.muted)
            Button("安排一件事", systemImage: "plus") { creating = true }.buttonStyle(.bordered)
          }.frame(maxWidth: .infinity).padding(.vertical, 35)
        }
        Toggle("按日期查看", isOn: $agenda).font(.subheadline)
        if agenda {
          ForEach(board.items.filter { taskStatus($0) == "scheduled" }.sorted {
            ($0["runs"].items.first?["due_at"].double ?? 0) < ($1["runs"].items.first?["due_at"].double ?? 0)
          }, id: \.self) { item in
            NavigationLink {
              TaskDetailScreen(account: account, taskID: item["id"].text, initial: item,
                               onViewed: { board.markSeen($0) })
            } label: {
              HStack(alignment: .top, spacing: 16) {
                Text(taskSchedule(item["schedule"])).font(.caption).foregroundStyle(Brand.muted)
                  .frame(width: 110, alignment: .leading)
                Text(item["title"].text).font(.subheadline).foregroundStyle(Brand.ink)
              }.padding(.vertical, 12)
            }
            Divider()
          }
        }
        ForEach(agenda ? [] : Array(groups.indices), id: \.self) { index in
          let values = visible(groups[index].1)
          if !values.isEmpty {
            VStack(alignment: .leading, spacing: 12) {
              HStack {
                Text(groups[index].0).font(.subheadline.weight(.semibold))
                Text("\(values.count)").font(.caption).foregroundStyle(Brand.muted)
              }
              ForEach(values, id: \.self) { item in
                NavigationLink {
                  TaskDetailScreen(
                    account: account, taskID: item["id"].text, initial: item,
                    onViewed: { board.markSeen($0) })
                } label: {
                  TaskSummaryCard(item: item)
                }.buttonStyle(GentlePress())
              }
            }
          }
        }
      }.padding(.horizontal, 22).padding(.bottom, 28).frame(maxWidth: 680).frame(
        maxWidth: .infinity)
    }.background(Brand.surface).navigationTitle("任务").navigationBarTitleDisplayMode(.inline)
      .toolbar {
        ToolbarItemGroup(placement: .topBarLeading) {
          AccountButton(account: account, action: onAccount)
        }.accountUnframed()
        ToolbarItem(placement: .topBarTrailing) {
          Button("安排一件事", systemImage: "plus") { creating = true }
        }
      }
      .sheet(isPresented: $creating, onDismiss: { Task { await board.refresh(account) } }) {
        TaskEditor(account: account)
      }.refreshable { await board.refresh(account) }
  }
}

struct TaskDetailScreen: View {
  @ObservedObject var account: AccountService
  let taskID: String
  let initial: JSON
  var previewMode = false
  var onViewed: (JSON) -> Void = { _ in }
  @Environment(\.dismiss) private var dismiss
  @State private var value: JSON = .null
  @State private var error = ""
  @State private var busy = false
  @State private var editing = false
  @State private var deleting = false
  @State private var continuation = ""
  private var item: JSON { value == .null ? initial : value }
  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 20) {
        VStack(alignment: .leading, spacing: 14) {
          HStack {
            Label(taskLabel(taskStatus(item)), systemImage: taskSymbol(taskStatus(item))).font(
              .caption
            ).foregroundStyle(
              ["failed", "blocked"].contains(taskStatus(item)) ? Brand.attention : Brand.muted)
            Spacer()
            Label(
              item["source"].text == "conversation" ? "来自对话" : taskSchedule(item["schedule"]),
              systemImage: item["source"].text == "conversation" ? "bubble.left" : "calendar"
            ).font(.system(size: 11))
              .foregroundStyle(.secondary)
          }
          Text(item["title"].text).font(.system(.title, design: .rounded, weight: .semibold))
            .tracking(-0.8)
          DisclosureGroup("任务信息") {
          Text(item["objective"].text).font(.subheadline).foregroundStyle(.secondary).lineSpacing(4)
          VStack(alignment: .leading, spacing: 7) {
            Label("怎样算完成", systemImage: "flag").font(.caption).foregroundStyle(.tertiary)
            Text(item["success_criteria"].text).font(.subheadline).foregroundStyle(.secondary)
          }.padding(.top, 6)
          }.font(.subheadline)
        }
        if let run = item["runs"].items.first, !run["result"].text.isEmpty {
          VStack(alignment: .leading, spacing: 13) {
            Label(
              run["status"].text == "succeeded" ? "这次的成果" : "最新进展", systemImage: "checkmark.circle"
            ).font(.caption).foregroundStyle(Brand.muted)
            MessageContent(content: run["result"].text, account: account)
          }.frame(maxWidth: .infinity, alignment: .leading).padding(20).background(
            Brand.mist, in: RoundedRectangle(cornerRadius: 16))
        }
        if let run = item["runs"].items.first, ["running", "blocked"].contains(run["status"].text),
          !run["progress"].text.isEmpty || !run["phase"].text.isEmpty
            || !run["next_step"].text.isEmpty
        {
          VStack(alignment: .leading, spacing: 10) {
            Label(
              run["status"].text == "blocked" ? "等待解决" : "推进到这里",
              systemImage: "point.topleft.down.to.point.bottomright.curvepath"
            )
            .font(.caption.weight(.medium)).foregroundStyle(Brand.blue)
            if !run["phase"].text.isEmpty { Text(run["phase"].text).font(.headline) }
            if !run["progress"].text.isEmpty {
              Text(run["progress"].text).font(.subheadline).foregroundStyle(Brand.ink)
            }
            if !run["next_step"].text.isEmpty {
              Divider()
              Label("下一步 · \(run["next_step"].text)", systemImage: "arrow.up.right")
                .font(.subheadline).foregroundStyle(Brand.muted)
            }
            if run["status"].text == "blocked" {
              TextField("补充决定或新的要求", text: $continuation, axis: .vertical)
                .font(.subheadline).lineLimit(1...3).padding(.vertical, 8)
              if run["resume_at"].double > 0 {
                Text("下次跟进：" + taskDate(run["resume_at"].double)).font(.caption).foregroundStyle(Brand.muted)
              }
              Button("继续推进", systemImage: "play") { Task { await action("continue") } }
                .font(.subheadline).frame(minHeight: 44).disabled(busy)
            }
          }.frame(maxWidth: .infinity, alignment: .leading).padding(18)
            .background(Brand.mist, in: RoundedRectangle(cornerRadius: 16))
        }
        if let agentID = item["runs"].items.first?["agent_id"].text,
           !agentID.isEmpty && agentID != "pending" {
          AgentActivityView(account: account, agentID: agentID)
        }
        Divider()
        HStack {
          Text("进展记录").font(.caption).foregroundStyle(.secondary)
          Spacer()
          Text("\(item["runs"].items.count) 次执行").font(.caption2).foregroundStyle(.tertiary)
        }
        ForEach(item["runs"].items, id: \.self) { run in
          VStack(alignment: .leading, spacing: 16) {
            if item["runs"].items.count > 1 {
            HStack {
              Text(taskLabel(run["status"].text)).font(.caption).foregroundStyle(Brand.muted)
              Spacer()
              Text(
                taskDate(
                  run["started_at"].double > 0 ? run["started_at"].double : run["due_at"].double)
              ).font(.caption2).foregroundStyle(.tertiary)
            }
            }
            if !run["agent_id"].text.isEmpty {
              Label("独立专家协作", systemImage: "sparkles").font(.caption2).foregroundStyle(.secondary)
            }
            ForEach(run["updates"].items, id: \.self) { note in
              HStack(alignment: .top, spacing: 12) {
                Circle().fill(Brand.blue.opacity(0.3)).frame(width: 5, height: 5).padding(.top, 6)
                VStack(alignment: .leading, spacing: 6) {
                  HStack {
                    Text(taskDate(note["created_at"].double)).foregroundStyle(.secondary)
                    if !note["status"].text.isEmpty {
                      Text(taskLabel(note["status"].text)).foregroundStyle(Brand.blue)
                    }
                  }.font(.caption2)
                  if !note["phase"].text.isEmpty {
                    Text(note["phase"].text).font(.subheadline.weight(.medium))
                  }
                  TaskNotePreview(content: note["content"].text)
                }
              }
            }
            if run["updates"].items.isEmpty {
              Text("进展和成果会记录在这里。").font(.caption).foregroundStyle(.tertiary)
            }
          }.padding(.leading, 14).overlay(alignment: .leading) { Rectangle().fill(Brand.line).frame(width: 1) }.padding(.vertical, 6)
        }
        if !error.isEmpty { Text(error).font(.caption).foregroundStyle(.secondary) }
      }.padding(24)
    }.onAppear { onViewed(item) }.background(Brand.surface).navigationTitle("任务详情")
      .navigationBarTitleDisplayMode(.inline)
      .toolbarBackground(.ultraThinMaterial, for: .navigationBar)
      .toolbar {
        ToolbarItem(placement: .topBarTrailing) {
          Menu {
            if ["paused", "cancelled"].contains(item["state"].text) {
              Button("重新安排", systemImage: "play") { Task { await action("resume") } }
            } else {
              if item["source"].text != "conversation",
                !["succeeded", "failed", "expired", "cancelled"].contains(
                  item["runs"].items.first?["status"].text ?? "")
              {
                Button("暂停日程", systemImage: "pause") { Task { await action("pause") } }
              }
              Button("取消任务", systemImage: "xmark.circle") { Task { await action("cancel") } }
            }
            Button("编辑", systemImage: "pencil") { editing = true }.disabled(
              ["running", "blocked"].contains(item["runs"].items.first?["status"].text ?? ""))
            Button("删除任务", systemImage: "trash", role: .destructive) { deleting = true }
          } label: {
            Image(systemName: "ellipsis").frame(width: 30, height: 30)
          }.disabled(busy)
        }
      }
      .confirmationDialog("删除任务并取消尚未完成的工作？", isPresented: $deleting, titleVisibility: .visible) {
        Button("删除任务", role: .destructive) {
          Task {
            await action("delete")
            if error.isEmpty { dismiss() }
          }
        }
      }
      .sheet(isPresented: $editing, onDismiss: { Task { await load() } }) {
        TaskEditor(account: account, existing: item)
      }
      .task {
        guard !previewMode else { return }
        while !Task.isCancelled {
          await load()
          do { try await Task.sleep(for: .seconds(5)) } catch { return }
        }
      }
  }
  private func load() async {
    do {
      value = try await account.request(
        "tasks", body: .object(["action": .string("get"), "task_id": .string(taskID)]))
      error = ""
      onViewed(value)
    } catch { self.error = "暂时无法读取最新进展。" }
  }
  private func action(_ action: String) async {
    busy = true
    defer { busy = false }
    do {
      _ = try await account.request(
        "tasks", body: .object(["action": .string(action), "task_id": .string(taskID), "content": .string(continuation)]))
      error = ""
      await load()
    } catch { self.error = "操作未完成，请稍后再试。" }
  }
}

private struct TaskNotePreview: View {
  let content: String
  @State private var expanded = false
  var body: some View {
    VStack(alignment: .leading, spacing: 4) {
      Text(content).font(.subheadline).foregroundStyle(Brand.muted).lineSpacing(4)
        .lineLimit(expanded ? nil : 3).textSelection(.enabled)
      if content.count > 120 || content.components(separatedBy: "\n").count > 3 {
        Button(expanded ? "收起" : "展开") { expanded.toggle() }
          .font(.caption).frame(minHeight: 44)
      }
    }
  }
}

private struct TaskEditor: View {
  @ObservedObject var account: AccountService
  @EnvironmentObject private var notifications: PushNotificationManager
  var existing: JSON = .null
  @Environment(\.dismiss) private var dismiss
  @State private var title = ""
  @State private var objective = ""
  @State private var criteria = ""
  @State private var mode = "now"
  @State private var kind = "task"
  @State private var grace = 900
  @State private var date = Date().addingTimeInterval(3600)
  @State private var weekday = 0
  @State private var requestID = UUID().uuidString
  @State private var busy = false
  @State private var error = ""
  @FocusState private var editingText: Bool
  var body: some View {
    NavigationStack {
      Form {
        Section {
          Picker("想交代什么", selection: $kind) {
            Text("帮我做件事").tag("task")
            Text("到时提醒我").tag("reminder")
          }.pickerStyle(.segmented)
          Text(kind == "reminder" ? "在约定的时间，把这件事提醒给你。" : "交代目标，Hymio 会推进并带回结果。")
            .font(.footnote).foregroundStyle(Brand.muted)
        }.listRowBackground(Brand.surface)
        Section("这件事叫什么") {
          TextField(kind == "reminder" ? "例如，提醒我出门" : "例如，整理周末出游路线", text: $title).focused(
            $editingText)
        }
        Section(kind == "reminder" ? "提醒内容" : "希望完成什么") {
          TextField("背景、范围，以及你关心的重点", text: $objective, axis: .vertical).lineLimit(3...7).focused(
            $editingText)
        }
        Section {
          Picker("开始时间", selection: $mode) {
            Text("现在").tag("now")
            Text("选个时间").tag("once")
            Text("每天").tag("daily")
            Text("每周").tag("weekly")
          }
          if mode == "weekly" {
            Picker("每周", selection: $weekday) {
              ForEach(0..<7) { i in Text(["周一", "周二", "周三", "周四", "周五", "周六", "周日"][i]).tag(i) }
            }
          }
          if mode != "now" {
            DatePicker(
              "时间", selection: $date,
              displayedComponents: mode == "once" ? [.date, .hourAndMinute] : [.hourAndMinute]
            )
            .environment(\.timeZone, timeZone)
          }
        } header: {
          Text("什么时候开始")
        } footer: {
          Text("\(timeZone.identifier) · 关闭 App 后，已安排的工作仍会继续。")
        }
        Section {
          DisclosureGroup("更多设置") {
            TextField("完成标准（可选）", text: $criteria, axis: .vertical).lineLimit(2...4).focused(
              $editingText)
            if mode != "now" {
              Picker("错过时间后", selection: $grace) {
                ForEach(Array(Set([60, 300, 900, 3600, grace])).sorted(), id: \.self) { seconds in
                  Text("\(seconds / 60) 分钟内补执行").tag(seconds)
                }
              }
            }
          }.foregroundStyle(Brand.muted)
        }
        if !error.isEmpty { Text(error).font(.footnote).foregroundStyle(Brand.attention) }
      }.navigationTitle(existing == .null ? "安排一件事" : "编辑任务")
        .navigationBarTitleDisplayMode(.inline).scrollDismissesKeyboard(.interactively)
        .onChange(of: kind) { _, next in
          if existing == .null && next == "reminder" && mode == "now" { mode = "once" }
        }
        .toolbar {
          ToolbarItemGroup(placement: .keyboard) {
            Spacer()
            Button("完成", systemImage: "keyboard.chevron.compact.down") { editingText = false }
          }
          ToolbarItem(placement: .cancellationAction) { Button("取消") { dismiss() }.disabled(busy) }
          ToolbarItem(placement: .confirmationAction) {
            Button {
              Task { await save() }
            } label: {
              if busy { ProgressView() } else { Text(existing == .null ? "交给 Hymio" : "保存修改") }
            }.disabled(
              busy || title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                || objective.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
          }
        }
        .onAppear {
          if existing != .null {
            kind = existing["kind"].text.isEmpty ? "task" : existing["kind"].text
            grace =
              existing["schedule"]["grace_seconds"].int > 0
              ? existing["schedule"]["grace_seconds"].int : 900
            title = existing["title"].text
            objective = existing["objective"].text
            criteria = existing["success_criteria"].text
            mode = existing["schedule"]["mode"].text
            weekday = existing["schedule"]["weekday"].int
            if mode == "once",
              let at = taskTimestamp(existing["schedule"]["at"].text)
            {
              date = at
            }
            if ["daily", "weekly"].contains(mode) {
              let parts = existing["schedule"]["time"].text.split(separator: ":").compactMap {
                Int($0)
              }
              if parts.count == 2 {
                var calendar = Calendar.current
                calendar.timeZone = timeZone
                date =
                  calendar.date(
                    bySettingHour: parts[0], minute: parts[1], second: 0, of: date) ?? date
              }
            }
          }
        }
    }.tint(Brand.blue)
  }
  private var timeZone: TimeZone {
    TimeZone(identifier: existing["schedule"]["timezone"].text) ?? .current
  }
  private func save() async {
    busy = true
    defer { busy = false }
    var schedule: [String: JSON] = [
      "mode": .string(mode), "timezone": .string(timeZone.identifier),
      "grace_seconds": .number(Double(grace)),
      "run_timeout_seconds": .number(
        Double(
          existing["schedule"]["run_timeout_seconds"].int > 0
            ? existing["schedule"]["run_timeout_seconds"].int : 3600)),
    ]
    if mode == "once" { schedule["at"] = .string(date.ISO8601Format()) }
    if ["daily", "weekly"].contains(mode) {
      let f = DateFormatter()
      f.timeZone = timeZone
      f.dateFormat = "HH:mm"
      schedule["time"] = .string(f.string(from: date))
    }
    if mode == "weekly" { schedule["weekday"] = .number(Double(weekday)) }
    var body: [String: JSON] = [
      "action": .string(existing == .null ? "create" : "edit"),
      "request_id": .string(requestID), "title": .string(title),
      "kind": .string(kind),
      "objective": .string(objective),
      "success_criteria": .string(
        criteria.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
          ? (kind == "reminder" ? "提醒已送达" : "完成所述目标，并记录结果与未解决事项。") : criteria),
      "schedule": .object(schedule),
    ]
    if existing != .null { body["task_id"] = existing["id"] }
    do {
      _ = try await account.request("tasks", body: .object(body))
      if mode != "now" {
        await notifications.requestForBackgroundWork(account)
      }
      dismiss()
    } catch { self.error = "暂时无法保存。执行中的任务需要先取消，再修改。" }
  }
}


struct AgentActivityView: View {
  @ObservedObject var account: AccountService
  let agentID: String
  @State private var entries: [JSON] = []
  @State private var error = ""
  @Environment(\.scenePhase) private var scene
  var body: some View {
    VStack(alignment: .leading, spacing: 12) {
      Text("执行过程").font(.subheadline.weight(.semibold))
      if entries.isEmpty { Text(error.isEmpty ? "等待第一条执行记录" : error).font(.caption).foregroundStyle(Brand.muted) }
      ForEach(entries, id: \.self) { entry in
        HStack(alignment: .top, spacing: 12) {
          Image(systemName: entry["kind"].text == "tool.terminal" ? "terminal" : "circle.dotted")
            .font(.caption).foregroundStyle(Brand.muted).frame(width: 16)
          VStack(alignment: .leading, spacing: 5) {
            HStack {
              Text(title(entry)).font(.caption.weight(.medium))
              Spacer()
              if let date = eventDate(entry["created_at"].text) {
                Text(date.formatted(date: .omitted, time: .shortened)).font(.caption2).foregroundStyle(Brand.muted)
              }
            }
            if !entry["content"].text.isEmpty {
              DisclosureGroup {
                Text(entry["content"].text).font(.subheadline).textSelection(.enabled)
              } label: { Text(entry["content"].text).lineLimit(2).font(.caption).foregroundStyle(Brand.muted) }
            }
            if !entry["trace_id"].text.isEmpty {
              NavigationLink("查看执行详情") {
                TraceRecordScreen(traceID: entry["trace_id"].text, agentID: agentID, account: account)
              }.font(.caption)
            }
          }
        }.padding(.vertical, 6)
      }
    }.frame(maxWidth: .infinity, alignment: .leading)
    .task(id: scene) {
      guard scene == .active else { return }
      while !Task.isCancelled {
        do {
          let result = try await account.request("agents/\(agentID)/activity")
          let next = result["entries"].items
          if next != entries { entries = next }
          error = ""
          try await Task.sleep(for: .seconds(result["status"].text == "running" ? 3 : 12))
        } catch is CancellationError { return }
        catch { self.error = "执行记录暂时不可用"; return }
      }
    }
  }
  private func eventDate(_ text: String) -> Date? {
    let format = ISO8601DateFormatter()
    format.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return format.date(from: text) ?? ISO8601DateFormatter().date(from: text)
  }
  private func title(_ entry: JSON) -> String {
    if entry["kind"].text == "tool.terminal" { return entry["tool"].text + " · " + taskLabel(entry["status"].text) }
    if entry["kind"].text == "assistant.message" { return "进展" }
    return taskLabel(entry["status"].text)
  }
}

#if DEBUG
struct TaskExperiencePreview: View {
  let account: AccountService
  private var item: JSON {
    .object([
      "id": .string("synthetic-task"), "title": .string("准备周末徒步路线"),
      "objective": .string("比较交通、距离和沿途补给，整理两条适合周末的路线。"),
      "success_criteria": .string("两条可比较的路线及交通建议"), "state": .string("active"),
      "source": .string("conversation"), "runs": .array([.object([
        "id": .string("synthetic-run"), "status": .string("blocked"),
        "phase": .string("两条路线已整理好"),
        "progress": .string("山间路线更安静，湖边路线交通方便。需要选定偏好后再细化行程。"),
        "next_step": .string("选择轻松散步或稍有挑战的徒步"), "wait_reason": .string("user"),
        "started_at": .number(Date().timeIntervalSince1970 - 1800),
        "updates": .array([
          .object(["created_at": .number(Date().timeIntervalSince1970 - 1800), "phase": .string("开始整理"), "status": .string("running"), "content": .string("查阅交通和路线信息，优先考虑当天往返。")]),
          .object(["created_at": .number(Date().timeIntervalSince1970 - 600), "phase": .string("完成比较"), "status": .string("blocked"), "content": .string("保留两条路线，等你选一个方向。")])])])])])
  }
  var body: some View {
    NavigationStack {
      TaskDetailScreen(account: account, taskID: "synthetic-task", initial: item, previewMode: true)
        .safeAreaInset(edge: .bottom) {
          HStack { Text("补充想法…").foregroundStyle(Brand.muted); Spacer(); Image(systemName: "arrow.up.circle.fill").foregroundStyle(Brand.blue) }
            .padding(18).modifier(ComposerSurface()).padding(.horizontal, 20).padding(.bottom, 10)
        }
    }
  }
}
#endif
