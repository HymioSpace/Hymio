# Chat bubbles and native streaming reveal

User images and text share the trailing edge. The native attachment grid is intrinsically sized to one, two or three80pt columns, choosing the largest layout that fits; it no longer reserves256pt for a single image. Assistant prose regains a low-contrast rounded surface, with timestamps, reasoning and tools outside. Compact exploration remains unboxed.

Native live inline Markdown uses SwiftUI TextRenderer/TextAttribute to fade and deblur only a bounded tail; stable Markdown blocks retain their existing renderer. Reduced Motion and settled/history text remain immediate. Existing selection, links, completion buffering and Unicode boundaries must be retained. No protocol or server changes.

Research: Apple's WWDC24 Create custom visual effects with SwiftUI (TextRenderer/TextAttribute); Vercel's How we built the v0 iOS app. These are implementation references, not claims that Hymio now matches another product's perceived smoothness. Native simulator frame metrics and visual capture are required before delivery.

## Validation and limits

Web build/format and47 shared-client tests passed. Native Debug application build and38 Swift core tests passed, including Unicode extensions, large completion drain and final correction preserving the visible prefix. The native buffer now processes only the last grapheme and appended suffix, with backlog-adaptive pacing and the existing450ms completion deadline.

Actual iPhone17 Simulator previews use real MessageRow/Markdown views and DEBUG-only synthetic thumbnail data, without business API calls. Single-image and7-image right-edge layout inspected. Web reply surface measured rgb(240,243,248),14×18px padding and20/20/20/6px corners.

Native frame probe: first run646 frames,9 gaps over50ms, max194ms; repeat682 frames,7 gaps over50ms, max110ms. Both include startup/layout in a shared desktop Simulator environment. These results show remaining long frames; they do not establish60fps on physical devices or prove a quantified improvement against the previous build. A Simulator recording is provided for visual review; physical-device profiling remains necessary.

Sources: https://developer.apple.com/videos/play/wwdc2024/10151/ and https://vercel.com/blog/how-we-built-the-v0-ios-app . The rendering implementation uses native TextRenderer/TextAttribute; the React Native architecture in the v0 article is not transplanted into SwiftUI.
