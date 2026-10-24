---
name: kit-builder
description: Create a small user-owned application from a conversation request.
channels: [ios]
---

# Build a small application

Use this workflow when the user asks Hymio to make an app, tracker, collection or simple tool. The
product calls these “应用”; the internal name Kit is not shown to the user.

## Clarify only what changes the app

Infer the display name, purpose, category and useful fields from the conversation. Ask only when a
missing field would make the app incorrect. Keep the first version small: usually one to five fields
that describe one entry.

Examples:

- “饮水记录” with fields `amount` (number) and `time` (text/date).
- “读书清单” with fields `title` (text), `author` (text), `finished` (boolean).
- “猫咪体重” with fields `weight` (number), `measured_on` (date) and `note` (text).

Generate a self-contained HTML application for iOS WKWebView. Inline its CSS and JavaScript and
call the host with the `HymioKit.call(operation, arguments)` bridge when it needs persistent data.
Do not use external network APIs in the MVP. For a purely presentational app such as a breathing
guide or reference page, omit `fields`; that Kit intentionally has no API or Agent operations.

## Product and visual bar

The result should feel like a finished app that happens to be generated, not a generic admin form.
Before writing HTML, decide:

- **One job.** What should the user understand or do at a glance?
- **One signature.** A chart, a spatial composition, an editorial number or one restrained motion
  moment. Spend boldness there and keep the surrounding surfaces quiet.
- **Product-specific structure.** Organize the page around the user's actual subject. Do not paste
  the same hero-plus-three-cards layout onto every request.
- **One color language.** Use 4–6 named color roles with light and dark values. Color never carries
  meaning alone; pair it with labels, shapes or numbers.
- **A real empty state.** Invite the first meaningful action without pretending there is data.

Use native-feeling mobile composition: 16–22 px page margins, clear type hierarchy, 44 px minimum
tap targets, visible focus, semantic buttons and labels, and safe-area-aware fixed actions. Support
light and dark appearance with `color-scheme: light dark`. Respect
`prefers-reduced-motion: reduce`. Aim for polished but calm; gradients and blur should clarify
functional layers and should not make content harder to read.

For a data app, show information that the available operations can actually derive. A small local
chart or summary from returned entries is good. Never invent a budget, trend or comparison that the
API did not return. Prefer ordinary DOM construction and `textContent` for user data.

## Technical constraints

- Produce one complete HTML document with inline CSS and JavaScript. Do not add a framework, CDN,
  build step, module imports, external fonts, remote images or another service.
- The MVP page runs without network access. CSP allows inline code and `data:` images only. Do not
  use fetch, XHR, WebSocket, iframes, workers, service workers, external navigation or external
  media.
- Keep the document under 512 KiB and avoid large embedded assets. It must render its useful initial
  state quickly on an iPhone.
- Persist domain data only through the declared operations and `HymioKit.call`. Do not treat
  `localStorage`, IndexedDB or page globals as the source of truth when Agent/user synchronization
  matters.
- Never place tokens, credentials, user IDs or Kit IDs in the page. The native host owns identity
  and the current Kit. The page chooses only an operation and its arguments.
- Keep operation IDs and argument names aligned with the fields passed to `kit_build`. A page must
  not assume an operation exists unless the generated field-backed Kit provides it.
- Handle loading, empty, success and failure states inside the app. Do not use `alert()` or
  `confirm()` for routine feedback; use in-page status, inline errors or a temporary toast.
- Make controls keyboard- and VoiceOver-friendly: label icon-only controls, use native buttons and
  inputs, maintain logical reading order and do not remove focus outlines.
- For purely presentational interactions, use local JavaScript freely. Do not add fake operations
  merely to make a static page look interactive.

## Call the builder

Call `kit_build` with:

```json
{
  "name": "饮水记录",
  "tagline": "记下每天喝了多少水。",
  "description": "记录饮水数量和时间，查看最近记录。",
  "category": "生活",
  "item_label": "杯水",
  "accent": "blue",
  "app_html": "<!doctype html>...",
  "fields": [
    {"key":"amount","label":"杯数","type":"number","required":true},
    {"key":"time","label":"时间","type":"text","required":false}
  ]
}
```

The generated Kit is owned by the current user and installed automatically. If fields are
provided, its `items.create`,
`items.list` and `summary` operations are injected into the current user's application context on
the next model step, with exact input schemas from the generated fields. If fields are omitted,
the page remains a real static application and no operation is injected.

## After creation

Tell the user the visible app name and what it can record. Do not expose manifest, handler or Kit
version terminology. Do not create a task merely because an app was generated.

To use the new app immediately after the tool result, call `kit_call` with the returned `kit_id` and
one of its operations. Do not request a catalog or operation list.
