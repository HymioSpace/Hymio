# 13 — 会话快照与历史分页

状态：Implemented

## 总览

打开会话先显示最近十轮快照，完成本机持久化后从 checkpoint 接收实时事件。
旧记录通过 Biz 查询并向上加载，不再逐 token 回放整段对话。

## 职责

Oath Storage 负责持久会话读模型、checkpoint 和按用户隔离的分页。
Gateway 传送 conversation.snapshot，客户端保存成功后才累计 ACK；工具执行不依赖历史分页。
Hymio Backend 代理 conversation_history 并验证登录身份；客户端负责显示和阅读位置。
Web/Tauri 使用同一查询协议，查询不接受客户端自选其他 user_id。

## 客户端

IndexedDB 原子保存快照和 checkpoint，待发命令不清空。
刷新从最近一页开始；加载更早消息不会推进实时 cursor，也不会改变已保存的 checkpoint。
前插历史保持视口位置，不自动滚到底部。快照携带页外的进行中任务与待授权依赖。
已缓存实时事件不重复写盘，累计 ACK 只确认连续且已持久化的进度。

## 边界

快照是 UI 读模型，不替代原始 Outbox、Journal、Trace 或模型 context。
网络、鉴权和本机存储失败要明确报错，不能用空快照冒充加载成功。
