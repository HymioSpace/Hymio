import XCTest

final class HymioUITests: XCTestCase {
  @MainActor func testRealAccountChatAndReconnect() throws {
    continueAfterFailure = false
    let app = XCUIApplication()
    app.launchEnvironment["HYMIO_UI_TEST"] = "1"
    app.launch()
    if app.buttons["我的账号"].waitForExistence(timeout: 3) {
      app.buttons["我的账号"].tap()
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
    XCTAssertTrue(app.staticTexts["很高兴，认识你。"].waitForExistence(timeout: 5))
    let name = app.textFields["login.username"]
    XCTAssertTrue(name.waitForExistence(timeout: 10))
    name.tap()
    name.typeText(username)
    let pass = app.secureTextFields["login.password"]
    pass.tap()
    pass.typeText(password)
    app.buttons["login.submit"].tap()
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
    let reply = app.staticTexts.matching(NSPredicate(format: "label == %@", String(code)))
      .firstMatch
    XCTAssertTrue(reply.waitForExistence(timeout: 90), app.debugDescription)
    app.terminate()
    app.launch()
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
      NSPredicate(format: "label CONTAINS %@", "AGAIN " + String(code)))
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
    app.buttons["我的账号"].tap()
    XCTAssertTrue(app.navigationBars["我的账号"].waitForExistence(timeout: 5))
    let account = XCTAttachment(screenshot: app.screenshot())
    account.name = "Hymio-iOS-account"
    account.lifetime = .keepAlways
    add(account)
    XCTAssertTrue(app.buttons["account.logout"].waitForExistence(timeout: 10))
    app.buttons["account.logout"].tap()
    XCTAssertTrue(
      app.buttons.matching(identifier: "account.confirmLogout").firstMatch.waitForExistence(
        timeout: 5))
    app.buttons.matching(identifier: "account.confirmLogout").firstMatch.tap()
    XCTAssertTrue(app.buttons["login.submit"].waitForExistence(timeout: 10))
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
