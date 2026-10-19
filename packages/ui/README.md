# Hymio UI

Shared presentation components for Web, Tauri and future Chrome surfaces. No network, credentials, storage or product workflows live here. Native iOS follows these roles in `apps/ios/Hymio/Views/DesignSystem.swift` and uses SwiftUI controls.

## Use

```tsx
import { Button, IconButton, Sheet, StatusBadge, Companion } from '@hymio/ui';

<Button variant="primary" busy={saving} onClick={save}>保存</Button>
<IconButton label="关闭" onClick={close}>×</IconButton>
<StatusBadge tone="active">已连接</StatusBadge>
<Companion mood="working" compact />
```

Styles and tokens load through the package entry. Render `Sheet` conditionally with `labelledBy` pointing to a visible heading and `onClose` removing it. It uses native dialog focus containment and restores focus on unmount. Buttons default to `type="button"`; use `type="submit"` in forms.

| Component | Contract |
| --- | --- |
| Button | primary / secondary / quiet / danger; busy disables repeated activation |
| IconButton | mandatory accessible label; normal HTML button attributes |
| StatusBadge | neutral / active / attention; always includes text |
| Sheet | native dialog, Escape and backdrop dismissal, viewport-limited scrolling |
| Companion | idle / working / replying / waiting / offline; compact avatar; short greeting on click |

## Foundations

Tokens are defined in `src/tokens.css`; light and dark roles match iOS. Body uses system fonts, data uses system monospace. Spacing follows 4pt increments. Control/input/panel radii are 12/20/24. Minimum mobile button targets are 44px. Primary actions use accent with on-accent, never an assumed white foreground in both appearances.

| Role | Light | Dark |
| --- | --- | --- |
| surface | #FFFFFF | #161923 |
| ink | #202536 | #EFF1F7 |
| muted | #626B7D | #A7AFC1 |
| accent (`blue`) | #425DE8 | #A2B0FF |
| on-accent | #FFFFFF | #18214A |
| line | #E6E8EF | #353B4B |
| subtle | #F6F7FA | #202530 |
| pale | #EEF1FF | #28314A |

The character is a half-body ivory otter with small navy ears, restrained facial marks and a flowing blue scarf. Thin navy contours and generous negative space keep the portrait light and legible.

Web and iOS bundle the same transparent 3 × 2 atlas: idle / working / replying on the first row; waiting / offline / greeting on the second. The master is `src/assets/companion-atlas.png`; keep the native `CompanionAtlas.imageset` copy byte-identical. Welcome screens show the half-body portrait; history avatars use the same quiet portrait without a circular crop. Large figures have lightweight state motion and a brief greeting. Background and reduced motion pause movement. This is rendered artwork with simple animation, not a live 3D model. Text remains the status source.

## Design studio

Start the client development server and open `/design.html`. This separate Vite entry shows the character, layout sketches, tokens, controls and a working dialog using synthetic content. It is not included in the default production app build. Do not place private conversation fixtures or account tokens in the gallery.

Keep business-specific components (approval actions, device manager, live conversation) in the app. Promote reusable presentation only when it is used, rather than adding unavailable features to navigation.
