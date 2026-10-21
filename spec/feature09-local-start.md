# 本机统一启动

Hymio 的部署入口负责组合 Casdoor、Backend、Oath 和可选客户端；客户端不承担服务启动。新安装通过 feature24 的统一私有配置自动初始化身份与内部凭据；以下手工服务配置路径保留兼容。

## 接口

`python3 deploy/start.py --client web|desk|none`，默认 web。`--backend-config` 与 `--oath-config` 指定现有配置；`--auth-project` 指定 Casdoor Compose 数据所属项目，默认 hymio-auth。配置文件中的端点和密钥引用仍是事实来源，无新增配置文件。

## 顺序与边界

检查命令、配置、端口 → 安装锁定依赖 → 启动 Casdoor 并等待 OIDC discovery → 启动 Backend 并等待 health → 以 remote 鉴权启动 Oath → 启动所选客户端。Oath 使用自身默认扩展；Hymio 扩展可在后续接入，不默认加载占位目录。

Backend 必须监听 0.0.0.0，供 Oath 容器访问。当前入口面向本机默认端口，要求 Backend 为 8080、issuer 为 localhost:8000，Oath 配置须匹配 Backend 的 WS/Biz 地址。拒绝占用的 Backend / Client 端口，不杀已有进程，不自动覆盖配置或登录数据库。

Backend 与 Client 前台运行，任一退出则关闭本次启动的子进程组。SIGINT/SIGTERM 同样清理；有界等待后强制终止。Docker 服务保留，Oath 已接纳任务继续执行。启动失败也保留 Docker 数据和容器，明确提示单独停止方式。服务等待有截止时间；不提供自动重启循环。

这是开发环境组合入口，不承诺生产部署、安装系统依赖或无人值守升级。统一配置模式的 Casdoor 初始化、可变 issuer 端口及新电脑流程见 [feature24](feature24-local-bootstrap.md)。
