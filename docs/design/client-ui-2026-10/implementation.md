# Client UI refinement: implementation and validation

## Delivered

- Sent images wrap into aligned 80px/pt thumbnails on Web and iOS.
- Budget pauses collapse the latest exploration and expose Continue through the existing message channel; draft text is preserved.
- Removed star-map screens and entry points; source evidence and backend APIs remain available.
- Reduced repeated decoration in conversation, home and memory lists; retained the existing sea-otter account identity and native navigation.
- Added four semantic background layers, focus shadows, numeric alignment and timed copy feedback. Web also uses accessible grid disclosures, dark font-weight offsets and grapheme streaming animation.

The ten interaction requirements and the explicit SwiftUI limitations are documented in [feature41](../../../spec/feature41-interaction-finish.md). CSS-specific behavior is not claimed as native implementation.

## Local validation (2026-10-27)

- Web production build passed; existing main-chunk size warning remains.
- Shared client: 45 tests passed, including budget pause/resume regression.
- Swift core: 37 tests passed, including paused events and turn grouping.
- iOS Simulator Debug application build passed with signing disabled.
- Web Prettier check and git diff whitespace check passed.
- Browser inspection of actual components: focus rings 2px/6px; closed disclosure height 0 with inert content; dark body weight 360; streaming duration 120ms, stagger 30ms and blur 6px; copy feedback resets after 2500ms.

Native keyboard, Dynamic Type, VoiceOver and physical-device interaction remain manual acceptance items. Simulator compilation is not device acceptance. The development-only craft-review.html uses synthetic content and is not a production navigation entry.

## Rollout

Only the Web edge image is deployed to mono-dev. Backend, Oath, persistent data and configuration remain pinned. iOS is delivered as source in the PR; it is not distributed through this cloud rollout. Keep the PR open for review.

## Follow-up acceptance (2026-10-28)

- Thumbnail loading/failure states now retain an 80×80 slot on both clients; Web retry targets measure 44×44. Seven failed fixtures in a 280px container form aligned 3/3/1 rows.
- Pause notices and Continue no longer compete for one line: Web wraps and native iOS stacks the action beneath the reason.
- Native memory rows suppress summaries identical to the title; source/date metadata uses a vertical fallback rather than truncation. Verified in the actual iPhone 17 Simulator application, dark appearance and accessibility3 text size, using synthetic preview data.
- Web build, format and 45 shared-client tests pass; iOS application build passes. This does not replace physical-device/VoiceOver acceptance.

## Long-output performance (2026-10-28)

Web TextBuffer previously resegmented the whole cumulative string on every delta, rebuilt every visible prefix on reads, and capped catch-up at180 graphemes/sec without a completion drain. A synthetic 50k UTF-16-unit stream took43520ms to finish displaying after input stopped.

The buffer now resegments only the trailing cluster plus new delta, caches the visible prefix, scales catch-up with backlog, and drains completion within450ms. Hooks stop idle tickers. MotionText renders history as plain text and limits its active tail to32 graphemes plus a bounded Latin-word boundary; very long unbroken tokens remain plain. Blur remains6px over120ms, with30ms phases in four bounded waves (0/30/60/90ms), rather than accumulating delay across a burst.

Reproduce the buffer microbenchmark with `node --experimental-strip-types packages/client/scripts/presentation-benchmark.mjs`. Same local workload: 2k/10k/50k tail drain changed from1952/8864/43520ms to320/288/320ms. CPU measurements vary; one50k sample changed from411ms to22ms. These are buffer microbenchmarks, not end-to-end model latency measurements.

Actual MessageView/Markdown browser fixture completed70499 visible characters, with exact normalized rendered text including combining accents and family emoji. At48268 characters,32 animated spans were observed; on completion, zero remained. Unicode cross-delta and completion regressions added;47 shared-client tests and Web build pass.

Read-only mono-dev snapshot: load0.70/0.45/0.45,1212MiB available, backend CPU3.46%, worker0.78%; host-local health requests21–46ms. Swap occupancy alone is not proof of current pressure. No user conversation bodies or credentials exported. These samples do not establish model/token transport latency; native Markdown rendering still needs separate profiling. No backend/Oath tuning was applied based on this snapshot.
