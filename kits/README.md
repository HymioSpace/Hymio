# Hymio Kit contract — v1

Kit 是用户拥有的真实应用。用户可以自己使用它，也可以让 Hymio Agent 通过业务 operation
操作同一份数据。当前首个客户端是 iOS；Web 不支持 Kit，也不请求 Kit API。

## 包结构

```text
kits/<kit-id>/
  manifest.json
  web/index.html
  README.md
```

页面是独立 HTML/CSS/JavaScript 应用，不是 A2UI 或受限组件协议。页面在 iOS `WKWebView`
中运行，使用宿主注入的 `HymioKit.call(operation, arguments)` 访问本 Kit 的业务 API。
页面不接触用户的 access token；所有调用由原生宿主使用当前账号代理。

纯静态页面可以没有 operation。需要持久化数据、Agent 操作或其他后端能力的页面才声明
operation。

## Manifest

```json
{
  "schema": "hymio.kit/v1",
  "id": "hymio.ledger",
  "version": "0.1.0",
  "display": {
    "name": "生活账本",
    "tagline": "随手记下花了什么，想知道时直接问 Hymio。",
    "description": "记录日常支出，查看最近记录和本月汇总。",
    "category": "生活",
    "icon": "wallet",
    "accent": "amber"
  },
  "api": {
    "transport": "bundled",
    "handler": "kit_host.builtin_ledger:LedgerKit"
  },
  "preview": true,
  "app": {
    "mode": "interactive",
    "bridge": "hymio.kit.bridge/v1",
    "entry": "web/index.html"
  },
  "operations": [
    {
      "id": "entries.create",
      "agent_visible": true,
      "name": "记一笔",
      "description": "记录一笔支出。",
      "effect": "write",
      "input_schema": {"type": "object"},
      "output_schema": {"type": "object"}
    }
  ]
}
```

`display` 面向用户。`operations` 可以为空。`preview` 表示首页是否展示紧凑摘要；
没有这个能力时只显示应用名称、用途和入口。

`app.mode` 为 `static` 时 `operations` 必须为空。这样页面仍然可以包含任意本机 HTML/CSS/JS
体验，但不会向 Agent 暴露任何业务 API；`app.mode` 为 `interactive` 时才声明页面可调用的
operation。

## 页面桥

页面调用：

```js
const result = await HymioKit.call("entries.create", {
  amount: 35,
  category: "food"
});
```

桥只允许当前 Kit 的 operation。用户身份、权限和幂等键由 Hymio 宿主添加，页面无法指定
其他用户或其他 Kit。页面 CSP 禁止外部连接、外部脚本和导航。

## Agent 可见性

Agent 使用统一的 `kit_call`：

```text
kit_call({kit_id, operation, arguments})
```

Hymio Backend 的 context provider 在每一轮把当前用户已安装 Kit 的真实 operation、
description 和 input schema 直接注入模型上下文。没有 `list` 或 discovery 调用。
该能力和 `kit_call`、`kit_build`、`kit-builder` 一样只对 iOS 渠道暴露；Web 不注入。

Kit 创建成功后，它的 operation 在下一次模型 step 自动出现。纯静态 Kit 的 operation
列表为空，不向 Agent 暴露业务操作。

执行时 Backend 和 Kit Host 仍会重新校验安装状态、operation 和数据 schema，不能依赖
prompt 中的旧清单绕过撤权。

TODO：安装的 operation 数量增多后，由 Hymio 按用户安装集在启动/请求时编译精简操作说明，
或按域拆成少量代理；不把查询 operation 清单变成模型工作流。

## 数据与幂等

写操作必须携带稳定幂等键。Kit 服务在同一事务中提交业务记录与 receipt。相同操作重试返回
原结果，不重复写入。

Kit Host 拥有独立 SQLite 数据库和安装状态。Hymio Backend 不持有 Kit 业务表，只做用户鉴权、
调用代理和错误映射。

## 托管

第一方或受信任 Kit 可在 Kit Host 的 bundled runtime 中运行。需要自定义服务代码、第三方
依赖或外部 API 的 Kit，应逐步迁移为独立容器和数据库。Hymio 只注册不可变版本和 service
endpoint，不执行用户上传的任意 Python 或 JavaScript。

Web 当前不渲染 Kit；不要为 Web 注入 Kit 清单或提供占位入口。
