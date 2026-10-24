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

Agent 通过语义化的 `remember` 工具保存用户明确要求保留、或明确陈述的稳定个人信息，
通过 `recall` 在回答过往偏好与经历前检索。remember 同时提交精炼摘要与对应原文，只有
有跨轮价值或用户明确要求的信息才保存，详见 feature31。工具调用由模型决定，不按关键词拦截消息；
保存成功前模型不得声称已经记住。用户主动选择历史导入时，才把既有对话转成原始
conversation record。

`assembly`、`events` 与 `injection` 是 context builder 的内部读取路径，不是 Agent 工具。
Dreaming 是 Nostalgia 内部的周期机制，不是普通对话可调用的动作。

Oath 只提供通用工具注册与运行机制，不定义 Hymio 的 `remember`、`recall`、`tasks` 或
context 业务语义。所有 Hymio 工具都位于本仓库 `extensions/tools/`，由部署时挂载。
Nostalgia owns context storage and scheduled dreaming; Hymio Backend wraps its API for clients,
and a stateless internal adapter supplies structured dream proposals when configured.

产品入口叫「记忆」：Web 侧栏和 iOS 原生 tab，分为「理解 / 足迹」。默认简约卡片，
搜索和直接文字收集可用，详情读取完整内容与依据，星图按需展示真实引用关系。
两类结果分别分页；读取失败不显示首次使用空态。产品机制、平台交互及演进边界见
[feature31](feature31-memory-space.md)。

参考检索为精确读取、过滤与全文子串，保留游标/来源/索引水位。后续 ranked/hybrid
provider 需保留这些契约并说明实际覆盖率；没有标注语料前不承诺高召回率。
不包含自动连接器采集或 embedding 服务；整理调度由 Nostalgia 内部负责。


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
