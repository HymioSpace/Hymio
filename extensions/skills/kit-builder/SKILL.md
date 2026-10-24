---
name: kit-builder
description: Build a polished, self-contained HTML application for Hymio's iOS application host.
metadata:
  channels: [ios]
---

# Build an app, not a form

Use this when the user asks Hymio to make an app, tracker, collection, log, guide or small tool.
Users see the product name “应用”; never surface internal words such as Kit, manifest, handler,
schema or operation unless the user is explicitly discussing implementation.

Treat “simple” as a small product, not a visually bare prototype. The result must look intentional
at iPhone size before it is useful. A centered title followed by an unstyled form is a failed result.

## 1. Choose an art direction

Before writing HTML, choose four things:

1. **One job** the user can complete without explanation.
2. **One focal artifact**: a number, an object, a timeline, a canvas or a visual index. It should
   change with the user's data and belong to this product.
3. **One signature**: a composition, typography treatment, data visualization or restrained motion.
   Spend visual boldness here; keep navigation and form controls quiet.
4. **A material story**: color, texture and spacing derived from the subject. “Finance” may feel
   precise and luminous; “reading” may feel editorial; “breathing” may feel spatial and calm.

Use the available content to select a structure:

| Product type | Strong starting structure |
| --- | --- |
| Tracker or ledger | Oversized current value + short trend + category breakdown + chronological entries |
| Collection or list | Editorial index + quick add + object detail, not another dashboard grid |
| Routine or guide | A paced sequence with one active step and obvious completion feedback |
| Calculator or utility | Large live result + tactile controls; controls and output occupy different layers |
| Static reference | Strong editorial hierarchy, anchors or sections; no fake data cards |

Do not reuse one hero-plus-three-cards template for every request. Prefer one distinctive content
surface and one compact supporting module over many equal-weight cards.

## 2. Define the visual tokens

Choose 4–6 named color roles and provide light and dark values:

- canvas, opaque content surface, primary ink, secondary ink, accent, optional data colors.
- Use `color-scheme: light dark` and CSS `light-dark()` when supported.
- Use color as a supporting signal, never as the only carrier of meaning.
- A floating control may use one translucent/material treatment. Content surfaces stay readable and
  do not require blur.

Use the system font stack (`-apple-system`, `PingFang SC`). Build hierarchy with size, weight,
leading and alignment:

- metadata 12–13 px; body 15–17 px; section title 17–20 px; focal value 34–64 px;
- avoid thin or light weights for small text;
- use tight tracking only on large display numbers or short headings.

Use a 4 px spacing rhythm, 16–22 px page margins and responsive `min()/clamp()` sizing. All tap
targets are at least 44 px. Respect safe areas and keep the primary action reachable near the bottom.

## 3. Quality gate

Reject and rewrite the page if any of these are true:

- it is only a white page with a generic heading, textarea/input and blue button;
- every section is the same white rounded card with equal emphasis;
- it invents totals, goals, trends or categories the API does not provide;
- it uses placeholder lorem text, emoji as the main visual system, or a stock dashboard composition;
- loading, empty, error and success states collapse into the same blank screen;
- the form or fixed action is hidden by the keyboard, tab bar or home indicator;
- dark mode is merely inverted without checking separators, disabled states or data colors;
- user-provided text is inserted with unchecked `innerHTML`.

The minimum visual bar is: on the first screen, the user can identify the product, its most useful
current fact and the primary action without scrolling.

## 4. Build a real web application

Produce one complete HTML document with inline CSS and JavaScript.

- No framework, build step, module import, CDN, remote font, remote image, fetch, XHR, WebSocket,
  iframe, worker, service worker or external navigation.
- Keep it under 512 KiB and avoid large embedded assets.
- Use semantic buttons, explicit labels, visible focus and a logical reading order.
- Respect `prefers-reduced-motion`, `prefers-color-scheme` and increased contrast where practical.
- Never place credentials, access tokens, user IDs or Kit IDs in the page.
- Do not use `localStorage` or IndexedDB as the source of truth for synchronized data.

Use `textContent` and DOM construction for user data. Keep document text at least 11 px and normal
body copy at least 15 px. Prefer native controls over custom gesture-only interactions.

## 5. Connect data when needed

When the app stores records, pass fields to `kit_build`. The generated operations are:

- `items.create`: create one record using the exact field keys;
- `items.list`: list recent records;
- `summary`: return the current count.

Use only the injected schemas. The page calls:

```js
const result = await HymioKit.call("items.create", {
  field_key: "value"
});
```

The host adds identity and the current application. The page cannot choose a user or another app.
Handle a rejected call in-page; do not claim persistence before the promise resolves.

For a purely presentational app such as a breathing guide or reference page, omit `fields`.
Use local JavaScript freely, but expose no fake business operation.

## 6. A finished data app includes

- a purposeful loading state that preserves layout;
- a first-use empty state that invites the first record;
- a responsive record list or other direct view of saved data;
- inline write errors with a retry path that does not silently duplicate writes;
- an in-app success acknowledgement;
- light and dark appearance that both look designed, not default;
- safe-area-aware controls and keyboard behavior verified at 390 px width.

Do not invent analytics. If recent records support a derived chart, state the window and compute it
from the returned data. Label approximated or recent-only information.

## 7. Call the builder

Call `kit_build` with a concise name, a one-sentence promise, relevant category, visible item label,
accent, the complete `app_html`, and optional fields:

```json
{
  "name": "饮水记录",
  "tagline": "把今天的每一杯水记下来。",
  "description": "记录饮水量，并查看今天的累计进度。",
  "category": "生活",
  "item_label": "杯水",
  "accent": "blue",
  "app_html": "<!doctype html>...",
  "fields": [
    {"key":"amount","label":"杯数","type":"number","required":true}
  ]
}
```

The app is owned by the current user and installed immediately. When fields exist, the new
operations appear in context on the next model step. Do not request a catalog or operation list.

After creation, tell the user the visible application name and the useful next action. If they asked
you to use it immediately, call `kit_call` with the returned `kit_id` and one injected operation.
