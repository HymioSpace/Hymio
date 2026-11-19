import XCTest

final class HymioUITests: XCTestCase {
  @MainActor func testArtworkAlignmentGallery() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-HymioArtworkPreview"]
    app.launch()
    XCTAssertTrue(app.staticTexts["Archive"].waitForExistence(timeout: 10))
    let shot = XCTAttachment(screenshot: app.screenshot())
    shot.name = "artwork-optical-centers"; shot.lifetime = .keepAlways; add(shot)
  }

  @MainActor func testTasksAreAgentManagedAndApplicationsAreRemoved() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-HymioCalendarPreview"]
    app.launch()
    XCTAssertTrue(app.navigationBars["任务与日程"].waitForExistence(timeout: 10))
    XCTAssertFalse(app.buttons["新建安排"].exists)
    XCTAssertFalse(app.buttons["添加安排"].exists)
    app.terminate()
    app.launchArguments = ["-HymioExperiencePreview"]
    app.launch()
    app.buttons["我的"].tap()
    XCTAssertTrue(app.buttons["任务与日程"].waitForExistence(timeout: 5))
    XCTAssertFalse(app.buttons["我的应用"].exists)
  }

  @MainActor func testTaskExecutionGraphExpandsTaskAgentAndLeafResults() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-HymioTaskPreview"]
    app.launchEnvironment["HYMIO_TASK_REVIEW_JSON"] = #"{"id":"ui-test-task","state":"active","title":"界面测试任务","objective":"检查协作节点展开","success_criteria":"可以展开查看结果","executor_kind":"agent","runs":[{"id":"ui-test-run","status":"running","progress":"","next_step":""}],"execution":{"executor":"agent","task_agent":{"agent_id":"parent","title":"执行节点","status":"running","execution_status":"running","result":"主节点测试结果","objective":"检查展开","success_criteria":"能够展开","notes":[],"activity":{"entries":[]}},"subagents":[{"agent_id":"child","title":"子节点","status":"succeeded","result":"子节点测试结果","objective":"检查子节点","success_criteria":"能够展开","notes":[],"activity":{"entries":[]}}],"events":[]}}"#
    app.launch()
    XCTAssertTrue(app.navigationBars["任务详情"].waitForExistence(timeout: 10))
    XCTAssertFalse(app.staticTexts["需要关注"].exists)
    XCTAssertFalse(app.staticTexts["验收"].exists)
    XCTAssertFalse(app.staticTexts["0 步 · 0 tokens"].exists)
    XCTAssertFalse(app.staticTexts["子节点测试结果"].exists)
    let coordinator = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", "任务 Agent · 执行节点")).firstMatch
    XCTAssertTrue(coordinator.isHittable)
    coordinator.tap()
    XCTAssertTrue(app.staticTexts["主节点测试结果"].exists)
    let leaf = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", "协作者 · 子节点")).firstMatch
    for _ in 0..<3 { if leaf.isHittable { break }; app.swipeUp() }
    leaf.tap()
    XCTAssertTrue(app.staticTexts["子节点测试结果"].exists)
  }

  @MainActor func testTaskPreviewWithoutDataDoesNotInventTask() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-HymioTaskPreview"]
    app.launch()
    XCTAssertTrue(app.staticTexts["未提供任务数据"].waitForExistence(timeout: 10))
    XCTAssertFalse(app.staticTexts["准备周末徒步路线"].exists)
  }

  @MainActor func testTaskSnapshotRestoresAndFailedMutationRollsBack() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-HymioTaskStorePreview"]
    app.launch()
    let status = app.staticTexts["task-store.validation"]
    XCTAssertTrue(status.waitForExistence(timeout: 10))
    expectation(for: NSPredicate(format: "label == %@", "Cache and rollback verified"), evaluatedWith: status)
    waitForExpectations(timeout: 10)
  }

  @MainActor func testDeleteTaskImmediatelyRemovesHomeDecision() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-HymioHomePreview", "-HymioHomeManyDecisions", "-HymioSlowDelete"]
    app.launch()
    XCTAssertTrue(app.buttons["home.focus"].firstMatch.waitForExistence(timeout: 10))
    app.buttons["home.focus"].firstMatch.tap()
    XCTAssertTrue(app.buttons["任务操作"].waitForExistence(timeout: 5))
    app.buttons["任务操作"].tap()
    app.buttons["取消任务"].tap()
    app.buttons["删除任务"].tap()
    XCTAssertTrue(app.buttons["home.decisions.all"].waitForExistence(timeout: 2))
    XCTAssertFalse(app.staticTexts["确认周五住哪家酒店"].exists)
    XCTAssertEqual(app.buttons["home.decisions.all"].label, "查看全部 · 4")
    let shot = XCTAttachment(screenshot: app.screenshot())
    shot.name = "home-delete-immediate"; shot.lifetime = .keepAlways; add(shot)
  }

  @MainActor func testRecollectionEmptyActionsAlwaysChangeDestination() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-HymioContextPreview", "-HymioContextRecordsOnly"]
    app.launch()
    app.segmentedControls.buttons["记住的事"].tap()
    XCTAssertTrue(app.buttons["context.empty.action"].waitForExistence(timeout: 5))
    XCTAssertEqual(app.buttons["context.empty.action"].label, "查看足迹")
    app.buttons["context.empty.action"].tap()
    XCTAssertTrue(app.staticTexts["产品体验复盘"].waitForExistence(timeout: 5))
    XCTAssertTrue(app.staticTexts["产品体验复盘"].isHittable)
    XCTAssertFalse(app.buttons["context.empty.action"].exists)
    let footprints = XCTAttachment(screenshot: app.screenshot())
    footprints.name = "view-footprints-opens-visible-records"; footprints.lifetime = .keepAlways; add(footprints)
    app.buttons["来源，苹果日历"].tap()
    XCTAssertTrue(app.staticTexts["产品体验复盘"].waitForExistence(timeout: 5))
    XCTAssertTrue(app.staticTexts["产品体验复盘"].isHittable)
    XCTAssertFalse(app.buttons["context.empty.action"].exists)
    app.buttons["来源，全部"].tap()
    app.terminate()
    app.launchArguments = ["-HymioContextPreview", "-HymioContextInsightsOnly"]
    app.launch()
    XCTAssertTrue(app.buttons["context.empty.action"].waitForExistence(timeout: 5))
    XCTAssertEqual(app.buttons["context.empty.action"].label, "记一笔")
    app.buttons["context.empty.action"].tap()
    XCTAssertTrue(app.buttons["保存到足迹"].waitForExistence(timeout: 5))
    let shot = XCTAttachment(screenshot: app.screenshot())
    shot.name = "recollection-empty-action-opens-editor"; shot.lifetime = .keepAlways; add(shot)
  }

  @MainActor func testNewAccountMemoryEmptyHasNoInventedSourcesOrRetry() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-HymioContextPreview", "-HymioContextEmptyPreview"]
    app.launch()
    XCTAssertTrue(app.staticTexts["还没有记忆"].waitForExistence(timeout: 10))
    XCTAssertFalse(app.staticTexts["暂时读不到记忆"].exists)
    XCTAssertFalse(app.buttons["重试"].exists)
    XCTAssertFalse(app.buttons["来源，Gmail"].exists)
    XCTAssertFalse(app.buttons["来源，滴答清单"].exists)
    XCTAssertTrue(app.buttons["来源，全部"].exists)
    app.segmentedControls.buttons["记住的事"].tap()
    XCTAssertTrue(app.staticTexts["还没有整理出的记忆"].waitForExistence(timeout: 5))
    XCTAssertFalse(app.buttons["重试"].exists)
    XCTAssertFalse(app.buttons["分类，工作"].exists)
    XCTAssertFalse(app.buttons["分类，学习"].exists)
    let shot = XCTAttachment(screenshot: app.screenshot())
    shot.name = "memory-empty-without-invented-taxonomy"
    shot.lifetime = .keepAlways
    add(shot)
  }

  @MainActor func testHomeDecisionCarouselAndEmptySchedule() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-HymioHomePreview", "-HymioHomeManyDecisions"]
    app.launch()
    let carousel = app.scrollViews["home.decisions"]
    XCTAssertTrue(carousel.waitForExistence(timeout: 10))
    XCTAssertTrue(app.buttons["home.focus"].firstMatch.isHittable)
    carousel.swipeLeft()
    XCTAssertTrue(app.buttons.matching(identifier: "home.focus").element(boundBy: 1).isHittable)
    var shot = XCTAttachment(screenshot: app.screenshot())
    shot.name = "home-decisions-second-page"; shot.lifetime = .keepAlways; add(shot)
    app.buttons["home.decisions.all"].tap()
    XCTAssertTrue(app.navigationBars["等你决定"].waitForExistence(timeout: 5))
    let lastDecision = app.descendants(matching: .any).matching(identifier: "home.decision.row.decision-4").firstMatch
    XCTAssertTrue(lastDecision.isHittable)
    XCTAssertLessThanOrEqual(lastDecision.frame.height, 100)
    let listShot = XCTAttachment(screenshot: app.screenshot())
    listShot.name = "home-decisions-compact-list"; listShot.lifetime = .keepAlways; add(listShot)
    app.scrollViews.firstMatch.swipeUp()
    XCTAssertTrue(app.staticTexts["确认要保留的应用"].exists)
    app.terminate()
    app.launchArguments = ["-HymioHomePreview", "-HymioHomeEmpty"]
    app.launch()
    XCTAssertTrue(app.staticTexts["暂无安排"].waitForExistence(timeout: 10))
    XCTAssertFalse(app.staticTexts["没有定时安排"].exists)
    let schedule = app.buttons.matching(identifier: "home.schedule").firstMatch.frame
    let agent = app.buttons.matching(identifier: "home.agent").firstMatch.frame
    XCTAssertLessThanOrEqual(agent.maxY, schedule.minY)
    XCTAssertEqual(schedule.minX, agent.minX, accuracy: 0.5)
    XCTAssertEqual(schedule.width, agent.width, accuracy: 0.5)
    shot = XCTAttachment(screenshot: app.screenshot())
    shot.name = "home-empty-schedule"; shot.lifetime = .keepAlways; add(shot)
  }

  @MainActor func testToolbarControlsAcrossProductDestinations() throws {
    let app = XCUIApplication()
    for (argument, name, addLabel) in [
      ("-HymioHomePreview", "home-menu", ""),
      ("-HymioCalendarPreview", "calendar-toolbar", ""),
      ("-HymioContextPreview", "recollections-toolbar", "添加回忆"),
    ] {
      app.launchArguments = [argument]
      app.launch()
      XCTAssertTrue(app.navigationBars.firstMatch.waitForExistence(timeout: 10))
      let shot = XCTAttachment(screenshot: app.screenshot())
      shot.name = name; shot.lifetime = .keepAlways; add(shot)
      if !addLabel.isEmpty {
        let button = app.buttons[addLabel]
        XCTAssertTrue(button.isHittable)
        XCTAssertGreaterThanOrEqual(button.frame.height, 43.5)
        button.tap()
        let sheet = XCTAttachment(screenshot: app.screenshot())
        sheet.name = name + "-add-sheet"; sheet.lifetime = .keepAlways; add(sheet)
      }
      app.terminate()
    }
    app.launchArguments = ["-HymioExperiencePreview"]
    app.launch()
    XCTAssertTrue(app.buttons["我的"].waitForExistence(timeout: 10))
    app.buttons["我的"].tap()
    XCTAssertTrue(app.buttons["任务与日程"].waitForExistence(timeout: 5))
    let my = XCTAttachment(screenshot: app.screenshot())
    my.name = "my-toolbar"; my.lifetime = .keepAlways; add(my)
  }

  @MainActor func testAccountPrimaryDestinationsStayDistinct() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-HymioExperiencePreview"]
    app.launch()
    app.buttons["我的"].tap()
    for (entry, title) in [("任务与日程", "任务与日程"), ("account.connectors", "连接来源"), ("任务与日程", "任务与日程")] {
      XCTAssertTrue(app.buttons[entry].waitForExistence(timeout: 5))
      app.buttons[entry].tap()
      XCTAssertTrue(app.navigationBars[title].waitForExistence(timeout: 5))
      let shot = XCTAttachment(screenshot: app.screenshot())
      shot.name = "account-destination-" + title; shot.lifetime = .keepAlways; add(shot)
      app.navigationBars[title].buttons.firstMatch.tap()
    }
  }

  @MainActor func testAccountLogoutUsesDedicatedExplanationSheet() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-HymioAccountPreview"]
    app.launch()
    let logout = app.buttons["account.logout"]
    XCTAssertTrue(logout.waitForExistence(timeout: 10))
    for _ in 0..<3 where !logout.isHittable { app.swipeUp() }
    logout.tap()
    XCTAssertTrue(app.staticTexts["云端的任务、记忆和连接不会删除"].waitForExistence(timeout: 5))
    XCTAssertTrue(app.buttons["account.confirmLogout"].exists)
    XCTAssertTrue(app.buttons["取消"].exists)
    let shot = XCTAttachment(screenshot: app.screenshot())
    shot.name = "account-logout-explanation"
    shot.lifetime = .keepAlways
    add(shot)
  }

  @MainActor func testThreeTabsAndGroupedMyNavigation() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-HymioExperiencePreview"]
    app.launch()
    XCTAssertTrue(app.tabBars.buttons["此刻"].waitForExistence(timeout: 10))
    XCTAssertEqual(app.tabBars.buttons.count, 2)
    XCTAssertFalse(app.tabBars.buttons["回忆"].exists)
    app.buttons["我的"].tap()
    XCTAssertTrue(app.buttons["任务与日程"].waitForExistence(timeout: 5))
    XCTAssertTrue(app.buttons["记忆"].exists)
    XCTAssertTrue(app.buttons["对话模型"].exists)
    app.buttons["记忆"].tap()
    XCTAssertTrue(app.staticTexts["记忆"].waitForExistence(timeout: 5))
    app.navigationBars.firstMatch.buttons.firstMatch.tap()
    app.buttons["对话模型"].tap()
    XCTAssertTrue(app.navigationBars["模型设置"].waitForExistence(timeout: 5))
    app.navigationBars.buttons.firstMatch.tap()
    let shot = XCTAttachment(screenshot: app.screenshot())
    shot.name = "my-grouped-navigation"; shot.lifetime = .keepAlways; add(shot)
    app.buttons["关闭我的"].tap()
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
    XCTAssertTrue(app.buttons["分类，做事方式"].exists)
    XCTAssertFalse(app.buttons["分类，工作"].exists)
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
    let editor = app.descendants(matching: .any).matching(identifier: "chat.input").firstMatch
    XCTAssertTrue(editor.isHittable)
    editor.coordinate(withNormalizedOffset: CGVector(dx: 0.7, dy: 0.5)).tap()
    XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 5))
    editor.typeText("draft only")
    XCTAssertTrue((editor.value as? String)?.contains("draft only") == true)
    XCTAssertTrue(final.isHittable, app.debugDescription)
    let input = XCTAttachment(screenshot: app.screenshot())
    input.name = "single-row-composer-keyboard"; input.lifetime = .keepAlways; add(input)
  }

  @MainActor func testHomeLargeTextAndDarkAppearance() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-HymioHomePreview", "-HymioHomeDarkPreview", "-HymioHomeLargePreview"]
    app.launch()
    XCTAssertTrue(app.buttons["home.focus"].waitForExistence(timeout: 10))
    let shot = XCTAttachment(screenshot: app.screenshot())
    shot.name = "home-large-dark"; shot.lifetime = .keepAlways; add(shot)
    app.scrollViews.firstMatch.swipeUp()
    XCTAssertTrue(app.staticTexts["正在发生"].exists)
  }

  @MainActor func testHomePrioritizesAttention() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-HymioHomePreview"]
    app.launch()
    XCTAssertTrue(app.buttons["home.focus"].waitForExistence(timeout: 10))
    XCTAssertTrue(app.staticTexts["确认周五住哪家酒店"].exists)
    XCTAssertTrue(app.staticTexts["接下来"].exists)
    XCTAssertTrue(app.staticTexts["正在发生"].exists)
    let screenshot = XCTAttachment(screenshot: app.screenshot())
    screenshot.name = "home-attention-hierarchy"
    screenshot.lifetime = .keepAlways
    add(screenshot)
  }

  @MainActor func testTasksSwitchCalendarAndStatusViews() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-HymioCalendarPreview"]
    app.launch()
    XCTAssertTrue(app.buttons["任务"].waitForExistence(timeout: 10))
    XCTAssertTrue(app.staticTexts["全部任务"].exists)
    XCTAssertTrue(app.staticTexts["等你决定"].waitForExistence(timeout: 5))
    XCTAssertTrue(app.staticTexts["正在进行"].exists)
    XCTAssertTrue(app.staticTexts["接下来的安排"].exists)
    app.buttons["周"].tap()
    XCTAssertTrue(app.buttons["今天"].waitForExistence(timeout: 5))
    app.buttons["日"].tap()
    XCTAssertTrue(app.buttons["今天"].waitForExistence(timeout: 5))
    app.buttons["月"].tap()
    XCTAssertTrue(app.buttons["任务"].waitForExistence(timeout: 5))
    app.buttons["任务"].tap()
    XCTAssertTrue(app.staticTexts["全部任务"].waitForExistence(timeout: 5))
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
    let gmailHeight = app.buttons["connector.gmail"].frame.height
    let healthHeight = app.buttons["connector.apple_health"].frame.height
    XCTAssertLessThan(gmailHeight, 100)
    XCTAssertEqual(gmailHeight, healthHeight, accuracy: 1)
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
    app.buttons["我的"].tap()
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
    let worked = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "已探索"))
      .firstMatch
    XCTAssertTrue(worked.waitForExistence(timeout: 10), app.debugDescription)
    XCTAssertTrue(worked.label.count > "已探索 ".count, worked.label)
    // 收起时过程不在无障碍树里。
    XCTAssertFalse(app.staticTexts["current_time"].exists, app.debugDescription)
    let folded = XCTAttachment(screenshot: app.screenshot())
    folded.name = "native-trace-folded"
    folded.lifetime = .keepAlways
    add(folded)

    fold.tap()
    XCTAssertTrue(app.navigationBars["探索过程"].waitForExistence(timeout: 5))
    XCTAssertTrue(
      app.staticTexts["current_time"].waitForExistence(timeout: 15), app.debugDescription)
    let expanded = XCTAttachment(screenshot: app.screenshot())
    expanded.name = "native-trace-expanded"
    expanded.lifetime = .keepAlways
    add(expanded)
  }

  @MainActor func testTraceActivityUsesIndependentPanel() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-HymioTracePanelPreview"]
    app.launch()
    XCTAssertTrue(app.navigationBars["探索过程"].waitForExistence(timeout: 10))
    XCTAssertTrue(app.staticTexts["这一次探索"].exists)
    XCTAssertTrue(app.staticTexts["安排已经核对好，下午两点前没有冲突。"].exists)
    let shot = XCTAttachment(screenshot: app.screenshot())
    shot.name = "trace-independent-panel"
    shot.lifetime = .keepAlways
    add(shot)
    app.buttons["完成"].tap()
    XCTAssertFalse(app.navigationBars["探索过程"].waitForExistence(timeout: 2))
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
    app.buttons["我的"].tap()
    XCTAssertTrue(app.navigationBars["我的"].waitForExistence(timeout: 5))
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

  @MainActor private func logoutIfNeeded(_ app: XCUIApplication) {
    guard app.tabBars.buttons["此刻"].waitForExistence(timeout: 8) else { return }
    let menu = app.buttons["我的"]
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
