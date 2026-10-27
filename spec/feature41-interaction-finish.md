# 展示层精修参数

用户明确指定的十条规则用于现有展示层；不改消息、执行、附件和任务协议。

## Web

- `craft.css`四层OKLCH背景：浅色L为96/97.5/99/100%，暗色18/20/22/24%，相邻差值1–2%。主框架通过层级分组，不使用黑框或纯黑色值。
- 输入框与composer聚焦不增加outline或有色border；两重box-shadow分别2px/6px扩散，颜色由当前accent派生；高对比模式增强阴影。按钮/链接的键盘焦点仍可见。
- 暗色`--weight-adjust:40`，既有显式数值字重改用`calc(weight - offset)`，保留层级。400→360、600→560，浅色offset为0；最终字形取决于平台字体是否支持对应字重。
- 流式显示按Unicode grapheme划分；同批新到文字以0/30/60/90ms四相错峰，120ms内从blur(6px)与透明变清晰。动画仅覆盖32个grapheme加有界单词边界的尾段，历史文字恢复普通文本节点；不让长输出的动画节点和延迟持续增长。已有文字的延迟和动画身份不变，不把整段历史的字符索引乘30ms。单词分组保留正常英文换行语义。减少动态效果时直接显示文字。
- 功能图标相对文字下移0.125em；所有数字启用tabular-nums；正文text-wrap:pretty。
- 对话过程、思考和工具折叠使用共用Disclosure组件，Grid 0fr→1fr，闭合后inert和aria-hidden，按钮保留aria-expanded/aria-controls。
- 拖拽1200/80（mass=1，过阻尼，无回弹），点赞380/18记录为参数。当前没有内容拖拽或用户点赞入口，不能用操作系统窗口拖动或Agent被动emoji回应冒充这些交互，因此不添加新业务/手势。
- 复制代码与回复成功后显示对勾，2500ms恢复；再次复制会重置timer，组件卸载取消timer。

## iOS适配边界

SwiftUI不运行CSS。已同步四层颜色、无描边的两层聚焦阴影、monospacedDigit、代码/回复复制2500ms反馈；记录相同质量/刚度/阻尼的原生弹簧常量，未绑定不存在的点赞/拖拽入口。

`Grid 0fr`、`text-wrap:pretty`、CSS wght数值偏移和逐字CSS filter仅为Web实现，不能声称已自动等价应用于原生Markdown/系统字体/DisclosureGroup。原生保留系统排版与折叠，不为实现CSS外观替换整套Markdown或原生导航。后续若需原生逐字TextRenderer，须单独验证Markdown布局、Dynamic Type、选择与减少动态效果，不能用整段反复模糊来冒充逐字渐显。

## 验证入口

`/craft-review.html`是开发专用的合成内容验证页，使用实际MessageView、Disclosure和ProgressiveContent，不连接用户账号、业务API或剪贴板读取。`?theme=dark`从实际CSS提取暗色变量，以便检查暗色视觉；不增加产品主题设置。

本次Web构建与iOS Simulator整体构建通过。浏览器已核对聚焦双环、闭合高度0、展开内容可访问、复制成功状态；最终验证记录见[implementation record](../docs/design/client-ui-2026-10/implementation.md)。
