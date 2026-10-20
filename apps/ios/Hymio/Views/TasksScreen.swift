import SwiftUI

private func taskStatus(_ item: JSON) -> String {
  item["state"].text == "active"
    ? (item["runs"].items.first?["status"].text ?? "scheduled") : item["state"].text
}
private func taskLabel(_ state: String) -> String {
  [
    "scheduled": "已安排", "delivering": "正在送达", "ready": "等待开始", "running": "进行中", "blocked": "需要关注",
    "succeeded": "已完成", "failed": "未完成", "cancelled": "已取消", "paused": "已暂停",
  ][state] ?? state
}
private func taskDate(_ stamp: Double) -> String {
  Date(timeIntervalSince1970: stamp).formatted(.dateTime.month(.abbreviated).day().hour().minute())
}
private func taskSchedule(_ value: JSON) -> String {
  switch value["mode"].text {
  case "daily": return "每天 \(value["time"].text)"
  case "weekly":
    return "每周\(["一","二","三","四","五","六","日"][min(6,value["weekday"].int)]) \(value["time"].text)"
  case "once":
    return
      (ISO8601DateFormatter().date(from: value["at"].text)?.formatted(
        date: .abbreviated, time: .shortened)) ?? value["at"].text
  default: return "即刻开始"
  }
}

struct TasksScreen: View {
  @ObservedObject var account: AccountService
  @State private var items: [JSON] = []
  @State private var filter = 0
  @State private var creating = false
  @State private var loaded = false
  @State private var error = ""
  private var visible: [JSON] {
    items.filter {
      filter == 0
        || (filter == 2
          ? taskStatus($0) == "succeeded" : !["succeeded", "cancelled"].contains(taskStatus($0)))
    }
  }
  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 24) {
        VStack(alignment: .leading, spacing: 9) {
          Text("A LITTLE FURTHER, EVERY DAY").font(.system(size: 9, weight: .medium)).tracking(1.8)
            .foregroundStyle(.secondary)
          Text("交给 Hymio 的事").font(.system(size: 29, weight: .semibold, design: .rounded)).tracking(
            -1)
          Text("从一句想法，到一件做成的事。").font(.subheadline).foregroundStyle(.secondary)
        }.padding(.top, 16)
        Picker("筛选任务", selection: $filter) {
          Text("全部").tag(0)
          Text("待推进").tag(1)
          Text("已完成").tag(2)
        }.pickerStyle(.segmented)
        if !error.isEmpty { Text(error).font(.caption).foregroundStyle(.secondary) }
        if !loaded { ProgressView().frame(maxWidth: .infinity).padding(40) }
        if loaded && visible.isEmpty {
          VStack(spacing: 17) {
            Image(systemName: "flag").font(.system(size: 29, weight: .light)).foregroundStyle(
              Brand.blue
            ).padding(22).background(
              Brand.blue.opacity(0.05), in: RoundedRectangle(cornerRadius: 22))
            Text(filter == 2 ? "好结果，会留在这里。" : "把想做的事，留给我。").font(.headline)
            Text("现在开始，或约个时间。\n你离开后，工作仍会继续。").font(.subheadline).foregroundStyle(.secondary)
              .multilineTextAlignment(.center)
            Button("安排第一件事", systemImage: "plus") { creating = true }.buttonStyle(
              .borderedProminent
            ).tint(Brand.blue)
          }.frame(maxWidth: .infinity).padding(.vertical, 55)
        }
        ForEach(visible, id: \.self) { item in
          NavigationLink {
            TaskDetailScreen(account: account, taskID: item["id"].text, initial: item)
          } label: {
            HStack(alignment: .top, spacing: 14) {
              Image(
                systemName: taskStatus(item) == "succeeded"
                  ? "checkmark" : taskStatus(item) == "running" ? "sparkles" : "clock"
              )
              .font(.system(size: 16, weight: .regular)).foregroundStyle(Brand.blue)
              .frame(width: 35, height: 35).background(
                Brand.blue.opacity(0.06), in: RoundedRectangle(cornerRadius: 11))
              VStack(alignment: .leading, spacing: 9) {
                Text(item["title"].text).font(.system(size: 15, weight: .medium)).foregroundStyle(
                  Brand.ink
                ).multilineTextAlignment(.leading)
                Text(
                  item["runs"].items.first?["result"].text.isEmpty == false
                    ? item["runs"].items.first!["result"].text : item["objective"].text
                ).font(.caption).foregroundStyle(.secondary).lineLimit(2).multilineTextAlignment(
                  .leading)
                HStack {
                  Text(taskLabel(taskStatus(item))).foregroundStyle(Brand.blue)
                  Text("·")
                  Text(taskSchedule(item["schedule"]))
                }.font(.system(size: 10)).foregroundStyle(.secondary)
              }.frame(maxWidth: .infinity, alignment: .leading)
              Image(systemName: "chevron.right").font(.caption2).foregroundStyle(.tertiary).padding(
                .top, 11)
            }.padding(17).background(.background, in: RoundedRectangle(cornerRadius: 17)).overlay(
              RoundedRectangle(cornerRadius: 17).stroke(Brand.line.opacity(0.7)))
          }.buttonStyle(.plain)
        }
        HStack(spacing: 6) {
          Image(systemName: "arrow.trianglehead.2.clockwise.rotate.90")
          Text("进展自动同步 · 一个 Hymio，持续为你推进。")
        }.font(.system(size: 10)).foregroundStyle(.tertiary).padding(.top, 10)
      }.padding(.horizontal, 22).padding(.bottom, 30)
    }.background(Brand.surface).navigationTitle("任务").navigationBarTitleDisplayMode(.inline)
      .toolbar {
        ToolbarItem(placement: .topBarTrailing) {
          Button("新建任务", systemImage: "plus") { creating = true }
        }
      }
      .sheet(isPresented: $creating, onDismiss: { Task { await load() } }) {
        TaskEditor(account: account)
      }
      .refreshable { await load() }.task {
        while !Task.isCancelled {
          await load()
          do { try await Task.sleep(for: .seconds(5)) } catch { return }
        }
      }
  }
  private func load() async {
    do {
      let value = try await account.request("tasks")
      items = value["tasks"].items
      loaded = true
      error = ""
    } catch { self.error = "暂时无法读取任务，下拉重试。" }
  }
}

private struct TaskDetailScreen: View {
  @ObservedObject var account: AccountService
  let taskID: String
  let initial: JSON
  @Environment(\.dismiss) private var dismiss
  @State private var value: JSON = .null
  @State private var error = ""
  @State private var busy = false
  @State private var editing = false
  @State private var deleting = false
  private var item: JSON { value == .null ? initial : value }
  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 25) {
        VStack(alignment: .leading, spacing: 14) {
          HStack {
            Text(taskLabel(taskStatus(item))).font(.caption).foregroundStyle(Brand.blue)
            Spacer()
            Label(taskSchedule(item["schedule"]), systemImage: "calendar").font(.system(size: 10))
              .foregroundStyle(.secondary)
          }
          Text(item["title"].text).font(.system(size: 27, weight: .semibold, design: .rounded))
            .tracking(-0.8)
          Text(item["objective"].text).font(.subheadline).foregroundStyle(.secondary).lineSpacing(6)
          VStack(alignment: .leading, spacing: 7) {
            Label("怎样算完成", systemImage: "flag").font(.caption).foregroundStyle(.tertiary)
            Text(item["success_criteria"].text).font(.subheadline).foregroundStyle(.secondary)
          }.padding(.top, 6)
        }
        if let run = item["runs"].items.first, !run["result"].text.isEmpty {
          VStack(alignment: .leading, spacing: 13) {
            Label(
              run["status"].text == "succeeded" ? "这次的成果" : "最新进展", systemImage: "checkmark.circle"
            ).font(.caption).foregroundStyle(Brand.blue)
            MessageContent(content: run["result"].text, account: account)
          }.frame(maxWidth: .infinity, alignment: .leading).padding(20).background(
            Brand.blue.opacity(0.045), in: RoundedRectangle(cornerRadius: 16))
        }
        Divider()
        HStack {
          Text("工作记录").font(.caption).foregroundStyle(.secondary)
          Spacer()
          Text("\(item["runs"].items.count) 次执行").font(.caption2).foregroundStyle(.tertiary)
        }
        ForEach(item["runs"].items, id: \.self) { run in
          VStack(alignment: .leading, spacing: 16) {
            HStack {
              Text(taskLabel(run["status"].text)).font(.caption).foregroundStyle(Brand.blue)
              Spacer()
              Text(
                taskDate(
                  run["started_at"].double > 0 ? run["started_at"].double : run["due_at"].double)
              ).font(.caption2).foregroundStyle(.tertiary)
            }
            if !run["agent_id"].text.isEmpty {
              Label("独立专家协作", systemImage: "sparkles").font(.caption2).foregroundStyle(.secondary)
            }
            ForEach(run["updates"].items, id: \.self) { note in
              HStack(alignment: .top, spacing: 12) {
                Circle().fill(Brand.blue.opacity(0.3)).frame(width: 5, height: 5).padding(.top, 6)
                VStack(alignment: .leading, spacing: 6) {
                  Text(taskDate(note["created_at"].double)).font(.system(size: 10)).foregroundStyle(
                    .tertiary)
                  Text(note["content"].text).font(.subheadline).lineSpacing(5).textSelection(
                    .enabled)
                }
              }
            }
            if run["updates"].items.isEmpty {
              Text("进展和成果会记录在这里。").font(.caption).foregroundStyle(.tertiary)
            }
          }.padding(.vertical, 6)
        }
        if !error.isEmpty { Text(error).font(.caption).foregroundStyle(.secondary) }
      }.padding(24)
    }.background(Brand.surface).navigationTitle("任务详情").navigationBarTitleDisplayMode(.inline)
      .toolbar {
        ToolbarItem(placement: .topBarTrailing) {
          Menu {
            if ["paused", "cancelled"].contains(item["state"].text) {
              Button("重新安排", systemImage: "play") { Task { await action("resume") } }
            } else {
              Button("暂停日程", systemImage: "pause") { Task { await action("pause") } }
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
      .sheet(isPresented: $editing) { TaskEditor(account: account, existing: item) }
      .task {
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
    } catch { self.error = "暂时无法读取最新进展。" }
  }
  private func action(_ action: String) async {
    busy = true
    defer { busy = false }
    do {
      _ = try await account.request(
        "tasks", body: .object(["action": .string(action), "task_id": .string(taskID)]))
      error = ""
      await load()
    } catch { self.error = "操作未完成，请稍后再试。" }
  }
}

private struct TaskEditor: View {
  @ObservedObject var account: AccountService
  var existing: JSON = .null
  @Environment(\.dismiss) private var dismiss
  @State private var title = ""
  @State private var objective = ""
  @State private var criteria = ""
  @State private var mode = "now"
  @State private var date = Date().addingTimeInterval(3600)
  @State private var weekday = 0
  @State private var requestID = UUID().uuidString
  @State private var busy = false
  @State private var error = ""
  var body: some View {
    NavigationStack {
      Form {
        Section {
          TextField("给这件事起个名字", text: $title)
          TextField("要做什么？背景、范围和你关心的重点", text: $objective, axis: .vertical).lineLimit(3...6)
          TextField("怎样算完成？", text: $criteria, axis: .vertical).lineLimit(2...4)
        } header: {
          Text("想让 Hymio 做什么？")
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
              displayedComponents: mode == "once" ? [.date, .hourAndMinute] : [.hourAndMinute])
          }
        } header: {
          Label("什么时候开始", systemImage: "calendar")
        } footer: {
          Text("\(TimeZone.current.identifier) · 工作会在云端执行，无需保持 App 打开。")
        }
        if !error.isEmpty { Text(error).font(.caption).foregroundStyle(.secondary) }
      }.navigationTitle(existing == .null ? "安排一件事" : "调整这件事").navigationBarTitleDisplayMode(
        .inline
      ).scrollDismissesKeyboard(.interactively)
        .toolbar {
          ToolbarItem(placement: .cancellationAction) { Button("取消") { dismiss() } }
          ToolbarItem(placement: .confirmationAction) {
            Button {
              Task { await save() }
            } label: {
              if busy { ProgressView() } else { Text("交给 Hymio") }
            }.disabled(
              busy || title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                || objective.isEmpty || criteria.isEmpty)
          }
        }
        .onAppear {
          if existing != .null {
            title = existing["title"].text
            objective = existing["objective"].text
            criteria = existing["success_criteria"].text
            mode = existing["schedule"]["mode"].text
            weekday = existing["schedule"]["weekday"].int
            if mode == "once",
              let at = ISO8601DateFormatter().date(from: existing["schedule"]["at"].text)
            {
              date = at
            }
            if ["daily", "weekly"].contains(mode) {
              let parts = existing["schedule"]["time"].text.split(separator: ":").compactMap {
                Int($0)
              }
              if parts.count == 2 {
                date =
                  Calendar.current.date(
                    bySettingHour: parts[0], minute: parts[1], second: 0, of: date) ?? date
              }
            }
          }
        }
    }.tint(Brand.blue)
  }
  private func save() async {
    busy = true
    defer { busy = false }
    var schedule: [String: JSON] = [
      "mode": .string(mode), "timezone": .string(TimeZone.current.identifier),
    ]
    if mode == "once" { schedule["at"] = .string(date.ISO8601Format()) }
    if ["daily", "weekly"].contains(mode) {
      let f = DateFormatter()
      f.dateFormat = "HH:mm"
      schedule["time"] = .string(f.string(from: date))
    }
    if mode == "weekly" { schedule["weekday"] = .number(Double(weekday)) }
    var body: [String: JSON] = [
      "action": .string(existing == .null ? "create" : "edit"),
      "request_id": .string(requestID), "title": .string(title),
      "objective": .string(objective), "success_criteria": .string(criteria),
      "schedule": .object(schedule),
    ]
    if existing != .null { body["task_id"] = existing["id"] }
    do {
      _ = try await account.request("tasks", body: .object(body))
      dismiss()
    } catch { self.error = "暂时无法保存。执行中的任务需要先取消，再修改。" }
  }
}
