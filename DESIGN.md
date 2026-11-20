# Hymio Material Design 3 direction

Status: recommended defaults applied; review together with the next TestFlight build.

## Product constraints

- Consumer mobile app first, with Web/Tauri desktop as adaptive layouts.
- One-thumb use, plain-language status, no raw implementation details in primary views.
- Existing Hymio blue remains the source color; Material purple is not introduced.
- Native iOS behavior stays intact. Roboto and the Material Symbols font are not bundled yet,
  so iOS uses the system typeface and the closest native symbol variants.

## Material decisions

- Scheme: Material 3 tonal-spot, standard contrast, generated from Hymio blue `#425DE8`.
- Roles: primary, primary-container and the full surface-container hierarchy. Cards use tonal
  surfaces and outlines before shadows; elevation is reserved for dialogs, menus and transient bars.
- Shape: chips and navigation indicators are full-round; cards use 12pt; dialogs and sheets use
  28pt; icon buttons retain a 48pt touch target.
- Typography: Material role sizes mapped to the platform system font (SF Pro on iOS,
  system UI on Web) until branding requires a bundled font.
- Compact navigation: three-destination Material navigation bar. Medium and expanded Web layouts
  use a navigation rail. Primary destinations are Today, Chat and My. The compact navigation body is
  56pt high above the system safe area, with 46pt minimum item targets.
- Motion: 100-300ms standard/emphasized transitions, with reduced-motion respected.
- Icons: native SF Symbols on iOS and Lucide on Web are temporary platform-compatible exceptions;
  they use Material sizes and selected/unselected/filled states.
- Accessibility: visible focus rings on Web, 48pt minimum targets, paired on-role colors,
  reduced transparency/motion support, loading, empty and error states.
- Agent detail uses one continuous tonal surface with section dividers instead of nested cards.
  Responsibilities, completion criteria, collaboration, timeline and tool records have distinct
  hierarchy without repeating labels or raw workflow metadata.
- A terminal Live Activity stops its timer and dismisses immediately. Completion may not preserve a
  running clock or remain on the Lock Screen after the accepted work has ended.

## Migration scope

1. App shell and navigation.
2. Today, Chat and My primary screens.
3. Tasks, Memories, Connections and Settings subpages.
4. Shared dialogs, sheets, buttons, chips, fields and list rows.

The token layer is shared even while existing screens migrate incrementally.
