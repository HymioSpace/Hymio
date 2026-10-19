# 12 — Hymio 命令行

状态：Implemented（本机源码安装与进程管理）

## 决策

提供 `hymio` 本机部署命令，复用 deploy/start.py 的服务编排，不复制启动逻辑。
安装入口 `bash scripts/hymio-install`；支持 start / status / stop / restart / logs。
这仍是基于源码目录的本机 Web/Tauri 启动器；云端 Compose 入口独立维护。

## 配置与进程

CLI 独立 Python 包放在 deploy/cli，不在仓库根引入客户端依赖。
安装将源码目录写入 ~/.hymio/installation.json；依赖该目录，不能安装后直接删除源码。
状态、操作锁和日志在 ~/.hymio/；可用 --home 隔离管理目录。
Backend 和 Oath 配置仍使用现有文件，CLI 不另存密钥；支持显式配置路径。
start 默认 web，可选 desk/none；启动器后台常驻，日志写本机文件。

实例使用随机 token + PID + 命令身份识别。start/stop/restart 由文件锁串行化。
重复 start 若已就绪则返回成功；配置/客户端不一致时要求 restart，不静默忽略。
已有但非 CLI 管理的 Hymio 仅提示可访问；不能接管或通过 stop 杀掉它。
陌生端口占用保持报错，不按端口直接杀进程。

## 失败语义

启动器在完成 Oath 编排后写入带实例 token 的就绪标记；CLI 同时检查该标记和 Backend/client HTTP，
不能把旧实例或仅 Backend 在线误判为整套就绪。启动器退出则显示日志位置。
超时不假装成功，保留明确启动状态，可 status/logs/stop；避免创建第二个实例。
stop 只停止受管理的启动器及其 Backend/client，不停止 Oath/Casdoor 或 E2B。
关闭客户端、退出 CLI 均不结束云端 Agent 工作。重启复用现有配置，不能创建新的登录数据卷。
首次安装提示已有 Casdoor project 选择，CLI 首次启动也可通过 --auth-project 指定。

## 验证边界

检查命令安装、重复启动、状态、配置冲突、日志、正常停止及重新启动。
PID 身份不匹配时不发送信号。云端服务不由此 CLI 托管。
