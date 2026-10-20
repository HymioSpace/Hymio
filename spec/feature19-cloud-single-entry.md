# 单域名云端部署

状态：Implemented

## 目标

一个公网 HTTPS 域名提供静态 Web、登录、业务 API、WS 与工具媒体。支持小规格单机，私有输入集中在服务器配置目录，不把个人域名、地址、凭据或运行数据写入仓库。

## 入口

cloud 配置允许 web_domain 与 api_domain 相同。Caddy 按路径分流：/auth/*、/agent/*、/oath-biz/*、/devices 与 /devices/*、/health 进入 Backend，其余路径提供 Web。内部认证与工具路由 /internal/* 不经公网开放。不同域名的现有部署继续支持。

Casdoor 使用内部网络，账号表单由 Hymio 提供。Oath 通过内部地址访问 Backend；模型凭据只导入 Vault。配置目录包含 deployment/cloud、Hymio、Oath 的 TOML 和按服务授权的 private 文件；运行库与配置分开备份。

signup_enabled 默认为 true 保持兼容；私有部署设为 false，服务端拒绝注册并通过 auth/options 通知 Web/iOS 隐藏注册入口。普通用户放在独立 Casdoor organization，不使用 built-in 管理组织。

## 部署

使用固定代码版本构建；容器只在入口发布 80/443。同机部署由 Backend 加入 Oath 的外部 Docker 网络，使用 gateway/biz/backend 服务名互通；Backend 不发布端口，Oath WS/Biz 与 Vault 只绑定 localhost。可选 managed_identity 提供私有 Casdoor 容器，账号与应用仍需显式初始化。初次部署检查登录、账号隔离、流式对话、重连和 E2B 操作；公网 DNS/TLS 以及服务器实际验证不能由本机测试替代。

## 邀请码注册

私有部署开启 signup_enabled 并配置 invitation_codes_file。文件每行一个可复用邀请码，注册时重新读取，修改无需重启；空文件、缺失文件均不放行。邀请码仅由 Backend 校验，不透传到 Casdoor、Oath 或模型上下文。auth/options 仅公开 invitation_required 布尔值，Web/iOS 据此展示输入框。未配置文件保持原有开放注册兼容行为。Casdoor 仅私网可达，应用允许注册，由 Backend 作为外部注册入口；将来若公开 Casdoor 必须另行保护其注册入口。

iOS 注册配置读取失败时提供重试，回到前台重新获取；注册页提示邀请码请联系作者获取。显式 Local.xcconfig 优先于 Debug 自动生成的局域网默认值。
