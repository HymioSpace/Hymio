# Hymio application contract

Hymio 的内部名称仍是 Kit；用户界面只使用“应用”。

## 生成应用

新应用是版本化的 React + Python 项目：

```text
app.json
server/main.py
web/src/main.jsx
web/src/App.jsx
web/src/styles.css
README.md
```

`app.json` 声明 operation ID、Python handler、effect、输入 schema 和 Agent 可见性。React
页面通过宿主注入的 `HymioKit.call` 调用 operation；Python handler 只接收 `ctx` 和 JSON 参数。

项目由应用专属 Oath coding context 修改。主 Agent 不直接获得源码；它通过 `kit_build`
提交产品 brief。Coding context 使用 `kit_dev` 读取、打补丁、构建和发布。

完整机制见 [application runtime](../spec/feature34-application-runtime.md)。

## 发布与数据

- published revision 原子替换 active React bundle、API contract 和展示信息。
- 相同 idempotency key 的写操作返回首次结果。
- 卸载保留业务记录；永久删除移除源码、版本、业务数据和安装。
- 页面、Agent 和 coding context 都不能指定其他用户或其他应用。

## 受信任内置应用

`kits/<kit-id>/manifest.json` 仍支持第一方 bundled handlers 和静态 HTML 页面。它们使用相同
安装、operation、数据与 `HymioKit.call` 契约，但不是用户生成源码。新的用户应用不得直接执行
上传的任意 Python 进程；生成后端只能在 Kit Host 的 bounded runner 内运行。
