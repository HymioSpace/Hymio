# Personal experience and rendering performance

Status: Implemented

## Navigation and visual direction

Three native tabs: Now, Chat, Recollections (此刻、对话、回忆). Tasks and applications remain reachable inside My, plus pinned/recent application shortcuts on Home. My groups product tools, model/preferences, privacy/device access and diagnostics behind separate destinations. One shared menu button and one shared add button use the same sizes, material, stroke and accessibility labels. Haptics accompany deliberate selection and completed actions, never token arrival or polling.

Home is composed from approvals awaiting a decision, explicit user-facing reminders, meaningful recent outcomes, common applications and evidence-grounded inspirations. Missing modules collapse rather than showing fabricated content. The otter is a small brand anchor. No all-tasks inventory is duplicated on Home.

## Task audience

An additive `for_user` boolean defaults false on creation and legacy records. User-facing reminders/schedules explicitly opt in; internal follow-ups remain false. API, CLI schema, prompt, editor and clients carry the same field. Home eligibility never infers audience from a title. Calendar remains the full task time workspace.

## Context presentation and ingestion

Technical device telemetry and health daily summaries are not human diary entries. Preserve original records and their permissions, but classify them separately from the default footprint feed. New connector records include readable summaries without external IDs in prose. Provider identity (Apple Health, Apple Calendar, Gmail, TickTick, chat, manual notes, applications) is separate from life/work categories and receives a distinct icon. Health collection is opt-in and useful high-level daily summaries remain available to authorized context tools, without flooding the diary or emitting identical updates on every sync. No automatic deletion of historical data.

## Performance and failures

Keep conversation receipt, reconciliation and durability independent of UI ticks. Bound streaming presentation work and limit scroll anchoring to actual visible content; no competing count/timer/geometry auto-scroll loops. No bottom placeholder may create an invisible screen of scroll range. Main tab hierarchy does not subscribe to token updates. Non-chat stores publish only actual changes; polling is foreground-scoped and bounded. Errors shown in product surfaces use user language; diagnostic details remain in the debug destination. WebSocket resumes on foreground/network recovery, with backoff; background suspension is expected on iOS and must not be presented as an unexplained failure.

## Validation

Native preview fixtures use synthetic source labels and health examples. Capture interaction recordings, inspect frames and measure main-thread scheduling stalls in debug performance previews, explicitly distinguishing simulator measurements from device performance. Verify empty/populated/dark/large-text cases, navigation, keyboard, task audience and connector classification. Deploy backend and Web only after checks; iOS changes require a new signed/TestFlight build.
