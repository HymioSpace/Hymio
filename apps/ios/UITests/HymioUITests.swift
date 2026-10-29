import XCTest

final class HymioUITests: XCTestCase {
  @MainActor func testThreeTabsAndGroupedMyNavigation() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-HymioExperiencePreview"]
    app.launch()
    XCTAssertTrue(app.tabBars.buttons["此刻"].waitForExistence(timeout: 10))
    XCTAssertEqual(app.tabBars.buttons.count, 3)
    XCTAssertTrue(app.tabBars.buttons["回忆"].exists)
    app.buttons["账号与设置"].tap()
    XCTAssertTrue(app.buttons["任务与日程"].waitForExistence(timeout: 5))
    XCTAssertTrue(app.buttons["模型与上下文"].exists)
    app.buttons["模型与上下文"].tap()
    XCTAssertTrue(app.navigationBars["模型设置"].waitForExistence(timeout: 5))
    app.navigationBars.buttons.firstMatch.tap()
    let shot = XCTAttachment(screenshot: app.screenshot())
    shot.name = "my-grouped-navigation"; shot.lifetime = .keepAlways; add(shot)
    app.buttons["关闭账号设置"].tap()
    app.tabBars.buttons["回忆"].tap()
    XCTAssertTrue(app.staticTexts["回忆"].waitForExistence(timeout: 5))
  }

  @MainActor func testRecollectionSourceLabelsAndDensity() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-HymioContextPreview"]
    app.launch()
    XCTAssertTrue(app.buttons["context.collect"].waitForExistence(timeout: 10))
    XCTAssertTrue(app.staticTexts["苹果日历"].exists)
    let shot = XCTAttachment(screenshot: app.screenshot())
    shot.name = "recollections-source-icons"; shot.lifetime = .keepAlways; add(shot)
    app.segmentedControls.buttons["记住的事"].tap()
    XCTAssertTrue(app.buttons["context.collect"].exists)
  }

  @MainActor func testActualChatStreamingAnchor() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-HymioActualChatPreview"]
    app.launch()
    XCTAssertTrue(app.staticTexts["chat.stress.complete"].waitForExistence(timeout: 35))
    let final = app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "最终结果已整理好。")).firstMatch
    XCTAssertTrue(final.isHittable, app.debugDescription)
    let shot = XCTAttachment(screenshot: app.screenshot())
    shot.name = "actual-chat-final-anchor"; shot.lifetime = .keepAlways; add(shot)
    app.scrollViews.firstMatch.swipeDown()
    XCTAssertTrue(app.buttons["最新消息"].waitForExistence(timeout: 5))
    app.buttons["最新消息"].tap()
    XCTAssertTrue(final.isHittable)
  }

  @MainActor func testHomeLargeTextAndDarkAppearance() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-HymioHomePreview", "-HymioHomeDarkPreview", "-HymioHomeLargePreview"]
    app.launch()
    XCTAssertTrue(app.buttons["home.focus"].waitForExistence(timeout: 10))
    let shot = XCTAttachment(screenshot: app.screenshot())
    shot.name = "home-large-dark"; shot.lifetime = .keepAlways; add(shot)
    app.scrollViews.firstMatch.swipeUp()
    XCTAssertTrue(app.staticTexts["Hymio"].exists)
  }

  @MainActor func testHomePrioritizesAttention() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-HymioHomePreview"]
    app.launch()
    XCTAssertTrue(app.buttons["home.focus"].waitForExistence(timeout: 10))
    XCTAssertTrue(app.staticTexts["确认周五住哪家酒店"].exists)
    XCTAssertTrue(app.staticTexts["接下来"].exists)
    XCTAssertTrue(app.staticTexts["正在推进"].exists)
    let screenshot = XCTAttachment(screenshot: app.screenshot())
    screenshot.name = "home-attention-hierarchy"
    screenshot.lifetime = .keepAlways
    add(screenshot)
  }

  @MainActor func testTasksSwitchCalendarAndStatusViews() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-HymioCalendarPreview"]
    app.launch()
    XCTAssertTrue(app.buttons["状态"].waitForExistence(timeout: 10))
    app.buttons["状态"].tap()
    XCTAssertTrue(app.staticTexts["等你决定"].waitForExistence(timeout: 5))
    XCTAssertTrue(app.staticTexts["正在进行"].exists)
    XCTAssertTrue(app.staticTexts["接下来的安排"].exists)
    app.buttons["周"].tap()
    XCTAssertTrue(app.buttons["今天"].waitForExistence(timeout: 5))
    app.buttons["日"].tap()
    XCTAssertTrue(app.buttons["今天"].waitForExistence(timeout: 5))
    app.buttons["月"].tap()
    XCTAssertTrue(app.buttons["状态"].waitForExistence(timeout: 5))
    let screenshot = XCTAttachment(screenshot: app.screenshot())
    screenshot.name = "tasks-status-view"
    screenshot.lifetime = .keepAlways
    add(screenshot)
  }

  @MainActor func testConnectorCatalogAndHealthConsent() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-HymioConnectorsPreview"]
    app.launch()
    XCTAssertTrue(app.buttons["connector.gmail"].waitForExistence(timeout: 10))
    let catalog = XCTAttachment(screenshot: app.screenshot())
    catalog.name = "connectors-ios-catalog"
    catalog.lifetime = .keepAlways
    add(catalog)
    app.buttons["connector.apple_health"].tap()
    XCTAssertTrue(app.switches["connector.consent"].waitForExistence(timeout: 5))
    XCTAssertEqual(app.switches["connector.consent"].value as? String, "0")
    let detail = XCTAttachment(screenshot: app.screenshot())
    detail.name = "connectors-ios-health-consent"
    detail.lifetime = .keepAlways
    add(detail)
  }

  @MainActor func testSyntheticStreamingCompletion() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-HymioStreamingPreview"]
    app.launch()
    let status = app.staticTexts["stream.preview.status"]
    XCTAssertTrue(status.waitForExistence(timeout: 10))
    let finished = NSPredicate(format: "label BEGINSWITH 'Complete'")
    expectation(for: finished, evaluatedWith: status)
    waitForExpectations(timeout: 25)
    let done = app.staticTexts["Done."]
    for _ in 0..<8 where !done.isHittable { app.scrollViews.firstMatch.swipeUp() }
    XCTAssertTrue(done.isHittable, app.debugDescription)
    let screenshot = XCTAttachment(screenshot: app.screenshot())
    screenshot.name = "synthetic-stream-completed"
    screenshot.lifetime = .keepAlways
    add(screenshot)
  }

  @MainActor func testNativeSurfaceInteraction() throws {
    continueAfterFailure = false
    let app = XCUIApplication()
    app.launchEnvironment["HYMIO_UI_TEST"] = "1"
    app.launch()
    logoutIfNeeded(app)
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
    app.buttons["打开菜单"].tap()
    app.buttons["探索记录"].tap()
    XCTAssertTrue(app.navigationBars["探索记录"].waitForExistence(timeout: 10))
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
    logoutIfNeeded(app)
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
    logoutIfNeeded(app)
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
    app.buttons["打开菜单"].tap()
    XCTAssertTrue(app.navigationBars["账号"].waitForExistence(timeout: 5))
    let account = XCTAttachment(screenshot: app.screenshot())
    account.name = "Hymio-iOS-account"
    account.lifetime = .keepAlways
    add(account)
    XCTAssertTrue(app.buttons["device.connect"].waitForExistence(timeout: 5))
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

  @MainActor func testBlankTapDismissesKeyboardAndAssistantReaction() throws {
    continueAfterFailure = false
    let app = XCUIApplication()
    app.launchEnvironment["HYMIO_UI_TEST"] = "1"
    app.launch()
    logoutIfNeeded(app)
    let username = "react_" + UUID().uuidString.replacingOccurrences(of: "-", with: "").prefix(10)
    let password = "Test-" + UUID().uuidString
    defer { cleanupAccount(username: String(username), password: password) }
    XCTAssertTrue(app.buttons["login.toggle"].waitForExistence(timeout: 15))
    app.buttons["login.toggle"].tap()
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
    XCTAssertTrue(editor.waitForExistence(timeout: 40), app.debugDescription)
    editor.tap()
    XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 5))
    editor.typeText("请只给这条消息发 🎉 表情，不要回复文字，也不要调用其他工具。")
    app.coordinate(withNormalizedOffset: CGVector(dx: 0.92, dy: 0.18)).tap()
    expectation(
      for: NSPredicate(format: "exists == false"), evaluatedWith: app.keyboards.firstMatch)
    waitForExpectations(timeout: 4)

    app.buttons["chat.send"].tap()
    let reaction = app.staticTexts.matching(
      NSPredicate(format: "label == %@", "Hymio 的回应：🎉")
    ).firstMatch
    XCTAssertTrue(reaction.waitForExistence(timeout: 180), app.debugDescription)
    let message = app.staticTexts.matching(
      NSPredicate(format: "label CONTAINS %@", "请只给这条消息发")
    ).firstMatch
    XCTAssertTrue(message.waitForExistence(timeout: 10), app.debugDescription)
    XCTAssertLessThanOrEqual(reaction.frame.minX, message.frame.minX + 12)
    XCTAssertGreaterThanOrEqual(reaction.frame.maxY, message.frame.maxY - 4)
    XCTAssertLessThanOrEqual(reaction.frame.maxY, message.frame.maxY + 56)

    let screenshot = XCTAttachment(screenshot: app.screenshot())
    screenshot.name = "assistant-reaction-on-user-bubble"
    screenshot.lifetime = .keepAlways
    add(screenshot)
  }

  @MainActor func testKitWebBridgeAndBusinessDataSync() throws {
    continueAfterFailure = false
    let environment = ProcessInfo.processInfo.environment
    let base = environment["HYMIO_KIT_E2E_BACKEND"] ?? "http://127.0.0.1:8080"

    let username = "kit_" + UUID().uuidString.replacingOccurrences(of: "-", with: "").prefix(10)
    let password = "Test-" + UUID().uuidString
    defer { cleanupAccount(username: String(username), password: password) }
    let created = requestJSON(
      base, "auth/account",
      body: [
        "action": "signup", "username": String(username), "password": password,
        "invitation_code": "",
      ])
    XCTAssertEqual(created.status, 200, String(describing: created.json))
    let accessToken = try XCTUnwrap(created.json["access_token"] as? String)
    let installed = requestJSON(
      base, "kits/hymio.ledger/install", body: [:], bearer: accessToken)
    XCTAssertEqual(installed.status, 200, String(describing: installed.json))
    let dayFormat = DateFormatter()
    dayFormat.locale = Locale(identifier: "en_US_POSIX")
    dayFormat.dateFormat = "yyyy-MM-dd"
    func daysAgo(_ count: Int) -> String {
      dayFormat.string(from: Calendar.current.date(byAdding: .day, value: -count, to: Date())!)
    }
    let seed = [
      ["amount": 68, "category": "food", "note": "和朋友吃午饭", "occurred_on": daysAgo(0)],
      ["amount": 8, "category": "transport", "note": "地铁", "occurred_on": daysAgo(1)],
      ["amount": 54, "category": "learning", "note": "一本想看很久的书", "occurred_on": daysAgo(2)],
      ["amount": 39, "category": "life", "note": "洗衣液和鲜花", "occurred_on": daysAgo(4)],
    ]
    for item in seed {
      let seeded = requestJSON(
        base, "kits/hymio.ledger/actions/entries.create",
        body: item, bearer: accessToken)
      XCTAssertEqual(seeded.status, 200, String(describing: seeded.json))
    }

    let app = XCUIApplication()
    app.launchEnvironment["HYMIO_UI_TEST"] = "1"
    app.launchEnvironment["HYMIO_BACKEND_URL_OVERRIDE"] = base
    app.terminate()
    app.launch()
    logoutIfNeeded(app)
    XCTAssertTrue(app.buttons["login.submit"].waitForExistence(timeout: 15))
    app.textFields["login.username"].tap()
    app.textFields["login.username"].typeText(username)
    app.secureTextFields["login.password"].tap()
    app.secureTextFields["login.password"].typeText(password)
    app.buttons["login.submit"].tap()

    XCTAssertTrue(app.tabBars.buttons["应用"].waitForExistence(timeout: 30), app.debugDescription)
    app.tabBars.buttons["应用"].tap()
    let card = app.descendants(matching: .any)
      .matching(identifier: "kit.card.hymio.ledger").firstMatch
    XCTAssertTrue(card.waitForExistence(timeout: 20), app.debugDescription)
    card.tap()
    let web = app.webViews.firstMatch
    XCTAssertTrue(web.waitForExistence(timeout: 20), app.debugDescription)
    let open = web.buttons["记一笔"]
    XCTAssertTrue(open.waitForExistence(timeout: 15), web.debugDescription)
    open.tap()
    let amount = web.textFields["金额"]
    XCTAssertTrue(amount.waitForExistence(timeout: 10), web.debugDescription)
    amount.tap()
    amount.typeText("23.5")
    let note = web.textFields["备注"]
    XCTAssertTrue(note.waitForExistence(timeout: 10), web.debugDescription)
    note.tap()
    note.typeText("页面写入记录")
    note.typeText("\n")
    XCTAssertTrue(
      web.staticTexts["页面写入记录"].waitForExistence(timeout: 20), web.debugDescription)

    let afterPage = requestJSON(
      base, "kits/hymio.ledger/actions/entries.list", body: [:], bearer: accessToken)
    XCTAssertEqual(afterPage.status, 200, String(describing: afterPage.json))
    XCTAssertTrue(notes(afterPage.json).contains("页面写入记录"))

    let afterBusiness = requestJSON(
      base, "kits/hymio.ledger/actions/entries.create",
      body: [
        "amount": 2, "category": "other", "note": "助手记录",
      ],
      bearer: accessToken)
    XCTAssertEqual(afterBusiness.status, 200, String(describing: afterBusiness.json))

    app.navigationBars["生活账本"].buttons.element(boundBy: 0).tap()
    XCTAssertTrue(card.waitForExistence(timeout: 10), app.debugDescription)
    card.tap()
    XCTAssertTrue(web.waitForExistence(timeout: 20), app.debugDescription)
    XCTAssertTrue(
      web.staticTexts["助手记录"].waitForExistence(timeout: 20), web.debugDescription)
    let screenshot = XCTAttachment(screenshot: app.screenshot())
    screenshot.name = "kit-web-bridge-data-sync"
    screenshot.lifetime = .keepAlways
    add(screenshot)
  }

  @MainActor func testCloudGeneratedKitBridge() throws {
    let defaults = UserDefaults.standard
    guard
      let base = defaults.string(forKey: "HYMIO_KIT_E2E_BACKEND"),
      let username = defaults.string(forKey: "HYMIO_KIT_E2E_USERNAME"),
      let password = defaults.string(forKey: "HYMIO_KIT_E2E_PASSWORD"),
      let kitID = defaults.string(forKey: "HYMIO_KIT_E2E_KIT_ID"),
      let kitName = defaults.string(forKey: "HYMIO_KIT_E2E_KIT_NAME")
    else {
      throw XCTSkip("Cloud Kit E2E defaults are not configured")
    }
    continueAfterFailure = false
    let app = XCUIApplication()
    app.launchEnvironment["HYMIO_UI_TEST"] = "1"
    app.launchEnvironment["HYMIO_BACKEND_URL_OVERRIDE"] = base
    app.terminate()
    app.launch()
    logoutIfNeeded(app)
    XCTAssertTrue(app.buttons["login.submit"].waitForExistence(timeout: 20))
    app.textFields["login.username"].tap()
    app.textFields["login.username"].typeText(username)
    app.secureTextFields["login.password"].tap()
    app.secureTextFields["login.password"].typeText(password)
    app.buttons["login.submit"].tap()
    XCTAssertTrue(app.tabBars.buttons["应用"].waitForExistence(timeout: 40))
    app.tabBars.buttons["应用"].tap()
    let card = app.descendants(matching: .any)
      .matching(identifier: "kit.card." + kitID).firstMatch
    XCTAssertTrue(card.waitForExistence(timeout: 30), app.debugDescription)
    card.tap()
    let web = app.webViews.firstMatch
    XCTAssertTrue(web.waitForExistence(timeout: 30), app.debugDescription)
    let write = web.buttons["页面写入"]
    XCTAssertTrue(write.waitForExistence(timeout: 20), web.debugDescription)
    write.tap()
    XCTAssertTrue(web.staticTexts["已保存"].waitForExistence(timeout: 30), web.debugDescription)

    let session = requestJSON(
      base, "auth/account",
      body: ["action": "login", "username": username, "password": password])
    XCTAssertEqual(session.status, 200, String(describing: session.json))
    let accessToken = try XCTUnwrap(session.json["access_token"] as? String)
    let records = requestJSON(
      base, "kits/\(kitID)/actions/items.list",
      body: ["limit": 20], bearer: accessToken)
    XCTAssertEqual(records.status, 200, String(describing: records.json))
    let notes = notes(records.json)
    XCTAssertTrue(notes.contains("页面写入"), String(describing: records.json))
    XCTAssertTrue(notes.contains("Agent写入"), String(describing: records.json))
    let screenshot = XCTAttachment(screenshot: app.screenshot())
    screenshot.name = "cloud-generated-kit-bridge"
    screenshot.lifetime = .keepAlways
    add(screenshot)
    XCTAssertTrue(kitName.isEmpty == false)
  }

  @MainActor private func logoutIfNeeded(_ app: XCUIApplication) {
    guard app.tabBars.buttons["此刻"].waitForExistence(timeout: 8) else { return }
    let menu = app.buttons["打开菜单"]
    XCTAssertTrue(menu.waitForExistence(timeout: 5), app.debugDescription)
    menu.tap()
    let logout = app.buttons["account.logout"]
    if !logout.waitForExistence(timeout: 3) {
      app.swipeUp()
    }
    XCTAssertTrue(logout.waitForExistence(timeout: 10), app.debugDescription)
    logout.tap()
    let confirm = app.buttons.matching(identifier: "account.confirmLogout").firstMatch
    XCTAssertTrue(confirm.waitForExistence(timeout: 5), app.debugDescription)
    confirm.tap()
  }

  @MainActor private func openChat(_ app: XCUIApplication) {
    let tab = app.tabBars.buttons["对话"]
    XCTAssertTrue(tab.waitForExistence(timeout: 40), app.debugDescription)
    tab.tap()
  }

  private func requestJSON(
    _ base: String,
    _ path: String,
    body: [String: Any]? = nil,
    bearer: String? = nil
  ) -> (status: Int, json: [String: Any]) {
    let semaphore = DispatchSemaphore(value: 0)
    var output: (status: Int, json: [String: Any]) = (0, [:])
    var request = URLRequest(url: URL(string: base + "/" + path)!)
    request.timeoutInterval = 30
    if let body {
      request.httpMethod = "POST"
      request.httpBody = try? JSONSerialization.data(withJSONObject: body)
      request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    }
    if let bearer {
      request.setValue("Bearer " + bearer, forHTTPHeaderField: "Authorization")
    }
    URLSession.shared.dataTask(with: request) { data, response, _ in
      defer { semaphore.signal() }
      let status = (response as? HTTPURLResponse)?.statusCode ?? 0
      let json =
        data.flatMap {
          (try? JSONSerialization.jsonObject(with: $0)) as? [String: Any]
        } ?? [:]
      output = (status, json)
    }.resume()
    _ = semaphore.wait(timeout: .now() + 35)
    return output
  }

  private func notes(_ response: [String: Any]) -> [String] {
    guard
      let result = response["result"] as? [String: Any],
      let items = result["items"] as? [[String: Any]]
    else { return [] }
    return items.compactMap {
      ($0["fields"] as? [String: Any])?["note"] as? String ?? $0["note"] as? String
    }
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
