# 11 — 单机云部署

状态：Implemented（部署入口；真实云端验收待部署）

## 决策

Hymio 提供独立的 Docker Compose 部署入口：Backend、静态 Web 与 Caddy HTTPS。
Oath 用自己的 CLI 启动，Casdoor 使用独立部署或托管地址；不会把开发 Vite 服务器用于公网。
云电脑默认选 E2B，应用容器不挂 Docker socket。首版单机、单 Backend、SQLite 持久卷。

## 配置与边界

部署输入集中在私有 cloud TOML；Backend/Oath 各自保留自己的配置。
部署脚本生成忽略的 Compose、Caddyfile 与公开 Web 构建配置，不使用 .env。
私有目录只读挂到 Backend，运行库写独立卷。密钥不进镜像、不传给客户端。
Web / Backend 通过两个域名提供 HTTPS；聊天 WSS 走 Backend 的 /agent/ws。Oath WS/Biz 仅供服务器内部访问。旧 agent_domain 为兼容选项，新部署不需要第三个域名。
反向代理的 host gateway 连接本机 Oath，Oath 启用 Hymio remote auth。
Backend 通过 host gateway 访问 Oath Biz；Oath 通过宿主机 Docker bridge 转发端口访问 Backend 验证器和工具路由。

## 生命周期

Compose restart policy 在服务退出或主机重启后恢复 Backend/入口。
SQLite 只允许单副本，不能通过增加容器数实现横向扩展。
备份必须覆盖 Backend SQLite、Casdoor 数据及 Oath 持久数据；截图在 Backend 数据库中。
E2B 沙箱另有生命周期，应用重启不等于沙箱续期或数据备份。
升级前先备份；回滚镜像不保证数据库 schema 可逆。

## 本次交付

容器构建、配置生成器、启动/停止/状态入口和部署说明。
域名 DNS、证书签发、云网络和真实 OIDC 回调需要部署者配置；没有云端验收则不宣称完成公网部署。
多机调度、托管数据库迁移、自动备份和自动沙箱续期不在本次范围。
