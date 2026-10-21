import XCTest

final class HymioUITests: XCTestCase {
  @MainActor func testNativeSurfaceInteraction() throws {
    continueAfterFailure = false
    let app = XCUIApplication()
    app.launchEnvironment["HYMIO_UI_TEST"] = "1"
    app.launch()
    if app.tabBars.buttons["我的"].waitForExistence(timeout: 3) {
      app.tabBars.buttons["我的"].tap()
      app.buttons["account.logout"].tap()
      let confirm = app.buttons.matching(identifier: "account.confirmLogout").firstMatch
      XCTAssertTrue(confirm.waitForExistence(timeout: 5))
      confirm.tap()
    }
    let username = "surface_" + UUID().uuidString.replacingOccurrences(of: "-", with: "").prefix(10)
    let password = "Test-" + UUID().uuidString
    defer { cleanupAccount(username: String(username), password: password) }
    XCTAssertTrue(app.buttons["login.toggle"].waitForExistence(timeout: 15))
    app.buttons["login.toggle"].tap()
    app.textFields["login.username"].tap()
    app.textFields["login.username"].typeText(username)
    app.secureTextFields["login.password"].tap()
    app.secureTextFields["login.password"].typeText(password)
    app.buttons["login.submit"].tap()
    openChat(app)
    let editor = app.descendants(matching: .any).matching(identifier: "chat.input").firstMatch
    XCTAssertTrue(editor.waitForExistence(timeout: 40))
    editor.tap()
    editor.typeText(
      """
      Do not call tools. Reply ONLY with a fenced hymio-ui block. Inside write exactly this JSON on a single line:
      {"root":"card","elements":{"card":{"type":"Card","props":{"title":"A little room for you","subtitle":"Choose your pace."},"children":["metric","duration","go"]},"metric":{"type":"Metric","props":{"label":"Your time","value":"30 min","detail":"One small thing, just for you."}},"duration":{"type":"Choice","props":{"label":"Time","options":["15 min","30 min"],"value":"30 min"}},"go":{"type":"Button","props":{"label":"Plan together","prompt":"Help me plan {{duration}} of reading. Do not call tools."}}}}
      """)
    app.buttons["chat.send"].tap()
    let title = app.staticTexts["A little room for you"]
    XCTAssertTrue(title.waitForExistence(timeout: 120), app.debugDescription)
    let choice = app.buttons["surface.choice.duration.15 min"]
    XCTAssertTrue(choice.waitForExistence(timeout: 15), app.debugDescription)
    choice.tap()
    let screenshot = XCTAttachment(screenshot: app.screenshot())
    screenshot.name = "native-agent-surface"
    screenshot.lifetime = .keepAlways
    add(screenshot)
    let action = app.buttons["surface.action.go"]
    XCTAssertTrue(action.exists)
    action.tap()
    XCTAssertTrue(
      app.staticTexts["Help me plan 15 min of reading. Do not call tools."].waitForExistence(
        timeout: 10))
    app.tabBars.buttons["我的"].tap()
    app.buttons["工作记录"].tap()
    XCTAssertTrue(app.navigationBars["工作记录"].waitForExistence(timeout: 10))
    let traceScreenshot = XCTAttachment(screenshot: app.screenshot())
    traceScreenshot.name = "native-trace-page"
    traceScreenshot.lifetime = .keepAlways
    add(traceScreenshot)
  }

  @MainActor func testFinishedTraceCollapsesIntoWorkedSummary() throws {
    continueAfterFailure = false
    let app = XCUIApplication()
    app.launchEnvironment["HYMIO_UI_TEST"] = "1"
    app.launch()
    if app.tabBars.buttons["我的"].waitForExistence(timeout: 3) {
      app.tabBars.buttons["我的"].tap()
      app.buttons["account.logout"].tap()
      let confirm = app.buttons.matching(identifier: "account.confirmLogout").firstMatch
      XCTAssertTrue(confirm.waitForExistence(timeout: 5))
      confirm.tap()
    }
    let username = "fold_" + UUID().uuidString.replacingOccurrences(of: "-", with: "").prefix(10)
    let password = "Test-" + UUID().uuidString
    defer { cleanupAccount(username: String(username), password: password) }
    XCTAssertTrue(app.buttons["login.toggle"].waitForExistence(timeout: 15))
    app.buttons["login.toggle"].tap()
    app.textFields["login.username"].tap()
    app.textFields["login.username"].typeText(username)
    app.secureTextFields["login.password"].tap()
    app.secureTextFields["login.password"].typeText(password)
    app.buttons["login.submit"].tap()
    openChat(app)
    let editor = app.descendants(matching: .any).matching(identifier: "chat.input").firstMatch
    XCTAssertTrue(editor.waitForExistence(timeout: 40))
    editor.tap()
    // current_time 是纯本地工具，秒回，不依赖云电脑。
    editor.typeText(
      "现在几点？先调用 current_time 工具拿到当前 UTC 时间，然后告诉我答案。必须调用工具，不要凭空回答。"
    )
    app.buttons["chat.send"].tap()

    let fold = app.descendants(matching: .any).matching(identifier: "trace.fold").firstMatch
    XCTAssertTrue(fold.waitForExistence(timeout: 180), app.debugDescription)
    let worked = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "已工作"))
      .firstMatch
    XCTAssertTrue(worked.waitForExistence(timeout: 10), app.debugDescription)
    XCTAssertTrue(worked.label.count > "已工作 ".count, worked.label)
    // 收起时过程不在无障碍树里。
    XCTAssertFalse(app.staticTexts["current_time"].exists, app.debugDescription)
    let folded = XCTAttachment(screenshot: app.screenshot())
    folded.name = "native-trace-folded"
    folded.lifetime = .keepAlways
    add(folded)

    fold.tap()
    XCTAssertTrue(
      app.staticTexts["current_time"].waitForExistence(timeout: 15), app.debugDescription)
    let expanded = XCTAttachment(screenshot: app.screenshot())
    expanded.name = "native-trace-expanded"
    expanded.lifetime = .keepAlways
    add(expanded)
  }

  @MainActor func testRealAccountChatAndReconnect() throws {
    continueAfterFailure = false
    let app = XCUIApplication()
    app.launchEnvironment["HYMIO_UI_TEST"] = "1"
    app.launch()
    if app.tabBars.buttons["我的"].waitForExistence(timeout: 3) {
      app.tabBars.buttons["我的"].tap()
      app.buttons["account.logout"].tap()
      XCTAssertTrue(
        app.buttons.matching(identifier: "account.confirmLogout").firstMatch.waitForExistence(
          timeout: 5))
      app.buttons.matching(identifier: "account.confirmLogout").firstMatch.tap()
    }
    let username = "ios_" + UUID().uuidString.replacingOccurrences(of: "-", with: "").prefix(12)
    let password = "Test-" + UUID().uuidString
    defer { cleanupAccount(username: String(username), password: password) }
    let toggle = app.buttons["login.toggle"]
    XCTAssertTrue(toggle.waitForExistence(timeout: 10))
    expectation(for: NSPredicate(format: "hittable == true"), evaluatedWith: toggle)
    waitForExpectations(timeout: 10)
    toggle.tap()
    XCTAssertTrue(app.staticTexts["想到什么，交给 Hymio。"].waitForExistence(timeout: 5))
    let name = app.textFields["login.username"]
    XCTAssertTrue(name.waitForExistence(timeout: 10))
    name.tap()
    name.typeText(username)
    let pass = app.secureTextFields["login.password"]
    pass.tap()
    pass.typeText(password)
    app.buttons["login.submit"].tap()
    openChat(app)
    let editor = app.descendants(matching: .any).matching(identifier: "chat.input").firstMatch
    XCTAssertTrue(editor.waitForExistence(timeout: 30), app.debugDescription)
    let code = "IOS" + UUID().uuidString.prefix(6)
    let send = app.buttons["chat.send"]
    XCTAssertTrue(
      NSPredicate(format: "enabled == true").evaluate(with: send)
        || send.waitForExistence(timeout: 15))
    editor.tap()
    editor.typeText("Remember this code: \(code). Reply only with the code. Do not use tools.")
    XCTAssertTrue(send.waitForExistence(timeout: 5))
    send.tap()
    XCTAssertTrue(
      app.descendants(matching: .any).matching(identifier: "message.user").firstMatch
        .waitForExistence(timeout: 2))
    let reply = app.staticTexts.matching(NSPredicate(format: "label == %@", String(code)))
      .firstMatch
    XCTAssertTrue(reply.waitForExistence(timeout: 90), app.debugDescription)
    app.terminate()
    app.launch()
    openChat(app)
    let restored = app.staticTexts.matching(NSPredicate(format: "label == %@", String(code)))
      .firstMatch
    XCTAssertTrue(restored.waitForExistence(timeout: 30), app.debugDescription)
    let next = app.descendants(matching: .any).matching(identifier: "chat.input").firstMatch
    next.tap()
    next.typeText(
      "What code did I ask you to remember? Start with AGAIN, a space, then that code. Then include Markdown: a level-two heading titled Markdown, one bold bullet, one quoted line, a fenced bash code block containing echo hello, and a small two-column table. Do not use tools."
    )
    app.buttons["chat.send"].tap()
    let twoReplies = app.staticTexts.matching(
      NSPredicate(format: "label CONTAINS %@ AND label CONTAINS %@", "AGAIN", String(code)))
    let complete = NSPredicate { _, _ in twoReplies.count >= 1 }
    expectation(for: complete, evaluatedWith: nil)
    waitForExpectations(timeout: 90)
    XCTAssertTrue(
      app.buttons.matching(identifier: "复制代码").firstMatch.waitForExistence(timeout: 45),
      app.debugDescription)
    let screenshot = XCTAttachment(screenshot: app.screenshot())
    screenshot.name = "Hymio-iOS-chat"
    screenshot.lifetime = .keepAlways
    add(screenshot)
    app.tabBars.buttons["我的"].tap()
    XCTAssertTrue(app.navigationBars["我的"].waitForExistence(timeout: 5))
    let account = XCTAttachment(screenshot: app.screenshot())
    account.name = "Hymio-iOS-account"
    account.lifetime = .keepAlways
    add(account)
    XCTAssertTrue(app.buttons["account.logout"].waitForExistence(timeout: 10))
    app.buttons["连接诊断"].tap()
    XCTAssertTrue(app.navigationBars["连接诊断"].waitForExistence(timeout: 5))
    app.navigationBars["连接诊断"].buttons.element(boundBy: 0).tap()
    XCTAssertTrue(app.buttons["account.logout"].waitForExistence(timeout: 5))
    app.buttons["account.logout"].tap()
    XCTAssertTrue(
      app.buttons.matching(identifier: "account.confirmLogout").firstMatch.waitForExistence(
        timeout: 5))
    app.buttons.matching(identifier: "account.confirmLogout").firstMatch.tap()
    XCTAssertTrue(app.buttons["login.submit"].waitForExistence(timeout: 10))
  }
  @MainActor private func openChat(_ app: XCUIApplication) {
    let tab = app.tabBars.buttons["对话"]
    XCTAssertTrue(tab.waitForExistence(timeout: 40), app.debugDescription)
    tab.tap()
  }

  private func cleanupAccount(username: String, password: String) {
    // This test account owns every device returned here; never select by another user's ID.
    let base = "http://127.0.0.1:8080/"
    func request(_ path: String, _ body: [String: Any]? = nil, token: String? = nil) -> [String:
      Any]?
    {
      let semaphore = DispatchSemaphore(value: 0)
      var output: [String: Any]?
      var req = URLRequest(url: URL(string: base + path)!)
      req.timeoutInterval = 20
      if let body {
        req.httpMethod = "POST"
        req.httpBody = try? JSONSerialization.data(withJSONObject: body)
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
      }
      if let token { req.setValue("Bearer " + token, forHTTPHeaderField: "Authorization") }
      URLSession.shared.dataTask(with: req) { data, _, _ in
        defer { semaphore.signal() }
        if let data { output = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] }
      }.resume()
      guard semaphore.wait(timeout: .now() + 25) == .success else { return nil }
      return output
    }
    guard
      let login = request(
        "auth/account", ["action": "login", "username": username, "password": password]),
      let token = login["access_token"] as? String
    else { return }
    if let list = request("devices", token: token)?["devices"] as? [[String: Any]] {
      for device in list {
        if let id = device["device_id"] as? String {
          _ = request("devices/" + id + "/revoke", [:], token: token)
        }
      }
    }
    _ = request("auth/logout", [:], token: token)
  }

}
