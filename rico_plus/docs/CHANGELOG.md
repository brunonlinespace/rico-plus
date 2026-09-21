# Changelog

## 0.0.3 — 2026-09-21

- Canonical release closing the 0.0.3 experimental line.
- Mapped **Refresh Workspace** to **Ctrl+Shift+F5**.
- Renamed **Manage Workspaces…** to **Open / Manage Workspaces…** and moved it directly below Refresh Workspace.
- Renamed **Launch New Window…** to **New Window…**, retaining **Ctrl+Alt+Shift+N**.
- Added Suite-Pythoine-style touchscreen scrolling/panning to the main Dashboard.
- Applied `QScroller.TouchGesture` to the existing Dashboard scroll viewport, covering both List and Grid views.
- Deliberately left the folder tree and Folder Dashboard untouched.
- Reissued the supplied 0.0.4-r1 code state as 0.0.3; no additional functional change.

## 0.0.3-exp12-r1 — 2026-09-19

- Moved **Launch New Window…** directly below **Manage Workspaces…** in the Workspace(s) menu, with no separator between them.
- Assigned **Ctrl+Alt+Shift+N** to Launch New Window….
- No other functional change.

## 0.0.3-exp12 — 2026-09-19

- Restored Ricopad-style touchscreen panning on every Rico Plus Ribbon page.
- Ribbon page viewports now accept touch events and use Qt `QScroller` with `TouchGesture`, preserving normal stationary taps on buttons/selectors while finger drags pan horizontally.
- Retained horizontal mouse-wheel/trackpad panning, including wheel events received over Ribbon child controls.
- Ribbon contents, ordering, shortcuts, and application behavior are otherwise unchanged.

## 0.0.3-exp11-r3 — 2026-09-19

- Fixed the exp11-r1 startup regression by supplying **File Header** and **Focused Mode** actions to the shell Ribbon.
- Renamed the Insert Ribbon group **Tables & Lines** to **Tables**.
- Moved **Classics** to the end of the Insert Ribbon, after Tables.
- Added a release-gate contract that rejects any ShellRibbon action not supplied by MainWindow.
- No other functional change.

## 0.0.3-exp11-r1 — 2026-09-19

- Regrouped the Home/Insert/Configure Ribbon commands into the approved Advanced, Classics, Editor Settings, and Theme Settings layouts.
- Moved existing actions only; command behavior and shortcuts are unchanged.
- No non-Ribbon functional change.

## 0.0.3-exp11 — 2026-09-19

- Added dedicated **File Header**, **Focused Mode**, and **System Theme** Ribbon/AppMenu icons.
- Implemented each icon in both **Classic** and **New** Rico families, with matching Light and Dark variants.
- File Header follows the approved document-header concept, Focused Mode uses inward arrows, and System Theme uses the approved monitor/adaptive-theme concept.
- Added icons for the corresponding actions in the application menus.
- No other functional change.

## 0.0.3-exp10 — 2026-09-19

- Softened the explicit **Light** theme to the approved neutral-gray reference.
- Changed Light-theme primary surfaces to Window `#D4D4D4`, Base `#F4F4F4`, and Button `#E4E4E4`, retaining Rico brick `#B24A3B`.
- Left **System** and **Dark** themes unchanged.
- No other functional change.

## 0.0.3-exp9-r8 — 2026-09-19

- Moved **Focused Mode** immediately before **Locked Mode** in the View AppMenu.
- Retained the separator immediately after **Locked Mode**.
- No other functional change.

## 0.0.3-exp9-r7 — 2026-09-19

- Restored **F3** to **Find Next**; **Shift+F3** remains Previous Match.
- Remapped **Bullet List** from Ctrl+5 to **Ctrl+Shift+L**.
- Renamed **New Window** to **Launch New Window…**, removed its shortcut, and moved it between **Page Setup…** and **Exit** with separators before and after.
- Made the Keyboard Shortcuts catalogue complete by recursively collecting assigned AppMenu shortcuts, including nested formatting commands, and explicitly listing non-menu shortcuts.
- No unrelated functional change.

## 0.0.3-exp9-r6 — 2026-09-19

- Assigned **F3** to **New Window**.
- Removed F3 from the editor Find Next button to avoid shortcut ambiguity; Find Next remains available from the Find bar.
- No other functional change.

## 0.0.3-exp9-r5 — 2026-09-19

- Remapped **Font…** to **Ctrl+Shift+F**.
- Added **Ctrl+Shift+]** for **Increase Font Size**.
- Added **Ctrl+Shift+[** for **Decrease Font Size**.
- Added both font-size commands to the keyboard-shortcuts catalogue.
- No other functional change.

## 0.0.3-exp9-r4 — 2026-09-19

- Renamed **Show File Header** to **File Header**.
- Assigned **Ctrl+Alt+Shift+F** to toggle File Header.
- Removed the same shortcut from **Font…** to prevent shortcut ambiguity.
- No other functional change.

## 0.0.3-exp9-r3 — 2026-09-19

- Swapped the Ribbon positions of **Zoom In** and **Zoom Out**.
- No other functional change.

## 0.0.3-exp9-r2 — 2026-09-19

- Removed live word counting from the editor status bar to eliminate a full-document plain-text copy and regex scan on every edit.
- Reordered editor status to **Insert/Overwrite | percentage | Chars | flexible status message**.
- Retained fixed-width operation/zoom/character fields with reduced padding and a zero-minimum elastic message field.
- Normalized the runtime/desktop ID to `rico-plus`, matching `rico-plus.desktop` and `StartupWMClass=rico-plus`.

## 0.0.3-exp9-r1 — 2026-09-19

- Reordered the editor status bar to **Insert/Overwrite | Chars, Words | flexible status message | percentage**, with zoom fixed at the far right.
- Restored Dark Editor toggle feedback to the editor status message field.
- Routed App Theme feedback to the main Rico Plus status bar instead of the editor status bar.
- Retained exp9's fixed-width operation/counter/zoom fields and zero-minimum elastic message field.

## 0.0.3-exp9 — 2026-09-19

- Removed the full filepath from the editor status bar; the file header remains the path display.
- Changed the editor status layout to **Insert/Overwrite | Chars, Words | percentage | flexible status message**.
- Added a live word counter alongside the character count.
- Reserved stable widths for the operation-mode, counter and zoom fields using their longest supported display strings.
- Added a dedicated right-hand flexible status-message label with zero minimum width and ignored horizontal size hint so status messages cannot drive the window minimum width.
- Removed cursor-position-driven status updates because line/column values are no longer displayed.

## 0.0.3-exp8-r3 — 2026-09-19

- Renamed the application-level **Lock Editor** command to **Locked Mode** and **Collapsed Mode** to **Focused Mode**.
- Added the requested View-menu separator immediately after **Locked Mode**.
- Updated the active locked-document title suffix and status text to **Locked Mode** terminology.
- When a document is opened while Locked Mode is active, reset its cursor and vertical viewport to the top, matching Marko Plus behavior.
- Kept internal `view_only` / `collapsed_mode` implementation identifiers unchanged to avoid unrelated refactoring.

## 0.0.3-exp8-r2 — 2026-09-19

- Added Marko Plus-style F2 folder rename parity.
- F2 renames the active RTF document when editing, otherwise the selected/open workspace subfolder.
- The Workspace root remains protected from rename.
- Updated the shortcut catalogue to describe F2 as **Rename File or Folder**.
- Reused the existing safe folder rename implementation; no new filesystem rename path was introduced.

## 0.0.3-exp8-r1 — 2026-09-19

- Replaced **Keep My Version** with **Save Version As…** for externally changed open documents.
- The preservation branch now forbids the externally changed source path as a Save As target, so external work cannot be silently overwritten.
- The preservation dialog proposes a distinct `- Rico Version` sibling filename by default.
- A successful Save Version As preserves the external disk copy and rebinds the Rico Plus editor to the newly saved version.
- Cancelling or selecting the protected source path keeps the external-change warning active.
- Retained exp8's proactive watcher/repository detection and independent warning surface.

## 0.0.3-exp8 — 2026-09-19

- Restored proactive external-change warnings for open managed RTF documents.
- Reconnected repository change notifications to `EditorPage` and verify real changes with Ricopad's exact disk-content signature.
- Made Reload protect unsaved edits and Keep My Version acknowledge the current disk baseline.
- Kept the external-change warning independent of File Header/Collapsed Mode visibility.

## 0.0.3-exp7 — 2026-09-19

- Adopted Marko Plus's staged `ClosingDialog` shutdown workflow.
- Preserve unsaved-document handling before entering closing mode.
- Save Workspace/application state before scanner shutdown and keep Rico Collapsed Mode splitter restoration semantics.
- Hide the main application hierarchy while the responsive closing dialog reports preference save, scanner stop, and final exit stages.
- Restore the application if scanner cancellation does not complete.
- Added opt-in `RICO_PLUS_PROFILE_SHUTDOWN=1` timing diagnostics and a static clean-shutdown release check.
- No word-wrap, Ribbon taxonomy, editor, or RTF changes.

## 0.0.3-exp6-r3 — 2026-09-19

- Removed the dormant `RtfEditorWindow(QMainWindow)` implementation from production source; `RicopadEditorWidget(QWidget)` is now the sole Ricopad-derived editor host.
- Removed dead standalone-window registry/test-switch code and unreachable editor-owned Ribbon host handling left behind by the exp6 extraction.
- Retargeted callback/component QA to the live QWidget editor instead of comparing against an obsolete duplicate implementation.
- Preserved the current Plus shell, intentional Configure Ribbon taxonomy, workspace workflow, RTF codec, rich-text semantics, and New File behavior.
- Deliberately does not address word wrap or the staged closing workflow.

## 0.0.3-exp6-r2 — 2026-09-19

- Fixed the managed-editor startup crash caused by one surviving `self.embedded` read in `RicopadEditorWidget.apply_editor_canvas_theme()`.
- Rewrote stale workspace runtime assertions so they test the real QWidget editor component instead of removed `centralWidget`, `ribbon_tabs`, and `toolbar_stack` compatibility surfaces.
- Added release-gate coverage that fails if the managed widget regains the retired embedded-QMainWindow state.
- No Ricopad parsing, serialization, formatting, document-default, or editing semantics changed; the approved empty-paragraph/cell codec correction is unchanged.
- Rebased the managed editor path to `MainWindow -> EditorPage -> RicopadEditorWidget(QWidget)`.
- Removed the exp1-exp5 QMainWindow compatibility surface and dynamic method transplantation.
- Ported Marko Plus's `QToolBar` Ribbon overflow mechanism for narrow windows without changing Rico command grouping/order.
- Retained the approved horizontal sidebar scrolling correction.
- Retained the approved Ricopad empty-paragraph/cell codec correction and added an upstream backport patch.
- Added source parity QA for the extracted Ricopad editor behavior and a consolidated Lair/Marko/Ricopad/Rico alignment audit.


## 0.0.3-exp5 — 2026-09-19

- Fixed the exp4 New Document Defaults regression where newly created blank workspace RTFs reopened with the correct font family/size but lost paragraph alignment and line spacing.
- Corrected the RTF importer so empty paragraphs/cells snapshot the paragraph state at completion instead of retaining the earlier `\pard` baseline.
- Preserve the blank paragraph typing signature on import, so Bold/Italic and other character defaults survive even when there is no text run.
- Added a Qt-backed regression for the exact generated-blank-document reopen path: 18 pt, Bold Italic, 1.5 spacing, Centre alignment.
- Kept exp4's programmatic New File generation; no bundled template dependency was reintroduced.

## 0.0.3-exp4 — 2026-09-19

- Removed the workspace New File dependency on `assets/templates/default-document.rtf`.
- New workspace RTF files are generated programmatically from Ricopad New Document Defaults using a shared pure document-domain factory.
- Ricopad's editor-side generated template path and Rico Plus workspace creation share the same RTF payload builder.
- Missing or corrupt editor preferences fall back to Ricopad's built-in defaults; deleting the bundled factory RTF cannot disable workspace New File.
- Added a non-Qt regression suite for payload generation. This test proved insufficient on its own because it did not reopen the blank RTF through the actual importer; exp5 adds that missing regression.

## 0.0.3-exp3 — 2026-09-18

- Rebased both `MainWindow` and `EditorPage` onto the established Plus-family ownership pattern rather than retaining the exp2 thin-wrapper seam.
- MainWindow now uses the Plus-style `_command()` / `_editor_call()` boundary and has no access to `page.engine` or other Ricopad implementation internals.
- Rebuilt EditorPage as the managed-document owner: file heading, dirty state, load/save/close lifecycle, external-change surface, managed preferences and command adaptation now live at the page layer.
- Kept `RicopadEditorSurface(QWidget)` private to EditorPage; managed pages still never instantiate `RtfEditorWindow(QMainWindow)`.
- Retained exp2's event-filter correction for drag/drop/New File construction, the zero-minimum editor geometry, removed duplicate Ricopad gutter, folder-tree horizontal overflow, and Lock Editor title suffix.
- Added a static regression contract that rejects MainWindow reach-through into Ricopad internals.

## 0.0.2-r1 — 2026-09-18

- Unified **Show Status** so it controls both the Rico Plus shell status bar and the embedded Ricopad editor status bar.
- Added persistent **Show File Header** as the first View → Editor Miscellaneous option, followed by a separator.
- Added AppMenu-only **Collapsed Mode** (`F10`) directly below Lock Editor. It temporarily hides Status, Sidebar and the file header and reuses the existing Ribbon double-click collapse behavior, then restores the prior independent view states when disabled.
- The Ribbon command layout itself is unchanged.

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
