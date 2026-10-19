# Feature 07 — Web / Desktop Client MVP

状态：Implemented（Web / macOS 客户端；产品后端与 Context 集成不在本次范围）。

## 总览

React + TypeScript + Vite 实现共享 Web 前端，Tauri 2 提供桌面壳。客户端直连已部署 Oath 的用户 WS，Biz HTTP 用于 trace 和健康检查。只保留单一持续对话，不创建会话；backend、Nostalgia、Kit 业务和连接器不在本次实现。

核心闭环：Hymio 登录 → 获取身份和端点 → attach → 重放事件 → 多轮输入/输出 → 断线重连 → 按需查看 debug。客户端关闭不取消服务端工作。

## 产品与视觉

白色主界面、深墨色线条、少量 Hymio 蓝；用带蓝色围带的线条角色表达 idle / working / replying / offline / approval 状态。动态遵循 reduced-motion 设置。

一条持续时间线，以可读消息、工具摘要、审批卡和离线补发标记承载内容。输入区支持多行、中文 IME、Enter 发送 / Shift+Enter 换行；Agent 工作时仍允许追加输入。暂不展示不可用的附件、语音、Kit 或连接器按钮。

主界面只有对话、账号设置与按需打开的工作观察侧栏。侧栏提供实际事件、运行状态、trace span/原始内容与 WS/Biz 健康；不假装能直接观测全部内部服务。

## 模块

- `packages/protocol`：Oath v2 的客户端消费类型、事件校验与 trace 类型。
- `packages/client`：连接、重试、事件持久化、可靠命令与消息投影。
- `packages/ui`：角色与共用视觉基础；不访问网络或凭据。
- `apps/client`：产品交互、平台 HTTP 适配、Tauri 壳与开发服务。

使用 pnpm workspace 管理实际包。运行依赖固定版本、提交 lockfile。A2UI 暂不实现协议，但消息呈现采用独立组件，为后续结构化响应保留接入位置。

## 通信与持久化

WS 第一帧 `agent.attach` 仅发送用户凭据和稳定 `client_id`。按 endpoint + 已认证 user_id 隔离 IndexedDB 记录。每事件事务完成后才发 ACK；按 event_seq 去重，失败停止确认并展示错误。

本机事件缓存丢失且服务端 ACK cursor 已前进时，更新设备 client_id 请求完整重放，避免把确认过的消息永久隐藏。

原始 delta 按 step/attempt 聚合，最终 assistant.message 替代同 step 的临时内容；工具调用与审批独立呈现。未知事件持久保存并进入 debug，不强制解释成对话。

待发送命令持久化 UUID 与完整 payload；断线重试使用相同 id 和 payload，收到 ACK 才删除。用户消息以服务端正式事件进入时间线，不按内容猜测去重。连接和 token 变更停止旧链路；已发送工作不随连接关闭取消。

Web tab 有稳定 tab client ID，Desktop 使用自己的 device ID，避免多个活跃连接竞争同一服务端 cursor。浏览器刷新保留本机消息；新设备通过 Oath 的 Outbox 补齐历史。

## HTTP 与凭据

HTTP 查询走 Hymio Backend 的已认证 Biz 代理，Web 使用 Backend 的 CORS allowlist；Desktop 用受限 Tauri HTTP command 调用健康与 trace 路径。

用户 token 仅在当前窗口 sessionStorage 保存，不进入日志、事件导出或构建产物。客户端不读取 Oath 本机配置、不接受手工凭据；账号登录与服务部署配置见 feature08。

## 失败与恢复

未认证、存储失败、模型失败与传输断开分别显示。连接重试有退避，主动断开不自动重连；心跳断连可恢复。未知接纳状态的命令重用原身份，不自动生成新的业务操作。

服务器 ACK 仅表示输入接纳，最终结果以事件为准。审批结果确认与工具执行分开；工具终态等待真实事件。`run.cancel` 与 `step.retry` 为明确用户操作。

默认 Oath allow-all 策略不会产生审批卡；UI 只展示实际请求。Trace 可能包含私人内容，导出需明确操作，不能把 user token 或 attach frame 带入导出。

## 设计参考

- [Muse design](https://introducing.muse.ai/)：连续对话承接后台工作，操作授权使用确定的控件。
- [Grok Bot design](https://x.ai/news/designing-grok-bot)：角色状态、渐进式工作可见性，避免让用户一直监督。
- [Macaron](https://macaron.im/)：从日常场景引导用户表达需求。

上述参考用于交互原则，角色、布局和组件独立设计。

客户端启动、构建命令与 TypeScript 配置归属 `apps/client`。TypeScript、类型定义和格式工具依赖由实际使用的应用或共享包声明，各自维护配置；根目录只保留 workspace、锁文件与递归检查入口，不以客户端启动命令作为整个 Hymio 的默认入口。

工具调用显示可理解的操作名称、查询关键词与实际状态，展开查看参数和返回结果。事件、Trace 和状态检查使用 JSON 树，默认展开前两层；嵌入对象或数组的 JSON 字符串只在展示时解码，原始 JSON 视图保留服务端值。小尺寸角色不持续旋转身体，保留眨眼和用户触发的挥手。

主界面的失败卡片只对应当前未恢复的步骤。重试提交后收起旧卡片；服务端若产生新的失败事件，再显示新卡片。用户可主动收起，收起记录按用户和事件标识保存，刷新不会恢复同一条提示。后续新消息不携带上一轮的错误。Dock 图标在透明画布内留边距，视觉尺寸与常见 macOS 应用接近。

产品登录和远程 Oath 鉴权已由 [feature08](feature08-login-auth.md) 实现；原直连配置与本机凭据读取已移除，只保留产品登录入口。

## 工具活动展示

连续、无正文的 assistant 工具调用合并为一个默认折叠的活动区，不重复显示头像和时间。
摘要展示调用次数及执行中 / 完成 / 异常；展开逐条查看参数和结构化结果。
有正文的回复仍独立展示，用户消息隔开活动分组，不跨消息合并。
授权卡保留独立操作；无匹配调用的工具事件保留单独的折叠入口，避免丢失回放信息。
分组只影响 UI，不改事件顺序、投递确认或工具执行语义。

截图 Markdown 的 /devices/media/{id} 通过当前 Backend 携带登录凭据读取，再用临时 Blob
展示；不把 token 拼进 URL，不向其他域名或重定向传递凭据。截图支持放大和加载失败重试。
沙箱文件路径不是可下载附件，Agent 应使用 computer screenshot 返回的媒体引用。

消息区仅在贴近底部时跟随内容高度变化，读取历史时不被服务端事件强制拉到底。
向上滚动立即停止跟随，点击最新消息恢复。固定 Markdown 组件身份，避免周期更新
重新挂载截图；滚动条预留宽度，避免出现滚动条时文本重新换行。
