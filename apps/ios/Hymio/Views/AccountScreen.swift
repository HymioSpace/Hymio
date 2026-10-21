import SwiftUI

struct AccountScreen: View {
  @ObservedObject var account: AccountService
  @ObservedObject var client: AgentClient
  @State private var loggingOut = false
  @State private var diagnostics = false
  @State private var modelOptions: [String] = []
  @State private var selectedModel = ""
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
      if !modelError.isEmpty {
        Text(modelError).font(.caption).foregroundStyle(.secondary)
        Button("重新读取") { Task { await loadModels() } }
      }
    } footer: {
      Text("保留对话，下次发送时生效。")
    }
    .task { await loadModels() }
  }
  private func loadModels() async {
    do {
      let value = try await account.request("settings/models")
      modelOptions = value["models"].items.map { $0.text }
      selectedModel = value["selected"].text
      modelError = ""
    } catch { modelError = "暂时无法读取模型设置" }
  }
  private func saveModel(_ model: String) {
    guard !modelBusy, model != selectedModel else { return }
    modelBusy = true
    Task {
      defer { modelBusy = false }
      do {
        _ = try await account.request("settings/models", body: .object(["model": .string(model)]))
        selectedModel = model
        modelError = ""
      } catch { modelError = "模型未更换，请稍后重试。" }
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
                  ? "desktopcomputer" : device["kind"].text == "ios" ? "iphone" : "globe"
              ).frame(width: 24).foregroundStyle(.secondary)
              VStack(alignment: .leading, spacing: 5) {
                Text(
                  device["kind"].text == "cloud_desktop"
                    ? "云电脑" : device["kind"].text == "ios" ? "iPhone" : device["name"].text
                ).font(.subheadline.weight(.medium))
                Text(
                  device["online"].flag
                    ? "在线" : device["state"].text == "paused" ? "已暂停 · 使用时恢复" : "暂不可用"
                ).font(.caption).foregroundStyle(.secondary)
                if device["kind"].text == "cloud_desktop" {
                  Text("终端 · 浏览器 · 桌面").font(.caption2).foregroundStyle(.tertiary)
                }
              }
              Spacer()
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
          Text("iPhone 只用于对话。云电脑负责执行命令、浏览网页和操作桌面。")
        }
        Section {
          NavigationLink {
            TraceScreen(account: account, client: client)
          } label: {
            Label("工作记录", systemImage: "clock.arrow.circlepath")
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
      .navigationTitle("我的").navigationBarTitleDisplayMode(.inline)
      .task {
        while !Task.isCancelled {
          await client.loadDevices()
          do { try await Task.sleep(for: .seconds(15)) } catch { return }
        }
      }
      .refreshable { await client.loadDevices() }
      .confirmationDialog(
        "退出后会清除本机缓存，云端工作仍会继续。", isPresented: $loggingOut, titleVisibility: .visible
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
}
