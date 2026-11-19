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
  return taskLabel(taskStatus(item))
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
  @State private var groupedTasks: [TaskLane: [JSON]] = [:]
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
    .background(Brand.surface)
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
    .toolbarBackground(.ultraThinMaterial, for: .navigationBar)
    .toolbar {
      ToolbarItem(placement: .topBarLeading) { if showAccountButton { AccountButton(account: account, action: onAccount) } }.accountUnframed()
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
      Picker(
        "查看方式",
        selection: Binding(
          get: { mode },
          set: { value in
            withAnimation(animation) {
              mode = value
            }
          })
      ) {
        ForEach([TaskDisplayMode.status, .month, .week, .day], id: \.rawValue) { value in
          Text(value.title).tag(value)
        }
      }.pickerStyle(.segmented).accessibilityIdentifier("tasks.view")

      if mode != .status {
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
      .background(Brand.surface)
  }
  private func rebuildCalendar() {
    let nextEvents = calendarWork(board.items, dates: dates)
    events = nextEvents
    eventsByDay = Dictionary(grouping: nextEvents) {
      calendar.startOfDay(for: $0.date)
    }
    groupedTasks = Dictionary(grouping: board.items, by: taskLane).mapValues { items in
      items.sorted {
        let left = taskSortDate($0), right = taskSortDate($1)
        return left == right ? $0["title"].text < $1["title"].text : left < right
      }
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
      LazyVStack(alignment: .leading, spacing: 0) {
        ForEach(visibleStatusLanes, id: \.0) { lane, items in
          VStack(alignment: .leading, spacing: 2) {
            HStack(alignment: .firstTextBaseline) {
              Circle().fill(statusTint(lane)).frame(width: 7, height: 7)
              Text(statusTitle(lane)).font(.headline.weight(.semibold)).foregroundStyle(Brand.ink)
              Text("\(items.count)").font(.caption.monospacedDigit()).foregroundStyle(Brand.muted)
              Spacer()
              if !dynamicTypeSize.isAccessibilitySize {
                Text(statusNote(lane)).font(.caption2).foregroundStyle(Brand.muted)
              }
            }.padding(.bottom, 8)
              .accessibilityElement(children: .combine)
              .accessibilityAddTraits(.isHeader)
            ForEach(items, id: \.self) { item in
              NavigationLink {
                TaskDetailScreen(
                  account: account, taskID: item["id"].text, initial: item, board: board,
                  previewMode: previewMode, onViewed: { board.markSeen($0) })
              } label: {
                TaskStatusRow(item: item)
              }.buttonStyle(.plain)
            }
          }
          .padding(.vertical, 16)
          .overlay(alignment: .bottom) { Rectangle().fill(Brand.line).frame(height: 0.5) }
        }
        if visibleStatusLanes.isEmpty {
          VStack(spacing: 10) {
            Image(systemName: "line.3.horizontal.decrease.circle")
              .font(.title2).foregroundStyle(Brand.muted)
            Text("这里暂时没有任务").font(.headline)
            Text("在对话里说需要做什么，我会替你记录和推进。").font(.subheadline)
              .foregroundStyle(Brand.muted)
          }.frame(maxWidth: .infinity).padding(.vertical, 54)
        }
      }.padding(.horizontal, 20).padding(.bottom, 24)
    }
  }
  private var visibleStatusLanes: [(TaskLane, [JSON])] {
    let lanes: [TaskLane] = [.attention, .active, .scheduled, .other, .finished]
    return lanes.compactMap { lane in
      let items = groupedTasks[lane] ?? []
      return items.isEmpty ? nil : (lane, items)
    }
  }
  private func statusTitle(_ lane: TaskLane) -> String {
    switch lane {
    case .attention: return "需要你处理"
    case .active: return "正在进行"
    case .scheduled: return "按计划"
    case .other: return "其他任务"
    case .finished: return "已完成"
    }
  }
  private func statusNote(_ lane: TaskLane) -> String {
    switch lane {
    case .attention: return "先处理这些"
    case .active: return "暂时不用操作"
    case .scheduled: return "下一次时间"
    case .other: return ""
    case .finished: return ""
    }
  }
  private func statusTint(_ lane: TaskLane) -> Color {
    switch lane {
    case .attention: return Brand.attention
    case .active: return Brand.blue
    case .scheduled: return Brand.ink
    case .other: return Brand.muted
    case .finished: return Brand.muted.opacity(0.7)
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

private func taskNotificationLabel(_ value: String) -> String {
  ["pending": "等待发送", "inflight": "正在发送", "accepted": "系统已接收", "unknown": "回执未知", "failed": "发送失败", "cancelled": "已取消"][value] ?? value
}

private struct TaskExecutionSummary: View {
  let item: JSON
  private var execution: JSON { item["execution"] }
  private var run: JSON { item["runs"].items.first ?? .null }
  var body: some View {
    if run != .null && !["succeeded", "cancelled"].contains(run["status"].text) &&
      (!run["progress"].text.isEmpty || !run["wait_reason"].text.isEmpty || !run["next_step"].text.isEmpty) {
    VStack(alignment: .leading, spacing: 14) {
      let progress = execution["checkpoint"]["progress"].text.isEmpty ? run["progress"].text : execution["checkpoint"]["progress"].text
      if !progress.isEmpty { Text(progress).font(.subheadline).lineLimit(3) }
      if !run["wait_reason"].text.isEmpty {
        Label(run["wait_reason"].text, systemImage: "moon.zzz")
          .font(.caption).foregroundStyle(Brand.blue)
      }
      if !run["next_step"].text.isEmpty {
        Label(run["next_step"].text, systemImage: "arrow.up.right").font(.caption).foregroundStyle(Brand.muted)
      }
    }.padding(16).background(Brand.mist, in: RoundedRectangle(cornerRadius: 14))
    }
  }
}

private struct TaskExecutionDetails: View {
  let item: JSON
  var body: some View {
    DisclosureGroup("执行细节") {
      VStack(alignment: .leading, spacing: 12) {
        let kind = item["executor_kind"].text.isEmpty ? item["execution"]["executor"].text : item["executor_kind"].text
        if !kind.isEmpty { Label(kind == "program" ? "程序规则" : "专属 Agent", systemImage: "cpu") }
        if item["execution"]["usage"] != .null {
          Text("\(item["execution"]["usage"]["steps"].int) 步 · \(item["execution"]["usage"]["tokens"].int) tokens").monospacedDigit()
        }
        if let run = item["runs"].items.first, !["", "none"].contains(run["notification_status"].text) {
          Label("结果通知 · " + taskNotificationLabel(run["notification_status"].text), systemImage: "bell")
        }
        if !item["context"]["brief"].text.isEmpty {
          DisclosureGroup("初始上下文") { Text(item["context"]["brief"].text).textSelection(.enabled) }
        }
        if !item["plan"].items.isEmpty {
          DisclosureGroup("执行计划") {
            ForEach(item["plan"].items, id: \.self) { step in
              Text(step["title"].text.isEmpty ? step["description"].text : step["title"].text)
            }
          }
        }
        if !item["evidence"].items.isEmpty {
          VStack(alignment: .leading, spacing: 6) {
            Text("Agent 提供的依据").font(.caption).foregroundStyle(Brand.muted)
            ForEach(item["evidence"].items, id: \.self) { evidence in
              Text(evidence["summary"].text).font(.subheadline)
              Text(evidence["ref"].text).font(.caption2).foregroundStyle(Brand.muted)
            }
          }
        }
      }.font(.caption).padding(.top, 10).frame(maxWidth: .infinity, alignment: .leading)
    }.font(.subheadline).foregroundStyle(Brand.muted)
  }
}

private struct TaskAgentNode: View {
  let agent: JSON
  let isTaskAgent: Bool
  var body: some View {
    DisclosureGroup {
      VStack(alignment: .leading, spacing: 8) {
        if !agent["result"].text.isEmpty {
          Text(agent["result"].text).font(.subheadline).textSelection(.enabled)
        }
        DisclosureGroup("过程与要求") {
          VStack(alignment: .leading, spacing: 8) {
            Text(agent["objective"].text).font(.caption).textSelection(.enabled)
            Text("完成条件：" + agent["success_criteria"].text).font(.caption).foregroundStyle(Brand.muted)
            ForEach(agent["notes"].items, id: \.self) { note in Text(note["content"].text).font(.caption) }
            ForEach(agent["activity"]["entries"].items, id: \.self) { entry in
              VStack(alignment: .leading, spacing: 4) {
                Text(entry["tool"].text.isEmpty ? entry["kind"].text : entry["tool"].text).font(.caption2).foregroundStyle(Brand.muted)
                if !entry["content"].text.isEmpty { Text(entry["content"].text).font(.caption) }
              }.padding(.vertical, 4)
            }
          }.frame(maxWidth: .infinity, alignment: .leading)
        }.font(.caption)
      }.frame(maxWidth: .infinity, alignment: .leading).padding(.top, 8)
    } label: {
      HStack(spacing: 10) {
        let status = agent["execution_status"].text.isEmpty ? agent["status"].text : agent["execution_status"].text
        Image(systemName: status == "succeeded" ? "checkmark.circle.fill" : (isTaskAgent ? "cpu" : "person.crop.circle"))
          .font(.title3).foregroundStyle(status == "succeeded" ? Color.green : Brand.blue)
          .frame(width: 34, height: 34).background(Brand.mist, in: RoundedRectangle(cornerRadius: 10))
        VStack(alignment: .leading, spacing: 4) {
          Text((isTaskAgent ? "任务 Agent · " : "协作者 · ") + agent["title"].text).font(.subheadline.weight(.medium))
          Text(taskLabel(status)).font(.caption2).foregroundStyle(Brand.muted)
        }
      }.foregroundStyle(Brand.ink)

    }.padding(.vertical, 8)
      .accessibilityIdentifier(isTaskAgent ? "task.agent" : "task.subagent.\(agent["agent_id"].text)")
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
      VStack(alignment: .leading, spacing: 20) {
        VStack(alignment: .leading, spacing: 14) {
          HStack {
            Label(taskDisplayLabel(item), systemImage: taskSymbol(taskStatus(item))).font(
              .caption
            ).foregroundStyle(
              ["failed", "blocked", "expired"].contains(taskStatus(item))
                ? Brand.attention : Brand.muted)
            Spacer()
            if !["", "now"].contains(item["schedule"]["mode"].text) { Text(taskSchedule(item["schedule"])).font(.caption).foregroundStyle(.secondary) }
          }
          Text(item["title"].text).font(.system(.title, design: .rounded, weight: .semibold))
            .tracking(-0.8)
          Text(item["objective"].text).font(.subheadline).foregroundStyle(.secondary).lineLimit(2)
          DisclosureGroup("任务要求") {
            VStack(alignment: .leading, spacing: 7) {
              Text(item["objective"].text)
              Label("怎样算完成", systemImage: "flag").foregroundStyle(Brand.muted)
              Text(item["success_criteria"].text)
            }.font(.caption).frame(maxWidth: .infinity, alignment: .leading).padding(.top, 8)
          }.font(.caption).foregroundStyle(Brand.muted)

        }
        TaskExecutionSummary(item: item)
        if let run = item["runs"].items.first, !run["result"].text.isEmpty {
          VStack(alignment: .leading, spacing: 13) {
            Label(
              run["status"].text == "succeeded" ? "这次的成果" : "最新进展", systemImage: "checkmark.circle"
            ).font(.caption).foregroundStyle(Brand.muted)
            Text(run["result"].text).font(.subheadline).lineLimit(3)
            DisclosureGroup("查看完整成果") { MessageContent(content: run["result"].text, account: account) }
              .font(.caption)
          }.frame(maxWidth: .infinity, alignment: .leading).padding(20).background(
            Brand.mist, in: RoundedRectangle(cornerRadius: 16))
        }
        if item["execution"]["task_agent"] != .null {
          VStack(alignment: .leading, spacing: 10) {
            Label("执行协作 · \(1 + item["execution"]["subagents"].items.count) 个 Agent", systemImage: "person.2")
              .font(.caption.weight(.medium)).foregroundStyle(Brand.muted)
            TaskAgentNode(agent: item["execution"]["task_agent"], isTaskAgent: true)
            ForEach(item["execution"]["subagents"].items, id: \.self) { agent in
              TaskAgentNode(agent: agent, isTaskAgent: false)
                .padding(.leading, 16)
                .overlay(alignment: .leading) { Rectangle().fill(Brand.line).frame(width: 1) }
            }
          }.accessibilityIdentifier("task.execution")
        }
        TaskExecutionDetails(item: item)
        if !item["execution"]["events"].items.isEmpty {
          DisclosureGroup("事件记录 · \(item["execution"]["events"].items.count) 条") {
            ForEach(item["execution"]["events"].items, id: \.self) { event in
              VStack(alignment: .leading, spacing: 4) {
                Text(event["type"].text).font(.caption.weight(.medium))
                Text(taskDate(event["created_at"].double)).font(.caption2).foregroundStyle(Brand.muted)
                let content = event["data"]["content"].text
                let reason = event["data"]["reason"].text
                if !content.isEmpty || !reason.isEmpty { Text(content.isEmpty ? reason : content).font(.caption) }
              }.frame(maxWidth: .infinity, alignment: .leading).padding(.vertical, 6)
            }
          }.font(.subheadline)
        }
        if !error.isEmpty { Text(error).font(.caption).foregroundStyle(.secondary) }
      }.padding(24)
    }.onAppear { onViewed(item) }.background(Brand.surface).navigationTitle("任务详情")
      .navigationBarTitleDisplayMode(.inline)
      .toolbarBackground(.ultraThinMaterial, for: .navigationBar)
      .toolbar {
        if item["state"].text != "closed" {
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
