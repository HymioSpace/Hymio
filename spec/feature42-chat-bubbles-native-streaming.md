# Chat bubbles and native streaming reveal

User images and text share the trailing edge. The native attachment grid is intrinsically sized to one, two or three80pt columns, choosing the largest layout that fits; it no longer reserves256pt for a single image. Assistant prose regains a low-contrast rounded surface, with timestamps, reasoning and tools outside. Compact exploration remains unboxed.

Native and Web live prose use a single paced presentation layer. The shared buffer estimates incoming graphemes per second and inter-arrival jitter, smooths the release rate, keeps a short reserve and accelerates only after genuine backlog or silence. Web updates on animation frames; native updates a plain Text tail every16ms while content is pending. Stable Markdown blocks retain their existing renderer. Reduced Motion and settled/history text remain immediate. Existing links, completion buffering and Unicode boundaries must be retained. No protocol or server changes.

Research: Apple's WWDC24 Create custom visual effects with SwiftUI (TextRenderer/TextAttribute); Vercel's How we built the v0 iOS app. These are implementation references, not claims that Hymio now matches another product's perceived smoothness. Native simulator frame metrics and visual capture are required before delivery.

The first native reveal prototype used TextRenderer with a6px deblur frontier, later reduced to1.5px. Follow-up review showed that even the smaller blur read as a dark moving edge, and the custom per-grapheme drawing plus a second opacity animation made irregular event cadence look like stutter. Web had the same double animation: paced buffer updates followed by per-grapheme spans and blur. Both client implementations now animate only the buffer frontier. No blur is applied to live text, so wrapping and settled content stay geometrically stable.

## Validation and limits

Web build/format and48 shared-client tests passed. Native Debug application build and39 Swift core tests passed, including Unicode extensions, large completion drain, irregular-arrival pacing and final correction preserving the visible prefix. The buffer processes only the last grapheme and appended suffix, with adaptive pacing and the existing450ms completion deadline.

Actual iPhone17 Simulator previews use real MessageRow/Markdown views and DEBUG-only synthetic thumbnail data, without business API calls. Single-image and7-image right-edge layout inspected. Web reply surface measured rgb(240,243,248),14×18px padding and20/20/20/6px corners.

Synthetic buffer traces cover steady 80ms deliveries, 240ms batched deliveries, an irregular40/80/360/40/160/280ms cadence and a deliberately slow400ms cadence. The irregular trace updated visible text at a32ms p95 with a160ms maximum gap on Web; native's equivalent unit trace measured176ms maximum. The slow trace remains event-limited: two characters per400ms allows only two visible updates and measured a224ms p95 with a288ms maximum. This is not a frame-time or physical-device smoothness claim.

Sources: https://developer.apple.com/videos/play/wwdc2024/10151/ and https://vercel.com/blog/how-we-built-the-v0-ios-app . The final renderer deliberately does not use TextRenderer; the React Native architecture in the v0 article is not transplanted into SwiftUI.

The old per-grapheme renderer required disabling live-tail selection to keep custom drawing active and still produced long cold-path frames. The simplified live tail preserves the parent Copy action; completed/stable Markdown remains selectable. Opening a closing Markdown block still settles existing text without replaying it. Physical-device profiling remains outstanding.
