# Feature 01 — 导入与同步

状态：Draft；依赖 Nostalgia context schema 与 Context HTTP API。

## 两种模式

**导入 Import**：一次性内容提交。输入文字、语音、照片、文件以及某渠道历史快照都是导入；“上传”是传输过程，不作为第三种用户概念。

**同步 Sync**：持久绑定来源，增量处理新增、修改和删除，维护 connection、权限、checkpoint、调度与重试。

两者复用解析/归一化流水线；connector 只负责拿到来源数据和变化，Nostalgia 只负责保存规范化 context。

## 数据流与 API 草案

Hymio 前缀 `/v1/app`：`POST /imports` 返回 durable operation，`GET /imports/{id}` 查询；`POST /connections` 建同步连接，`POST /connections/{id}/sync` 触发一次同步，`DELETE /connections/{id}` 停止同步并撤销凭据，保留/删除已导入内容需独立明确策略。

Import 状态：accepted → parsing → writing → completed / partial / failed / cancelled。多项导入返回逐项结果，不宣称跨全部对象原子提交。客户端用稳定 client_operation_id / Idempotency-Key 重试。

媒体先上传 asset，解析器/OCR/转写生成可追溯派生记录；原始内容不因解析失败而消失。记录来源 namespace/external_id、上游版本、业务时间与固定 parent revision。敏感原始数据不写普通应用日志。

同步的 checkpoint 只在这一批每项得到 durable receipt 或已记录可恢复失败后推进；失败项保留独立重试队列。exactly-once 不依赖队列承诺，靠来源唯一键、幂等与 revision 前置条件。webhook 重复、乱序、轮询重叠都必须可重放。

## 更新、删除与离线

同一连接的变更序列化处理；上游无可靠 revision 时，connector 对固定快照计算 hash 并检测冲突。Nostalgia 的 412 不通过盲目重读覆写解决，而应对比来源版本和本地编辑策略。

增量来源能表达 delete 则转 tombstone；全量快照只有标记完整成功后才能判断缺失项删除，不能把抓取失败当成全部删除。手动删除后的 tombstone 不因同步自动复活，需用户明确 restore。

离线手机缓存 pending imports；恢复网络后重用同一个操作 ID。成功但 ACK 丢失的重试返回原结果，避免同一照片/语音重复入库。重试窗口和来源键持久化期限与 Nostalgia capability 对齐。

## 验收

文字/照片/语音都通过导入；重复 webhook 不重复建对象；部分失败可单项重试；同步被撤权后停止访问；离线重传不重复；上游删除传播到检索；多账号相同外部 ID 不冲突。
