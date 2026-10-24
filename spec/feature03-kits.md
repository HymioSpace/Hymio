# Feature 03 — 应用、安装与 Agent 调用

状态：Implementing。React/Python 项目运行与 coding context 见
[feature34](feature34-application-runtime.md)。

## 总览

用户看到的是“应用”，不是内部 Kit。应用拥有自己的页面、业务 API、安装状态、数据和可选
Agent operation。用户可以自己使用，也可以让 Hymio 通过同一条 API 操作同一份数据。

```text
用户 ──> iOS 应用页 ──> Hymio Backend ──> Kit Host
  │                                             │
  └──> 主 Agent ──> kit_call ───────────────────┘
```

新生成应用使用 React 前端和 bounded Python API。受信任第一方应用可继续使用 bundled Python
handler；两者都通过相同 operation 与 idempotency 契约对外提供能力。

## 产品入口

- iOS 一级导航保持“此刻、对话、任务、记忆、应用”五项；账号由左上角伴侣头像打开，使用
  44 pt 点击区、系统工具栏和 sheet，不占第六个 tab。
- 应用首页展示已发布应用；是否展示预览由 application capability 决定，不强制每个应用都有
  指标或图表。
- 打开应用后，iOS 原生容器加载应用自己的 Web bundle。原生壳只负责加载、错误兜底、删除、
  账号和编辑入口。
- 应用详情中的“编辑应用”打开 coding conversation sheet，不增加一级导航。

当前 Web 客户端没有应用入口，不请求应用 API，也不接收应用 context 注入。

## 安装与删除

- 安装只绑定当前用户和 published revision，不复制源码或业务记录。
- 卸载移除安装，记录保留；重新安装后仍读取原数据。
- 永久删除移除项目、源码 revisions、coding messages、业务记录、receipts 和安装，并取消
  coding context。调用需要用户明确确认。
- 删除、卸载和发布均按稳定 request/key 幂等。

## Agent 可见性

主 Agent 只有一个 `kit_call({kit_id, operation, arguments})`。Hymio context provider 将当前
用户已安装应用的真实 operation、description 和 input schema 直接注入模型请求；不提供
`list` 或 discovery action。

新应用发布后的下一个模型 step 自动看到其 operation。应用不可用、未安装或 schema 已变化时，
Kit Host 在执行时拒绝；prompt 中的旧清单不构成授权。

主 Agent 通过 `kit_build` 创建或修改项目。它提供产品 brief 和验收条件，源码由专属 coding
context 处理，详见 feature34。

operation 数量较多后，TODO 是由 Hymio 编译更紧凑的按域说明或少量代理，不把列清单变成模型
工作流。

## 页面 API

iOS 注入最小 bridge：

```js
await HymioKit.call("entries.create", { amount: 35 });
```

页面不能指定 user、其他应用或权限。原生宿主冻结当前应用身份，Backend 完成鉴权并添加
idempotency key。CSP 禁止外部脚本、网络连接、frame 和导航。

## 用户交互事件

页面写操作成功后可以产生 `app.kit.interaction` user-queue event，包含应用、operation 和受限
结果摘要。该事件使用 `defer_wake`，不立即启动 Agent；它随下一次自然模型 step 进入上下文。
系统提示要求主 Agent 把它当作背景事实，用户没有主动提起时不得主动播报。只读操作不产生该
事件。

业务写入成功但 event 入队失败时不回滚业务结果；日志记录投递失败，不用最终一致性伪装成
写入失败。

## 失败与恢复

- 同一 idempotency key 重复写入返回首次结果，不重复写数据。
- Kit Host 不可用时页面显示重试，Agent 说明应用能力暂不可用；不调用缓存 schema 猜测结果。
- 页面读取失败不等于卸载。上一 published revision 继续服务，直到新 revision 原子发布。
- 删除不可恢复；卸载可恢复。客户端文案必须区分两者。

## 验收

React/Python 应用可以从主对话创建，由独立 coding context 构建并发布；页面和 `kit_call`
读写同一数据；编辑复用同一 context 且保留旧记录；编辑台显示版本记录；Web 不出现应用能力。
