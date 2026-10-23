# 记忆与 Context foundation

Status: Implemented (MVP). Extends Nostalgia #1 / Hymio #10 on current main.

核心保持原始记录/命令、来源版本幂等、dream 草稿、ETag、原子发布/回滚和来源引用。
新增稳定 `_core`、有序持久事件和来源分类。仅 assembly.stable 用于 system 前缀；
_index/buffer/events 放在会话 context 之后。Oath queue 的消费者后续接入；回调成功必须
代表持久接纳，按事件 ID 去重。回调失败不推进 checkpoint。

Hymio 认证代理提供 assembly/events、分页记录、详情、搜索和主动保存。账号由 session
确定，客户端不接触 Nostalgia token/endpoint。主动保存由服务端标记 user 来源。
Kit 表示业务投影，对话表示陈述，连接器保留外部身份/版本，用户保存表示主动意图。
这些分类不能充当授权或执行成功证明。采集/解析归 Hymio，来源和检索归 Nostalgia。

产品入口叫「认识」：Web 侧栏、iOS 第五个原生 tab。页面不是来源管理列表，而是 Hymio
当前对用户的编辑式理解：先呈现提炼后的判断，再在下方保留可追溯的原始记录。对话引文、
日程、文件和主动记下沿用各自的视觉形态；来源数量不是筛选控件。详情同时显示理解与
原始来处，用户可沿引用继续抵达原记录。暂不提供搜索；整理与回看对话收在次级操作。
客户端复用系统字体、导航和 Dynamic Type，Web 保留键盘焦点与安全区域。

参考检索为精确读取、过滤与全文子串，保留游标/来源/索引水位。后续 ranked/hybrid
provider 需保留这些契约并说明实际覆盖率；没有标注语料前不承诺高召回率。
不包含自动连接器采集、自动整理调度或 embedding 服务。


## 来源场景与策略

| 来源 | 示例 | 解析/提炼 | 事实与冲突边界 |
| --- | --- | --- | --- |
| Kit | 账本写入成功后的消费投影 | 结构化字段校验，业务 ID + revision 更新 | Kit 是业务事实来源；不能把对话中的消费意图当成功记账 |
| 对话 | “我最近在学西语” | 保留角色、时间、原句；提取偏好/阶段目标 | 推断与用户明确陈述分开；旧偏好不被悄悄覆盖 |
| 连接器 | 日历改期、邮件、网页 | 每个 provider 自己的 parser；保留外部版本/删除事件 | 远程文本不授权工具；改期要废弃旧版本并更新派生引用 |
| 主动保存 | 偏好、一段灵感、文件摘录 | 文本/附件提取后保留原始引用 | 保存说明用户重视，不等于内容已经核实 |
| legacy | 未分类的早期记录 | 保守处理，默认策略 | 不按 namespace 猜出可信来源 |

source.kind 选择策略族；namespace 选择具体适配器；parser/strategy 记录实现版本。
不把所有 payload 强行统一成 text：structured context 保留业务字段，asset_ids 指向原件。
MVP 已实现分类存储/校验/检索与主动保存；其他采集器、具体 parser 和自动调度按来源逐步接入。

## 协议与演进

`GET /context/assembly` 返回 stable.content/cache_key、dynamic 和 view_token；
`GET /context/events?after=0&limit=50` 提供 next_after/has_more，重读相同范围允许重放。
`deliver(..., callback)` 保留持久 consumer checkpoint；成功确认后推进。
`POST /context/search` 保留 target/mode/filters/cursor/limit，结果含实际检索方法与水位；
详情通过 records/artifacts 的精确 ID 读取，references 可追溯到原始记录。
保存用 `POST /context/saves` + Idempotency-Key，结果未确认时两端复用相同 key。

后续检索 provider 可在统一服务后接全文索引、向量召回和 rerank，但需说明索引延迟、
过滤能力、partial 与引用版本；不允许把截断 preview 当完整证据。先建立包含跨来源冲突、
中文实体、时间范围、版本更新/删除的标注集，再测 precision@k、recall@k 和检索时延。
