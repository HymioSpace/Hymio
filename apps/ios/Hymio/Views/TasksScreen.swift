import SwiftUI

func taskStatus(_ item: JSON) -> String {
  if item["state"].text == "closed", item["close_reason"].text == "achieved" { return "succeeded" }
  if item["state"].text == "closed", item["close_reason"].text == "cancelled" { return "cancelled" }
  if item["state"].text == "active", item["runs"].items.first?["status"].text == "succeeded", item["next_due_at"].double > 0 { return "scheduled" }
  return item["state"].text == "active"
    ? (item["runs"].items.first?["status"].text ?? "scheduled") : item["state"].text
}
func taskLabel(_ state: String) -> String {
  [
    "queued": "准备中", "waiting": "等待条件", "closed": "已结束", "scheduled": "已安排",
    "delivering": "整理结果", "ready": "准备执行", "running": "进行中",
    "pending": "等待依赖",
    "blocked": "需要你处理", "succeeded": "已完成", "failed": "未完成",
    "expired": "已过期", "cancelled": "已取消", "paused": "已暂停",
  ][state] ?? state
}

func taskDisplayLabel(_ item: JSON) -> String {
  let run = item["runs"].items.first ?? .null
  let mode = item["schedule"]["mode"].text
  let state = taskStatus(item)
  if ["blocked", "failed"].contains(state) { return "需要你处理" }
  if state == "expired" { return "已过期" }
  if item["state"].text == "active", run == .null, ["daily", "weekly"].contains(mode) {
    return "循环中"
  }
  if item["state"].text == "active", run == .null, mode == "once", taskSortDate(item).isFinite {
    return "已安排"
  }
  if state == "waiting" {
    if run["wait_kind"].text == "user" { return "等待你回复" }
    if taskExecutionMode(item) == .program { return "发送中" }
    return "等待完成"
  }
  return taskLabel(taskStatus(item))
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
    let names = ["一", "二", "三", "四", "五", "六", "日"]
    let indexes =
      value["weekdays"].items.map(\.int).isEmpty
      ? [value["weekday"].int] : value["weekdays"].items.map(\.int)
    let days = indexes.filter { 0..<7 ~= $0 }.sorted().map { names[$0] }.joined(separator: "、")
    return "每周\(days.isEmpty ? "" : days + " ")\(value["time"].text)"
  case "once":
    return taskTimestamp(value["at"].text)?.formatted(date: .abbreviated, time: .shortened)
      ?? "等待时间确认"
  case "event": return "等待条件"
  default: return "随时可处理"
  }
}

func taskTimingText(_ item: JSON) -> String? {
  let due = taskSortDate(item)
  guard due.isFinite else { return nil }
  let date = Date(timeIntervalSince1970: due)
  let calendar = Calendar.current
  let day: String
  if calendar.isDateInToday(date) {
    day = "今天"
  } else if calendar.isDateInTomorrow(date) {
    day = "明天"
  } else if let days = calendar.dateComponents([.day], from: calendar.startOfDay(for: Date()), to: calendar.startOfDay(for: date)).day,
    (2...6).contains(days)
  {
    day = date.formatted(.dateTime.weekday(.abbreviated))
  } else {
    day = date.formatted(.dateTime.month(.abbreviated).day())
  }
  return day + " " + date.formatted(.dateTime.hour().minute())
}

func taskTimingSummary(_ item: JSON) -> String? {
  guard let timing = taskTimingText(item) else { return nil }
  let mode = item["schedule"]["mode"].text
  return ["daily", "weekly"].contains(mode)
    ? taskSchedule(item["schedule"]) + " · 下次 " + timing
    : "下次 " + timing
}

enum TaskPortfolioScope: CaseIterable {
  case ongoing, temporary, completed

  var title: String {
    switch self {
    case .ongoing: return "长期任务"
    case .temporary: return "临时任务"
    case .completed: return "已完成"
    }
  }

  var subtitle: String {
    switch self {
    case .ongoing: return "由 Supervisor 持续唤醒和恢复"
    case .temporary: return "执行完成即结束，不进入长期调度"
    case .completed: return "保留结果，不再占用执行资源"
    }
  }
}

func taskPortfolioScope(_ item: JSON) -> TaskPortfolioScope {
  let state = taskStatus(item)
  if ["succeeded", "cancelled", "expired", "closed"].contains(state)
    || ["closed", "archived"].contains(item["state"].text)
  {
    return .completed
  }
  return taskTemporalScope(item)
}

func taskTemporalScope(_ item: JSON) -> TaskPortfolioScope {
  if item["scope"].text == "ongoing" { return .ongoing }
  let mode = item["schedule"]["mode"].text
  if item["completion"].text == "maintain" || ["daily", "weekly", "event"].contains(mode) {
    return .ongoing
  }
  return .temporary
}

enum TaskExecutionMode: String {
  case program
  case parallelSubagents = "parallel_subagents"
  case agentTeam = "agent_team"
  case dynamicWorkflow = "dynamic_workflow"

  var title: String {
    switch self {
    case .program: return "自动执行"
    case .parallelSubagents: return "Agent 并行"
    case .agentTeam: return "Agent Team"
    case .dynamicWorkflow: return "动态工作流"
    }
  }

  var symbol: String {
    switch self {
    case .program: return "bolt.badge.clock"
    case .parallelSubagents: return "person.2"
    case .agentTeam: return "person.3"
    case .dynamicWorkflow: return "point.3.connected.trianglepath.dotted"
    }
  }

  var detail: String {
    switch self {
    case .program: return "按时间或条件执行固定动作，不启动模型"
    case .parallelSubagents: return "主 Agent 拆分独立步骤并整合结果"
    case .agentTeam: return "Leader 与成员可以互相沟通并共同完成"
    case .dynamicWorkflow: return "先拆成有依赖关系的步骤，再按顺序自动执行"
    }
  }
}

func taskExecutionMode(_ item: JSON) -> TaskExecutionMode {
  if item["executor_kind"].text == "program" { return .program }
  let raw =
    item["execution_mode"].text.isEmpty
    ? item["execution"]["mode"].text : item["execution_mode"].text
  return TaskExecutionMode(rawValue: raw) ?? .parallelSubagents
}

func taskCurrentRun(_ item: JSON) -> JSON {
  item["runs"].items.first ?? .null
}

func taskRunNeedsAttention(_ item: JSON) -> Bool {
  let run = taskCurrentRun(item)
  return item["needs_attention"].flag
    || ["paused", "blocked", "failed", "expired"].contains(taskStatus(item))
    || ["paused", "blocked", "failed", "expired"].contains(run["status"].text)
    || (run["status"].text == "waiting" && run["wait_kind"].text == "user")
}

func taskAttentionTitle(_ item: JSON) -> String {
  let run = taskCurrentRun(item)
  if run["error_code"].text == "BUDGET_EXHAUSTED" { return "本轮预算已用尽" }
  if run["status"].text == "waiting" { return "等待条件满足" }
  if ["blocked", "failed", "expired"].contains(taskStatus(item)) { return "需要你处理" }
  return taskDisplayLabel(item)
}

func taskAttentionDetail(_ item: JSON) -> String {
  let run = taskCurrentRun(item)
  if run["error_code"].text == "BUDGET_EXHAUSTED" {
    let used = run["usage"]["tokens"].int
    let limit = item["budget"]["max_tokens"].int
    if used > 0 && limit > 0 {
      return "已使用 \(used.formatted()) / \(limit.formatted()) tokens。任务已保存，可在对话中调整预算后继续。"
    }
    return "任务已保存。可在对话中调整本轮预算后继续。"
  }
  if !run["wait_reason"].text.isEmpty { return run["wait_reason"].text }
  if !run["progress"].text.isEmpty { return run["progress"].text }
  return "打开任务查看执行进度。"
}

func taskCardSummary(_ item: JSON) -> String {
  let run = taskCurrentRun(item)
  if taskRunNeedsAttention(item) { return taskAttentionDetail(item) }
  if run["status"].text == "running" {
    return [run["progress"].text, item["objective"].text].first { !$0.isEmpty }
      ?? "执行 Agent 正在处理"
  }
  if let timing = taskTimingSummary(item), taskPortfolioScope(item) == .ongoing {
    return timing
  }
  return item["objective"].text
}

func humanToolName(_ value: String) -> String {
  [
    "browser": "浏览网页", "computer": "操作桌面", "bash": "执行命令",
    "devices": "查看设备", "cli": "运行工具", "recall": "查找记忆",
    "remember": "整理记忆", "subagent_spawn": "委派子 Agent",
    "task_report": "汇报进展",
  ][value] ?? value
}

private struct TaskHumanActivity: Identifiable {
  let id: String
  let title: String
  let tool: String
  let status: String
}

private func taskHumanActivity(_ agent: JSON) -> [TaskHumanActivity] {
  var result: [TaskHumanActivity] = []
  var seen: Set<String> = []
  for entry in agent["activity"]["entries"].items {
    let entryID = String(entry["id"].int)
    if !entry["tool_description"].text.isEmpty {
      let title = entry["tool_description"].text
      let key = title + "|" + entry["tool"].text + "|" + entry["status"].text
      if seen.insert(key).inserted {
        result.append(
          TaskHumanActivity(
            id: entryID, title: title, tool: humanToolName(entry["tool"].text),
            status: taskLabel(entry["status"].text)))
      }
    }
    for (index, call) in entry["tool_calls"].items.enumerated() {
      let description = call["description"].text
      guard !description.isEmpty else { continue }
      let key = description + "|" + call["name"].text
      if seen.insert(key).inserted {
        result.append(
          TaskHumanActivity(
            id: entryID + "-\(index)", title: description,
            tool: humanToolName(call["name"].text), status: ""))
      }
    }
    let content = entry["content"].text.trimmingCharacters(in: .whitespacesAndNewlines)
    if entry["kind"].text == "assistant.message", !content.isEmpty,
      !content.hasPrefix("<"), !content.hasPrefix("{"), !content.hasPrefix("[")
    {
      let text = String(content.prefix(220))
      let key = "message|" + text
      if seen.insert(key).inserted {
        result.append(TaskHumanActivity(id: entryID, title: text, tool: "", status: ""))
      }
    }
  }
  return Array(result.suffix(10))
}

private enum TaskDisplayMode: Int, CaseIterable {
  case month, week, day, status

  var title: String {
    switch self {
    case .month: return "月"
    case .week: return "周"
    case .day: return "日"
    case .status: return "任务"
    }
  }

  var calendarScale: Int? {
    self == .status ? nil : rawValue
  }
}

struct TasksScreen: View {
  @ObservedObject var account: AccountService
  @ObservedObject var board: TaskBoard
  let onAccount: () -> Void
  var showAccountButton = true
  var previewMode = false
  @State private var focus = Date()
  @State private var mode = TaskDisplayMode.status
  @State private var hourHeight: CGFloat = 72
  @Environment(\.accessibilityReduceMotion) private var reduceMotion
  @Environment(\.dynamicTypeSize) private var dynamicTypeSize
  private var calendar: Calendar { var c = Calendar.current; c.firstWeekday = 2; return c }
  private var dates: [Date] { calendarDays(focus, scale: mode.calendarScale ?? 0) }
  @State private var events: [CalendarWork] = []
  @State private var eventsByDay: [Date: [CalendarWork]] = [:]
  var body: some View {
    VStack(spacing: 0) {
      calendarHeader
      if !board.error.isEmpty {
        Button("读取失败，点击重试") { Task { await board.refresh(account) } }
          .font(.footnote).padding(12)
      }
      if mode == .status {
        statusContent
      } else if mode == .month {
        ScrollView {
          VStack(spacing: 0) {
            monthGrid
            selectedDay
          }.padding(.bottom, 24)
        }.refreshable { if !previewMode { await board.refresh(account) } }
      } else {
        CalendarTimeGrid(account: account, board: board, dates: dates, events: events,
          focus: $focus, hourHeight: hourHeight, previewMode: previewMode)
      }
    }
    .background(mode == .status ? Brand.canvas : Brand.surface)
    .onChange(of: board.items, initial: true) { _, _ in rebuildCalendar() }
    .onChange(of: focus) { _, _ in rebuildCalendar() }
    .onChange(of: mode) { _, _ in Haptics.selection(); rebuildCalendar() }
    .simultaneousGesture(MagnifyGesture().onEnded { value in
      guard let current = mode.calendarScale else { return }
      let next =
        value.magnification > 1.18
        ? min(2, current + 1) : value.magnification < 0.84 ? max(0, current - 1) : current
      guard next != current else { return }
      withAnimation(animation) { mode = TaskDisplayMode(rawValue: next) ?? mode }
    })
    .navigationTitle("任务").navigationBarTitleDisplayMode(.inline)
    .toolbarBackground(.regularMaterial, for: .navigationBar)
    .toolbar {
      ToolbarItem(placement: .topBarLeading) { if showAccountButton { AccountButton(account: account, action: onAccount) } }.accountUnframed()
      ToolbarItem(placement: .topBarTrailing) {
        Button {
          withAnimation(animation) {
            mode = mode == .status ? .month : .status
          }
        } label: {
          Label(mode == .status ? "日历" : "列表", systemImage: mode == .status ? "calendar" : "list.bullet")
            .labelStyle(.iconOnly)
        }
        .accessibilityLabel(mode == .status ? "切换到日历" : "切换到任务列表")
      }.accountUnframed()
    }

  }
  private var calendarHeader: some View {
    VStack(alignment: .leading, spacing: 14) {
      HStack(alignment: .center) {
        if mode == .status {
          VStack(alignment: .leading, spacing: 3) {
            Text("\(board.items.count) 项任务").font(.title3.weight(.semibold)).foregroundStyle(Brand.ink)
            Text("需要你处理、正在发生和下一次时间").font(.caption).foregroundStyle(Brand.muted)
          }
        } else {
          VStack(alignment: .leading, spacing: 4) {
            Text(focus.formatted(.dateTime.year().month(.wide)))
              .font(.caption).foregroundStyle(Brand.muted)
            Text(focus.formatted(.dateTime.month(.wide)))
              .font(.largeTitle.weight(.semibold)).tracking(-1)
          }
        }
        Spacer()
        if mode != .status {
          Button("今天") { withAnimation(animation) { focus = Date() } }
            .font(.subheadline.weight(.medium)).padding(.horizontal, 14).frame(minHeight: 44)
            .background(Brand.base, in: Capsule())
          Button("上一页", systemImage: "chevron.left") { move(-1) }
            .labelStyle(.iconOnly).frame(width: 36, height: 44)
          Button("下一页", systemImage: "chevron.right") { move(1) }
            .labelStyle(.iconOnly).frame(width: 36, height: 44)
        }
      }
      if mode != .status {
        Picker(
          "日历范围",
          selection: Binding(
            get: { mode },
            set: { value in
              withAnimation(animation) { mode = value }
            })
        ) {
          ForEach([TaskDisplayMode.month, .week, .day], id: \.rawValue) { value in
            Text(value.title).tag(value)
          }
        }.pickerStyle(.segmented).accessibilityIdentifier("tasks.calendar-scale")
        HStack(spacing: 12) {
          if mode != .month {
            Text(TimeZone.current.identifier).font(.caption2).foregroundStyle(Brand.muted)
            Button("缩小时间轴", systemImage: "minus.magnifyingglass") {
              hourHeight = max(48, hourHeight - 24)
            }.labelStyle(.iconOnly).frame(width: 44, height: 36).disabled(hourHeight <= 48)
            Button("放大时间轴", systemImage: "plus.magnifyingglass") {
              hourHeight = min(144, hourHeight + 24)
            }.labelStyle(.iconOnly).frame(width: 44, height: 36).disabled(hourHeight >= 144)
          }
          Spacer()
          Text("从任务自动生成").font(.caption2).foregroundStyle(Brand.muted)
        }
      }
    }.padding(.horizontal, 20).padding(.top, 12).padding(.bottom, 12)
      .background(mode == .status ? Brand.canvas : Brand.surface)
  }
  private func rebuildCalendar() {
    let nextEvents = calendarWork(board.items, dates: dates)
    events = nextEvents
    eventsByDay = Dictionary(grouping: nextEvents) {
      calendar.startOfDay(for: $0.date)
    }
  }
  private var animation: Animation? { reduceMotion ? nil : .easeInOut(duration: 0.24) }
  private func move(_ direction: Int) {
    withAnimation(animation) {
      let component: Calendar.Component =
        mode == .month ? .month : mode == .week ? .weekOfYear : .day
      focus = calendar.date(byAdding: component, value: direction, to: focus) ?? focus
    }
  }
  private var statusContent: some View {
    ScrollView {
      LazyVStack(alignment: .leading, spacing: 16) {
        if let item = board.items.first(where: taskRunNeedsAttention) {
          NavigationLink {
            TaskDetailScreen(
              account: account, taskID: item["id"].text, initial: item, board: board,
              previewMode: previewMode, onViewed: { board.markSeen($0) })
          } label: {
            MaterialAttentionCard(item: item)
          }.buttonStyle(.plain)
        }
        ForEach(TaskPortfolioScope.allCases, id: \.self) { scope in
          let items = board.items.filter { taskPortfolioScope($0) == scope }
          if !items.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
              HStack(alignment: .firstTextBaseline) {
                Text(scope.title).font(.headline).foregroundStyle(Brand.ink)
                Text("\(items.count)").font(.caption.monospacedDigit()).foregroundStyle(Brand.muted)
                Spacer()
                Text(scope.subtitle).font(.caption2).foregroundStyle(Brand.muted)
                  .lineLimit(1)
              }
              ForEach(items, id: \.self) { item in
                NavigationLink {
                  TaskDetailScreen(
                    account: account, taskID: item["id"].text, initial: item, board: board,
                    previewMode: previewMode, onViewed: { board.markSeen($0) })
                } label: {
                  MaterialTaskCard(item: item)
                }.buttonStyle(.plain)
              }
            }
          }
        }
        if board.items.isEmpty {
          MaterialEmptyTasks()
        }
      }.padding(.horizontal, 16).padding(.top, 4).padding(.bottom, 28)
    }
  }
  private var monthGrid: some View {
    VStack(spacing: 6) {
      HStack(spacing: 0) {
        ForEach(["一", "二", "三", "四", "五", "六", "日"], id: \.self) { day in
          Text(day).font(.caption).foregroundStyle(Brand.muted).frame(maxWidth: .infinity)
        }
      }.padding(.vertical, 8)
      LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 0), count: 7), spacing: 2) {
        ForEach(dates, id: \.self) { day in monthDay(day) }
      }
    }.padding(.horizontal, 14).padding(.bottom, 18)
  }
  private func monthDay(_ day: Date) -> some View {
    let selected = calendar.isDate(day, inSameDayAs: focus)
    let dayEvents = eventsByDay[calendar.startOfDay(for: day)] ?? []
    let inMonth = calendar.isDate(day, equalTo: focus, toGranularity: .month)
    return Button { withAnimation(animation) { focus = day } } label: {
      VStack(spacing: 7) {
        Text("\(calendar.component(.day, from: day))")
          .font(.system(size: 17, weight: selected || calendar.isDateInToday(day) ? .semibold : .regular))
          .frame(width: 36, height: 36)
          .background(selected ? Brand.blue : calendar.isDateInToday(day) ? Brand.softBlue : .clear, in: Circle())
          .foregroundStyle(selected ? Brand.onAccent : inMonth ? Brand.ink : Brand.muted.opacity(0.55))
        HStack(spacing: 3) {
          ForEach(Array(dayEvents.prefix(3).enumerated()), id: \.offset) { _, event in
            Circle().fill(calendarTint(event.status)).frame(width: 4, height: 4)
          }
        }.frame(height: 5)
      }.frame(maxWidth: .infinity).padding(.vertical, 3).contentShape(Rectangle())
    }.buttonStyle(.plain).accessibilityLabel(day.formatted(date: .complete, time: .omitted) + "，\(dayEvents.count) 项安排")
      .accessibilityAddTraits(selected ? .isSelected : [])
  }
  private var selectedDay: some View {
    let values = eventsByDay[calendar.startOfDay(for: focus)] ?? []
    return VStack(alignment: .leading, spacing: 18) {
      HStack {
        Text(focus.formatted(.dateTime.month().day().weekday(.wide))).font(.subheadline.weight(.semibold))
        Spacer()
        Text("\(values.count) 项安排").font(.caption).foregroundStyle(Brand.muted)
      }
      if !board.loaded { ProgressView("正在读取…").font(.footnote) }
      else if values.isEmpty {
        VStack(alignment: .leading, spacing: 10) {
          Image(systemName: "sun.max").font(.title2).foregroundStyle(Brand.muted)
          Text("这一天，留点空白。 ").font(.headline)
          Text("在对话中交代需要安排的工作。").font(.subheadline)
        }.frame(maxWidth: .infinity, alignment: .leading).padding(22)
          .background(Brand.base, in: RoundedRectangle(cornerRadius: 20))
      }
      ForEach(values) { event in
        NavigationLink {
          TaskDetailScreen(account: account, taskID: event.task["id"].text, initial: event.task, board: board,
            previewMode: previewMode, onViewed: { board.markSeen($0) })
        } label: { CalendarAgendaRow(event: event) }.buttonStyle(.plain)
      }
    }.padding(22).frame(maxWidth: .infinity, alignment: .leading)
      .background(Brand.raised, in: UnevenRoundedRectangle(topLeadingRadius: 26, topTrailingRadius: 26))
      .overlay(alignment: .top) { Capsule().fill(Brand.line).frame(width: 30, height: 3).padding(.top, 8) }
  }
}

private func materialStatusColor(_ item: JSON) -> Color {
  if taskRunNeedsAttention(item) { return Brand.attention }
  if ["running", "ready", "delivering"].contains(taskStatus(item)) { return Brand.blue }
  if taskPortfolioScope(item) == .completed { return Brand.muted }
  return Brand.blue
}

private struct MaterialStatusPill: View {
  let text: String
  let color: Color

  var body: some View {
    Text(text)
      .font(.caption.weight(.semibold))
      .foregroundStyle(color)
      .padding(.horizontal, 10)
      .padding(.vertical, 5)
      .background(color.opacity(0.11), in: Capsule())
  }
}

private struct TaskModePill: View {
  let item: JSON
  @State private var showHelp = false

  var body: some View {
    HStack(spacing: 4) {
      Label(taskExecutionMode(item).title, systemImage: taskExecutionMode(item).symbol)
        .font(.caption.weight(.medium))
      Button {
        showHelp.toggle()
      } label: {
        Image(systemName: "questionmark.circle")
          .font(.caption.weight(.medium))
          .frame(width: 28, height: 28)
          .contentShape(Circle())
      }
      .buttonStyle(.plain)
      .accessibilityLabel("\(taskExecutionMode(item).title)说明")
      .alert(taskExecutionMode(item).title, isPresented: $showHelp) {
        Button("知道了") {}
      } message: {
        Text(taskExecutionMode(item).detail)
      }
    }
    .foregroundStyle(Brand.blue)
    .padding(.leading, 10)
    .padding(.trailing, 2)
    .padding(.vertical, 2)
    .background(Brand.softBlue, in: Capsule())
  }
}

private struct MaterialAttentionCard: View {
  let item: JSON

  var body: some View {
    HStack(alignment: .top, spacing: 12) {
      Image(systemName: "exclamationmark")
        .font(.system(size: 18, weight: .bold))
        .foregroundStyle(Brand.attention)
        .frame(width: 34, height: 34)
        .background(Brand.attention.opacity(0.12), in: RoundedRectangle(cornerRadius: 11))
      VStack(alignment: .leading, spacing: 4) {
        Text(taskAttentionTitle(item)).font(.subheadline.weight(.semibold)).foregroundStyle(
          Brand.ink)
        Text(taskAttentionDetail(item)).font(.caption).foregroundStyle(Brand.muted)
          .lineLimit(3).multilineTextAlignment(.leading)
        Text(item["title"].text).font(.caption2.weight(.medium)).foregroundStyle(Brand.attention)
          .lineLimit(1)
      }
      Spacer(minLength: 4)
      Image(systemName: "chevron.right").font(.caption.weight(.semibold))
        .foregroundStyle(Brand.muted).padding(.top, 8)
    }
    .padding(14)
    .background(Brand.attentionSurface, in: RoundedRectangle(cornerRadius: 18))
    .overlay(RoundedRectangle(cornerRadius: 18).strokeBorder(Brand.attention.opacity(0.2)))
    .accessibilityIdentifier("tasks.attention")
  }
}

private struct MaterialTaskCard: View {
  let item: JSON
  private var scope: TaskPortfolioScope { taskPortfolioScope(item) }
  private var run: JSON { taskCurrentRun(item) }

  var body: some View {
    VStack(alignment: .leading, spacing: 10) {
      HStack(spacing: 8) {
        MaterialStatusPill(
          text: taskDisplayLabel(item), color: materialStatusColor(item))
        Text(taskTemporalScope(item).title).font(.caption2).foregroundStyle(Brand.muted)
        Spacer(minLength: 4)
        Image(systemName: "chevron.right").font(.caption2.weight(.semibold))
          .foregroundStyle(Brand.muted)
      }
      Text(item["title"].text)
        .font(.headline.weight(.semibold))
        .foregroundStyle(Brand.ink)
        .lineLimit(2).multilineTextAlignment(.leading)
      Text(taskCardSummary(item))
        .font(.subheadline)
        .foregroundStyle(Brand.muted)
        .lineLimit(3).multilineTextAlignment(.leading)
      if !run["agent_id"].text.isEmpty {
        HStack(spacing: 6) {
          Image(systemName: "person.2").font(.caption2)
          Text("执行 Agent").font(.caption2)
          if !run["usage"]["steps"].text.isEmpty {
            Text("· \(run["usage"]["steps"].int) 步").font(.caption2)
          }
        }.foregroundStyle(Brand.muted)
      }
    }
    .padding(16)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(Brand.raised, in: RoundedRectangle(cornerRadius: 18))
    .overlay(RoundedRectangle(cornerRadius: 18).strokeBorder(Brand.line.opacity(0.75)))
    .shadow(color: .black.opacity(0.035), radius: 8, y: 2)
    .accessibilityIdentifier("task.card.\(item["id"].text)")
  }
}

private struct MaterialEmptyTasks: View {
  var body: some View {
    VStack(spacing: 12) {
      Image(systemName: "task_alt")
        .font(.system(size: 26, weight: .regular)).foregroundStyle(Brand.blue)
        .frame(width: 48, height: 48).background(Brand.softBlue, in: RoundedRectangle(cornerRadius: 16))
      Text("还没有任务").font(.headline).foregroundStyle(Brand.ink)
      Text("在对话里说出目标，需要并行或后台执行的复杂工作会出现在这里。")
        .font(.subheadline).foregroundStyle(Brand.muted).multilineTextAlignment(.center)
    }
    .frame(maxWidth: .infinity).padding(.vertical, 48)
  }
}

private struct CalendarWork: Identifiable {
  let task: JSON
  let date: Date
  let status: String
  var projected = false
  var id: String { task["id"].text + ":" + String(Int(date.timeIntervalSince1970 / 60)) }
}
private func calendarTint(_ status: String) -> Color {
  if ["blocked", "failed", "expired"].contains(status) { return Brand.attention }
  if status == "succeeded" { return Color.secondary }
  return Brand.blue
}
private func calendarDays(_ date: Date, scale: Int) -> [Date] {
  var c = Calendar.current; c.firstWeekday = 2
  if scale == 2 { return [c.startOfDay(for: date)] }
  let start = c.dateInterval(of: scale == 0 ? .month : .weekOfYear, for: date)!.start
  let offset = scale == 0 ? (c.component(.weekday, from: start) + 5) % 7 : 0
  let first = c.date(byAdding: .day, value: -offset, to: start)!
  return (0..<(scale == 0 ? 42 : 7)).compactMap { c.date(byAdding: .day, value: $0, to: first) }
}
private func calendarWork(_ tasks: [JSON], dates: [Date]) -> [CalendarWork] {
  guard let start = dates.first, let last = dates.last else { return [] }
  let end = Calendar.current.date(byAdding: .day, value: 1, to: last)!
  var result: [CalendarWork] = []
  for task in tasks {
    let mode = task["schedule"]["mode"].text
    guard !["now", ""].contains(mode) else { continue }
    var seen = Set<Int>()
    func insert(_ date: Date, status: String, projected: Bool) {
      let key = Int(date.timeIntervalSince1970 / 60)
      if date >= start && date < end && seen.insert(key).inserted {
        result.append(CalendarWork(task: task, date: date, status: status, projected: projected))
      }
    }
    for run in task["runs"].items where run["due_at"].double > 0 {
      insert(Date(timeIntervalSince1970: run["due_at"].double), status: run["status"].text, projected: false)
    }
    if mode == "once", let date = taskTimestamp(task["schedule"]["at"].text) {
      insert(date, status: taskStatus(task), projected: false)
    }
    guard task["state"].text == "active", ["daily", "weekly"].contains(mode) else { continue }
    var c = Calendar.current
    c.timeZone = TimeZone(identifier: task["schedule"]["timezone"].text) ?? .current
    let time = task["schedule"]["time"].text.split(separator: ":").compactMap { Int($0) }
    guard time.count == 2 else { continue }
    for offset in -1...43 {
      guard let day = c.date(byAdding: .day, value: offset, to: c.startOfDay(for: start)),
        let date = c.date(bySettingHour: time[0], minute: time[1], second: 0, of: day), date > Date() else { continue }
      if mode == "weekly" && (c.component(.weekday, from: day) + 5) % 7 != task["schedule"]["weekday"].int { continue }
      insert(date, status: "scheduled", projected: true)
    }
  }
  return result.sorted { $0.date < $1.date }
}
private struct CalendarAgendaRow: View {
  let event: CalendarWork
  @ScaledMetric(relativeTo: .subheadline) private var timeWidth: CGFloat = 48
  @Environment(\.dynamicTypeSize) private var dynamicTypeSize
  var body: some View {
    Group {
      if dynamicTypeSize.isAccessibilitySize {
        VStack(alignment: .leading, spacing: 6) {
          Text(event.date.formatted(.dateTime.hour().minute()))
            .font(.caption.monospacedDigit()).foregroundStyle(Brand.muted)
          HStack(alignment: .top, spacing: 12) {
            RoundedRectangle(cornerRadius: 2).fill(calendarTint(event.status))
              .frame(width: 3, height: 48)
            VStack(alignment: .leading, spacing: 5) {
              Text(event.task["title"].text).font(.body.weight(.medium))
                .foregroundStyle(Brand.ink).multilineTextAlignment(.leading)
              Text(event.projected ? "重复安排" : taskLabel(event.status))
                .font(.caption).foregroundStyle(Brand.muted)
            }
          }
        }.frame(maxWidth: .infinity, alignment: .leading)
      } else {
        HStack(alignment: .top, spacing: 16) {
          Text(event.date.formatted(.dateTime.hour().minute())).font(.subheadline.monospacedDigit())
            .foregroundStyle(Brand.muted).frame(width: timeWidth, alignment: .leading)
          RoundedRectangle(cornerRadius: 2).fill(calendarTint(event.status)).frame(width: 3, height: 44)
          VStack(alignment: .leading, spacing: 6) {
            Text(event.task["title"].text).font(.subheadline.weight(.medium)).foregroundStyle(Brand.ink).lineLimit(2)
            Text(event.projected ? "重复安排" : taskLabel(event.status)).font(.caption).foregroundStyle(Brand.muted)
          }
          Spacer(minLength: 0)
          Image(systemName: "chevron.right").font(.caption2).foregroundStyle(Brand.muted)
        }.padding(.vertical, 8).frame(maxWidth: .infinity, alignment: .leading)
      }
    }
  }
}
private struct TaskStatusRow: View {
  let item: JSON
  @Environment(\.dynamicTypeSize) private var dynamicTypeSize
  private var state: String { taskStatus(item) }
  private var run: JSON { item["runs"].items.first ?? .null }
  private var detail: String {
    [run["progress"].text, run["next_step"].text, item["objective"].text]
      .first { !$0.isEmpty } ?? "还没有新的进展"
  }
  var body: some View {
    Group {
      if dynamicTypeSize.isAccessibilitySize {
        VStack(alignment: .leading, spacing: 5) {
          HStack(alignment: .top, spacing: 10) {
            Image(systemName: taskSymbol(state)).font(.subheadline)
              .foregroundStyle(["blocked", "failed"].contains(state) ? Brand.attention : Brand.muted)
            Text(item["title"].text).font(.subheadline.weight(.semibold)).foregroundStyle(Brand.ink)
              .multilineTextAlignment(.leading)
          }
          Text(detail).font(.caption).foregroundStyle(Brand.muted)
            .multilineTextAlignment(.leading)
          if let timing = taskTimingSummary(item), taskLane(item) == .scheduled {
            Text(timing)
              .font(.caption2).foregroundStyle(Brand.muted)
          }
          Text(taskDisplayLabel(item)).font(.caption2.weight(.medium))
            .foregroundStyle(["blocked", "failed", "expired"].contains(state) ? Brand.attention : Brand.muted)
        }.frame(maxWidth: .infinity, alignment: .leading)
      } else {
        HStack(alignment: .top, spacing: 12) {
          Image(systemName: taskSymbol(state)).font(.subheadline)
            .foregroundStyle(["blocked", "failed"].contains(state) ? Brand.attention : Brand.muted)
            .frame(width: 20).padding(.top, 3)
          VStack(alignment: .leading, spacing: 4) {
            Text(item["title"].text).font(.subheadline.weight(.semibold)).foregroundStyle(Brand.ink)
              .lineLimit(2).multilineTextAlignment(.leading)
            Text(detail).font(.caption).foregroundStyle(Brand.muted).lineLimit(2)
              .multilineTextAlignment(.leading)
            if taskLane(item) == .scheduled, let timing = taskTimingSummary(item) {
              Label(timing, systemImage: "calendar")
                .font(.caption2).foregroundStyle(Brand.muted)
            }
          }
          Spacer(minLength: 8)
          VStack(alignment: .trailing, spacing: 5) {
            Text(taskDisplayLabel(item)).font(.caption2.weight(.medium))
              .foregroundStyle(["blocked", "failed", "expired"].contains(state) ? Brand.attention : Brand.muted)
            Image(systemName: "chevron.right").font(.caption2).foregroundStyle(Brand.muted)
          }.padding(.top, 1)
        }
      }
    }.padding(.vertical, 7).frame(minHeight: 58)
    .contentShape(Rectangle())
    .accessibilityElement(children: .combine)
  }
}
private func calendarLane(_ values: [CalendarWork], index: Int, hourHeight: CGFloat) -> (Int, Int) {
  let gap = Double(56 / hourHeight * 3600)
  var start = index, end = index
  while start > 0 && values[start].date.timeIntervalSince(values[start - 1].date) < gap { start -= 1 }
  while end + 1 < values.count && values[end + 1].date.timeIntervalSince(values[end].date) < gap { end += 1 }
  return (index - start, end - start + 1)
}
private struct CalendarTimeGrid: View {
  let account: AccountService
  let board: TaskBoard
  let dates: [Date]
  let events: [CalendarWork]
  @Binding var focus: Date
  let hourHeight: CGFloat
  var previewMode: Bool
  private var c: Calendar { Calendar.current }
  var body: some View {
    GeometryReader { geometry in
      let timelineWidth = max(220, geometry.size.width - 50)
      let dayWidth = max(38, timelineWidth / CGFloat(max(1, dates.count)))
      let selectedDay = dates.first { c.isDate($0, inSameDayAs: focus) } ?? dates.first ?? focus
      ScrollViewReader { proxy in
        VStack(spacing: 0) {
          HStack(spacing: 0) {
            Color.clear.frame(width: 50, height: 58)
            ForEach(dates, id: \.self) { day in
              let selected = c.isDate(day, inSameDayAs: selectedDay)
              Button {
                withAnimation(.easeOut(duration: 0.18)) { focus = day }
              } label: {
                VStack(spacing: 4) {
                  Text(day.formatted(.dateTime.weekday(.narrow))).font(.caption2)
                  Text(day.formatted(.dateTime.day())).font(.subheadline.weight(.semibold))
                }
                .foregroundStyle(selected ? Brand.onAccent : Brand.muted)
                .frame(width: dayWidth, height: 48)
                .background(selected ? Brand.blue : Color.clear, in: RoundedRectangle(cornerRadius: 12))
              }
              .buttonStyle(.plain)
              .accessibilityLabel(day.formatted(date: .complete, time: .omitted))
              .accessibilityAddTraits(selected ? .isSelected : [])
            }
          }
          .padding(.horizontal, 2).padding(.bottom, 6)
          .overlay(alignment: .bottom) { Rectangle().fill(Brand.line).frame(height: 0.5) }
          ScrollView(.vertical) {
            HStack(alignment: .top, spacing: 0) {
              VStack(spacing: 0) {
                ForEach(0..<24) { hour in
                  Text(String(format: "%02d", hour)).font(.caption2.monospacedDigit())
                    .foregroundStyle(Brand.muted)
                    .frame(width: 44, height: hourHeight, alignment: .topTrailing)
                    .padding(.trailing, 6)
                    .id("hour-\(hour)")
                }
              }
              timeColumn(selectedDay, width: timelineWidth)
            }.padding(.top, 12)
          }
          .onAppear { proxy.scrollTo("hour-7", anchor: .topLeading) }
        }
      }
    }
  }
  private func timeColumn(_ day: Date, width: CGFloat) -> some View {
    let values = events.filter { c.isDate($0.date, inSameDayAs: day) }
    return ZStack(alignment: .topLeading) {
      VStack(spacing: 0) {
        ForEach(0..<24) { _ in
          Rectangle().fill(Brand.line.opacity(0.7)).frame(height: 0.5)
            .frame(height: hourHeight, alignment: .top)
        }
      }.frame(width: width).overlay(alignment: .leading) { Rectangle().fill(Brand.line.opacity(0.6)).frame(width: 0.5) }
      ForEach(Array(values.enumerated()), id: \.element.id) { index, event in
        let minutes = CGFloat(c.component(.hour, from: event.date) * 60 + c.component(.minute, from: event.date))
        let placement = calendarLane(values, index: index, hourHeight: hourHeight)
        let lane = placement.0
        let cardWidth = (width - 8) / CGFloat(placement.1)
        NavigationLink {
          TaskDetailScreen(account: account, taskID: event.task["id"].text, initial: event.task, board: board,
            previewMode: previewMode, onViewed: { board.markSeen($0) })
        } label: {
          VStack(alignment: .leading, spacing: 4) {
            Text(event.date.formatted(.dateTime.hour().minute())).font(.system(size: 10, weight: .medium))
            Text(event.task["title"].text).font(.caption.weight(.medium)).lineLimit(2)
          }.frame(maxWidth: .infinity, alignment: .leading).padding(8)
            .foregroundStyle(calendarTint(event.status)).background(Brand.softBlue, in: RoundedRectangle(cornerRadius: 8))
            .overlay(alignment: .leading) { RoundedRectangle(cornerRadius: 2).fill(calendarTint(event.status)).frame(width: 2).padding(.vertical, 6) }
        }.buttonStyle(.plain).frame(width: cardWidth)
          .offset(x: 4 + CGFloat(lane) * cardWidth, y: minutes / 60 * hourHeight)
          .accessibilityLabel(event.date.formatted(date: .complete, time: .shortened) + "，" + event.task["title"].text)
      }
      if c.isDateInToday(day) {
        TimelineView(.periodic(from: .now, by: 60)) { context in
          let minutes = CGFloat(c.component(.hour, from: context.date) * 60 + c.component(.minute, from: context.date))
          Rectangle().fill(Brand.blue).frame(height: 1).overlay(alignment: .leading) { Circle().fill(Brand.blue).frame(width: 5, height: 5) }
            .offset(y: minutes / 60 * hourHeight)
        }.allowsHitTesting(false)
      }
    }.frame(width: width, height: hourHeight * 24 + 64)
  }
}

private struct TaskDetailHero: View {
  let item: JSON

  var body: some View {
    VStack(alignment: .leading, spacing: 12) {
      HStack(spacing: 8) {
        MaterialStatusPill(
          text: taskDisplayLabel(item), color: materialStatusColor(item))
        Text(taskTemporalScope(item).title)
          .font(.caption2.weight(.medium)).foregroundStyle(Brand.muted)
        Spacer(minLength: 4)
        if !["", "now"].contains(item["schedule"]["mode"].text) {
          Label(taskSchedule(item["schedule"]), systemImage: "schedule")
            .font(.caption2).foregroundStyle(Brand.muted)
        }
      }
      Text(item["title"].text)
        .font(.title2.weight(.semibold))
        .foregroundStyle(Brand.ink)
        .lineLimit(3)
      Text(item["objective"].text)
        .font(.subheadline)
        .foregroundStyle(Brand.muted)
        .lineLimit(4)
        .lineSpacing(3)
      TaskModePill(item: item)
    }
    .padding(18)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(Brand.raised, in: RoundedRectangle(cornerRadius: 22))
    .overlay(RoundedRectangle(cornerRadius: 22).strokeBorder(Brand.line.opacity(0.8)))
    .shadow(color: .black.opacity(0.04), radius: 10, y: 3)
    .accessibilityIdentifier("task.summary")
  }
}

private struct TaskAttentionPanel: View {
  let item: JSON

  var body: some View {
    HStack(alignment: .top, spacing: 12) {
      Image(systemName: "exclamationmark")
        .font(.system(size: 17, weight: .bold))
        .foregroundStyle(Brand.attention)
        .frame(width: 32, height: 32)
        .background(Brand.attention.opacity(0.12), in: RoundedRectangle(cornerRadius: 10))
      VStack(alignment: .leading, spacing: 5) {
        Text(taskAttentionTitle(item)).font(.subheadline.weight(.semibold))
          .foregroundStyle(Brand.ink)
        Text(taskAttentionDetail(item)).font(.caption).foregroundStyle(Brand.muted)
          .lineSpacing(2)
      }
    }
    .padding(14)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(Brand.attentionSurface, in: RoundedRectangle(cornerRadius: 18))
    .overlay(RoundedRectangle(cornerRadius: 18).strokeBorder(Brand.attention.opacity(0.2)))
    .accessibilityIdentifier("task.attention")
  }
}

private struct MaterialRunOverview: View {
  let item: JSON
  private var run: JSON { taskCurrentRun(item) }
  private var usage: JSON { run["usage"] }
  private var budget: JSON { item["budget"] }

  var body: some View {
    VStack(alignment: .leading, spacing: 14) {
      HStack {
        Text("本次运行").font(.headline).foregroundStyle(Brand.ink)
        Spacer()
        Text(taskDisplayLabel(item)).font(.caption).foregroundStyle(
          materialStatusColor(item))
      }
      if !run["progress"].text.isEmpty {
        Text(run["progress"].text).font(.subheadline).foregroundStyle(Brand.ink)
          .lineSpacing(2).lineLimit(4)
      } else if run["status"].text == "paused" {
        Text("执行进度已保存，恢复后从当前步骤继续。")
          .font(.subheadline).foregroundStyle(Brand.muted)
      }
      if taskExecutionMode(item) != .program {
        HStack(spacing: 10) {
          TaskMetricChip(
            icon: "number", value: compactMetric(usage["tokens"].int),
            label: budget["max_tokens"].int > 0
              ? "/ \(compactMetric(budget["max_tokens"].int))" : "tokens")
          TaskMetricChip(
            icon: "list.number",
            value: "\(usage["steps"].int)", label: "/ \(compactMetric(budget["max_steps"].int)) 步")
          TaskMetricChip(
            icon: "timer", value: durationLabel(usage["active_seconds"].double),
            label: "运行")
        }
        if budget["max_tokens"].int > 0 {
          ProgressView(
            value: min(Double(usage["tokens"].int), Double(budget["max_tokens"].int)),
            total: Double(budget["max_tokens"].int))
            .tint(run["error_code"].text == "BUDGET_EXHAUSTED" ? Brand.attention : Brand.blue)
        }
      }
    }
    .padding(18)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(Brand.surface, in: RoundedRectangle(cornerRadius: 20))
    .overlay(RoundedRectangle(cornerRadius: 20).strokeBorder(Brand.line))
  }

  private func durationLabel(_ seconds: Double) -> String {
    guard seconds > 0 else { return "—" }
    return seconds < 60
      ? "\(Int(seconds.rounded()))s" : "\(Int((seconds / 60).rounded()))m"
  }

  private func compactMetric(_ value: Int) -> String {
    if value >= 1_000_000 {
      return String(format: "%.1fm", Double(value) / 1_000_000).replacingOccurrences(
        of: ".0", with: "")
    }
    if value >= 1_000 {
      return String(format: "%.1fk", Double(value) / 1_000).replacingOccurrences(
        of: ".0", with: "")
    }
    return "\(value)"
  }
}

private struct TaskMetricChip: View {
  let icon: String
  let value: String
  let label: String

  var body: some View {
    HStack(spacing: 5) {
      Image(systemName: icon).font(.caption2)
      Text(value).font(.caption.weight(.semibold)).monospacedDigit()
        .lineLimit(1).minimumScaleFactor(0.8)
      Text(label).font(.caption2).lineLimit(1).minimumScaleFactor(0.8)
    }
    .foregroundStyle(Brand.muted)
    .padding(.horizontal, 9).frame(minHeight: 30)
    .background(Brand.base, in: Capsule())
  }
}

private struct MaterialPlanCard: View {
  let item: JSON

  var body: some View {
    let plan = item["execution"]["plan"].items.isEmpty
      ? item["plan"].items : item["execution"]["plan"].items
    VStack(alignment: .leading, spacing: 12) {
      Text("计划").font(.headline).foregroundStyle(Brand.ink)
      if plan.isEmpty {
        Text("执行 Agent 尚未提交结构化计划。").font(.subheadline).foregroundStyle(Brand.muted)
      } else {
        ForEach(Array(plan.enumerated()), id: \.offset) { index, step in
          HStack(alignment: .top, spacing: 10) {
            Image(systemName: planSymbol(step["state"].text))
              .font(.system(size: 15, weight: .medium))
              .foregroundStyle(planColor(step["state"].text))
              .frame(width: 20, height: 22)
            Text(step["title"].text.isEmpty ? step["description"].text : step["title"].text)
              .font(.subheadline).foregroundStyle(Brand.ink)
              .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 4)
            Text("\(index + 1)").font(.caption2.monospacedDigit()).foregroundStyle(Brand.muted)
          }
        }
      }
    }
    .padding(18)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(Brand.raised, in: RoundedRectangle(cornerRadius: 20))
    .overlay(RoundedRectangle(cornerRadius: 20).strokeBorder(Brand.line))
  }

  private func planSymbol(_ state: String) -> String {
    ["done", "completed", "succeeded"].contains(state)
      ? "checkmark.circle.fill" : ["doing", "in_progress", "running"].contains(state)
        ? "circle.dotted" : "circle"
  }
  private func planColor(_ state: String) -> Color {
    ["done", "completed", "succeeded"].contains(state)
      ? Color.green : ["doing", "in_progress", "running"].contains(state)
        ? Brand.blue : Brand.muted.opacity(0.65)
  }
}

private struct MaterialWorkflowCard: View {
  let item: JSON

  private var nodes: [JSON] { item["execution"]["workflow"]["nodes"].items }
  private var names: [String: String] {
    Dictionary(uniqueKeysWithValues: nodes.map { ($0["id"].text, $0["title"].text) })
  }

  private func color(_ status: String) -> Color {
    if ["failed", "blocked", "cancelled"].contains(status) { return Brand.attention }
    if status == "succeeded" { return .green }
    if status == "running" { return Brand.blue }
    return Brand.muted
  }

  var body: some View {
    VStack(alignment: .leading, spacing: 14) {
      HStack(alignment: .firstTextBaseline) {
        Label("执行依赖", systemImage: "point.3.connected.trianglepath.dotted")
          .font(.headline)
          .foregroundStyle(Brand.ink)
        Spacer()
        Text("\(nodes.filter { $0["status"].text == "succeeded" }.count)/\(nodes.count)")
          .font(.caption.monospacedDigit())
          .foregroundStyle(Brand.muted)
      }
      ForEach(Array(nodes.enumerated()), id: \.offset) { index, node in
        HStack(alignment: .top, spacing: 10) {
          VStack(spacing: 0) {
            ZStack {
              Circle().fill(color(node["status"].text).opacity(0.13)).frame(width: 28, height: 28)
              Image(
                systemName: node["status"].text == "succeeded"
                  ? "checkmark" : node["status"].text == "running" ? "play.fill" : "circle.fill"
              )
              .font(.system(size: 10, weight: .bold))
              .foregroundStyle(color(node["status"].text))
            }
            if index < nodes.count - 1 {
              Rectangle()
                .fill(Brand.line)
                .frame(width: 1, height: 34)
            }
          }
          VStack(alignment: .leading, spacing: 5) {
            HStack(spacing: 7) {
              Text(node["title"].text)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(Brand.ink)
              Spacer(minLength: 4)
              MaterialStatusPill(
                text: taskLabel(node["status"].text),
                color: color(node["status"].text))
            }
            let dependencies = node["depends_on"].items.map(\.text)
            if !dependencies.isEmpty {
              Text(
                "依赖 " + dependencies.map { names[$0] ?? $0 }.joined(separator: "、")
              )
              .font(.caption2)
              .foregroundStyle(Brand.muted)
            }
            if !node["result"].text.isEmpty {
              Text(node["result"].text)
                .font(.caption)
                .foregroundStyle(Brand.muted)
                .lineLimit(2)
            }
          }
          .padding(12)
          .background(Brand.base, in: RoundedRectangle(cornerRadius: 14))
        }
      }
    }
    .padding(18)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(Brand.raised, in: RoundedRectangle(cornerRadius: 20))
    .overlay(RoundedRectangle(cornerRadius: 20).strokeBorder(Brand.line))
    .accessibilityIdentifier("task.workflow")
  }
}

private struct MaterialExecutionTeam: View {
  let item: JSON

  var body: some View {
    let execution = item["execution"]
    let agent = execution["task_agent"]
    let children = execution["subagents"].items
    let mode = taskExecutionMode(item)
    VStack(alignment: .leading, spacing: 12) {
      HStack {
        Text(mode == .program ? "执行方式" : "执行团队").font(.headline).foregroundStyle(Brand.ink)
        Spacer()
        Text(
          mode == .program
            ? mode.title
            : children.isEmpty ? "等待委派" : "\(children.count + 1) 个 Agent"
        )
          .font(.caption).foregroundStyle(Brand.muted)
      }
      if mode == .program {
        HStack(alignment: .top, spacing: 10) {
          Image(systemName: mode.symbol)
            .foregroundStyle(Brand.blue)
            .frame(width: 30, height: 30)
            .background(Brand.softBlue, in: RoundedRectangle(cornerRadius: 10))
          VStack(alignment: .leading, spacing: 3) {
            Text("不启动 Agent").font(.subheadline.weight(.semibold)).foregroundStyle(Brand.ink)
          }
        }
      } else if agent != .null {
        NavigationLink {
          AgentContextScreen(
            agent: agent, taskTitle: item["title"].text, isTaskAgent: true, parentTitle: "")
        } label: {
          MaterialAgentCard(
            agent: agent, isTaskAgent: true,
            memberTitle: mode == .agentTeam
              ? "Leader · 主执行 Agent"
              : mode == .dynamicWorkflow ? "主流程 Agent" : "主执行 Agent")
        }.buttonStyle(.plain)
      }
      if mode != .program && children.isEmpty && agent == .null {
        HStack(alignment: .top, spacing: 10) {
          Image(systemName: "info.circle").foregroundStyle(Brand.blue)
          Text("正在准备执行 Agent。绑定到本任务运行的成员才会显示在这里。")
            .font(.caption).foregroundStyle(Brand.muted).lineSpacing(2)
        }
        .padding(14).frame(maxWidth: .infinity, alignment: .leading)
        .background(Brand.softBlue, in: RoundedRectangle(cornerRadius: 16))
      } else if mode != .program {
        ForEach(children, id: \.self) { child in
          NavigationLink {
            AgentContextScreen(
              agent: child, taskTitle: item["title"].text, isTaskAgent: false,
              parentTitle: agent["title"].text)
          } label: {
            MaterialAgentCard(
              agent: child, isTaskAgent: false,
              memberTitle: child["delegation_role"].text == "teammate"
                ? "Team 成员"
                : child["delegation_role"].text == "workflow_node" ? "工作流节点" : "绑定子 Agent")
          }.buttonStyle(.plain)
            .padding(.leading, 14)
            .overlay(alignment: .leading) {
              Rectangle().fill(Brand.blue.opacity(0.2)).frame(width: 2).padding(.vertical, 18)
            }
        }
      }
    }
    .padding(18)
    .background(Brand.raised, in: RoundedRectangle(cornerRadius: 20))
    .overlay(RoundedRectangle(cornerRadius: 20).strokeBorder(Brand.line))
  }
}

private struct MaterialAgentCard: View {
  let agent: JSON
  let isTaskAgent: Bool
  var memberTitle: String? = nil
  private var status: String {
    agent["execution_status"].text.isEmpty ? agent["status"].text : agent["execution_status"].text
  }
  private var latestSummary: String {
    let result = agent["result"].text.trimmingCharacters(in: .whitespacesAndNewlines)
    if !result.isEmpty { return String(result.prefix(260)) }
    if let note = agent["notes"].items.last?["content"].text, !note.isEmpty {
      return String(note.prefix(260))
    }
    return "等待第一条执行记录"
  }

  var body: some View {
    VStack(alignment: .leading, spacing: 10) {
      HStack(alignment: .top, spacing: 10) {
        Image(systemName: isTaskAgent ? "smart_toy" : "person.2")
          .font(.system(size: 17, weight: .medium))
          .foregroundStyle(statusColor)
          .frame(width: 36, height: 36)
          .background(statusColor.opacity(0.11), in: RoundedRectangle(cornerRadius: 12))
        VStack(alignment: .leading, spacing: 4) {
          Text(agent["title"].text.isEmpty ? (isTaskAgent ? "执行 Agent" : "子 Agent") : agent["title"].text)
            .font(.subheadline.weight(.semibold)).foregroundStyle(Brand.ink).lineLimit(2)
            .accessibilityIdentifier(
              isTaskAgent ? "task.agent.title" : "task.subagent.title.\(agent["agent_id"].text)")
          HStack(spacing: 6) {
            Text(memberTitle ?? (isTaskAgent ? "主执行 Agent" : "绑定子 Agent"))
            Text("·")
            Text(taskLabel(status))
          }.font(.caption2).foregroundStyle(statusColor)
        }
        Spacer(minLength: 4)
        Image(systemName: "chevron.right").font(.caption.weight(.semibold))
          .foregroundStyle(Brand.muted).padding(.top, 10)
      }
      Text(latestSummary).font(.subheadline).foregroundStyle(Brand.muted)
        .lineSpacing(2).lineLimit(3)
      HStack(spacing: 6) {
        Text("查看详情")
          .font(.caption2.weight(.medium)).foregroundStyle(Brand.blue)
        Image(systemName: "arrow.up.right").font(.caption2).foregroundStyle(Brand.blue)
      }
    }
    .padding(14)
    .background(Brand.surface, in: RoundedRectangle(cornerRadius: 16))
    .overlay(RoundedRectangle(cornerRadius: 16).strokeBorder(Brand.line.opacity(0.75)))
  }

  private var statusColor: Color {
    if ["failed", "blocked", "expired"].contains(status) { return Brand.attention }
    if ["paused", "waiting"].contains(status) { return Brand.muted }
    if status == "succeeded" { return Color.green }
    return Brand.blue
  }
}

private struct AgentContextScreen: View {
  let agent: JSON
  let taskTitle: String
  let isTaskAgent: Bool
  let parentTitle: String
  @State private var toolsExpanded = false

  private var status: String {
    agent["execution_status"].text.isEmpty ? agent["status"].text : agent["execution_status"].text
  }
  private var activities: [TaskHumanActivity] { taskHumanActivity(agent) }
  private var tools: [TaskHumanActivity] {
    activities.filter { !$0.tool.isEmpty }
  }
  private var communication: [(String, String, String)] {
    var values: [(String, String, String)] = []
    for message in agent["communications"].items {
      let outgoing = message["sender_agent_id"].text == agent["agent_id"].text
      let counterpart =
        outgoing ? message["recipient_title"].text : message["sender_title"].text
      values.append(
        (
          outgoing ? "发给 \(counterpart)" : "来自 \(counterpart)",
          message["content"].text,
          recordDate(message["created_at"].double)
        ))
    }
    for turn in agent["turns"].items {
      values.append(("来自主 Agent 的指令", turn["content"].text, recordDate(turn["created_at"].double)))
    }
    for note in agent["notes"].items {
      values.append(("Agent 回报", note["content"].text, recordDate(note["created_at"].double)))
    }
    let result = agent["result"].text.trimmingCharacters(in: .whitespacesAndNewlines)
    if !result.isEmpty {
      values.append(("最终结果", result, recordDate(agent["finished_at"].double)))
    }
    return values
  }

  var body: some View {
    ScrollView {
      LazyVStack(alignment: .leading, spacing: 16) {
        VStack(alignment: .leading, spacing: 10) {
          HStack {
            MaterialStatusPill(text: taskLabel(status), color: Brand.blue)
            Text(isTaskAgent ? "主执行 Agent" : "绑定子 Agent")
              .font(.caption).foregroundStyle(Brand.muted)
            Spacer()
          }
          Text(agent["title"].text.isEmpty ? "Agent" : agent["title"].text)
            .font(.title2.weight(.semibold)).foregroundStyle(Brand.ink)
          Text(
            isTaskAgent
              ? "负责「\(taskTitle)」的主执行 Agent"
              : "受 \(parentTitle.isEmpty ? "主执行 Agent" : parentTitle) 委派，绑定同一个 TaskRun"
          ).font(.caption).foregroundStyle(Brand.muted)
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Brand.raised, in: RoundedRectangle(cornerRadius: 20))
        .overlay(RoundedRectangle(cornerRadius: 20).strokeBorder(Brand.line))

        AgentDetailCard(title: "上下文与职责", icon: "doc.text") {
          VStack(alignment: .leading, spacing: 10) {
            if !agent["objective"].text.isEmpty {
              Text(agent["objective"].text).font(.subheadline).foregroundStyle(Brand.ink)
                .lineSpacing(2)
            }
            if !agent["success_criteria"].text.isEmpty {
              Text("完成标准：\(agent["success_criteria"].text)")
                .font(.caption).foregroundStyle(Brand.muted).lineSpacing(2)
            }
          }
        }

        AgentDetailCard(title: "Agent 间通信", icon: "arrow.left.arrow.right") {
          if communication.isEmpty {
            Text("还没有可展示的委派指令或回报。").font(.caption).foregroundStyle(Brand.muted)
          } else {
            VStack(alignment: .leading, spacing: 12) {
              ForEach(Array(communication.enumerated()), id: \.offset) { _, item in
                VStack(alignment: .leading, spacing: 4) {
                  HStack {
                    Text(item.0).font(.caption.weight(.semibold)).foregroundStyle(Brand.ink)
                    Spacer()
                    if !item.2.isEmpty {
                      Text(item.2).font(.caption2).foregroundStyle(Brand.muted)
                    }
                  }
                  Text(item.1).font(.caption).foregroundStyle(Brand.muted).lineSpacing(2)
                }
                .padding(12)
                .background(Brand.base, in: RoundedRectangle(cornerRadius: 12))
              }
            }
          }
        }

        AgentDetailCard(title: "执行记录", icon: "list.bullet.rectangle") {
          if activities.isEmpty {
            Text("还没有结构化执行记录。").font(.caption).foregroundStyle(Brand.muted)
          } else {
            VStack(alignment: .leading, spacing: 10) {
              ForEach(activities) { activity in
                HStack(alignment: .top, spacing: 9) {
                  Circle().fill(Brand.blue.opacity(0.7)).frame(width: 6, height: 6)
                    .padding(.top, 5)
                  VStack(alignment: .leading, spacing: 3) {
                    Text(activity.title).font(.caption).foregroundStyle(Brand.ink)
                    if !activity.status.isEmpty {
                      Text(activity.status).font(.caption2).foregroundStyle(Brand.muted)
                    }
                  }
                }
              }
            }
          }
        }

        AgentDetailCard(title: "工具调用", icon: "wrench.and.screwdriver") {
          if tools.isEmpty {
            Text("还没有可展示的工具调用。").font(.caption).foregroundStyle(Brand.muted)
          } else {
            Button {
              withAnimation(.snappy(duration: 0.22)) { toolsExpanded.toggle() }
            } label: {
              HStack {
                Text(toolsExpanded ? "收起工具调用" : "查看 \(tools.count) 条工具调用")
                  .font(.caption.weight(.semibold)).foregroundStyle(Brand.blue)
                Spacer()
                Image(systemName: "chevron.down").font(.caption.weight(.semibold))
                  .rotationEffect(.degrees(toolsExpanded ? 180 : 0)).foregroundStyle(Brand.muted)
              }
            }.buttonStyle(.plain)
            if toolsExpanded {
              VStack(alignment: .leading, spacing: 8) {
                ForEach(tools) { item in
                  HStack(alignment: .top, spacing: 8) {
                    Image(systemName: "wrench.and.screwdriver").font(.caption2)
                      .foregroundStyle(Brand.muted).frame(width: 16)
                    VStack(alignment: .leading, spacing: 2) {
                      Text(item.title).font(.caption).foregroundStyle(Brand.ink)
                      Text([item.tool, item.status].filter { !$0.isEmpty }.joined(separator: " · "))
                        .font(.caption2).foregroundStyle(Brand.muted)
                    }
                  }
                }
              }.padding(.top, 8)
            }
          }
        }
      }.padding(16)
    }
    .background(Brand.canvas)
    .navigationTitle("Agent 详情")
    .navigationBarTitleDisplayMode(.inline)
  }

  private func recordDate(_ stamp: Double) -> String {
    guard stamp > 0 else { return "" }
    return Date(timeIntervalSince1970: stamp).formatted(
      .dateTime.month(.abbreviated).day().hour().minute())
  }
}

private struct AgentDetailCard<Content: View>: View {
  let title: String
  let icon: String
  @ViewBuilder let content: Content

  init(title: String, icon: String, @ViewBuilder content: () -> Content) {
    self.title = title
    self.icon = icon
    self.content = content()
  }

  var body: some View {
    VStack(alignment: .leading, spacing: 12) {
      Label(title, systemImage: icon).font(.headline).foregroundStyle(Brand.ink)
      content
    }
    .padding(18)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(Brand.raised, in: RoundedRectangle(cornerRadius: 20))
    .overlay(RoundedRectangle(cornerRadius: 20).strokeBorder(Brand.line))
  }
}

private struct MaterialTaskDefinitionCard: View {
  let item: JSON
  @State private var expanded = false

  var body: some View {
    VStack(alignment: .leading, spacing: 10) {
      Button {
        withAnimation(.snappy(duration: 0.22)) { expanded.toggle() }
      } label: {
        HStack {
          Label("任务定义", systemImage: "description")
            .font(.subheadline.weight(.semibold)).foregroundStyle(Brand.ink)
          Spacer()
          Image(systemName: "chevron.down").font(.caption.weight(.semibold))
            .rotationEffect(.degrees(expanded ? 180 : 0)).foregroundStyle(Brand.muted)
        }
      }.buttonStyle(.plain)
      if expanded {
        VStack(alignment: .leading, spacing: 10) {
          Text(item["objective"].text).font(.caption).foregroundStyle(Brand.ink)
            .lineSpacing(2)
          VStack(alignment: .leading, spacing: 3) {
            Text("完成标准").font(.caption.weight(.semibold)).foregroundStyle(Brand.muted)
            Text(item["success_criteria"].text).font(.caption).foregroundStyle(Brand.muted)
              .lineSpacing(2)
          }
          HStack(spacing: 8) {
            Text(taskTemporalScope(item).title)
            if !["", "now"].contains(item["schedule"]["mode"].text) {
              Text("·")
              Text(taskSchedule(item["schedule"]))
            }
          }.font(.caption2).foregroundStyle(Brand.muted)
        }
      }
    }
    .padding(16)
    .background(Brand.raised, in: RoundedRectangle(cornerRadius: 18))
    .overlay(RoundedRectangle(cornerRadius: 18).strokeBorder(Brand.line))
  }
}

struct TaskDetailScreen: View {
  @ObservedObject var account: AccountService
  let taskID: String
  let initial: JSON
  var board: TaskBoard? = nil
  var previewMode = false
  var onViewed: (JSON) -> Void = { _ in }
  @Environment(\.dismiss) private var dismiss
  @State private var value: JSON = .null
  @State private var error = ""
  @State private var busy = false
  @State private var deleting = false
  @State private var continuation = ""
  @Environment(\.scenePhase) private var scene
  private var item: JSON { value == .null ? initial : value }
  var body: some View {
    ScrollView {
      LazyVStack(alignment: .leading, spacing: 16) {
        TaskDetailHero(item: item)
        if taskRunNeedsAttention(item) {
          TaskAttentionPanel(item: item)
        }
        if taskCurrentRun(item) != .null {
          MaterialRunOverview(item: item)
        }
        if taskExecutionMode(item) == .dynamicWorkflow,
          !item["execution"]["workflow"]["nodes"].items.isEmpty
        {
          MaterialWorkflowCard(item: item)
        }
        if taskExecutionMode(item) != .program {
          MaterialPlanCard(item: item)
        }
        MaterialExecutionTeam(item: item)
        if let result = item["runs"].items.first?["result"].text, !result.isEmpty {
          VStack(alignment: .leading, spacing: 10) {
            Label("任务结果", systemImage: "check_circle")
              .font(.headline).foregroundStyle(Brand.ink)
            MessageContent(content: result, account: account)
          }
          .padding(18)
          .frame(maxWidth: .infinity, alignment: .leading)
          .background(Color.green.opacity(0.08), in: RoundedRectangle(cornerRadius: 20))
          .overlay(RoundedRectangle(cornerRadius: 20).strokeBorder(Color.green.opacity(0.18)))
        }
        MaterialTaskDefinitionCard(item: item)
        if !error.isEmpty {
          Text(error).font(.caption).foregroundStyle(Brand.attention)
            .padding(.horizontal, 4)
        }
      }.padding(16)
    }.onAppear { onViewed(item) }.background(Brand.canvas).navigationTitle("任务详情")
      .navigationBarTitleDisplayMode(.inline)
      .toolbarBackground(.ultraThinMaterial, for: .navigationBar)
      .toolbar {
        if item["state"].text != "closed" {
        ToolbarItem(placement: .topBarTrailing) {
          Menu {
            if ["paused", "cancelled"].contains(item["state"].text) {
              if taskCurrentRun(item)["error_code"].text == "BUDGET_EXHAUSTED" {
                Text("请在对话中调整预算后继续")
              } else {
                Button("继续任务", systemImage: "play") { Task { await action("resume") } }
              }
            } else {
              if item["source"].text != "conversation",
                !["succeeded", "failed", "expired", "cancelled"].contains(
                  item["runs"].items.first?["status"].text ?? "")
              {
                Button("暂停任务", systemImage: "pause") { Task { await action("pause") } }
              }
              Button("取消任务", systemImage: "xmark.circle", role: .destructive) {
                deleting = true
              }
            }
            Text("请在对话中修改要求")
          } label: {
            Image(systemName: "ellipsis").frame(width: 30, height: 30)
          }.disabled(busy).accessibilityLabel("任务操作")
        }
        }
      }
      .confirmationDialog("删除任务并取消尚未完成的工作？", isPresented: $deleting, titleVisibility: .visible) {
        Button("删除任务", role: .destructive) { deleteImmediately() }
      }
      .task(id: scene) {
        guard !previewMode, scene == .active else { return }
        while !Task.isCancelled {
          await load()
          do { try await Task.sleep(for: .seconds(5)) } catch { return }
        }
      }
  }
  private func load() async {
    do {
      let next = try await account.request(
        "tasks", body: .object(["action": .string("get"), "task_id": .string(taskID)]))
      guard !Task.isCancelled else { return }
      if value != next { value = next; board?.apply(next); onViewed(next) }
      if !error.isEmpty { error = "" }
    } catch is CancellationError {
    } catch { self.error = "暂时无法读取最新进展。" }
  }
  private func deleteImmediately() {
    let store = board
    let removed = store?.hide(taskID)
    let id = taskID
    dismiss()
    Task { @MainActor in
      do {
        #if DEBUG
          if previewMode && ProcessInfo.processInfo.arguments.contains("-HymioSlowDelete") {
            try await Task.sleep(for: .seconds(5))
          }
        #endif
        if !previewMode {
          _ = try await account.request("tasks", body: .object(["action": .string("delete"), "task_id": .string(id)]))
        }
        store?.finishRemoval(id)
      } catch {
        if let removed { store?.restore(removed) }
      }
    }
  }
  private func action(_ action: String) async {
    busy = true
    defer { busy = false }
    do {
      if !previewMode {
        _ = try await account.request("tasks", body: .object(["action": .string(action),
          "task_id": .string(taskID), "content": .string(continuation)]))
      }
      error = ""
      if !previewMode { await load() }
    } catch {
      self.error = "操作未完成，请稍后再试。"
    }
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

struct AgentActivityView: View {
  @ObservedObject var account: AccountService
  let agentID: String
  @State private var entries: [JSON] = []
  @State private var error = ""
  @Environment(\.scenePhase) private var scene
  var body: some View {
    LazyVStack(alignment: .leading, spacing: 12) {
      Text("执行过程").font(.subheadline.weight(.semibold))
      if entries.isEmpty { Text(error.isEmpty ? "等待第一条执行记录" : error).font(.caption).foregroundStyle(Brand.muted) }
      ForEach(entries, id: \.["id"]) { entry in
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
  private var item: JSON? {
    guard let value = ProcessInfo.processInfo.environment["HYMIO_TASK_REVIEW_JSON"],
      let data = value.data(using: .utf8) else { return nil }
    return try? JSONDecoder().decode(JSON.self, from: data)
  }
  var body: some View {
    NavigationStack {
      if let item {
        TaskDetailScreen(account: account, taskID: item["id"].text, initial: item, previewMode: true)
      } else {
        ContentUnavailableView("未提供任务数据", systemImage: "list.bullet.rectangle",
          description: Text("提供任务接口返回的数据后，再查看任务详情。"))
      }
    }
  }
}

struct MultiAgentTaskPreview: View {
  let account: AccountService

  private var item: JSON {
    .object([
      "id": .string("preview-multi-agent"), "revision": .number(1),
      "state": .string("active"), "completion": .string("achieve"),
      "scope": .string("ongoing"), "needs_attention": .bool(true),
      "title": .string("Multi-Agent 入门深度调研与学习路线"),
      "objective": .string("调研多智能体架构、主流框架和学习路线，汇总为一份可执行报告。"),
      "success_criteria": .string("形成有来源、去重且可直接执行的学习报告。"),
      "executor_kind": .string("agent"), "source": .string("conversation"),
      "execution_mode": .string("agent_team"),
      "schedule": .object(["mode": .string("now")]),
      "budget": .object([
        "max_steps": .number(60), "max_tokens": .number(200000),
        "max_active_seconds": .number(2400),
      ]),
      "plan": .array([
        .object(["id": .string("concepts"), "title": .string("调研核心架构"), "state": .string("done")]),
        .object(["id": .string("frameworks"), "title": .string("比较主流框架"), "state": .string("doing")]),
        .object(["id": .string("roadmap"), "title": .string("设计学习路线"), "state": .string("todo")]),
        .object(["id": .string("report"), "title": .string("整合报告"), "state": .string("todo")]),
      ]),
      "runs": .array([
        .object([
          "id": .string("preview-run"), "status": .string("paused"), "stage": .string("execute"),
          "progress": .string("已收集架构模式与三家框架的官方资料，正在等待恢复执行。"),
          "error_code": .string("BUDGET_EXHAUSTED"),
          "agent_id": .string("preview-task-agent"),
          "usage": .object([
            "tokens": .number(194296), "steps": .number(15),
            "active_seconds": .number(29),
          ]),
        ])
      ]),
      "execution": .object([
        "executor": .string("agent"),
        "mode": .string("agent_team"),
        "plan": .array([
          .object(["title": .string("调研核心架构"), "state": .string("done")]),
          .object(["title": .string("比较主流框架"), "state": .string("doing")]),
          .object(["title": .string("设计学习路线"), "state": .string("todo")]),
          .object(["title": .string("整合报告"), "state": .string("todo")]),
        ]),
        "task_agent": .object([
          "agent_id": .string("preview-task-agent"), "title": .string("Multi-Agent 调研主 Agent"),
          "status": .string("paused"), "execution_status": .string("paused"),
          "objective": .string("负责拆分调研任务、监督子 Agent 并整合最终报告。"),
          "success_criteria": .string("汇总所有子任务并完成来源核验。"),
          "notes": .array([
            .object(["content": .string("已确认研究范围，并完成架构模式的第一轮资料收集。")])
          ]),
          "communications": .array([
            .object([
              "id": .string("preview-message-1"),
              "sender_agent_id": .string("preview-child-1"),
              "recipient_agent_id": .string("preview-task-agent"),
              "sender_title": .string("架构模式调研"),
              "recipient_title": .string("Multi-Agent 调研主 Agent"),
              "content": .string("已发现三种架构模式的边界差异，建议纳入最终报告。"),
              "created_at": .number(1_763_600_000),
            ])
          ]),
          "activity": .object([
            "entries": .array([
              .object([
                "id": .number(1), "kind": .string("assistant.message"),
                "content": .string("先把研究拆成架构、框架和学习路线三个并行方向。"),
                "tool_calls": .array([
                  .object([
                    "name": .string("subagent_spawn"),
                    "description": .string("委派架构模式与框架选型调研"),
                  ])
                ]),
              ]),
              .object([
                "id": .number(2), "kind": .string("tool.terminal"),
                "tool": .string("browser"), "tool_description": .string("查阅 Anthropic 多智能体研究"),
                "status": .string("succeeded"), "content": .string(""),
              ]),
              .object([
                "id": .number(3), "kind": .string("assistant.message"),
                "content": .string("资料已整理，下一步需要汇总各子 Agent 的结论。"),
                "tool_calls": .array([]),
              ]),
            ])
          ]),
        ]),
        "subagents": .array([
          .object([
            "agent_id": .string("preview-child-1"), "title": .string("架构模式调研"),
            "delegation_role": .string("teammate"),
            "status": .string("paused"), "execution_status": .string("paused"),
            "objective": .string("梳理 9 种多智能体架构及适用场景。"),
            "success_criteria": .string("每种模式都有代表实现和取舍。"),
            "result": .string("已整理 Orchestrator-Worker、Supervisor 和并行模式。"),
            "notes": .array([]),
            "activity": .object([
              "entries": .array([
                .object([
                  "id": .number(1), "kind": .string("tool.terminal"),
                  "tool": .string("browser"), "tool_description": .string("查阅多智能体架构综述"),
                  "status": .string("succeeded"), "content": .string(""),
                ])
              ])
            ]),
          ]),
          .object([
            "agent_id": .string("preview-child-2"), "title": .string("框架选型调研"),
            "delegation_role": .string("teammate"),
            "status": .string("succeeded"), "execution_status": .string("succeeded"),
            "objective": .string("比较 LangGraph、AutoGen、CrewAI 等框架。"),
            "success_criteria": .string("提供选型决策树。"),
            "result": .string("已完成 10 个框架的定位与核心抽象比较。"),
            "notes": .array([]), "activity": .object(["entries": .array([])]),
          ]),
          .object([
            "agent_id": .string("preview-child-3"), "title": .string("学习路线调研"),
            "delegation_role": .string("teammate"),
            "status": .string("failed"), "execution_status": .string("failed"),
            "objective": .string("整理学习阶段和实战项目。"),
            "success_criteria": .string("形成四阶段路线。"),
            "result": .string("资料源不可用，尚未完成。"),
            "notes": .array([]), "activity": .object(["entries": .array([])]),
          ]),
        ]),
        "team_messages": .array([
          .object([
            "id": .string("preview-message-1"),
            "sender_agent_id": .string("preview-child-1"),
            "recipient_agent_id": .string("preview-task-agent"),
            "sender_title": .string("架构模式调研"),
            "recipient_title": .string("Multi-Agent 调研主 Agent"),
            "content": .string("已发现三种架构模式的边界差异，建议纳入最终报告。"),
            "created_at": .number(1_763_600_000),
          ])
        ]),
        "workflow": .object(["nodes": .array([]), "edges": .array([])]),
        "events": .array([]),
      ]),
    ])
  }

  var body: some View {
    NavigationStack {
      TaskDetailScreen(
        account: account, taskID: "preview-multi-agent", initial: item, previewMode: true)
    }
  }
}

struct WorkflowTaskPreview: View {
  let account: AccountService

  private var item: JSON {
    let agents: [(String, String, String)] = [
      ("preview-wf-design", "交互稿检查", "succeeded"),
      ("preview-wf-backend", "接口回归", "running"),
      ("preview-wf-review", "交叉复核", "pending"),
      ("preview-wf-release", "发布说明", "pending"),
    ]
    return .object([
      "id": .string("preview-workflow"),
      "state": .string("active"),
      "scope": .string("temporary"),
      "completion": .string("achieve"),
      "title": .string("发布前三路核验与整合"),
      "objective": .string("并行完成设计、接口与发布检查，依赖满足后统一复核并生成发布说明。"),
      "success_criteria": .string("所有检查有结果，复核通过并形成发布说明。"),
      "executor_kind": .string("agent"),
      "execution_mode": .string("dynamic_workflow"),
      "schedule": .object(["mode": .string("now")]),
      "budget": .object([
        "max_tokens": .number(80000),
        "max_steps": .number(40),
        "max_active_seconds": .number(1800),
      ]),
      "plan": .array([
        .object(["title": .string("并行检查"), "state": .string("doing")]),
        .object(["title": .string("交叉复核"), "state": .string("todo")]),
        .object(["title": .string("生成发布说明"), "state": .string("todo")]),
      ]),
      "runs": .array([
        .object([
          "id": .string("preview-workflow-run"),
          "status": .string("running"),
          "progress": .string("设计检查已完成，接口回归正在执行。"),
          "agent_id": .string("preview-workflow-leader"),
          "usage": .object([
            "tokens": .number(21400),
            "steps": .number(8),
            "active_seconds": .number(96),
          ]),
        ])
      ]),
      "execution": .object([
        "executor": .string("agent"),
        "mode": .string("dynamic_workflow"),
        "plan": .array([]),
        "task_agent": .object([
          "agent_id": .string("preview-workflow-leader"),
          "title": .string("发布流程 Leader"),
          "status": .string("running"),
          "execution_status": .string("running"),
          "objective": .string("建立依赖，等待节点结果并完成最终整合。"),
          "success_criteria": .string("所有节点成功且发布说明完整。"),
          "result": .string(""),
          "notes": .array([]),
          "activity": .object(["entries": .array([])]),
          "communications": .array([]),
        ]),
        "subagents": .array(
          agents.map { id, title, status in
            .object([
              "agent_id": .string(id),
              "title": .string(title),
              "status": .string(status),
              "execution_status": .string(status),
              "delegation_role": .string("workflow_node"),
              "objective": .string("执行 \(title) 并返回可核验结论。"),
              "success_criteria": .string("结论完整且有证据。"),
              "result": .string(status == "succeeded" ? "已完成交互稿一致性检查。" : ""),
              "notes": .array([]),
              "activity": .object(["entries": .array([])]),
              "communications": .array([]),
            ])
          }),
        "workflow": .object([
          "nodes": .array([
            .object([
              "id": .string("design"), "title": .string("交互稿检查"),
              "depends_on": .array([]), "status": .string("succeeded"),
              "result": .string("主要流程无阻断问题。"),
              "agent_id": .string("preview-wf-design"),
            ]),
            .object([
              "id": .string("backend"), "title": .string("接口回归"),
              "depends_on": .array([]), "status": .string("running"),
              "result": .string(""), "agent_id": .string("preview-wf-backend"),
            ]),
            .object([
              "id": .string("review"), "title": .string("交叉复核"),
              "depends_on": .array([.string("design"), .string("backend")]),
              "status": .string("pending"), "result": .string(""),
              "agent_id": .string("preview-wf-review"),
            ]),
            .object([
              "id": .string("release"), "title": .string("发布说明"),
              "depends_on": .array([.string("review")]),
              "status": .string("pending"), "result": .string(""),
              "agent_id": .string("preview-wf-release"),
            ]),
          ]),
          "edges": .array([
            .object(["from": .string("design"), "to": .string("review")]),
            .object(["from": .string("backend"), "to": .string("review")]),
            .object(["from": .string("review"), "to": .string("release")]),
          ]),
        ]),
        "team_messages": .array([]),
        "events": .array([]),
      ]),
    ])
  }

  var body: some View {
    NavigationStack {
      TaskDetailScreen(
        account: account, taskID: "preview-workflow", initial: item, previewMode: true)
    }
  }
}

struct CalendarWorkspacePreview: View {
  let account: AccountService
  @StateObject private var board = TaskBoard()
  var body: some View {
    NavigationStack { TasksScreen(account: account, board: board, onAccount: {}, previewMode: true) }
      .onAppear {
        guard !board.loaded else { return }
        var c = Calendar.current; c.firstWeekday = 2
        let today = c.startOfDay(for: Date())
        let examples: [(String, Int, Int, Int, String, String)] = [
          ("确认周五住哪家酒店", 0, 9, 0, "active", "blocked"),
          ("比较两家云服务方案", 0, 11, 30, "active", "running"),
          ("下班前带上雨伞", 0, 18, 0, "active", "scheduled"),
          ("准备下一周的阅读清单", 1, 10, 0, "active", "scheduled"),
          ("检查应用的运行情况", 3, 14, 0, "active", "paused"),
          ("订好周末的车票", 5, 16, 30, "active", "scheduled"),
          ("更新周末出行清单", -1, 16, 0, "succeeded", "succeeded"),
          ("整理旧项目的归档说明", -2, 15, 0, "failed", "failed"),
        ]
        board.items = examples.enumerated().map { index, example in
          let day = c.date(byAdding: .day, value: example.1, to: today)!
          let date = c.date(bySettingHour: example.2, minute: example.3, second: 0, of: day)!
          return .object([
            "id": .string("calendar-preview-\(index)"), "title": .string(example.0),
            "objective": .string("把这件事安排好，并带回清楚的结果。"), "source": .string("conversation"),
            "state": .string(example.4), "kind": .string(index == 2 ? "reminder" : "task"),
            "schedule": .object(["mode": .string("once"), "timezone": .string(TimeZone.current.identifier), "at": .string(ISO8601DateFormatter().string(from: date))]),
            "runs": .array([.object(["id": .string("run-\(index)"), "status": .string(example.5), "due_at": .number(date.timeIntervalSince1970), "progress": .string("整理出清楚的下一步，等你看一眼。")])])])
        }
        board.items.append(.object([
          "id": .string("calendar-preview-inbox"),
          "title": .string("把零散想法收进一个笔记"),
          "objective": .string("没有明确时间，先留在待安排。"),
          "source": .string("conversation"), "state": .string("active"), "kind": .string("task"),
          "schedule": .object(["mode": .string("now")]),
          "runs": .array([.object(["id": .string("run-inbox"), "status": .string("scheduled")])]),
        ]))
        board.loaded = true
      }
  }
}

struct MonoTaskStatesPreview: View {
  let account: AccountService
  @StateObject private var board = TaskBoard()

  var body: some View {
    NavigationStack {
      TasksScreen(account: account, board: board, onAccount: {}, showAccountButton: false)
    }
    .onAppear {
      guard board.items.isEmpty else { return }
      var calendar = Calendar.current
      calendar.timeZone = TimeZone(identifier: "Asia/Shanghai") ?? .current
      let start = calendar.startOfDay(for: Date())
      let daily = calendar.date(byAdding: .day, value: 1, to: start).flatMap {
        calendar.date(bySettingHour: 7, minute: 30, second: 0, of: $0)
      }
      let weekly = calendar.date(byAdding: .day, value: 5, to: start).flatMap {
        calendar.date(bySettingHour: 8, minute: 0, second: 0, of: $0)
      }
      board.items = [
        .object([
          "id": .string("mono-food"), "title": .string("每日食谱与买菜提醒"),
          "objective": .string("按当天安排给出食谱与买菜清单"), "state": .string("active"),
          "for_user": .bool(true), "runs": .array([]),
          "schedule": .object([
            "mode": .string("daily"), "time": .string("07:30"),
            "timezone": .string("Asia/Shanghai"),
          ]),
          "next_due_at": .number(daily?.timeIntervalSince1970 ?? 0),
        ]),
        .object([
          "id": .string("mono-weight"), "title": .string("减重追踪：77kg → 65kg（半年）"),
          "objective": .string("每周记录体重和饮食，持续调整计划"), "state": .string("active"),
          "for_user": .bool(true), "runs": .array([]),
          "schedule": .object([
            "mode": .string("weekly"), "weekdays": .array([.number(1)]),
            "time": .string("08:00"), "timezone": .string("Asia/Shanghai"),
          ]),
          "next_due_at": .number(weekly?.timeIntervalSince1970 ?? 0),
        ]),
      ]
      board.loaded = true
    }
  }
}
#endif
