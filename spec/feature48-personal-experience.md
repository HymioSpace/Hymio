# Personal experience and rendering performance

Status: Implemented

## Navigation and visual direction

Three native tabs: Now, Chat, Recollections (此刻、对话、回忆). Tasks and applications remain reachable inside My, plus pinned/recent application shortcuts on Home. My groups product tools, model/preferences, privacy/device access and diagnostics behind separate destinations. One shared menu button and one shared add button use the same sizes, material, stroke and accessibility labels. Haptics accompany deliberate selection and completed actions, never token arrival or polling.

Home is composed from approvals awaiting a decision, explicit user-facing reminders, meaningful recent outcomes, common applications and evidence-grounded inspirations. Missing modules collapse rather than showing fabricated content. The otter is a small brand anchor. No all-tasks inventory is duplicated on Home.

Multiple decisions form a horizontally paged carousel with a visible position and a complete decision list. Every count has a navigation path. A missing schedule has a quiet illustrated empty state and a real task entry, rather than a dash. My uses illustrated task/application shortcuts, a connector entry and readable preference rows; deeper configuration keeps platform controls. Generated artwork is bundled locally and reused without network image loading. The composer keeps attachment, multiline editor and send controls on a single bottom-aligned row, and the surrounding input surface focuses the editor.

## Task audience

An additive `for_user` boolean defaults false on creation and legacy records. User-facing reminders/schedules explicitly opt in; internal follow-ups remain false. API, CLI schema, prompt, editor and clients carry the same field. Home eligibility never infers audience from a title. Calendar remains the full task time workspace.

## Context presentation and ingestion

Technical device telemetry and health daily summaries are not human diary entries. Preserve original records and their permissions, but classify them separately from the default footprint feed. New connector records include readable summaries without external IDs in prose. Provider identity (Apple Health, Apple Calendar, Gmail, TickTick, chat, manual notes, applications) is separate from life/work categories and receives a distinct icon. Health collection is opt-in and useful high-level daily summaries remain available to authorized context tools, without flooding the diary or emitting identical updates on every sync. No automatic deletion of historical data.

## Performance and failures

Home and task destinations share one TaskBoard. Store a protected, account-and-deployment-scoped snapshot in the app cache, present it immediately on binding, and refresh in the background. Cache writes run off the main thread in order. Task deletion and suggestion dismissal remove items optimistically, roll back on failure, and invalidate older in-flight list responses so they cannot resurrect removed cards. A successful delete never fetches the deleted detail again. Detail updates and editor saves apply their returned task to the shared store.

Keep conversation receipt, reconciliation and durability independent of UI ticks. Bound streaming presentation work and limit scroll anchoring to actual visible content; no competing count/timer/geometry auto-scroll loops. No bottom placeholder may create an invisible screen of scroll range. Main tab hierarchy does not subscribe to token updates. Non-chat stores publish only actual changes; polling is foreground-scoped and bounded. Errors shown in product surfaces use user language; diagnostic details remain in the debug destination. WebSocket resumes on foreground/network recovery, with backoff; background suspension is expected on iOS and must not be presented as an unexplained failure.

## Streaming text and toolbar geometry

The jitter buffer controls output cadence; a separate native text renderer softens only the arriving edge with a brief Gaussian blur and opacity transition. Settled runs draw without a filter. Completed messages stop animating, and Reduce Motion shows clear text immediately. The active tail uses the same Markdown view before, during and after completion, avoiding a change from plain Text to a different layout engine. Draw settled run prefixes together; only the arriving edge needs individual glyph drawing.

Use a light 0.65-point blur and 160ms reveal, rather than a diffuse text cloud. A single native ScrollPosition maintains the bottom edge; no timer or repeated scroll animation competes with it. Manual scrolling detaches following until the user returns to the latest content. Track content height and scroll offset separately from display-frame gaps: a normal new-line advance is different from reverse movement or a completion layout shrink. Full decision lists use compact rows rather than reusing the hero card. Artwork uses individual subject centers because the source sheet is not an equally spaced sprite atlas.

Home module titles are primary text, not muted comments. A module presents its title, one useful item and an action; avoid duplicated status labels, decorative progress marks and explanatory paragraphs. Inspirations are optional and shown only from pending proposals carrying a dream identity and source record evidence. Do not seed a placeholder inspiration into Home, including its ordinary design fixture; no eligible proposal means no inspiration module.

Toolbar symbols have a balanced visible footprint inside a 44-point hit target. Custom circular add buttons use a 36-point visible surface and explicitly hide the system toolbar's shared background so two surfaces cannot overlap or clip each other. Review actual screenshots of every affected destination and record the real ChatScreen streaming path, rather than relying on a standalone text demo.

## Validation

Empty-state actions depend on the visible layer and its active filters, rather than whether any data exists elsewhere in the store. Only an empty understanding layer with available footprints offers “View footprints”; an empty footprints layer opens collection. Clear-filter actions reset source, category and query together. Regression checks must tap each action and verify the destination or visible records, including the source-filter recovery path.

Native preview fixtures use synthetic source labels and health examples. Capture interaction recordings, inspect frames and measure main-thread scheduling stalls in debug performance previews, explicitly distinguishing simulator measurements from device performance. Verify empty/populated/dark/large-text cases, navigation, keyboard, task audience and connector classification. Deploy backend and Web only after checks; iOS changes require a new signed/TestFlight build.
