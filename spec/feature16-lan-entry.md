# 单入口与局域网真机体验

状态：Implemented（本机 LAN、Web 与 iOS 模拟器验证；真实 iPhone 安装需用户在 Xcode 完成）

## 目标

客户端只访问 Hymio Backend 的一个 HTTP(S) 地址。登录、业务查询、聊天 WS 统一进入 Backend；Oath 的 WS/Biz 地址为后端内部地址。默认本机启动行为兼容，局域网通过唯一的本地部署配置 `deploy/local.toml` 的 `lan_host` 开启，不要求修改已保存的后端配置或开放 Oath 端口。

## 边界

- `/agent/ws` 只做双向 WebSocket 传输代理，不消费事件、不保存会话、不创建 Agent。Oath 仍验证 attach 凭据并负责身份隔离、持久化和重放。
- 登录响应中的 oath_ws 从 public_url 派生，oath_biz 继续使用 Backend 代理；配置 oath_ws/oath_biz 指向内部 Oath。
- 校验浏览器 Origin；无 Origin 的原生客户端仍由 Oath 验证凭据。拒绝二进制帧。任一侧断线取消另一侧转发；不记录消息或凭据，失败关闭使用可重连错误码。
- 开发脚本保持 Backend 在 Mac，Oath/Casdoor 在 Docker。局域网只需访问 8080；Web 开发预览额外使用 1420。Docker 内部认证和扩展连接不变。

## 启动配置

`lan_host` 支持 auto / off 或本机网络接口的 IPv4 地址，不接受 URL、任意 hostname 或 0.0.0.0。启动生成忽略的 Backend runtime 配置，保留身份与数据库来源，路径转绝对路径；覆盖 public_url 并添加明确的 Web Origin。首版 LAN 自动配置仅支持 account 登录；保留已在 Casdoor 注册的 callback_url，账号登录通过后端交换授权码，手机无需访问此回调。浏览器 OIDC 仍要求回调与 public_url 一致。Web 使用进程配置覆盖 Backend URL，避免改写用户 client.toml。CLI 只记录配置路径，restart 重新读取文件；不将地址缓存为启动参数，status 输出可访问地址。

iOS 网络单独生成到 Network.generated.xcconfig，仅被 Debug 包含；Local.xcconfig 中的用户签名和 Bundle ID 不改动。Team 在 Xcode Signing 中选择。所有本地配置与生成文件均不进入 Git/Docker context。Release 不读取 LAN 生成文件，仍要求 HTTPS/WSS。

## 恢复

代理不参与 ACK，客户端断线后按已有 cursor 重连。原始配置不变，配置 lan_host = "off" 后重启恢复本机模式。启动不杀占用端口的无关进程。局域网 HTTP 只用于可信网络的 Debug 体验，公网使用现有 HTTPS 部署入口。

## 云部署兼容

新云配置仅要求 web_domain 与 api_domain；Backend 的 oath_ws 为从容器可达的内部地址。旧 agent_domain 保留为可选直接代理入口，避免破坏已有部署。客户端统一使用 API 域名下的 /agent/ws。云端需要的 DNS、证书与实际网络验收仍由部署完成后验证。

## 传输限制

Backend 到可信 Oath 的接收帧不额外限制大小：运行状态与历史快照可能大于 8MB，代理必须保持原直连协议语义。接收队列限为一帧，使用流控，不积压多个大帧；客户端到 Oath 的输入限制仍由原服务执行。上游关闭码透传（保留码映射为可重试错误），日志仅记录码或异常类型。客户端遇到 1009 消息过大时显示错误并停止自动重连，避免永久失败形成重连风暴。
