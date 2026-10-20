---
name: hymio-ui
description: Present a comparison, plan, metrics or small interactive form inside Hymio chat. Use when UI helps the user decide, configure or explore; concise answers remain prose.
---

# Hymio native interaction surfaces v1

Web and iOS render the same controlled catalog natively. Put standalone `hymio-ui` fenced
blocks in assistant content. Never send React, HTML, scripts, CSS or arbitrary URLs. Each line
is either a complete spec or one complete JSON patch. Prefer patches: add a parent with reserved
child IDs, then add children as information arrives. One JSON object per line, no pretty-printing.
Use at most 64 nodes and 64 KiB per block, depth 12. Each child belongs to only one parent.
Use stable IDs `[A-Za-z0-9_-]{1,64}`. Ordinary text can precede/follow the surface.

Allowed patch paths: `/root`, `/elements/<id>`; operations add, replace, remove. Replacing a node
replaces the whole node. No nested property patching, data bindings or other JSON Patch operations.
A full spec has `{ "root": "id", "elements": { "id": {"type":"Card","props":{},"children":[]} } }`.
All props are strings except Choice.options (array of strings). Text is literal, not Markdown.

| Component | Props | Children |
| --- | --- | --- |
| Card | title, subtitle | yes |
| Column / Row | none | yes |
| Text | text, tone (muted optional) | no |
| Metric | label, value, detail | no |
| Badge | text | no |
| Input | label, placeholder, value (initial only) | no |
| Choice | label, options (max 12), value (initial) | no |
| Button | label, prompt | no |

Button prompts can contain `{{input-id}}` or `{{choice-id}}`. A click substitutes current values
and sends an ordinary **visible user message**. It never executes a tool or approves permission.
Do not label a button as having completed a real action before tools confirm it. Do not generate
secret-entry fields: submitted values become conversation content. IDs remain stable so input
survives incremental updates. Give all input/select controls descriptive labels.

Example (use separate complete lines as shown):

```hymio-ui
{"op":"add","path":"/root","value":"plan"}
{"op":"add","path":"/elements/plan","value":{"type":"Card","props":{"title":"留一点时间给自己","subtitle":"先选节奏，再安排今天。"},"children":["duration","focus","continue"]}}
{"op":"add","path":"/elements/duration","value":{"type":"Choice","props":{"label":"空闲时间","options":["15 分钟","30 分钟","1 小时"],"value":"30 分钟"}}}
{"op":"add","path":"/elements/focus","value":{"type":"Input","props":{"label":"想做点什么","placeholder":"散步、阅读，或只是休息","value":"散步"}}}
{"op":"add","path":"/elements/continue","value":{"type":"Button","props":{"label":"一起安排","prompt":"请帮我安排{{duration}}的{{focus}}，先给出建议，不要直接创建日程。"}}}
```

Use accurate observed data. A placeholder is not a fabricated result; describe missing data in
prose. Avoid surfaces for a greeting, single fact or an error requiring only a short explanation.
