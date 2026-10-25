import SwiftUI

struct AccountScreen: View {
  @ObservedObject var account: AccountService
  @ObservedObject var client: AgentClient
  @Environment(\.dismiss) private var dismiss
  @State private var loggingOut = false
  @State private var diagnostics = false
  @State private var modelOptions: [String] = []
  @State private var selectedModel = ""
  @State private var contextWindow = 256_000
  @State private var effectiveWindow = 256_000
  @State private var contextWindows: [Int] = []
  @State private var modelBusy = false
  @State private var modelError = ""
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
  var body: some View {
    NavigationStack {
      List {
        Section {
          HStack(spacing: 14) {
            Companion(size: 64)
            VStack(alignment: .leading, spacing: 5) {
              Text(account.session?.displayName ?? "我的账号").font(.headline)
              Text("在不同设备上，继续同一段对话。").font(.caption).foregroundStyle(.secondary)
            }
          }.padding(.vertical, 6)
        }
        modelSection
        Section {
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
          Text("iPhone 用于对话、记忆和应用。云电脑负责执行命令、浏览网页和操作桌面。")
        }
        Section {
          NavigationLink {
            TraceScreen(account: account, client: client)
          } label: {
            Label("探索记录", systemImage: "clock.arrow.circlepath")
          }
          Button {
            diagnostics = true
          } label: {
            Label("连接诊断", systemImage: "waveform.path.ecg")
          }
          Button(role: .destructive) {
            loggingOut = true
          } label: {
            Label("退出登录", systemImage: "rectangle.portrait.and.arrow.right")
          }.accessibilityIdentifier("account.logout")
        }
      }
      .navigationTitle("账号").navigationBarTitleDisplayMode(.inline)
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
      .task {
        while !Task.isCancelled {
          await client.loadDevices()
          do { try await Task.sleep(for: .seconds(15)) } catch { return }
        }
      }
      .refreshable { await client.loadDevices() }
      .confirmationDialog(
        "退出后会清除本机缓存，云端探索仍会继续。", isPresented: $loggingOut, titleVisibility: .visible
      ) {
        Button("退出登录", role: .destructive) {
          client.reset()
          Task { await account.logout() }
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
