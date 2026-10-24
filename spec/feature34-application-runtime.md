# Feature 34 — React / Python application runtime

状态：Implemented：React/Python MVP 已在本地与云端完成生成、发布、编辑和数据同步验证。

## 总览

应用从“一个 HTML 文件”升级为有独立源码、API、构建产物和 Agent context 的软件项目。用户仍只
看到“应用”；内部由主 Agent 描述产品变化，应用的专属 coding context 修改源码、检查并发布。

```text
用户/主 Agent
     │ product brief
     ▼
Kit coding context (Oath subagent)
     │ kit_dev read / patch / check / publish
     ▼
Kit Host workspace ── React build ── immutable published revision
     │                                  │
     └ Python API ◄── HymioKit.call ─── App WebView
```

贯穿规则：

- Hymio 拥有应用源码、构建、数据、安装、版本和编码对话。
- Oath 只提供通用执行、journal、subagent continuation 和工具运行；不包含应用业务概念。
- 主 Agent 不阅读整份源码，也不生成整页代码。它给出产品目标、数据约束和验收条件。
- 同一个应用使用同一个 coding context；每轮修改有独立预算，但历史 journal 不丢失。
- 发布产物不可变。页面、API contract 和源码 revision 必须来自同一次构建。

## 源码项目

```text
app.json              display metadata + API operations
server/main.py        bounded Python handlers
web/src/main.jsx      React entry
web/src/App.jsx       application UI
web/src/styles.css    application visual system
README.md             product and data notes
```

`app.json` 保存 display metadata；它的 operation 是前端、Python handler 和 Agent schema 的单一契约。每项声明 operation
ID、handler 名、effect、输入 schema 与是否对 Agent 可见。修改字段键必须被视为数据模型变更，
不能把旧记录解释成另一套字段。

源码以不可变 revision 摘要标识。`kit_dev` 修改已存在文件时必须携带当前 revision，新文件需要
完整内容。精确 `old/new` patch 在源文件中必须唯一匹配；并发或过期修改被拒绝。

## 构建与运行

### React

Kit Host 使用固定的本地 `esbuild`、React 和 React DOM 依赖把 `web/src/main.jsx` 打成单个
HTML bundle。运行时不下载依赖，也不访问 CDN。后端返回的 HTML 继续在 iOS `WKWebView` 的
CSP 沙箱中执行。

构建输入和输出均有大小限制；构建失败返回有界的文件、行、列错误，不能发布部分产物。

### Python API

每个应用的后端是一个纯 Python handler 模块，不监听独立端口。Kit Host 在独立子进程内加载它，
只提供受限 builtins、白名单 import 和 `ctx` 数据接口：

```text
ctx.list / get / insert / update / delete / count
```

handler 只返回 JSON 兼容结果；数据修改先记录为 mutation，handler 成功后与幂等 receipt 一起
原子提交。read operation 产生 mutation 时整次调用失败。子进程有 CPU、文件、内存和 wall-clock
上限，不能打开文件、网络或启动进程。

这是 MVP 的 bounded runtime，不是租户级任意代码沙箱。需要第三方包、外网或独立数据库的应用，
以后迁移到独立 service；React/API contract 与客户端桥不变。

## Oath coding context

每个项目绑定一个稳定的 Oath `agent_id`。它不是新的用户身份：`user_id` 仍是授权 owner，
`agent_id` 只选择该 owner 下的独立 journal 和 workspace context。

Hymio 先创建项目，调用 Oath `subagent.spawn(defer_start=true)`，完成
owner/kit/agent 绑定后才发送首个 bounded work message。这样 coding 工具第一次启动时，
`(user_id, agent_id)` 已能安全解析到唯一项目。

每个后续修改通过 Oath `subagent.continue` 复用同一 context。每个 turn 有稳定 message ID、
期限和 step budget；相同 message ID 重试不重复执行。coding context 可以记录 progress，
但不能委派、管理其他 task、读取其他应用或执行主对话的审批流程。

## Agent 工具

### 主 Agent

主 Agent 只看到 `kit_build`：

- `action=create`：显示信息、字段与产品 brief → 创建项目并启动 coding context。
- `action=edit`：已安装 source app + 明确变更要求 → 继续已有 coding context。

返回 `status=coding` 表示任务已接纳，不表示应用已发布。主 Agent 通过统一 `kit_call` 使用已
发布的 operation；应用不存在时不能凭缓存 schema 自行执行。

### Coding context

Coding context 只获得 `kit_dev`：

- `read`：按字符偏移读取一个源文件；
- `patch`：带 revision 的精确补丁或受限新文件写入；
- `check`：Python 静态检查与 React 构建，成功才进入下一步；
- `publish`：再次验证当前 revision，构建并原子发布。

文件树、display、API contract 和 source revision 由 context provider 直接注入，不依赖额外的
discovery 对话。`kit_dev` 标记为 subagent-only；主 Agent 的工具定义中不出现。

## 编辑对话与版本

应用详情里的“编辑应用”打开独立 sheet，不增加一级 tab。该页面展示：

- 用户与主 Agent 发起的修改要求；
- coding context 当前状态和最近完成摘要；
- 每次成功发布的版本号、时间和变更摘要；
- 输入框与发送后的持续状态。

编辑对话使用项目专属 context；UI 发起的 turn 不通知主对话。主 Agent 发起的 turn 可以通知
主对话完成。只有 publish 成功才写入 `app_revisions`、替换 active bundle 并刷新安装版本。

## 数据与隔离

- 业务记录按 `(user_id, kit_id)` 隔离，源码按 `(owner_user_id, kit_id)` 隔离。
- Coding agent 和主 Agent 都不能指定其他 owner；Backend 只从认证身份与已绑定 agent 取 owner。
- operation 在执行时重新检查安装、contract、effect、输入 schema 和 idempotency。
- 删除应用同时移除 source project、revision、coding messages、业务记录、receipts 和安装，
  并取消对应 Oath context；卸载只移除安装。

## 失败与恢复

- Spawn 后绑定失败：context 处于 waiting，不执行工具；同一 request 重试可继续绑定。
- Publish 前崩溃：active bundle 不变，source 仍是 draft。
- Build 失败：返回有界诊断，不产生 revision，不阻挡上一 published revision 运行。
- 工具结果不确定：沿用原 invocation/message ID 查询，不生成新的修改。
- Coding context 完成或失败后可继续新 turn；cancel 后只能删除/重建应用。
- 主对话不依赖 coding subagent 的完整 journal；完成摘要与 revision 通过 Hymio 的稳定接口读取。

## MVP 验收

1. 主 Agent 通过 `kit_build` 创建项目，Oath waiting context 在绑定后收到首个 turn。
2. Coding context 读取真实 React/Python 源码，打补丁并成功构建。
3. Publish 后应用出现在“应用”页，同一 API 可供页面与 `kit_call` 使用。
4. Edits 复用同一 coding context，已有记录不因发布轮换而丢失。
5. 编辑 sheet 展示请求、最近结果与版本摘要。
6. Web 不注入 `kit_build`、`kit_dev` 或应用 operation。
7. 云端完成一次真实模型驱动的创建、编辑、发布与数据同步。
