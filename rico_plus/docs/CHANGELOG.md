# Changelog

## 0.0.2 — 2026-09-17

- Disable Symbol while Lock Editor is active.
- Regroup Keyboard Shortcuts by AppMenu menu and relabel Tab to Menu while keeping All.
- Align the runtime desktop-file identity with Suite Pythoine so the active instance is identified as Rico Plus.

## 0.0.1-r10 — 2026-09-17

- Remapped Ctrl+Shift+N from New Window to New Folder.
- Reimplemented the Rico Plus About dialog on the authoritative Ricopad Pad-family presentation.
- Restored the Rico Plus repository line at the top of About details, the brunonlinespace GitHub profile line, and the Configuration label.
- Updated the slogan to “Friendly. Fast. Focused.”

## 0.0.1-r9 — 2026-09-17

- Corrected the r8 Dark Editor regression by copying Marko Plus's single-owner follow/override contract: managed editors follow App Theme until Dark Editor is explicitly used, then the chosen canvas state persists independently.
- Prevented embedded Ricopad's standalone `editor_canvas_theme` preference from competing with the Rico Plus preference during file loads and other internal canvas refreshes.
- Removed the invented permanent `palette(highlight)` QSS border from r8.
- Preserved the requested always-visible editor outline using Qt's native focus-frame primitive, so the platform/Breeze focus treatment supplies the same dimmer appearance instead of a hard-coded colour.
- No Ribbon, appmenu, shortcut, workspace, RTF, icon-set, or file-heading changes.
## 0.0.1-r7 — 2026-09-17

- Rebuilt the first-time Tutorial Wizard in the established Marko Plus / Ricopad wizard style.
- Added dedicated Rico-family Light Theme, Dark Theme, Classic Icons, and New Icons artwork in light/dark variants.
- Applied the requested Configure Ribbon Theme Settings and Editor Settings ordering.
- Added Marko Plus-style editor-theme synchronization: the canvas follows App Theme until Dark Editor is explicitly used, after which the editor-only override persists.

## 0.0.1-r6 — 2026-09-17

- Fixed Plasma global-menu ownership across Dashboard/editor transitions by removing the embedded Ricopad `QMenuBar` object entirely.
- Corrected `My Nest` to `My Workspace`.
- Made Lock Editor application-wide and persistent across files/sessions; relabeled View Only menu/Ribbon references accordingly.
- Restored the specified shortcut map: Ctrl+Alt+Shift+D List/Grid toggle, Ctrl+D Duplicate Line / Selection, Ctrl+Shift+D Duplicate File, Ctrl+Shift+S Save and New.
- Applied the specified File/Workspace/More Actions/View appmenu ordering and wording without changing unrelated menus.

## 0.0.1-r5-r1 — 2026-09-17

- Explicit native/global-menu request on the one authoritative Plus menu bar.
- Restored New Window to appmenu/Ribbon; Properties now uses F4.
- Restored shortcut-bearing Ribbon hover tooltips from live QAction bindings.
- Applied the approved File and Configure Ribbon matrices exactly.
- Moved Find Bar into View > Editor Miscellaneous before Tab Width / New Document Defaults, with the requested separator placement.
- Re-aligned residual embedded-editor shortcut definitions with Ricopad authority where the Plus shell already owned the correct runtime binding.

## 0.0.1-r5 — 2026-09-17

- Fixed startup failure caused by `new_folder_action` being referenced by the restored Ribbon but omitted from the shell action dictionary passed to `ShellRibbon`.
- No UI, shortcut, wording, layout, asset, workflow, or editor-behavior changes beyond this startup wiring correction.

## 0.0.1-r5 — 2026-09-17

- Corrective no-opportunistic-changes rebase from r4-r1.
- Re-established Ricopad as authoritative for RTF Ribbon layout, wording, shortcuts, tooltips, icon semantics and View Only behavior.
- Kept Marko Plus authority limited to managed Workspace/shell behavior.
- Removed transplanted Marko toolbar assets and their fallback path.
- Added dedicated Rico-family assets only for genuinely Plus-specific shell commands.
- Restored Settings submenu icons, including App Theme and App Icons.
- Hardened the application menu path to match the authoritative Marko Plus QMenuBar pattern (no forced non-native menu, no startup clear, explicitly shown).
