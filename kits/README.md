# Kit contract — v0.1 draft

Kit 同时向 agent 提供可调用的操作，向用户提供应用体验。API、数据、UI 分离；UI 是可选项，API 与业务语义必须明确。

## Manifest

```json
{
  "id": "hymio.ledger",
  "version": "0.1.0",
  "contract_version": "1",
  "description": "Record and query personal expenses.",
  "api": {"transport": "http", "service": "ledger"},
  "operations": [
    {"id": "expense.create", "effect": "write", "timeout_ms": 10000, "permission": "ledger:write"},
    {"id": "expense.query", "effect": "read", "timeout_ms": 5000, "permission": "ledger:read"}
  ],
  "context": {"publishes": ["expense"], "subscribes": []},
  "ui": {"platforms": ["ios"]}
}
```

这是 manifest 形状示例，不是可安装包。每个 operation 的完整 descriptor 还必须提供 description、input/output JSON Schema、幂等/对账能力、最大 timeout、权限和版本。安装时引用不可变 artifact digest，实际 endpoint 与 credential 从部署配置解析。

## 统一操作

Agent tool adapter 和 UI 都调用同一个 operation 层；不得各写一套业务逻辑或由 UI 直连数据库。MCP 可以暴露操作，但不能代替业务 API 的 revision、权限、幂等与数据迁移规则。

规范化 tool_id 为 `kit.{kit_id}.{operation_id}`（例如 `kit.hymio.ledger.expense.create`）；UI 不使用模型 provider 的临时 tool-call ID。服务处理 principal、permission scope、idempotency_key、request_id、expected_revision?、deadline；Oath adapter 将结果转成工具事件。

## Context projection

Kit 拥有业务真相，使用事务 outbox 向 Nostalgia 发布 context projection，带 source.namespace、业务 external_id/revision、occurred_at 和 projection provenance。订阅 context 为 opt-in，需要明确规则、去重键和防回环标记；默认不订阅全部用户消息自动执行。

## 生命周期

安装 → 校验版本/权限/依赖 → 授权 → 注册操作 → 使用 → drain → 停用/卸载。升级必须提供业务 schema 迁移与 rollback 策略。卸载先停止派发并收敛 in-flight 操作，再撤销 credentials；用户数据导出/保留/删除是显式选项，不能静默删除账本。

第三方或 AI 生成 Kit 通过相同规范接入，生成代码不自动获得生产权限。私有 Kit 可在独立私有仓库或 `/private/` 下实现，不成为公共默认依赖。
