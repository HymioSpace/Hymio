import Foundation
import SwiftUI
import UIKit

struct AccountScreen: View {
  @ObservedObject var account: AccountService
  @ObservedObject var client: AgentClient
  @EnvironmentObject private var notifications: PushNotificationManager
  @Environment(\.dismiss) private var dismiss
  @ObservedObject var taskBoard: TaskBoard
  private enum Destination: String, Identifiable {
    case tasks, applications, connectors
    var id: String { rawValue }
  }
  @State private var destination: Destination?
  @State private var loggingOut = false
  @State private var diagnostics = false
  @State private var modelOptions: [String] = []
  @State private var selectedModel = ""
  @State private var contextWindow = 256_000
  @State private var effectiveWindow = 256_000
  @State private var contextWindows: [Int] = []
  @State private var modelBusy = false
  @State private var modelError = ""
  @State private var authorizationMode = "guided"
  @State private var authorizationModes = ["read_only", "guided", "autonomous"]
  @State private var authorizationRules: [JSON] = []
  @State private var authorizationBusy = false
  @State private var authorizationError = ""
  @State private var pairingPresented = false
  @State private var revokeTarget: JSON?
  @State private var revokePresented = false
  private var modelSection: some View {
    Section {
      Picker(selection: Binding(get: { selectedModel }, set: { saveModel($0) })) {
        if modelOptions.isEmpty { Text("正在读取…").tag("") }
        ForEach(modelOptions, id: \.self) { model in Text(model).tag(model) }
      } label: {
        Label("对话模型", systemImage: "slider.horizontal.3")
      }.pickerStyle(.menu).disabled(modelBusy || modelOptions.isEmpty)
      Picker(selection: Binding(get: { contextWindow }, set: { saveWindow($0) })) {
        ForEach(contextWindows, id: \.self) { value in
          Text(windowLabel(value) + (value == 256_000 ? "（默认）" : "")).tag(value)
        }
      } label: {
        Label("上下文长度", systemImage: "square.stack.3d.up")
      }.pickerStyle(.menu).disabled(modelBusy || contextWindows.isEmpty)
      if !modelError.isEmpty {
        Text(modelError).font(.caption).foregroundStyle(.secondary)
        Button("重新读取") { Task { await loadModels() } }
      }
    } footer: {
      Text(
        effectiveWindow < contextWindow
          ? "当前模型最多使用 \(windowLabel(effectiveWindow))。保留对话，下次发送时生效。"
          : "较短更轻快，较长保留更多近期细节。下次发送时生效。")
    }
    .task { await loadModels() }
  }
  private var authorizationSection: some View {
    Section {
      Picker(
        selection: Binding(
          get: { authorizationMode },
          set: { saveAuthorizationMode($0) }
        )
      ) {
        ForEach(authorizationModes, id: \.self) { mode in
          Text(authorizationModeLabel(mode)).tag(mode)
        }
      } label: {
        Label("工具授权", systemImage: "shield.checkered")
      }.pickerStyle(.menu).disabled(authorizationBusy)
      if !authorizationRules.isEmpty {
        NavigationLink {
          ToolAuthorizationRulesScreen(account: account, initialRules: authorizationRules)
        } label: {
          LabeledContent("始终允许", value: "\(authorizationRules.count) 条")
        }
      }
      if !authorizationError.isEmpty {
        Text(authorizationError).font(.caption).foregroundStyle(.secondary)
      }
    } footer: {
      Text(authorizationModeDetail(authorizationMode))
    }.task { await loadAuthorizationMode() }
  }
  private func loadModels() async {
    do {
      let value = try await account.request("settings/models")
      applyPreferences(value)
      modelError = ""
    } catch { modelError = "暂时无法读取模型设置" }
  }
  private func saveModel(_ model: String) {
    guard !modelBusy, model != selectedModel else { return }
    modelBusy = true
    Task {
      defer { modelBusy = false }
      do {
        let value = try await account.request(
          "settings/models", body: .object(["model": .string(model)]))
        applyPreferences(value)
        modelError = ""
      } catch { modelError = "模型未更换，请稍后重试。" }
    }
  }
  private func windowLabel(_ value: Int) -> String {
    value >= 1_000_000 ? "1M" : String(format: "%gK", Double(value) / 1000)
  }
  private func applyPreferences(_ value: JSON) {
    modelOptions = value["models"].items.map { $0.text }
    selectedModel = value["selected"].text
    contextWindow = value["context_window"].int
    effectiveWindow = value["effective_context_window"].int
    contextWindows = value["context_windows"].items.map { $0.int }
  }
  private func loadAuthorizationMode() async {
    do {
      applyAuthorization(try await account.request("settings/tool-authorization"))
      authorizationError = ""
    } catch { authorizationError = "暂时无法读取工具授权设置" }
  }
  private func applyAuthorization(_ value: JSON) {
    let modes = value["modes"].items.map(\.text).filter { !$0.isEmpty }
    if !modes.isEmpty { authorizationModes = modes }
    let mode = value["mode"].text
    authorizationMode = authorizationModes.contains(mode) ? mode : "guided"
    authorizationRules = value["rules"].items
  }
  private func saveAuthorizationMode(_ mode: String) {
    guard !authorizationBusy, mode != authorizationMode else { return }
    authorizationBusy = true
    Task {
      defer { authorizationBusy = false }
      do {
        applyAuthorization(
          try await account.request(
            "settings/tool-authorization", body: .object(["mode": .string(mode)])))
        authorizationError = ""
      } catch { authorizationError = "授权模式未更改，请稍后重试。" }
    }
  }
  private func authorizationModeLabel(_ mode: String) -> String {
    ["read_only": "只读", "guided": "按需确认", "autonomous": "完全访问"][mode] ?? mode
  }
  private func authorizationModeDetail(_ mode: String) -> String {
    [
      "read_only": "读取、查看和检查类操作直接执行；任何写入都会被阻止。",
      "guided": "读取自动执行；修改操作可在当前任务中确认一次，也可加入始终允许。",
      "autonomous": "普通读写自动执行；支付、凭据、安全设置和不可逆操作仍会确认或阻止。",
    ][mode] ?? "选择 Hymio 何时可以自动执行工具。"
  }
  private func saveWindow(_ size: Int) {
    guard !modelBusy, size != contextWindow else { return }
    modelBusy = true
    Task {
      defer { modelBusy = false }
      do {
        let value = try await account.request(
          "settings/models", body: .object(["context_window": .number(Double(size))]))
        applyPreferences(value)
        modelError = ""
      } catch { modelError = "上下文长度未更改，请稍后重试。" }
    }
  }
  private func accountTile(_ title: String, detail: String, artwork: FeatureArtwork.Kind) -> some View {
    VStack(spacing: 10) {
      FeatureArtwork(kind: artwork, size: 76)
      Text(title).font(.subheadline.weight(.semibold)).foregroundStyle(Brand.ink)
    }.frame(maxWidth: .infinity).padding(.vertical, 14)
      .contentShape(Rectangle())
      .accessibilityElement(children: .ignore).accessibilityLabel(title).accessibilityHint(detail)
  }
  private func accountRow(_ title: String, detail: String, symbol: String) -> some View {
    HStack(spacing: 14) {
      Image(systemName: symbol).font(.system(size: 18, weight: .regular))
        .foregroundStyle(Brand.blue).frame(width: 28)
      VStack(alignment: .leading, spacing: 4) {
        Text(title).font(.subheadline.weight(.medium)).foregroundStyle(Brand.ink)
      }
      Spacer(minLength: 4)
      Image(systemName: "chevron.right").font(.system(size: 11, weight: .medium)).foregroundStyle(Brand.muted)
    }.padding(.vertical, 12).contentShape(Rectangle())
      .accessibilityElement(children: .ignore).accessibilityLabel(title).accessibilityHint(detail)
  }
  var body: some View {
    NavigationStack {
      ScrollView {
        VStack(alignment: .leading, spacing: 24) {
          HStack(alignment: .center, spacing: 18) {
            VStack(alignment: .leading, spacing: 8) {
              Text(account.session?.displayName ?? "我的账号").font(.title.weight(.semibold)).foregroundStyle(Brand.ink)
            }
            Spacer(minLength: 8)
            Companion(size: 72)
          }.padding(.top, 12)
          HStack(spacing: 0) {
            Button { destination = .tasks } label: {
              accountTile("任务与日程", detail: "安排与进展", artwork: .calendar)
            }
            Rectangle().fill(Brand.line).frame(width: 1, height: 56)
            Button { destination = .applications } label: {
              accountTile("我的应用", detail: "为日常添些工具", artwork: .archive)
            }
          }.padding(.vertical, 4)
          Button { destination = .connectors } label: {
            HStack(spacing: 14) {
              FeatureArtwork(kind: .mail, size: 64)
              VStack(alignment: .leading, spacing: 5) {
                Text("连接服务").font(.headline).foregroundStyle(Brand.ink)
                Text("Gmail · 滴答清单 · 健康 · 日历")
                  .font(.caption).foregroundStyle(Brand.muted).fixedSize(horizontal: false, vertical: true)
              }
              Spacer(minLength: 0)
              Image(systemName: "chevron.right").font(.caption).foregroundStyle(Brand.muted)
            }.padding(16).background(Brand.paper, in: RoundedRectangle(cornerRadius: 22))
          }.accessibilityIdentifier("account.connectors")
          VStack(alignment: .leading, spacing: 6) {
            Text("偏好设置").font(.subheadline.weight(.semibold)).foregroundStyle(Brand.ink).padding(.bottom, 6)
            NavigationLink { Form { modelSection }.navigationTitle("模型设置").navigationBarTitleDisplayMode(.inline) } label: {
              accountRow("对话模型", detail: "选择对话模型与上下文长度", symbol: "slider.horizontal.3")
            }
            Divider().overlay(Brand.line)
            NavigationLink { Form { authorizationSection }.navigationTitle("隐私与授权").navigationBarTitleDisplayMode(.inline) } label: {
              accountRow("隐私与授权", detail: "由你决定 Hymio 能做什么", symbol: "hand.raised")
            }
            Divider().overlay(Brand.line)
            NavigationLink { NotificationSettingsScreen(account: account) } label: {
              accountRow("通知与实时活动", detail: "重要进展，及时知道", symbol: "bell")
            }
          }
          VStack(alignment: .leading, spacing: 6) {
            Text("设备").font(.subheadline.weight(.semibold)).foregroundStyle(Brand.ink).padding(.bottom, 6)
          NavigationLink { List {
        Section {
          Button {
            pairingPresented = true
          } label: {
            Label("连接 Mac 或 Android", systemImage: "link.badge.plus")
          }
          .accessibilityIdentifier("device.connect")
          ForEach(client.devices, id: \.self) { device in
            HStack(alignment: .top, spacing: 12) {
              Image(
                systemName: device["kind"].text == "cloud_desktop"
                  ? "desktopcomputer"
                  : device["kind"].text == "personal_mac"
                    ? "desktopcomputer"
                    : ["ios", "personal_android"].contains(device["kind"].text) ? "iphone" : "globe"
              ).frame(width: 24).foregroundStyle(.secondary)
              VStack(alignment: .leading, spacing: 5) {
                Text(
                  device["kind"].text == "cloud_desktop"
                    ? "云电脑" : device["kind"].text == "ios" ? "iPhone" : device["name"].text
                ).font(.subheadline.weight(.medium))
                Text(deviceStatus(device)).font(.caption).foregroundStyle(.secondary)
                if device["kind"].text == "cloud_desktop" {
                  Text("终端 · 浏览器 · 桌面").font(.caption2).foregroundStyle(.tertiary)
                } else if device["kind"].text == "personal_android" {
                  Text("HymioDevice · 手机操作").font(.caption2).foregroundStyle(.tertiary)
                } else if device["kind"].text == "personal_mac" {
                  Text("HymioDevice · 本机操作").font(.caption2).foregroundStyle(.tertiary)
                }
              }
              Spacer()
              if device["kind"].text == "cloud_desktop" {
                let state = device["state"].text
                if state == "paused" || state == "recovery_required" {
                  Button(state == "paused" ? "继续" : "核对并继续") {
                    Task { await client.controlDevice(device["device_id"].text, action: "resume") }
                  }
                  .buttonStyle(.bordered)
                  .controlSize(.small)
                  .disabled(!client.deviceActionID.isEmpty || client.devicesLoading)
                  .accessibilityIdentifier("device.resume")
                }
              }
              if device["provider"].text == "link" {
                if client.deviceActionID == device["device_id"].text {
                  ProgressView().controlSize(.small)
                } else {
                  Menu {
                    Button(
                      device["state"].text == "paused" ? "继续连接" : "暂停连接"
                    ) {
                      Task {
                        await client.controlDevice(
                          device["device_id"].text,
                          action: device["state"].text == "paused" ? "resume" : "pause")
                      }
                    }
                    Button("解除连接", role: .destructive) {
                      revokeTarget = device
                      revokePresented = true
                    }
                  } label: {
                    Image(systemName: "ellipsis.circle")
                      .frame(width: 30, height: 30)
                      .contentShape(Rectangle())
                  }
                  .menuStyle(.borderlessButton)
                  .disabled(client.devicesLoading || !client.deviceActionID.isEmpty)
                  .accessibilityLabel("管理 \(device["name"].text)")
                }
              }
              if device["online"].flag {
                Circle().fill(Brand.blue).frame(width: 5, height: 5).padding(.top, 7)
              }
            }.padding(.vertical, 5)
          }
          if client.devicesLoading && client.devices.isEmpty {
            ProgressView("正在读取设备…").font(.subheadline)
          } else if client.devices.isEmpty && client.devicesError.isEmpty {
            Text("尚未绑定设备").font(.subheadline).foregroundStyle(Brand.muted)
          }
          if !client.devicesError.isEmpty {
            Text(client.devicesError).font(.footnote).foregroundStyle(Brand.muted)
            Button("重新读取") { Task { await client.loadDevices() } }
          }
        } header: {
          Text("我的设备")
        } footer: {
          Text("Mac 和 Android 经 HymioDevice 接入。iPhone 用于对话、记忆和应用。")
        }
          }.navigationTitle("我的设备").navigationBarTitleDisplayMode(.inline)
            .task {
              while !Task.isCancelled {
                await client.loadDevices()
                do { try await Task.sleep(for: .seconds(20)) } catch { return }
              }
            }
          } label: { accountRow("我的设备", detail: "Mac、手机与云电脑", symbol: "desktopcomputer") }

          }
          NavigationLink {
            ScrollView {
              VStack(spacing: 12) {
                NavigationLink { TraceScreen(account: account, client: client) } label: {
                  accountRow("探索记录", detail: "查看一次工作的执行过程", symbol: "clock.arrow.circlepath")
                }
                Button { diagnostics = true } label: {
                  accountRow("连接诊断", detail: "检查连接与同步状态", symbol: "waveform.path.ecg")
                }
              }.padding(22)
            }.background(Brand.base).navigationTitle("调试与诊断").navigationBarTitleDisplayMode(.inline)
          } label: {
            accountRow("调试与诊断", detail: "需要排查问题时再来这里", symbol: "wrench.adjustable")
          }
          Button(role: .destructive) { loggingOut = true } label: {
            Text("退出登录").font(.subheadline).frame(minHeight: 44)
          }.accessibilityIdentifier("account.logout").padding(.top, 8)
        }.padding(.horizontal, 24).padding(.bottom, 28)
          .frame(maxWidth: 620).frame(maxWidth: .infinity)
      }.background(Brand.base).buttonStyle(.plain)
      .navigationTitle("我的").navigationBarTitleDisplayMode(.inline)
      .navigationDestination(item: $destination) { route in
        switch route {
        case .tasks:
          TasksScreen(account: account, board: taskBoard, onAccount: {}, showAccountButton: false)
            .task { taskBoard.bind(account); await taskBoard.refresh(account) }
        case .applications:
          KitsScreen(account: account, onAccount: {}, showAccountButton: false)
        case .connectors:
          ConnectorsScreen(account: account)
        }
      }
      .toolbar {
        ToolbarItem(placement: .cancellationAction) {
          Button {
            dismiss()
          } label: {
            Image(systemName: "xmark")
          }
          .accessibilityLabel("关闭账号设置")
        }
      }
      .refreshable { await client.loadDevices() }
      .sheet(isPresented: $pairingPresented) {
        LinkPairingSheet(account: account) {
          await client.loadDevices()
        }
      }
      .confirmationDialog(
        "解除这台设备？",
        isPresented: $revokePresented,
        titleVisibility: .visible
      ) {
        Button("解除连接", role: .destructive) {
          guard let device = revokeTarget else { return }
          let id = device["device_id"].text
          revokeTarget = nil
          Task { await client.controlDevice(id, action: "revoke") }
        }
        Button("取消", role: .cancel) { revokeTarget = nil }
      } message: {
        Text("会立即停止新的远程操作。已开始的点击或命令不能撤销；HymioDevice 的本机文件和操作历史会保留。")
      }
      .confirmationDialog(
        "退出后会清除本机缓存，云端探索仍会继续。", isPresented: $loggingOut, titleVisibility: .visible
      ) {
        Button("退出登录", role: .destructive) {
          client.reset()
          Task {
            await notifications.detach()
            await account.logout()
          }
        }.accessibilityIdentifier("account.confirmLogout")
      }
      .navigationDestination(isPresented: $diagnostics) {
        List {
          LabeledContent("连接", value: client.phase)
          LabeledContent("已保存事件进度", value: String(client.state.cursor))
          LabeledContent("待确认命令", value: String(client.state.pending.count))
          if !client.error.isEmpty { Text(client.error).font(.caption) }
          Button("重新连接") { client.reconnect() }
          Section("最近事件") {
            ForEach(Array(client.state.events.suffix(25).reversed())) { event in
              DisclosureGroup("\(event.id) · \(event.event_type)") {
                Text(event.payload.pretty).font(.system(.caption2, design: .monospaced))
                  .textSelection(.enabled)
              }.font(.caption)
            }
          }
        }.navigationTitle("连接诊断").navigationBarTitleDisplayMode(.inline)
      }
    }
  }
  private func deviceStatus(_ device: JSON) -> String {
    if device["online"].flag { return "在线" }
    switch device["state"].text {
    case "paused": return "已暂停 · 文件保留，可继续"
    case "recovery_required": return "需要核对 · 不会重复原操作"
    case "changing": return "状态确认中"
    case "preparing": return "正在准备"
    case "missing": return "原环境已失效"
    case "offline": return "暂时无法连接"
    default: return "暂不可用"
    }
  }
}

struct ToolAuthorizationRulesScreen: View {
  @ObservedObject var account: AccountService
  @State private var rules: [JSON]
  @State private var busyID = ""
  @State private var error = ""

  init(account: AccountService, initialRules: [JSON] = []) {
    self.account = account
    _rules = State(initialValue: initialRules)
  }

  var body: some View {
    List {
      if rules.isEmpty {
        ContentUnavailableView(
          "还没有长期规则",
          systemImage: "checkmark.shield",
          description: Text("确认操作时选择“始终允许”，相同操作以后会自动执行。")
        )
      } else {
        Section {
          ForEach(rules, id: \.self) { rule in
            VStack(alignment: .leading, spacing: 4) {
              Text(rule["title"].text).font(.subheadline.weight(.medium))
              let detail = [
                rule["target"].text,
                rule["last_used_at"].double > 0 ? "最近使用过" : "尚未使用",
              ].filter { !$0.isEmpty }.joined(separator: " · ")
              if !detail.isEmpty {
                Text(detail).font(.caption).foregroundStyle(.secondary)
              }
            }
            .padding(.vertical, 4)
            .swipeActions(edge: .trailing, allowsFullSwipe: true) {
              Button("撤销", role: .destructive) {
                Task { await remove(rule) }
              }
            }
            .disabled(busyID == rule["id"].text)
          }
        } footer: {
          Text("这些规则只匹配相同工具、目标和动作；“本次任务”授权不会出现在这里。")
        }
      }
      if !error.isEmpty {
        Text(error).font(.footnote).foregroundStyle(.secondary)
      }
    }
    .navigationTitle("始终允许")
    .navigationBarTitleDisplayMode(.inline)
    .refreshable { await load() }
    .task { await load() }
  }

  private func load() async {
    do {
      let value = try await account.request("settings/tool-authorization")
      rules = value["rules"].items
      error = ""
    } catch {
      self.error = "暂时无法读取长期规则"
    }
  }

  private func remove(_ rule: JSON) async {
    let id = rule["id"].text
    guard !id.isEmpty, busyID.isEmpty else { return }
    busyID = id
    defer { busyID = "" }
    do {
      let value = try await account.request(
        "settings/tool-authorization/rules",
        body: .object(["operation": .string("delete"), "id": .string(id)]))
      rules = value["rules"].items
      error = ""
    } catch {
      self.error = "规则未撤销，请稍后重试"
    }
  }
}

private struct LinkPairingSheet: View {
  @ObservedObject var account: AccountService
  let refreshDevices: () async -> Void
  @Environment(\.dismiss) private var dismiss
  @State private var code = ""
  @State private var expiresAt = 0.0
  @State private var now = Date()
  @State private var busy = false
  @State private var copied = false
  @State private var addressCopied = false
  @State private var error = ""
  private var remaining: Int { max(0, Int(ceil(expiresAt - now.timeIntervalSince1970))) }
  private var backend: String {
    account.backend.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
  }
  var body: some View {
    NavigationStack {
      List {
        Section {
          Text("在 Mac 或 Android 上打开 HymioDevice，填写下面的服务地址和一次性配对码。")
            .font(.callout)
          VStack(alignment: .leading, spacing: 5) {
            Text("服务地址").font(.subheadline)
            Text(backend)
              .font(.caption.monospaced())
              .foregroundStyle(.secondary)
              .textSelection(.enabled)
          }
          Button {
            UIPasteboard.general.string = backend
            addressCopied = true
          } label: {
            Label(
              addressCopied ? "服务地址已复制" : "复制服务地址",
              systemImage: addressCopied ? "checkmark" : "doc.on.doc")
          }
          if busy && code.isEmpty {
            HStack {
              ProgressView()
              Text("正在生成配对码…").foregroundStyle(.secondary)
            }
          } else if !code.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
              Text(code)
                .font(.system(.title2, design: .monospaced, weight: .semibold))
                .textSelection(.enabled)
                .accessibilityLabel("配对码 \(code)")
              Text(remaining > 0 ? "\(remaining / 60):\(String(format: "%02d", remaining % 60)) 后失效" : "配对码已过期")
                .font(.caption)
                .foregroundStyle(remaining > 0 ? Color.secondary : Color.orange)
            }
            Button {
              UIPasteboard.general.string = code
              copied = true
            } label: {
              Label(copied ? "已复制" : "复制配对码", systemImage: copied ? "checkmark" : "doc.on.doc")
            }
          }
          if !error.isEmpty {
            Text(error).font(.footnote).foregroundStyle(.red)
          }
        } footer: {
          Text("配对码五分钟内有效且只能使用一次。连接后仍需在设备上授予屏幕或辅助功能权限。")
        }
        Section {
          Button("重新生成配对码") { Task { await create() } }
            .disabled(busy)
          Button("刷新设备列表") {
            Task {
              await refreshDevices()
              dismiss()
            }
          }
        }
      }
      .navigationTitle("连接个人设备")
      .navigationBarTitleDisplayMode(.inline)
      .toolbar {
        ToolbarItem(placement: .cancellationAction) {
          Button("完成") { dismiss() }
        }
      }
      .task {
        await create()
        while !Task.isCancelled {
          now = Date()
          do { try await Task.sleep(for: .seconds(1)) } catch { return }
        }
      }
    }
  }
  private func create() async {
    guard !busy else { return }
    busy = true
    error = ""
    copied = false
    addressCopied = false
    do {
      let value = try await account.request("devices/link/pairings", body: .object([:]))
      guard value["code"].text.count == 20, value["expires_at"].double > 0 else {
        throw ServiceError.message("服务返回了无效的配对码")
      }
      code = value["code"].text
      expiresAt = value["expires_at"].double
      now = Date()
    } catch {
      code = ""
      self.error = error.localizedDescription
    }
    busy = false
  }
}
