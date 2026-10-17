# Feature 03 — Kit 注册、调用与跨端使用

状态：Draft；规范入口为 [kits/README.md](../kits/README.md)。

## Registry 与适配

Registry 记录 Kit 版本/digest、兼容协议、operation schema、权限、UI 能力、context projection、安装状态。tool discovery 只返回已启用且授权的操作；执行时再校验权限，防止工具列表缓存导致撤权失效。

HTTP API 是通用业务服务入口，可由 MCP façade 暴露给 agent；只有 MCP 的 Kit 也需满足业务协议的字段与幂等要求。Oath tool adapter 持久化 tool identity 映射、deadline、attempt 和 result。UI 用业务 API，不依赖 agent 才能查看账本或 todo。

## 第一条闭环

用户在手机说“午饭花了 35，记一下”：

1. 输入作为消息进入 Oath，按用户 context 设置保存原始陈述到 Nostalgia。
2. Agent 选择 `expense.create`，提供金额、币种、分类、发生时间和 source_message_id；缺失且不能从已知设置确定的字段先澄清，不凭空补。
3. Kit 在同一个本地事务写账本、幂等 receipt 和 projection outbox；成功响应包含 expense_id、revision、projection_status=pending/available。
4. Oath 持久化工具成功，回复账本写入已完成；手机 Kit UI 从同一账本读到数据。
5. Outbox 按 expense revision 顺序推送 Nostalgia，同 source ID 只维护一个 context。Nostalgia 暂不可用时账本仍成功，同步状态可见并可重试。

超时后 agent 不重建新的幂等键再次记账。通过原操作状态/幂等键 reconcile；原始用户陈述与 expense projection 在检索时通过 source_message_id 关联，不能把两条 context 当两笔支出。

## 综合查询

“这周外卖花了多少”：账本精确查询按用户时区算时间边界，以 currency 分组返回总额、记录数和覆盖范围；不跨币种直接相加。Nostalgia 搜索聊天、订单或备注补充解释与未确认线索。回答区分已入账数据与可能漏记的信息；top-k 搜索不保证总量完整。

结果标注 canonical 来源和 projection 新鲜度。只配置 Nostalgia、未安装账本 Kit 时仍能回答已存信息，但不能声称查询了完整账本。

## 验收

Agent 和 UI 读写同一业务记录；工具成功但 projection 延迟可见；修改/删除账单同步更新 context；同 source 消息重试不重复记账；未装原生 UI 的客户端能通过 chat 调用；订阅者不会对自己发布的 projection 循环执行。
