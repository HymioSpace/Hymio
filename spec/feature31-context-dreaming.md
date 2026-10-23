# Context 与 dreaming 接入

状态：Implemented（MVP：手动触发、恢复、查询与放弃）。

Nostalgia 保存原始记录、整理草稿和生效制品；Hymio 保存用户到服务的绑定、派发回执，提供工具和 skill；Oath 使用现有 Gateway、AgentBrain 和工具系统执行。不增加 Oath 协议或第二个 Agent。

## 路径

采集端通过 Hymio 追加 context 或 command。它只表达输入或意图，原始写入成功不表示删除、修改已经执行。主 Agent 使用 Hymio extension 的 `nostalgia` 工具读取 injection、搜索和按 ID/根 ID 读取，必要时追加用户的明确请求。

`POST /context/dreams` 创建固定 `(C,H]` 草稿，通过 Oath WS 的 `agent.attach`、`user.message` 提交明确标记的后台任务。任务正文包含短摘要和有界 buffer，`user_context` 只携带任务标识。Oath 的透传 `user_context` 不会自动进入模型提示，不能用它替代正文注入。

Agent 读取 `dreaming` skill，完整分页读取输入，按根 ID 找到相关制品和历史，增删改草稿制品，记录每条输入的处理结论。最后重建 `_index`，读取整个草稿 ETag，提交发布。来源引用、未处理输入、索引确认等校验由 Nostalgia 完成；自然语言说“完成”不会发布。

提交前主 Agent 仍看到旧制品与近期输入；提交后一次切换摘要、制品、状态与游标。执行期间新增记录保留到下次整理。固定截止范围、来源根 ID、ETag、幂等键和提交语义见 Nostalgia 仓库 `spec/api.md`。

## Hymio HTTP 接口

公开接口均使用应用 Bearer token，不接受正文指定用户。POST 请求使用 JSON 对象；写入及任务操作要求 `Idempotency-Key`，1..120 字符。

- `GET /context/injection`：生效摘要、近期 buffer 与遗漏计数。
- `POST /context/records`：透传 Nostalgia RecordCreate；返回原始持久回执。
- `POST /context/search`：透传 Nostalgia Search；无需幂等键。
- `POST /context/dreams`：正文 `{}`，创建并派发；`202` 只代表 Oath 已可靠接纳。
- `GET /context/dreams/{id}`：查询 Nostalgia 的实际草稿/提交/放弃状态。
- `POST /context/dreams/{id}/resume`：正文 `{}`，恢复已有草稿；新的执行使用新的请求键。
- `POST /context/dreams/{id}/abort`：正文 `{}`，放弃草稿。已接纳 Oath 任务可能继续，但其迟到草稿写入会被拒绝。

内部 `POST /internal/context/call` 使用服务凭据，正文为 `{user_id,action,item_id?,dream_id?,data?,query?,etag?,create?,operation_id?}`。只有 Hymio 受信任工具能访问；工具用 Oath invocation 的用户覆盖模型输入，端点与凭据不由模型选择。返回 `{status_code,data,etag}`；上游错误保留 HTTP 状态及结构化信息。请求上限 256 KiB，响应上限 1 MiB，超限需缩小分页；大资源直接使用 Nostalgia 资源 API，当前工具不封装二进制上传。

工具动作只有 injection、search、records.list/read/append/mark、artifacts.read/put/delete、dreams.read/commit/abort。`data` 与 `query` 对应 Nostalgia v1 的正文与参数，不重新定义存储协议。写入必须带稳定 `operation_id`；修改条目和提交携带读取所得 `etag`，新制品用 `create=true`。创建任务只从 Hymio 生命周期入口发起。

## 重试和边界

相同开始请求键复用同一草稿，相同用户、草稿、派发键生成稳定 Oath command ID。Hymio 数据库中的 `context_dispatches` 仅保存首次派发的完整帧，确保进程重启、buffer 更新和摘要变化后仍重发同一内容；其中不存用户凭据。它不是任务队列表，实际执行状态由 Oath 管，发布状态由 Nostalgia 管。回执随应用数据库保留，包含私人摘要，按应用数据库一起备份。

Oath 接纳不确定时返回 `503 dispatch_unconfirmed` 和 `dream_id`，保留草稿。用原路径、原请求键重试；需要新的执行才调用 resume 并使用新键。ETag 冲突必须重新读取并协调，不能直接覆盖。重复开始已提交任务只返回实际终态，不重新执行。并发 resume 可能产生多个串行 Oath 输入，仍由同一草稿、前置条件及终态校验保护。

MVP 与用户聊天共享同一个 Oath 持续对话，整理任务和简短结果会出现在会话历史。没有定时调度、独立后台对话或自动恢复循环。普通聊天目前由 Agent 调用工具取摘要，客户端不自动把摘要塞进每条消息。模型未调用工具、预算不足或判断失败时草稿会保留，需查询后手动 resume 或 abort。

## 配置与验收

配置和调用示例见 Backend README 的 Nostalgia 部分。Nostalgia wire 协议由其自身 OpenAPI 和 `spec/api.md` 维护，Hymio 本适配针对 v1。

跨仓库测试启动真实 HTTP 服务、Oath Gateway、SQLite 持久存储、AgentBrain 和线程工具系统；仅模型决策使用可控实现，内部 RPC 用进程内 StoragePort。覆盖身份隔离、幂等冲突、派发失败保留、skill 加载、完整工具结果回到模型、草稿维护、摘要发布及 H 后 buffer 保留。这不代表外部真实模型的整理质量已经验收。
