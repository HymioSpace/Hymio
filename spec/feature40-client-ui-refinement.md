# Client UI refinement

## Scope

Web/Desktop 与 iOS 改善多图片消息、执行预算暂停的恢复入口，撤下星图展示。整体设计规划见 [UI plan](../docs/design/client-ui-2026-10/implementation.md)。

## Mechanism

- Web 已发送附件采用可换行 flex，80px 缩略图、8px 间距、左对齐。iOS 用 adaptive LazyVGrid，80pt 缩略图、最大256pt，窄容器自动减少列数。顺序和授权读取/放大行为不变。
- 现有 `agent.paused(reason=tool_only_budget)` 表达自动续行预算暂停。`buildTurns` 接受可选 paused 参数；最新一轮非流式过程允许折叠，不要求存在最终回复。不把暂停伪装为成功，不合成最终答案。
- Web 在会话渲染时传入 pauseNotice；iOS Conversation 的 turns 派生值传入同一状态。iOS settled 转换时重置手动展开状态。
- 两端暂停提示旁显示「继续处理」。使用已有 user.message 通道发送同名消息，沿用断线、错误、回显和幂等语义；发送中/离线禁用。保留已有输入草稿。
- 删除 Web MemoryGraph、记忆详情关系图模式和 iOS ContextGraphScreen、两端星图入口；原始依据列表、读取分页和详情返回仍保留。后端存储/检索/关系 API 不在此次删除范围，避免影响 Agent 或其他消费者。

## Compatibility

没有协议或持久数据格式变更。buildTurns 的新参数默认 false，旧调用兼容。布局更改可直接读取已有多图片消息。

## Validation

共享客户端回归覆盖：没有最终回复的工具调用轮次，运行时保持展开、暂停时可折叠、恢复时取消暂停覆盖，且不生成最终回复。iOS 使用真实 agent.paused/resumed 事件进行同场景回归。

实际执行结果和剩余人工走查项记录于 [UI plan](../docs/design/client-ui-2026-10/implementation.md)。

## Reviewed layout implementation

对话展示层已落实到Web及SwiftUI：附件单独成组，文字单独气泡；助手正文取消外围整块卡片。iOS输入框分为文字与操作两层，保持已有draft、Photos/Camera/Files、发送/outbox和断线恢复逻辑。预算继续按钮沿用现有user.message，不新增恢复接口。

此刻页按需要确认、正在推进、最新进展、未来安排排序，基于已有tasks与baseline，不新增聚合服务。去重复问候与大海獭、装饰色块，保留账号处现有海獭。任务摘要保持真实status/result/progress/next_step。

记忆列表保留足迹/理解、来源、分页、读取原文与修改，去掉每行重复书本图标和整卡边框，加入已有preview摘要。选中样式不改变数据或权限。

客户端十条精修的实现与原生边界见feature41。所有视觉调整仍依赖同一协议和持久化语义。
