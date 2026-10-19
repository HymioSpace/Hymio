import SwiftUI

struct LoginScreen: View {
  @ObservedObject var account: AccountService
  @State private var username = ""
  @State private var password = ""
  @State private var signup = false
  @FocusState private var focused: Bool
  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 30) {
        HStack {
          Spacer()
          Companion(size: 100, animated: true)
          Spacer()
        }.padding(.top, 58)
        VStack(alignment: .leading, spacing: 10) {
          Text(signup ? "很高兴，认识你。" : "回来啦。")
            .font(.system(.largeTitle, design: .rounded, weight: .medium)).tracking(-1)
          Text("一个 Hymio，随时接着聊。")
            .font(.subheadline).foregroundStyle(Brand.muted)
        }
        VStack(spacing: 0) {
          TextField("用户名", text: $username)
            .textContentType(.username).textInputAutocapitalization(.never).autocorrectionDisabled()
            .padding(18).accessibilityIdentifier("login.username")
          Divider().padding(.horizontal, 18)
          SecureField(signup ? "密码，至少 8 位" : "密码", text: $password)
            .textContentType(
              ProcessInfo.processInfo.environment["HYMIO_UI_TEST"] == "1"
                ? .oneTimeCode : (signup ? .newPassword : .password)
            )
            .padding(18).accessibilityIdentifier("login.password")
        }
        .background(Brand.mist, in: RoundedRectangle(cornerRadius: 20))
        .focused($focused)
        if !account.error.isEmpty {
          Text(account.error).font(.footnote).foregroundStyle(.red).accessibilityIdentifier(
            "login.error")
        }
        Button {
          focused = false
          Task {
            await account.login(
              username: username.trimmingCharacters(in: .whitespaces), password: password,
              signup: signup)
            password = ""
          }
        } label: {
          HStack {
            Spacer()
            if account.busy {
              ProgressView().tint(Brand.onAccent)
            } else {
              Text(signup ? "创建账号" : "登录").fontWeight(.semibold)
              Image(systemName: "arrow.right")
            }
            Spacer()
          }
          .padding(.horizontal, 18)
        }
        .disabled(account.busy || username.count < 3 || password.count < (signup ? 8 : 1))
        .buttonStyle(PrimaryAction())
        .accessibilityIdentifier("login.submit")
        Button {
          signup.toggle()
          password = ""
          account.error = ""
        } label: {
          Text(signup ? "已有账号？登录" : "第一次来？创建账号").font(.subheadline)
        }
        .frame(maxWidth: .infinity).accessibilityIdentifier("login.toggle")
        Text("与桌面和网页版使用同一账号。\n关闭 App 后，云端已接纳的工作仍会继续。")
          .font(.footnote).foregroundStyle(Brand.muted).lineSpacing(5).padding(.top, 18)
      }.padding(.horizontal, 30).padding(.bottom, 32).frame(maxWidth: 520)
    }
    .background(Brand.surface).foregroundStyle(Brand.ink)
  }
}
