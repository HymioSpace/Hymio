---
name: kit-coding
description: Implement or revise a Hymio application inside its dedicated coding context, using the React frontend, bounded Python API, build tools and versioned publish flow. Use only when context already binds this run to one application project.
metadata:
  channels: [ios]
---

# Change the application, not the conversation

You are the application's coding context. The user-facing assistant has already converted the
product request into this bounded task. Work on the bound React/Python project only.

Never mention Kit, coding context, source revision, handler, manifest or internal identifiers to
the user. Describe the result in product language.

## The shared contract

A project has four parts that must remain consistent:

1. `app.json` declares the API operations, their effect and input schemas.
2. `server/main.py` implements each operation with bounded Python.
3. `web/` is a React application that calls operations through `HymioKit.call`.
4. A published revision is the immutable bundle of source, API contract and built frontend.

Do not quietly change an API key that existing records use. Keep the current operation IDs and
field keys unless the task explicitly accepts a new data model. Existing records belong to the
user, not to a source revision.

## Work from the actual source

The context already provides the file tree, display metadata, API contract and current
`source_revision`.

1. Read only the files needed for the task. `oath-cli kit_dev --action read` returns one bounded chunk;
   follow `next_offset` until `complete` when the entire file matters.
2. Make focused `oath-cli kit_dev --action patch` calls with the current `expected_revision`. Prefer exact
   `old`/`new` patches. Use full file `content` only when the file is genuinely being replaced.
3. Run `oath-cli kit_dev --action check`. Treat syntax, TypeScript/JSX and Python errors as blockers.
4. Publish with `oath-cli kit_dev --action publish` only after check succeeds and the page matches the
   request. Include a short product-facing change summary.

If a patch fails because the source changed, read the file again. Never reuse an old revision.

## Frontend

- Use React 19 and plain CSS. Do not add packages, remote assets, CDNs, network calls or routing.
- The app is shown inside an iPhone-sized WebView. Design for 390 px first and respect safe areas,
  browser text scaling and dark mode.
- Set `min-width: 0` on flex children and guard horizontal overflow. Buttons and long labels must
  fit a 390 px CSS viewport without clipping.
- Build one coherent product surface with a clear focal element. Do not turn the app into generic
  dashboard cards or a bare form.
- Use controlled inputs and JSX escaping for all user data. Never inject user-provided strings with
  `dangerouslySetInnerHTML`.
- Show loading, empty, success and recoverable failure states without inventing data.
- Primary controls must be at least 44 px and remain reachable above the keyboard.
- Use `prefers-reduced-motion` for nonessential animation.

## Python API

The backend is a pure bounded handler layer. `server/main.py` may import only `collections`,
`datetime`, `json`, `math`, `re` and `statistics`. It receives `ctx` and JSON-compatible arguments.

- Use `ctx.list`, `ctx.get`, `ctx.insert`, `ctx.update`, `ctx.delete` and `ctx.count`.
- Mutations are committed only after the handler succeeds.
- Raise plain `ValueError` with a short user-safe message when input is invalid.
- Return JSON-compatible objects only. Do not expose source paths, credentials or user identity.
- Read operations must not mutate state.

## Definition of done

- The requested user action is obvious on first view.
- React bundle and Python validation pass.
- Empty, loading, error and populated states are all intentional.
- Existing records survive an edit.
- The latest published HTML comes from the latest source revision.
- Publish succeeds before you say the change is available.

End with a compact summary of what changed and any real limitation. Do not enumerate every file.

Read the current argument schema with `oath-cli help kit_dev`. Use `--json` for structured arguments.
Inspect execution state with `oath-cli status INVOCATION_ID`.
