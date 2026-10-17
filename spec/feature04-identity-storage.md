# Feature 04 — 身份、授权与自带 Context 存储

状态：Draft；认证服务、凭据存储与 Nostalgia 协议待实现。

## 总览

Hymio 管理用户、设备、渠道绑定、连接器授权、Kit 安装与 Context endpoint。产品用户映射到 Oath `user_id`，不引入会话身份。Context 权限模型由 Nostalgia 定义，Hymio 根据正式契约接入。

外部账号 token 不进入 context、projection、runtime trace 或前端构建；服务持有 secret 引用，执行时解析需要的凭据。客户端提供的 user_context 不替代经过验证的身份和权限。

## Endpoint 与授权

用户可以使用托管 Nostalgia，也可以配置兼容的自带 endpoint。配置包含协议版本、base URL、认证引用与能力信息。具体 API 路径和实体 schema 需以 Nostalgia 实现为准，当前不宣称存在某层正式 API。

配置变更先验证兼容性；切换地址不代表数据已迁移。撤销渠道/Kit 授权后阻止新调用，对在途动作请求取消，并保留无法确认取消的状态。安装 Kit 不自动授予所有私人 Context 的读取权限。

## 失败与恢复

跨端凭据失效时重新认证；账号绑定冲突不静默合并。Context endpoint 不支持某种检索能力时，客户端显示实际可用范围。

数据迁移应作为独立操作固定来源快照、导出记录与资源、导入目标并校验后切换；未能保存身份和历史时不能宣称无损迁移。这是后续能力，本次初始化不实现。
