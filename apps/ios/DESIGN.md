# Hymio iOS — design direction

A quiet place to talk to one agent that stays with you. The blue-scarf companion supplies personality;
reading and typing remain the main actions. Native navigation, sheets and controls supply familiarity.

## Shared foundations

The Web/Desktop and native clients share semantic color roles, action hierarchy and character artwork. Web components live in `packages/ui`; SwiftUI uses `DesignSystem.swift`. See [the shared design guide](../../packages/ui/README.md) and [feature15](../../spec/feature15-unified-design.md).

The character is a half-body ivory otter with small navy ears, delicate contours and a flowing blue scarf. Web and iOS bundle an identical transparent 3 × 2 state atlas. Welcome screens and small avatars use the same half-body portrait, retaining the ears and scarf for recognition. This is rendered artwork, not a live 3D model. Scene state selects a static pose; no continuous animation runs.

System text styles provide Dynamic Type. Primary controls provide a 44-point touch region. Primary actions use `Brand.blue` with `Brand.onAccent` in both appearances. Increased contrast and Reduce Transparency replace the floating glass input with an opaque outlined surface. No unavailable feature receives a navigation button.

## Layout

Compact iPhone: one text column, assistant avatar column and trailing user bubbles.
Wider iPhone: same hierarchy with extra line length; no dashboard or second column.

```text
            hymio                     account
          connection

          companion                   [empty only]
          嗨，我在。
          想到什么，就和我说说。

 avatar   readable response
                   user message

       [ message input       ↑ ]      floating control
```

## Motion

- Companion: static artwork only; mood changes swap the pose without a running animation.
- Send: immediate press feedback and selection haptic after the command is saved.
- Replies: short spring on message insertion, never animate individual tokens or force a reader off history.
- Account: system zoom transition starts at the profile control; swipe dismissal remains native.
- Reduce Motion: static companion, no custom insertion spring or profile zoom. No feature depends on animation.

## Notifications and Live Activities

Notifications are quiet doorbells, not a second inbox. Lock-screen text defaults to a neutral
summary; task titles are opt-in. The app never repeats a foreground event as a banner. Permission
is requested only after the user schedules or starts work that outlives the current screen.

The Live Activity uses one recognizable signature: a small blue-scarf wave mark beside a continuous
time readout. Its background is a deep navy-to-blue field with three discrete stage segments, never
a fabricated percentage. Waiting uses an amber raised-hand glyph, failure uses a red exclamation
glyph, and completion uses a mint checkmark; every state also has a text label for VoiceOver.

Compact presentations keep only the wave or status glyph and elapsed time. The limited-width
Dynamic Island uses a single 28-point-safe glyph. Expanded and Lock Screen presentations add the
current human phase and a short action line. System text styles, 14-point Lock Screen margins and
semantic foreground colors preserve Dynamic Type and reduced-luminance legibility.

## References and interpretation

- [Meet Liquid Glass](https://developer.apple.com/videos/play/wwdc2025/219/): material distinguishes floating controls from readable content. Use it on the input and native navigation, not message cards.
- [Build a SwiftUI app with the new design](https://developer.apple.com/videos/play/wwdc2025/323/): the Landmarks sample demonstrates continuity from a source control into its presented sheet. Apply that continuity to the account button.
- [Advanced SwiftUI animations](https://developer.apple.com/videos/play/wwdc2023/10157/): motion should express state and interaction. Keep recurring motion confined to the companion rather than the entire screen.
- [Apple Design Awards 2025](https://developer.apple.com/design/awards/2025/): Lumy's restrained palette and CapWords' responsive playfulness are references for the balance of calm and personality; no screens or assets are copied.

Reviewed with the community `dickwu/apple-design-skill` and its HIG references: accessibility,
layout, typography, color, iOS, buttons, motion, materials, Liquid Glass and sheets. The skill is
installed locally and is not an app dependency or an Apple-endorsed product.
