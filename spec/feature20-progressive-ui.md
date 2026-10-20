# Progressive agent UI

状态：Implemented

## 目标

Web/Desk 与原生 iOS 用同一套受限声明数据展示交互卡片；正文通过 jitter buffer 平滑显示。Oath 事件持久化、ACK 与业务权限不受展示节奏影响。Trace 使用独立页面，自动连续读取列表，无翻页按钮；聊天历史分页保持现有行为。

## 流式正文

只缓冲正在接收的消息；首次载入历史直接展示。正文以 grapheme 为单位先蓄水 100ms，之后固定每秒 90 个字符输出。终态仍排空待显示内容；文本改写/重试重置，后台恢复与减少动态效果直接对齐。装饰只动画最新的一小段，不重复动画整段回复；Markdown 与图片保留已有渲染器。供给不足时等待，不伪造内容。缓冲内容不写入事件库。

## Hymio UI v1

受 json-render flat spec / JSONL streaming 启发的有限子集，不宣称完整 json-render 或 Google A2UI 兼容。使用 assistant Markdown 中独立的 hymio-ui fence，块内每行一个 add/replace/remove 操作，仅允许 /root 与 /elements/<id>。完整 spec {root,elements} 也允许。语法未完成保留最后有效帧；未知组件/非法属性不执行，终态给出可理解的失败提示。每块最多 64KiB、64 节点、深度 12、字段 2000 字符。普通代码块不参与解析。

目录：Card、Column、Row、Text、Metric、Badge、Input、Choice、Button。组件只接受文档中的属性，无脚本、原始 HTML、CSS、网络请求。稳定 ID 保持本地输入；input 的 value 是初始值，不覆盖已编辑内容。Button 的 prompt 可以引用 {{input-id}}，只在用户明确点击后发送可见普通消息。失败可重试，不自动执行工具，不承接权限批准。历史动作需要用户主动确认点击；发送时走现有账号、消息提交与用户隔离链路；离线请求未被接纳时保留表单并提示重试，不能误报成功。

结构 UI 使用原始接收内容，按完整记录提交，不能被逐字缓冲拖慢；正文缓冲与结构解析独立。新增卡片/节点做短时渐入，稳定节点不重复 mount。两端支持减少动态效果。模型使用方式由 Hymio extension skill 提供，Oath 无需修改。

## 验证

覆盖 Unicode、突发/延迟/终态、历史、不完整与非法 UI、循环/超限树、输入状态、显式动作、真实双端构建及可视化检查。调研报告保存在仓库外；spec 只记录交付契约。

## 模型接入与开发

`extensions/skills/hymio-ui/SKILL.md` 是模型可读取的组件目录与生成范例。运行 Oath 时挂载 Hymio 的 extensions/skills，重启 Worker 以刷新技能目录。普通问答仍用 Markdown；需要比较、调整参数或确认下一步时由模型加载 skill 并输出 UI block。按钮只走普通 user.message；不会自动创建日程或执行工具。

规范明确：每行完整 spec 或一个完整 patch；patch 仅支持根与整节点操作，不支持任意 JSON pointer。行内不完整保留旧帧，终态未完成显示说明。每个 child 只能有一个 parent，拒绝循环、重复父节点与 __proto__/constructor/prototype IDs。Choice.options 必须是字符串数组。未解析 children 在生成时预留占位，终态仍未解析则省略；错误不会把内容作为代码执行。当前无跨消息 surface 更新、Canvas、任意图表或第三方 UI 动作。

Web Trace 路由为 #/trace，聊天视图保持挂载但隐藏，返回不会清空草稿或重建连接。iOS 使用 NavigationStack 独立页面。列表以服务端 limit/offset 分块连续读取并随批更新，没有用户翻页按钮；取消后停止合并，重复记录按 trace ID 去重。事件列表只显示该端已同步事件，不冒充完整服务器 journal。

## 展示边界

模型输出不是执行权限。UI 只能在白名单中表达信息，Button 仅发送普通消息；动态卡片不执行 JS/TSX，也不接受远程代码、原始 HTML、任意 CSS 或隐藏 HTTP 动作。输入不因流式 patch 重置；引用的表单节点尚未到达时，动作保持不可提交。

原生滚动使用系统内容尺寸锚点跟随缓冲文本增长，不在布局高度回调中反复 scrollTo；往上阅读时暂停跟随。历史/账号切换与重试通过消息/attempt 身份分隔缓冲，减少动态效果和后台恢复直接对齐文本。

原生正文使用独立展示对象管理时钟，只发布可见帧；不把内部计时字段放进 SwiftUI 的 State。稳定 Markdown 段落保留原渲染器，尚未完成的段落使用轻量原生行内文本，终态恢复完整 Markdown。复制菜单仅放在正文，不能包裹生成表单控件。
