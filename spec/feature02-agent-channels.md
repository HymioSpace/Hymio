# Feature 02 — 统一身份、Agent 与渠道

状态：Draft；依赖 Hymio 认证方案与 Oath 用户凭据接入。

## 总览

各端和外部渠道使用同一个 Hymio 用户与持续对话。Hymio 管产品账号及渠道绑定，Oath 按 `user_id` 隔离执行；不创建 session。不同设备保留独立、稳定的 `client_id` 和交付 cursor。

跨渠道绑定必须验证账号控制权，不能按显示名合并身份。Slack 群聊不是私人对话的无条件镜像，输出前需校验目标渠道权限。

## Oath 接入

当前 Oath 通过配置中的 `services.users` 将用户凭据映射到 `user_id`；动态产品账号的凭据签发、撤销与验证尚需设计。Hymio 登录成功不能被视为已经自动完成 Oath 认证接入。

Oath WS v2 的 `agent.attach` 建立已认证设备连接，`user.message` 提交输入，`permission.decide` 处理审批；服务级 token 不进入客户端。Biz HTTP 提供 trace 与 CLI 能力。客户端直连用户端点还是通过 Hymio 代理，在认证实现时确定，不另造未经实现的 Oath `/inputs` API。

关闭连接不发送任务取消。重连收到 `offline.start`、未确认事件、`offline.end`，按 `user_id + event_seq` 去重；实际处理完成后才提交 ACK。执行期间的新输入由 Oath 独立接纳和调度。

## 渠道适配

`backend/channels` 验证 callback 身份，将来源消息映射到稳定输入 ID，再通过正式 Oath 接口提交。渠道重投不能创建新意图；接纳、重试和来源到运行输入的映射需要持久化。

出站使用稳定 delivery ID 和可重试状态。渠道不支持幂等发送时，明确可能重复的交付边界，不重复要求模型生成答案。外部渠道无法原样呈现某类 UI 时，提供支持的文本/链接表现。

## Context 与能力

普通对话、纯导入和显式业务动作由 UI/API 明确表达。保存 Context 不代表执行业务工具。连接器 secret 不写入 user_context；用户提交的 KV 不能作为可信授权依据。

Nostalgia adapter 检索已授权片段并保留来源和版本。Kit 操作与 UI 调用遵循同一业务授权，工具发现过滤不能替代执行时鉴权。

## 失败与恢复

用户凭据失效时停止接收敏感事件并重新认证，不靠客户端自行声明 user_id。网络断开不撤销已接纳工作；设备 cursor 丢失可能触发重放，消费方必须按事件身份去重。

渠道接纳失败与 Oath 接纳失败分别处理；不能在未取得 durable receipt 时向来源宣称已可靠提交。跨用户绑定冲突应拒绝，禁止静默覆盖。
