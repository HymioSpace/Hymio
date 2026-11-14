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

private enum TaskDisplayMode: Int, CaseIterable {
  case month, week, day, status

  var title: String {
    switch self {
    case .month: return "月"
    case .week: return "周"
    case .day: return "日"
    case .status: return "状态"
    }
  }

  var calendarScale: Int? {
    self == .status ? nil : rawValue
  }
}

private enum TaskStatusFilter: Hashable, CaseIterable {
  case all, attention, active, scheduled, inbox, finished

  var title: String {
    switch self {
    case .all: return "全部"
    case .attention: return "等你"
    case .active: return "进行中"
    case .scheduled: return "待开始"
    case .inbox: return "待安排"
    case .finished: return "已结束"
    }
  }

  var lane: TaskLane? {
    switch self {
    case .all: return nil
    case .attention: return .attention
    case .active: return .active
    case .scheduled: return .scheduled
    case .inbox: return .inbox
    case .finished: return .finished
    }
  }

}

struct TasksScreen: View {
  @ObservedObject var account: AccountService
  @ObservedObject var board: TaskBoard
  let onAccount: () -> Void
  var showAccountButton = true
  var previewMode = false
  @State private var focus = Date()
  @State private var mode = TaskDisplayMode.month
  @State private var statusFilter = TaskStatusFilter.all
  @State private var hourHeight: CGFloat = 72
  @State private var creating = false
  @State private var inbox = false
  @Environment(\.accessibilityReduceMotion) private var reduceMotion
  @Environment(\.dynamicTypeSize) private var dynamicTypeSize
  private var calendar: Calendar { var c = Calendar.current; c.firstWeekday = 2; return c }
  private var dates: [Date] { calendarDays(focus, scale: mode.calendarScale ?? 0) }
  @State private var events: [CalendarWork] = []
  @State private var eventsByDay: [Date: [CalendarWork]] = [:]
  @State private var groupedTasks: [TaskLane: [JSON]] = [:]
  private var unscheduled: [JSON] { groupedTasks[.inbox] ?? [] }
  var body: some View {
    VStack(spacing: 0) {
      calendarHeader
      if !board.error.isEmpty {
        Button("读取失败，点击重试") { Task { await board.refresh(account) } }
          .font(.footnote).padding(12)
      }
      if mode == .status {
        statusContent
      } else if inbox {
        inboxContent
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
      ToolbarItem(placement: .topBarTrailing) {
        AddActionButton(title: "新建安排") { creating = true }
      }.accountUnframed()
    }
    .sheet(isPresented: $creating, onDismiss: {
      if !previewMode { Task { await board.refresh(account) } }
    }) { TaskEditor(account: account, board: board, initialDate: calendar.date(bySettingHour: 9, minute: 0, second: 0, of: focus)) }
  }
  private var calendarHeader: some View {
    VStack(alignment: .leading, spacing: 14) {
      HStack(alignment: .center) {
        VStack(alignment: .leading, spacing: 4) {
          Text(
            mode == .status
              ? "你的工作 · \(board.items.count) 项"
              : focus.formatted(.dateTime.year().month(.wide))
          ).font(.caption).foregroundStyle(Brand.muted)
          Text(mode == .status ? "状态" : focus.formatted(.dateTime.month(.wide)))
            .font(.largeTitle.weight(.semibold)).tracking(-1)
        }
        Spacer()
        if mode != .status {
          Button("今天") { withAnimation(animation) { focus = Date(); inbox = false } }
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
              inbox = false
            }
          })
      ) {
        ForEach(TaskDisplayMode.allCases, id: \.rawValue) { value in
          Text(value.title).tag(value)
        }
      }.pickerStyle(.segmented).accessibilityIdentifier("tasks.view")

      if mode == .status {
        ScrollView(.horizontal, showsIndicators: false) {
          HStack(spacing: 8) {
            ForEach(TaskStatusFilter.allCases, id: \.self) { value in
              let selected = statusFilter == value
              Button {
                withAnimation(animation) { statusFilter = value }
              } label: {
                HStack(spacing: 5) {
                  Text(value.title)
                  Text("\(statusCount(value))").font(.caption2.monospacedDigit())
                }
                .font(.caption.weight(.medium)).foregroundStyle(selected ? Brand.onAccent : Brand.muted)
                .padding(.horizontal, 12).frame(minHeight: 36)
                .background(selected ? Brand.blue : Brand.base, in: Capsule())
              }.buttonStyle(.plain)
                .accessibilityAddTraits(selected ? .isSelected : [])
            }
          }.padding(.horizontal, 2)
        }
      } else {
        HStack(spacing: 12) {
          Button { withAnimation(animation) { inbox.toggle() } } label: {
            HStack(spacing: 5) {
              Image(systemName: "tray")
              Text("待安排")
              Text("\(unscheduled.count)").font(.caption.monospacedDigit())
            }.font(.caption.weight(.medium)).frame(minHeight: 44)
          }.foregroundStyle(inbox ? Brand.blue : Brand.muted)
            .accessibilityLabel("待安排，\(unscheduled.count) 件")
          Spacer()
          if mode != .month && !inbox {
            Text(TimeZone.current.identifier).font(.caption2).foregroundStyle(Brand.muted)
            Button("缩小时间轴", systemImage: "minus.magnifyingglass") {
              hourHeight = max(48, hourHeight - 24)
            }.labelStyle(.iconOnly).frame(width: 44, height: 36).disabled(hourHeight <= 48)
            Button("放大时间轴", systemImage: "plus.magnifyingglass") {
              hourHeight = min(144, hourHeight + 24)
            }.labelStyle(.iconOnly).frame(width: 44, height: 36).disabled(hourHeight >= 144)
          }
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
  private func statusCount(_ value: TaskStatusFilter) -> Int {
    guard let lane = value.lane else { return board.items.count }
    return groupedTasks[lane]?.count ?? 0
  }
  private var statusContent: some View {
    ScrollView {
      LazyVStack(alignment: .leading, spacing: 0) {
        ForEach(visibleStatusLanes, id: \.0) { lane, items in
          VStack(alignment: .leading, spacing: 2) {
            HStack(alignment: .firstTextBaseline) {
              Circle().fill(statusTint(lane)).frame(width: 7, height: 7)
              Text(statusTitle(lane)).font(.title3.weight(.semibold)).foregroundStyle(Brand.ink)
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
          .padding(.vertical, 18)
          .overlay(alignment: .bottom) { Rectangle().fill(Brand.line).frame(height: 0.5) }
        }
        if visibleStatusLanes.isEmpty {
          VStack(spacing: 10) {
            Image(systemName: "line.3.horizontal.decrease.circle")
              .font(.title2).foregroundStyle(Brand.muted)
            Text("这里暂时没有任务").font(.headline)
            Text("换个状态看看，或新建一项安排。").font(.subheadline)
              .foregroundStyle(Brand.muted)
          }.frame(maxWidth: .infinity).padding(.vertical, 54)
        }
      }.padding(.horizontal, 20).padding(.bottom, 24)
    }
  }
  private var visibleStatusLanes: [(TaskLane, [JSON])] {
    let lanes: [TaskLane] = [.attention, .active, .scheduled, .inbox, .finished]
    return lanes.compactMap { lane in
      guard statusFilter == .all || statusFilter.lane == lane else { return nil }
      let items = groupedTasks[lane] ?? []
      return items.isEmpty ? nil : (lane, items)
    }
  }
  private func statusTitle(_ lane: TaskLane) -> String {
    switch lane {
    case .attention: return "等你决定"
    case .active: return "正在进行"
    case .scheduled: return "接下来的安排"
    case .inbox: return "尚未安排"
    case .finished: return "已经结束"
    }
  }
  private func statusNote(_ lane: TaskLane) -> String {
    switch lane {
    case .attention: return "先看这里"
    case .active: return "无需盯着"
    case .scheduled: return "按时间"
    case .inbox: return "缺少时间"
    case .finished: return "需要时回看"
    }
  }
  private func statusTint(_ lane: TaskLane) -> Color {
    switch lane {
    case .attention: return Brand.attention
    case .active: return Brand.blue
    case .scheduled: return Brand.ink
    case .inbox: return Brand.muted
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
          Button("添加安排", systemImage: "plus") { creating = true }.font(.subheadline).frame(minHeight: 44)
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
  private var inboxContent: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 20) {
        Text("尚未放进日历").font(.title2.weight(.semibold))
        Text("没有指定时间的事情留在这里，正在进行的工作也不会被挪到今天。").font(.subheadline).foregroundStyle(Brand.muted)
        if unscheduled.isEmpty { Text("暂时没有待安排的事。").foregroundStyle(Brand.muted).padding(.vertical, 30) }
        ForEach(unscheduled, id: \.self) { item in
          NavigationLink { TaskDetailScreen(account: account, taskID: item["id"].text, initial: item, board: board, previewMode: previewMode) }
          label: { TaskSummaryCard(item: item) }.buttonStyle(.plain)
        }
      }.padding(22)
    }
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
      .first { !$0.isEmpty } ?? taskSchedule(item["schedule"])
  }
  var body: some View {
    Group {
      if dynamicTypeSize.isAccessibilitySize {
        VStack(alignment: .leading, spacing: 5) {
          HStack(alignment: .top, spacing: 10) {
            Image(systemName: taskSymbol(state)).font(.subheadline)
              .foregroundStyle(["blocked", "failed"].contains(state) ? Brand.attention : Brand.muted)
            Text(item["title"].text).font(.body.weight(.medium)).foregroundStyle(Brand.ink)
              .multilineTextAlignment(.leading)
          }
          Text(detail).font(.caption).foregroundStyle(Brand.muted)
            .multilineTextAlignment(.leading)
          Text(taskLabel(state)).font(.caption2.weight(.medium))
            .foregroundStyle(["blocked", "failed"].contains(state) ? Brand.attention : Brand.muted)
        }.frame(maxWidth: .infinity, alignment: .leading)
      } else {
        HStack(alignment: .top, spacing: 12) {
          Image(systemName: taskSymbol(state)).font(.subheadline)
            .foregroundStyle(["blocked", "failed"].contains(state) ? Brand.attention : Brand.muted)
            .frame(width: 20).padding(.top, 3)
          VStack(alignment: .leading, spacing: 4) {
            Text(item["title"].text).font(.body.weight(.medium)).foregroundStyle(Brand.ink)
              .lineLimit(2).multilineTextAlignment(.leading)
            Text(detail).font(.caption).foregroundStyle(Brand.muted).lineLimit(2)
              .multilineTextAlignment(.leading)
            if taskLane(item) == .scheduled {
              Label(taskSchedule(item["schedule"]), systemImage: "calendar")
                .font(.caption2).foregroundStyle(Brand.muted)
            }
          }
          Spacer(minLength: 8)
          VStack(alignment: .trailing, spacing: 5) {
            Text(taskLabel(state)).font(.caption2.weight(.medium))
              .foregroundStyle(["blocked", "failed"].contains(state) ? Brand.attention : Brand.muted)
            Image(systemName: "chevron.right").font(.caption2).foregroundStyle(Brand.muted)
          }.padding(.top, 1)
        }
      }
    }.frame(minHeight: 54)
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
  @State private var editing = false
  @State private var deleting = false
  @State private var continuation = ""
  @Environment(\.scenePhase) private var scene
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
          }.disabled(busy).accessibilityLabel("任务操作")
        }
      }
      .confirmationDialog("删除任务并取消尚未完成的工作？", isPresented: $deleting, titleVisibility: .visible) {
        Button("删除任务", role: .destructive) { deleteImmediately() }
      }
      .sheet(isPresented: $editing, onDismiss: { Task { await load() } }) {
        TaskEditor(account: account, board: board, existing: item)
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

private struct TaskEditor: View {
  @ObservedObject var account: AccountService
  var board: TaskBoard? = nil
  @EnvironmentObject private var notifications: PushNotificationManager
  var existing: JSON = .null
  var initialDate: Date? = nil
  @Environment(\.dismiss) private var dismiss
  @State private var title = ""
  @State private var objective = ""
  @State private var criteria = ""
  @State private var mode = "now"
  @State private var kind = "task"
  @State private var forUser = false
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
            Toggle("作为我的安排显示在此刻", isOn: $forUser)
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
          if existing == .null && next == "reminder" { if mode == "now" { mode = "once" }; forUser = true }
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
          if existing == .null, let initialDate { date = initialDate; mode = "once" }
          if existing != .null {
            forUser = existing["for_user"].flag
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
      "kind": .string(kind), "for_user": .bool(forUser),
      "objective": .string(objective),
      "success_criteria": .string(
        criteria.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
          ? (kind == "reminder" ? "提醒已送达" : "完成所述目标，并记录结果与未解决事项。") : criteria),
      "schedule": .object(schedule),
    ]
    if existing != .null { body["task_id"] = existing["id"] }
    do {
      let saved = try await account.request("tasks", body: .object(body))
      board?.apply(saved)
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
#endif
