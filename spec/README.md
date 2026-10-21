# Hymio 设计

[整体架构](overview.md) 是入口，每个 feature 使用递增的 `featureNN-short-name.md`。

| 编号 | 方案 | 状态 |
| --- | --- | --- |
| 01 | [导入与同步](feature01-context-ingress.md) | Draft |
| 02 | [身份、Agent 与渠道](feature02-agent-channels.md) | Draft |
| 03 | [Kit 注册、调用与跨端使用](feature03-kits.md) | Draft |
| 04 | [授权与自带 Context 存储](feature04-identity-storage.md) | Draft |
| 05 | [产品部署与外部依赖](feature05-repository-deployment.md) | Draft |
| 06 | [应用层 Monorepo](feature06-application-monorepo.md) | Implemented：目录与边界 |
| 07 | [Web / Desktop Client MVP](feature07-client-mvp.md) | Implemented |
| 08 | [登录与 Oath 身份接入](feature08-login-auth.md) | Implemented |
| 09 | [本机统一启动](feature09-local-start.md) | Implemented |
| 10 | [多设备与执行环境](feature10-multi-device.md) | Implemented：多 Provider 设备执行 |
| 11 | [单机云部署](feature11-cloud-deployment.md) | Implemented：部署入口；公网验收待部署 |
| 12 | [本机命令行](feature12-command-line.md) | Implemented |
| 13 | [会话快照与历史分页](feature13-conversation-history.md) | Implemented |
| 14 | [iOS MVP](feature14-ios-mvp.md) | Implemented：SwiftUI、同账号持续对话与前台恢复 |
| 15 | [统一设计与组件](feature15-unified-design.md) | Implemented |
| 16 | [单入口与局域网真机体验](feature16-lan-entry.md) | Implemented：单入口、LAN 启动与配置 |
| 17 | [App 响应与状态反馈](feature17-app-responsiveness.md) | Implemented |
| 18 | [Trace 与设备可用性](feature18-trace-devices.md) | Implemented |
| 19 | [单域名云端部署](feature19-cloud-single-entry.md) | Implemented |
| 20 | [Progressive agent UI](feature20-progressive-ui.md) | Implemented |
| 21 | [应用 Prompt 与云电脑恢复](feature21-prompt-computer-recovery.md) | Implemented |
| 22 | [Models and media](feature22-models-and-media.md) | Implemented |
| 23 | [Tasks and delegation](feature23-tasks-and-delegation.md) | Implemented |
| 24 | [Portable local deployment](feature24-local-bootstrap.md) | Implemented |
| 25 | [Personal home and platform navigation](feature25-personal-home.md) | Implemented |
| 26 | [Cloud and custom device providers](feature26-cloud-device-providers.md) | Implementing |
| 27 | [Resource access and administration](feature27-resource-access-administration.md) | Implemented |


## 设计与实现

先写方案，再实现。文档从总览展开机制、边界和失败恢复；不把开发流水、命令输出或测试数量写成设计。状态使用 Draft → Accepted → Implementing → Implemented，只对实际交付的范围标记完成。

修改已有功能更新原 feature，跨模块调整同步 overview。共享规则在本目录维护；本地 `AGENTS.md` 被忽略，不 force-add。

## 模块约束

- 应用代码留在 monorepo，Web/Tauri 共用前端；平台能力经 adapter，iOS 不强制复用 Web 视图。
- 共享包不依赖 app；UI 不直接访问数据库或持有服务级凭据。
- 一个产品用户对应 Oath `user_id` 与一段持续对话；设备有各自稳定 client ID，不创建 session。
- Hymio 管产品业务、采集与连接器；Oath 管执行，Nostalgia 管 Context 实体和检索。
- 产品后端先模块化，按实际需要拆部署；Oath CLI handler 与 Hymio backend 不混为同一个服务。
- API 与业务约束独立于 UI，Kit 和 Agent 调用共享同一业务操作。
- 用户断线不取消已接纳任务。事件成功处理后确认，允许重放和去重。
- 未选定的框架、存储、认证提供商和 license 不宣称已有决定；不生成无可运行内容的工程。
- Secret、私人 Context、生产 trace 和私有扩展不能进入提交；公开默认构建不依赖私有凭据。

## 下一步

当前云电脑已具备 Daytona、兼容 E2B 和运维托管 Linux API 三种 Provider，并有独立资源管理台。
下一步补齐火山云手机生命周期、Android 交互能力、自助设备接入，以及 Context collector/Nostalgia 的正式集成。

- [Models and media](feature22-models-and-media.md): model preferences, private attachments, multimodal understanding and image creation.

- [Tasks and delegation](feature23-tasks-and-delegation.md): conversational intentions, milestones, optional schedules, bounded experts and Web/iOS task panels.
