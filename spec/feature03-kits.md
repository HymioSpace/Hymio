# Feature 03 — Kit 应用、生成与 Agent 调用

状态：Implemented：iOS MVP 闭环已验证，发布待部署；协议入口为
[kits/README.md](../kits/README.md)。

## 总览

用户看到的是“应用”。应用由用户与 Hymio 对话生成，或由受信任开发流程发布；它可以完全静态，
也可以提供真实 HTML/CSS/JavaScript 页面和业务 operation。

```text
用户与 Hymio 对话 ──> kit_build ──> Kit Host
                                      │ 独立安装状态 / 数据 / 页面
iOS 应用页 ──> Hymio Backend ─────────┘
                     │
Agent ──> kit_call ──┘
```

当前 Web 客户端不支持应用。Web 不请求 Kit API，也不接收 Kit prompt 注入。

## 产品入口

- iOS 一级导航保持“此刻、对话、任务、记忆、应用”五项；账号由左上角三横线菜单进入。
- 应用首页展示已加入和可加入的应用。预览是可选的摘要，不要求所有应用都有指标。
- 打开应用后，iOS 原生容器加载 Kit 自带的页面代码。应用不需要把页面改写成 A2UI。
- 应用为空、加载失败、静态无数据等状态由应用页面自己呈现；宿主只负责加载、错误兜底和账号入口。

## 应用生成

`kit_build` 让 Agent 从用户需求生成一个自包含 HTML 应用。Agent 同时给出名称、用途和
可选的数据字段；生成结果自动属于当前用户并安装。

- 有字段和业务 operation：页面通过 `HymioKit.call` 读写 Kit 数据。
- 无 operation：纯静态页面，Agent 不获得任何业务调用。
- MVP 禁止外部网络资源和任意后端代码；复杂应用以后使用独立容器和正式 service endpoint。

## 页面桥

iOS `WKWebView` 注入最小的 `HymioKit.call(operation, arguments)` bridge。JS 不持有 access
token，也不能指定 user_id、其他 Kit 或权限。原生宿主冻结当前 Kit 身份并调用 Hymio Backend。
页面同时受 CSP 限制，不能加载外部脚本、连接网络或导航离开应用。

## 动态 Agent 可见性

Agent 只有一个 `kit_call` 代理，不进行 operation discovery。

Hymio 的 context provider 根据当前用户已安装的 Kit，将真实 operation、说明和 JSON Schema
直接注入 prompt。新生成的 Kit 在下一模型 step 自动出现；静态 Kit 只出现空 operation 列表。
Oath 将当前客户端渠道传给 context provider；`kit_call`、`kit_build`、`kit-builder` skill
和 Kit 上下文都只对 iOS 暴露。Web 与 Mac 不收到 Kit 工具、技能索引或提示内容。

Kit Host 和 Backend 在每一次执行时重新检查安装状态、operation 和参数，prompt 清单不构成授权。

TODO：operation 数量较多时，由 Hymio 按用户安装集编译 prompt 或拆分域代理；不默认引入
`list` 请求。

## 服务边界

- Hymio 拥有 Kit registry、生成、安装、页面、业务数据和 Agent 扩展。
- Kit Host 是 Hymio 组合中的独立服务，拥有 `kits.sqlite3`。
- Hymio Backend 只做账号鉴权、Kit 代理和 context 组织。
- Oath 只使用已有 context-provider 基座能力承载最终 prompt；Oath 不包含 Kit 业务、页面、
  安装或生成逻辑。

## 失败与恢复

- 同一幂等键重复写入返回第一次结果。
- 应用卸载后页面 API 和 Agent 调用都拒绝新操作，业务数据保留。
- 页面读取失败不等于应用卸载；宿主显示重试。
- Kit Host 不可用时 Agent 说明应用能力暂不可用，不把提示词中的旧清单当成授权。

## 第一版验收

对话生成一个带真实页面的 Kit；自动安装；下一 step 的模型上下文直接出现其 operation；
用户通过页面写入；Agent 通过统一 `kit_call` 读取和写入同一数据；重复写入不重复；另一账号
不可见；纯静态 Kit 不产生 Agent operation；Web 没有 Kit 入口或请求。
