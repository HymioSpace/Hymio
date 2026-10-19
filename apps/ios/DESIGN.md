# Hymio iOS — design direction

A quiet place to talk to one agent that stays with you. The line companion supplies personality;
reading and typing remain the main actions. Native navigation, sheets and controls supply familiarity.

## What changes

The initial MVP had a slab behind the input, static character poses, an oversized profile tint,
and fixed light-only colors. Use a floating input surface, restrained monochrome navigation,
a companion with breathing/blinking/greeting motion, and adaptive colors. Remove decorative controls
that have no working capability. Keep the app to one conversation and account details.

## Tokens

| Role | Light | Dark | Contrast against white / black |
| --- | --- | --- | --- |
| Primary content | #172033 | #EFF2FA | 16.27 / 18.75 |
| Action / status | #425DE8 | #9AABFF | 5.30 / 9.64 |
| Secondary content | #606A7A | #A4ABBA | 5.47 / 9.11 |
| Content fill | #F4F5F9 | #1D202A | Not used as text |
| User message | #F0F2FB | #242B43 | Primary content above |
| Background | System background | System background | Adaptive |
| Companion bridge | #4A6BFA | #4A6BFA | Illustration only |

SF rounded display text gives the greeting a soft voice. Body, captions and navigation use semantic
system text styles and Dynamic Type. Primary controls provide a 44-point touch region. Increased
contrast and Reduce Transparency replace the custom glass input with an opaque outlined surface.

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

- Companion: low amplitude breathing, brief blink, occasional small hand greeting; active foreground only.
- Send: immediate press feedback and selection haptic after the command is saved.
- Replies: short spring on message insertion, never animate individual tokens or force a reader off history.
- Account: system zoom transition starts at the profile control; swipe dismissal remains native.
- Reduce Motion: static companion, no custom insertion spring or profile zoom. No feature depends on animation.

## References and interpretation

- [Meet Liquid Glass](https://developer.apple.com/videos/play/wwdc2025/219/): material distinguishes floating controls from readable content. Use it on the input and native navigation, not message cards.
- [Build a SwiftUI app with the new design](https://developer.apple.com/videos/play/wwdc2025/323/): the Landmarks sample demonstrates continuity from a source control into its presented sheet. Apply that continuity to the account button.
- [Advanced SwiftUI animations](https://developer.apple.com/videos/play/wwdc2023/10157/): motion should express state and interaction. Keep recurring motion confined to the companion rather than the entire screen.
- [Apple Design Awards 2025](https://developer.apple.com/design/awards/2025/): Lumy's restrained palette and CapWords' responsive playfulness are references for the balance of calm and personality; no screens or assets are copied.

Reviewed with the community `dickwu/apple-design-skill` and its HIG references: accessibility,
layout, typography, color, iOS, buttons, motion, materials, Liquid Glass and sheets. The skill is
installed locally and is not an app dependency or an Apple-endorsed product.
