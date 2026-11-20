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
    XCTAssertTrue(app.navigationBars["任务"].waitForExistence(timeout: 10))
    XCTAssertFalse(app.buttons["新建安排"].exists)
    XCTAssertFalse(app.buttons["添加安排"].exists)
    app.terminate()
    app.launchArguments = ["-HymioExperiencePreview"]
    app.launch()
    app.buttons["我的"].tap()
    XCTAssertTrue(app.buttons["任务"].waitForExistence(timeout: 5))
    XCTAssertFalse(app.buttons["我的应用"].exists)
  }

  @MainActor func testTaskExecutionGraphExpandsTaskAgentAndLeafResults() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-HymioMultiAgentTaskPreview"]
    app.launch()
    XCTAssertTrue(app.navigationBars["任务详情"].waitForExistence(timeout: 10))
    XCTAssertTrue(app.staticTexts["Multi-Agent 入门深度调研与学习路线"].exists)
    XCTAssertTrue(app.staticTexts["长期任务"].exists)
    XCTAssertTrue(app.staticTexts["Agent Team"].exists)
    XCTAssertTrue(app.staticTexts["本轮预算已用尽"].exists)
    XCTAssertTrue(
      app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "194.3k"))
        .firstMatch.exists)
    XCTAssertFalse(app.staticTexts["执行细节"].exists)
    XCTAssertFalse(app.staticTexts["事件记录"].exists)
    for _ in 0..<6 where !app.staticTexts["执行团队"].isHittable { app.swipeUp() }
    XCTAssertTrue(app.staticTexts["执行团队"].exists)
    XCTAssertTrue(app.staticTexts["Multi-Agent 调研主 Agent"].exists)
    XCTAssertFalse(app.staticTexts["查阅 Anthropic 多智能体研究"].exists)
    for _ in 0..<4 where !app.staticTexts["架构模式调研"].isHittable { app.swipeUp() }
    XCTAssertTrue(app.staticTexts["架构模式调研"].isHittable)
    XCTAssertTrue(app.staticTexts["已整理 Orchestrator-Worker、Supervisor 和并行模式。"].exists)
    for _ in 0..<4 where !app.staticTexts["资料源不可用，尚未完成。"].isHittable { app.swipeUp() }
    XCTAssertTrue(app.staticTexts["资料源不可用，尚未完成。"].isHittable)
    for _ in 0..<6 where !app.staticTexts["Multi-Agent 调研主 Agent"].isHittable { app.swipeDown() }
    app.staticTexts["Multi-Agent 调研主 Agent"].tap()
    XCTAssertTrue(app.navigationBars["Agent 详情"].waitForExistence(timeout: 5))
    XCTAssertTrue(app.staticTexts["职责与完成标准"].exists)
    XCTAssertTrue(app.staticTexts["协作记录"].exists)
    XCTAssertTrue(app.buttons["查看内容"].firstMatch.exists)
    XCTAssertTrue(
      app.staticTexts["架构模式调研 → Multi-Agent 调研主 Agent"].exists)
    XCTAssertTrue(app.staticTexts["执行脉络"].exists)
    XCTAssertTrue(app.staticTexts["agent.activity.time.1-tool-0"].exists)
    let toolButton = app.buttons.matching(
      NSPredicate(format: "label CONTAINS %@", "条工具记录")).firstMatch
    for _ in 0..<4 where !toolButton.isHittable { app.swipeUp() }
    XCTAssertTrue(toolButton.isHittable)
    toolButton.tap()
    XCTAssertTrue(app.staticTexts["查阅 Anthropic 多智能体研究"].waitForExistence(timeout: 5))
    XCTAssertFalse(app.staticTexts.matching(
      NSPredicate(format: "label CONTAINS %@", "<!DOCTYPE")).firstMatch.exists)
    let shot = XCTAttachment(screenshot: app.screenshot())
    shot.name = "material-multi-agent-task-panel"
    shot.lifetime = .keepAlways
    add(shot)
  }

  @MainActor func testSubagentDetailRendersReadableBriefAndMarkdownRecord() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-HymioMultiAgentTaskPreview"]
    app.launch()
    XCTAssertTrue(app.navigationBars["任务详情"].waitForExistence(timeout: 10))
    let child = app.staticTexts["架构模式调研"]
    for _ in 0..<8 where !child.isHittable { app.swipeUp() }
    XCTAssertTrue(child.waitForExistence(timeout: 5), app.debugDescription)
    child.tap()
    XCTAssertTrue(app.navigationBars["Agent 详情"].waitForExistence(timeout: 5))
    XCTAssertFalse(
      app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "Dependencies:"))
        .firstMatch.exists)
    XCTAssertFalse(
      app.staticTexts.matching(
        NSPredicate(format: "label CONTAINS %@", "Return a bounded result")
      ).firstMatch.exists)
    let brief = app.descendants(matching: .any).matching(
      NSPredicate(format: "label == %@", "查看完整职责")
    ).firstMatch
    XCTAssertTrue(brief.waitForExistence(timeout: 5), app.debugDescription)
    let rendered = app.descendants(matching: .any).matching(
      NSPredicate(format: "label == %@", "收起内容")
    ).firstMatch
    for _ in 0..<5 where !rendered.isHittable { app.swipeUp() }
    XCTAssertTrue(rendered.isHittable, app.debugDescription)
    XCTAssertTrue(app.staticTexts["低嘌呤菜品池"].waitForExistence(timeout: 5))
    XCTAssertTrue(
      app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "鸡蛋"))
        .firstMatch.waitForExistence(timeout: 5),
      app.debugDescription)
    XCTAssertFalse(
      app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "|---|"))
        .firstMatch.exists)
    let shot = XCTAttachment(screenshot: app.screenshot())
    shot.name = "subagent-readable-brief-and-record"
    shot.lifetime = .keepAlways
    add(shot)
  }

  @MainActor func testDynamicWorkflowShowsDependenciesWithoutToolNoise() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-HymioWorkflowTaskPreview"]
    app.launch()
    XCTAssertTrue(app.navigationBars["任务详情"].waitForExistence(timeout: 10))
    XCTAssertTrue(app.staticTexts["动态工作流"].exists)
    XCTAssertTrue(app.staticTexts["临时任务"].exists)
    for _ in 0..<5 where !app.staticTexts["Workflow DAG"].isHittable { app.swipeUp() }
    XCTAssertTrue(app.staticTexts["Workflow DAG"].exists)
    XCTAssertTrue(app.staticTexts["交互稿检查"].waitForExistence(timeout: 5))
    XCTAssertTrue(app.staticTexts["交叉复核"].exists)
    XCTAssertTrue(app.staticTexts["等待依赖"].exists)
    let reviewNode = app.buttons.matching(
      NSPredicate(format: "label CONTAINS %@", "依赖 交互稿检查、接口回归")
    ).firstMatch
    XCTAssertTrue(reviewNode.exists)
    reviewNode.tap()
    XCTAssertTrue(app.staticTexts["交叉复核"].exists)
    XCTAssertFalse(app.staticTexts["Agent 间通信"].exists)
    XCTAssertFalse(app.staticTexts["执行细节"].exists)
    XCTAssertFalse(app.staticTexts["事件记录"].exists)
    for _ in 0..<5 where !app.buttons["动态工作流说明"].isHittable { app.swipeDown() }
    app.buttons["动态工作流说明"].tap()
    XCTAssertTrue(app.alerts["动态工作流"].waitForExistence(timeout: 5))
    XCTAssertTrue(
      app.alerts["动态工作流"].staticTexts.matching(
        NSPredicate(format: "label CONTAINS %@", "确定步骤依赖")).firstMatch.exists)
    let shot = XCTAttachment(screenshot: app.screenshot())
    shot.name = "material-dynamic-workflow"
    shot.lifetime = .keepAlways
    add(shot)
  }

  @MainActor func testDynamicWorkflowShowsPreparingStateBeforeDAGExists() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-HymioWorkflowTaskPreview"]
    app.launchEnvironment["HYMIO_WORKFLOW_PREVIEW_PENDING"] = "1"
    app.launch()
    XCTAssertTrue(app.staticTexts["工作流准备中"].waitForExistence(timeout: 10))
    XCTAssertFalse(app.staticTexts["Workflow DAG"].exists)
  }

  @MainActor func testTraceShowsChronologicalModelAndToolEvents() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-HymioTracePreview"]
    app.launch()
    XCTAssertTrue(app.navigationBars["执行详情"].waitForExistence(timeout: 10))
    XCTAssertTrue(app.staticTexts["事件顺序"].waitForExistence(timeout: 5))
    XCTAssertTrue(app.staticTexts["trace.detail.title"].exists)
    XCTAssertEqual(app.staticTexts["trace.detail.title"].label, "Compare two sources")
    XCTAssertTrue(app.staticTexts["trace.event.time.1"].label.contains("· +"))
    let labels = ["用户事件", "LLM 请求", "LLM 响应", "Tool 调用", "Tool 结果"]
    for label in labels {
      for _ in 0..<5 where !app.staticTexts[label].exists { app.swipeUp() }
      XCTAssertTrue(app.staticTexts[label].exists, "Missing trace event: \(label)")
    }
    XCTAssertTrue(app.staticTexts["Read the comparison page"].exists)
    let shot = XCTAttachment(screenshot: app.screenshot())
    shot.name = "trace-event-order-request-tool-result"
    shot.lifetime = .keepAlways
    add(shot)
  }

  @MainActor func testTaskPreviewWithoutDataDoesNotInventTask() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-HymioTaskPreview"]
    app.launch()
    XCTAssertTrue(app.staticTexts["未提供任务数据"].waitForExistence(timeout: 10))
    XCTAssertFalse(app.staticTexts["准备周末徒步路线"].exists)
  }

  @MainActor func testMaterialTaskPanelTwentyFourRoundVerificationMatrix() throws {
    func json(_ value: [String: Any]) -> String {
      String(
        data: try! JSONSerialization.data(withJSONObject: value, options: []),
        encoding: .utf8)!
    }
    func fixture(
      index: Int, scope: String, mode: String, runStatus: String, agentStatus: String,
      subagentStatuses: [String]
    ) -> String {
      var task: [String: Any] = [
        "id": "matrix-\(index)", "state": agentStatus == "succeeded" ? "closed" : "active",
        "completion": scope == "ongoing" ? "maintain" : "achieve",
        "scope": scope, "needs_attention": ["paused", "failed", "blocked"].contains(runStatus),
        "title": "验证任务 \(index)：Multi-Agent 研究",
        "objective": "验证任务列表、执行团队、计划、预算和等待状态在 Material 任务面板中的表达。",
        "success_criteria": "所有关键信息可读，且不展示原始 HTML 或调试 JSON。",
        "executor_kind": mode == "program" ? "program" : "agent",
        "execution_mode": mode, "source": "conversation",
        "schedule": ["mode": scope == "ongoing" ? "daily" : "now", "time": "08:00"],
        "budget": ["max_steps": 60, "max_tokens": 200000, "max_active_seconds": 2400],
        "plan": [
          ["title": "收集资料", "state": index % 2 == 0 ? "done" : "doing"],
          ["title": "比较方案", "state": "todo"],
          ["title": "整合结论", "state": "todo"],
        ],
      ]
      task["runs"] = [
        [
          "id": "run-\(index)", "status": runStatus, "stage": "execute",
          "progress": "正在整理可验证的研究结论。",
          "error_code": runStatus == "paused" ? "BUDGET_EXHAUSTED" : "",
          "agent_id": "agent-\(index)",
          "usage": ["tokens": 120000, "steps": 12, "active_seconds": 42],
        ]
      ]
      let children: [[String: Any]] = subagentStatuses.enumerated().map { offset, status in
        [
          "agent_id": "child-\(index)-\(offset)", "title": "子 Agent \(offset + 1)",
          "status": status, "execution_status": status,
          "objective": "完成一个边界清晰的调研子任务。",
          "success_criteria": "返回带来源的结论。",
          "result": status == "succeeded" ? "子任务已完成。" : "",
          "notes": [], "activity": ["entries": []],
        ]
      }
      let taskAgent: [String: Any] = [
          "agent_id": "agent-\(index)", "title": "研究执行 Agent",
          "status": agentStatus, "execution_status": runStatus == "paused" ? "paused" : agentStatus,
          "objective": "组织调研并汇总结论。", "success_criteria": "形成统一报告。",
          "result": agentStatus == "succeeded" ? "报告已经完成。" : "",
          "notes": [],
          "activity": [
            "entries": [
              [
                "id": 1, "kind": "assistant.message", "content": "先拆分研究任务。",
                "tool_calls": [["name": "subagent_spawn", "description": "委派边界清晰的调研任务"]],
              ],
              [
                "id": 2, "kind": "tool.terminal", "tool": "browser",
                "tool_description": "查阅官方研究资料", "status": "succeeded", "content": "",
              ],
            ]
          ],
        ]
      let workflowNodes: [[String: Any]] =
        mode == "dynamic_workflow"
        ? [
          [
            "id": "source", "title": "收集来源", "depends_on": [],
            "status": "succeeded", "result": "来源已收集。",
          ],
          [
            "id": "compare", "title": "比较结论", "depends_on": ["source"],
            "status": "running", "result": "",
          ],
          [
            "id": "report", "title": "形成报告", "depends_on": ["compare"],
            "status": "pending", "result": "",
          ],
        ] : []
      let messages: [[String: Any]] =
        mode == "agent_team"
        ? [[
          "id": "message-\(index)",
          "sender_agent_id": "child-\(index)-0",
          "recipient_agent_id": "agent-\(index)",
          "sender_title": "子 Agent 1",
          "recipient_title": "研究执行 Agent",
          "content": "已核对来源并回报关键差异。",
          "created_at": 1_763_600_000,
        ]] : []
      let taskAgentPayload: Any = mode == "program" ? NSNull() : taskAgent
      let subagentsPayload: Any = mode == "program" ? [] : children
      task["execution"] = [
        "executor": mode == "program" ? "program" : "agent",
        "mode": mode,
        "plan": task["plan"]!,
        "task_agent": taskAgentPayload,
        "subagents": subagentsPayload,
        "team_messages": messages,
        "workflow": [
          "nodes": workflowNodes,
          "edges": mode == "dynamic_workflow"
            ? [
              ["from": "source", "to": "compare"],
              ["from": "compare", "to": "report"],
            ] : [],
        ],
        "events": [],
      ]
      return json(task)
    }

    let cases: [(String, String, String, String, [String])] = [
      ("ongoing", "parallel_subagents", "running", "running", ["running"]),
      ("temporary", "parallel_subagents", "paused", "paused", ["paused", "succeeded"]),
      ("ongoing", "agent_team", "running", "running", ["running", "succeeded"]),
      ("temporary", "agent_team", "paused", "paused", ["paused"]),
      ("ongoing", "dynamic_workflow", "running", "running", ["running", "pending"]),
      ("temporary", "dynamic_workflow", "queued", "running", ["waiting"]),
      ("ongoing", "program", "waiting", "running", []),
      ("temporary", "program", "succeeded", "succeeded", []),
    ]
    let app = XCUIApplication()
    app.launchArguments = ["-HymioTaskPreview"]
    for round in 0..<24 {
      let scenario = cases[round % cases.count]
      app.launchEnvironment["HYMIO_TASK_REVIEW_JSON"] = fixture(
        index: round + 1, scope: scenario.0, mode: scenario.1, runStatus: scenario.2,
        agentStatus: scenario.3, subagentStatuses: scenario.4)
      app.launch()
      XCTAssertTrue(app.navigationBars["任务详情"].waitForExistence(timeout: 10))
      XCTAssertTrue(app.staticTexts.matching(
        NSPredicate(format: "label CONTAINS %@", "验证任务 \(round + 1)")).firstMatch.exists)
      XCTAssertTrue(app.staticTexts["长期任务"].exists || app.staticTexts["临时任务"].exists)
      let modeLabel = [
        "parallel_subagents": "Agent 并行",
        "agent_team": "Agent Team",
        "dynamic_workflow": "动态工作流",
        "program": "自动执行",
      ][scenario.1]!
      XCTAssertTrue(app.staticTexts[modeLabel].exists)
      if scenario.1 == "program" {
        XCTAssertFalse(app.staticTexts["需要你处理"].exists)
        XCTAssertFalse(app.staticTexts["等待条件满足"].exists)
        if scenario.2 == "waiting" { XCTAssertTrue(app.staticTexts["发送中"].exists) }
      }
      XCTAssertFalse(app.staticTexts["执行细节"].exists)
      XCTAssertFalse(app.staticTexts["事件记录"].exists)
      XCTAssertFalse(app.staticTexts["查阅官方研究资料"].exists)
      XCTAssertFalse(app.staticTexts.matching(
        NSPredicate(format: "label CONTAINS %@", "<!DOCTYPE")).firstMatch.exists)
      if round < 8 {
        let shot = XCTAttachment(screenshot: app.screenshot())
        shot.name = "material-task-matrix-\(round + 1)"
        shot.lifetime = .keepAlways
        add(shot)
      }
      app.terminate()
      print("MATERIAL_TASK_VERIFICATION_ROUND=\(round + 1)")
    }
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

  @MainActor func testCancelTaskImmediatelyRemovesHomeDecision() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-HymioHomePreview", "-HymioHomeManyDecisions", "-HymioSlowDelete"]
    app.launch()
    XCTAssertTrue(app.buttons["home.focus"].firstMatch.waitForExistence(timeout: 10))
    app.buttons["home.focus"].firstMatch.tap()
    XCTAssertTrue(app.buttons["任务操作"].waitForExistence(timeout: 5))
    app.buttons["任务操作"].tap()
    app.buttons["取消任务"].tap()
    app.buttons["取消任务"].tap()
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
      XCTAssertTrue(
        app.navigationBars.firstMatch.waitForExistence(timeout: 10)
          || app.scrollViews.firstMatch.exists)
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
    XCTAssertTrue(app.buttons["任务"].waitForExistence(timeout: 5))
    let my = XCTAttachment(screenshot: app.screenshot())
    my.name = "my-toolbar"; my.lifetime = .keepAlways; add(my)
  }

  @MainActor func testAccountPrimaryDestinationsStayDistinct() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-HymioExperiencePreview"]
    app.launch()
    app.buttons["我的"].tap()
    for (entry, title) in [("任务", "任务"), ("account.connectors", "连接来源"), ("任务", "任务")] {
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
    XCTAssertEqual(
      app.buttons["account.confirmLogout"].frame.midX,
      app.buttons["取消"].frame.midX,
      accuracy: 1)
    let shot = XCTAttachment(screenshot: app.screenshot())
    shot.name = "account-logout-explanation"
    shot.lifetime = .keepAlways
    add(shot)
  }

  @MainActor func testMyDevicesOmitsCurrentIPhone() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-HymioAccountPreview"]
    app.launch()
    let devices = app.buttons["我的设备"]
    XCTAssertTrue(devices.waitForExistence(timeout: 10))
    for _ in 0..<3 where !devices.isHittable { app.swipeUp() }
    devices.tap()
    XCTAssertTrue(app.navigationBars["我的设备"].waitForExistence(timeout: 5))
    XCTAssertTrue(app.staticTexts["Mac mini"].waitForExistence(timeout: 5))
    XCTAssertFalse(app.staticTexts["iPhone"].exists)
    XCTAssertFalse(app.staticTexts["Web"].exists)
  }

  @MainActor func testBudgetExhaustionStaysInConversation() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-HymioMultiAgentTaskPreview"]
    app.launch()
    let note = app.staticTexts["在对话中让我调整预算后继续。"]
    for _ in 0..<5 where !note.isHittable { app.swipeUp() }
    XCTAssertTrue(note.isHittable)
    XCTAssertFalse(app.buttons["task.budget.adjust"].exists)
    XCTAssertFalse(app.navigationBars["调整本轮预算"].exists)
    let shot = XCTAttachment(screenshot: app.screenshot())
    shot.name = "task-budget-uses-conversation-not-editor"
    shot.lifetime = .keepAlways
    add(shot)
  }

  @MainActor func testTaskArchiveShowsClosedWorkAndSoftRemoves() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-HymioCalendarPreview"]
    app.launch()
    XCTAssertTrue(app.navigationBars["任务"].waitForExistence(timeout: 10))
    XCTAssertFalse(app.staticTexts["已取消的旧任务"].exists)
    XCTAssertFalse(app.staticTexts["更新周末出行清单"].exists)
    app.buttons["查看归档"].tap()
    XCTAssertTrue(app.navigationBars["归档"].waitForExistence(timeout: 5))
    XCTAssertTrue(app.staticTexts["已取消的旧任务"].waitForExistence(timeout: 5))
    XCTAssertTrue(app.staticTexts["更新周末出行清单"].exists)
    app.staticTexts["已取消的旧任务"].tap()
    XCTAssertTrue(app.navigationBars["任务详情"].waitForExistence(timeout: 5))
    app.buttons["从归档移除"].tap()
    let remove = app.buttons.matching(identifier: "从归档移除")
    XCTAssertTrue(remove.firstMatch.waitForExistence(timeout: 3))
    remove.element(boundBy: remove.count - 1).tap()
    XCTAssertFalse(app.staticTexts["已取消的旧任务"].waitForExistence(timeout: 2))
    let shot = XCTAttachment(screenshot: app.screenshot())
    shot.name = "task-archive-after-soft-remove"
    shot.lifetime = .keepAlways
    add(shot)
  }

  @MainActor func testThreeTabsAndGroupedMyNavigation() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-HymioExperiencePreview"]
    app.launch()
    XCTAssertTrue(app.buttons["此刻"].waitForExistence(timeout: 10))
    XCTAssertTrue(app.buttons["对话"].exists)
    XCTAssertTrue(app.buttons["我的"].exists)
    let dock = app.descendants(matching: .any).matching(identifier: "product.dock").firstMatch
    XCTAssertTrue(dock.waitForExistence(timeout: 5), app.debugDescription)
    XCTAssertLessThanOrEqual(dock.frame.height, 92)
    XCTAssertFalse(app.buttons["回忆"].exists)
    app.buttons["我的"].tap()
    XCTAssertTrue(app.buttons["任务"].waitForExistence(timeout: 5))
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
    app.buttons["此刻"].tap()
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
    app.buttons["chat.send"].tap()
    XCTAssertTrue(app.staticTexts["draft only"].waitForExistence(timeout: 5), app.debugDescription)
    XCTAssertTrue(app.keyboards.firstMatch.waitForNonExistence(timeout: 3), app.debugDescription)
    XCTAssertTrue(app.staticTexts["draft only"].isHittable, app.debugDescription)
    XCTAssertTrue(app.staticTexts["收到，我正在处理。"].waitForExistence(timeout: 5), app.debugDescription)
    XCTAssertTrue(app.staticTexts["收到，我正在处理。"].isHittable, app.debugDescription)
    let sent = XCTAttachment(screenshot: app.screenshot())
    sent.name = "chat-after-send-no-blank"; sent.lifetime = .keepAlways; add(sent)
  }

  @MainActor func testSentMessageStaysVisibleBeforeFirstReply() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-HymioActualChatPreview", "-HymioPreviewNoReply"]
    app.launch()
    let editor = app.descendants(matching: .any).matching(identifier: "chat.input").firstMatch
    XCTAssertTrue(editor.waitForExistence(timeout: 10), app.debugDescription)
    editor.tap()
    XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 5))
    editor.typeText("只显示已发送消息")
    app.buttons["chat.send"].tap()
    XCTAssertTrue(app.keyboards.firstMatch.waitForNonExistence(timeout: 3), app.debugDescription)
    let message = app.staticTexts["只显示已发送消息"]
    XCTAssertTrue(message.waitForExistence(timeout: 5), app.debugDescription)
    XCTAssertTrue(message.isHittable, app.debugDescription)
    XCTAssertFalse(app.buttons["最新消息"].exists)
    let shot = XCTAttachment(screenshot: app.screenshot())
    shot.name = "chat-sent-message-visible-before-reply"
    shot.lifetime = .keepAlways
    add(shot)
  }

  @MainActor func testExpandedExplorationDoesNotBlankDuringNewContent() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-HymioActualChatPreview", "-HymioExpandAnchorReview"]
    app.launch()
    let fold = app.buttons.matching(identifier: "trace.fold").firstMatch
    XCTAssertTrue(fold.waitForExistence(timeout: 10), app.debugDescription)
    fold.tap()
    XCTAssertTrue(fold.isHittable, app.debugDescription)
    XCTAssertTrue(app.staticTexts["chat.stress.complete"].waitForExistence(timeout: 35))
    XCTAssertTrue(fold.isHittable, app.debugDescription)
    let final = app.staticTexts.matching(
      NSPredicate(format: "label CONTAINS %@", "最终结果已整理好。")
    ).firstMatch
    if app.buttons["最新消息"].exists {
      app.buttons["最新消息"].tap()
      XCTAssertTrue(final.waitForExistence(timeout: 5), app.debugDescription)
      XCTAssertTrue(final.isHittable, app.debugDescription)
    }
    let shot = XCTAttachment(screenshot: app.screenshot())
    shot.name = "expanded-exploration-new-content-anchor"
    shot.lifetime = .keepAlways
    add(shot)
  }

  @MainActor func testProductDockReturnsAfterSend() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-HymioExperiencePreview"]
    app.launch()
    app.buttons["对话"].tap()
    let editor = app.descendants(matching: .any).matching(identifier: "chat.input").firstMatch
    XCTAssertTrue(editor.waitForExistence(timeout: 10))
    editor.tap()
    XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 5))
    editor.typeText("dock test")
    app.buttons["chat.send"].tap()
    XCTAssertTrue(app.keyboards.firstMatch.waitForNonExistence(timeout: 3))
    XCTAssertTrue(app.buttons["我的"].waitForExistence(timeout: 5))
    XCTAssertTrue(app.staticTexts["dock test"].exists)
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
    XCTAssertTrue(app.buttons["切换到日历"].waitForExistence(timeout: 10))
    XCTAssertFalse(
      app.staticTexts.matching(NSPredicate(format: "label ENDSWITH %@", "项任务"))
        .firstMatch.exists)
    XCTAssertTrue(app.staticTexts["需要你处理"].waitForExistence(timeout: 5))
    XCTAssertTrue(app.staticTexts["临时任务"].exists)
    XCTAssertFalse(app.staticTexts["已取消的旧任务"].exists)
    app.buttons["切换到日历"].tap()
    app.buttons["周"].tap()
    XCTAssertTrue(app.buttons["今天"].waitForExistence(timeout: 5))
    app.buttons["日"].tap()
    XCTAssertTrue(app.buttons["今天"].waitForExistence(timeout: 5))
    app.buttons["月"].tap()
    XCTAssertTrue(app.buttons["切换到任务列表"].waitForExistence(timeout: 5))
    app.buttons["切换到任务列表"].tap()
    let restoredTask = app.buttons.matching(
      NSPredicate(format: "label CONTAINS %@", "比较两家云服务方案")).firstMatch
    for _ in 0..<4 where !restoredTask.exists {
      app.swipeDown()
    }
    XCTAssertTrue(restoredTask.waitForExistence(timeout: 5))
    XCTAssertFalse(
      app.staticTexts.matching(NSPredicate(format: "label ENDSWITH %@", "项任务"))
        .firstMatch.exists)
    XCTAssertFalse(app.staticTexts["已取消的旧任务"].exists)
    let screenshot = XCTAttachment(screenshot: app.screenshot())
    screenshot.name = "tasks-status-view"
    screenshot.lifetime = .keepAlways
    add(screenshot)
  }

  @MainActor func testRecurringTasksUseHumanStatesAndRealNextDates() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-HymioMonoTaskPreview"]
    app.launch()
    XCTAssertTrue(app.navigationBars["任务"].waitForExistence(timeout: 10))
    XCTAssertFalse(app.staticTexts["待开始"].exists)
    XCTAssertFalse(app.staticTexts["待安排"].exists)
    XCTAssertTrue(app.staticTexts["每日食谱与买菜提醒"].exists)
    XCTAssertTrue(app.staticTexts["减重追踪：77kg → 65kg（半年）"].exists)
    XCTAssertEqual(app.staticTexts.matching(NSPredicate(format: "label == %@", "循环中")).count, 2)
    XCTAssertTrue(
      app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "每天 07:30"))
        .firstMatch.exists)
    XCTAssertTrue(
      app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "每周二 08:00"))
        .firstMatch.exists)
    let shot = XCTAttachment(screenshot: app.screenshot())
    shot.name = "recurring-tasks-human-state"
    shot.lifetime = .keepAlways
    add(shot)
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
    XCTAssertEqual(fold.value as? String, "已展开")
    XCTAssertTrue(
      app.staticTexts["current_time"].waitForExistence(timeout: 15), app.debugDescription)
    let expanded = XCTAttachment(screenshot: app.screenshot())
    expanded.name = "native-trace-expanded"
    expanded.lifetime = .keepAlways
    add(expanded)
  }

  @MainActor func testTraceActivityExpandsInlineWithoutModal() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-HymioTraceInlinePreview"]
    app.launch()
    XCTAssertTrue(app.navigationBars["对话"].waitForExistence(timeout: 10))
    XCTAssertTrue(app.staticTexts["安排已经核对好，下午两点前没有冲突。"].exists)
    XCTAssertFalse(app.staticTexts["我先看一下今天的日历与任务，再核对时间冲突。"].exists)
    let fold = app.descendants(matching: .any).matching(identifier: "trace.fold").firstMatch
    XCTAssertTrue(fold.waitForExistence(timeout: 5))
    let anchoredY = fold.frame.minY
    fold.tap()
    XCTAssertEqual(fold.value as? String, "已展开")
    XCTAssertEqual(fold.frame.minY, anchoredY, accuracy: 4)
    let activity = app.descendants(matching: .any).matching(identifier: "trace.activity").firstMatch
    XCTAssertTrue(activity.waitForExistence(timeout: 5))
    XCTAssertGreaterThanOrEqual(activity.frame.minY, fold.frame.maxY)
    XCTAssertTrue(
      app.staticTexts["我先看一下今天的日历与任务，再核对时间冲突。"].waitForExistence(timeout: 5))
    XCTAssertTrue(app.staticTexts["查看日历"].exists)
    XCTAssertTrue(app.staticTexts["检查今天下午是否已有安排"].exists)
    let details = app.buttons["调用详情"]
    XCTAssertTrue(details.exists)
    details.tap()
    XCTAssertTrue(
      app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "2026-11-19"))
        .firstMatch.waitForExistence(timeout: 5))
    XCTAssertFalse(app.staticTexts["继续处理下一步"].exists)
    XCTAssertFalse(app.navigationBars["探索过程"].exists)
    XCTAssertFalse(app.buttons["完整执行记录"].exists)
    let shot = XCTAttachment(screenshot: app.screenshot())
    shot.name = "trace-inline-expanded"
    shot.lifetime = .keepAlways
    add(shot)
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
    guard app.buttons["此刻"].waitForExistence(timeout: 8) else { return }
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
    let tab = app.buttons["对话"]
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
