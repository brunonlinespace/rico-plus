# Rico Plus Project Memory

## Identity

- Product: Rico Plus 0.0.3
- Toolkit: Python 3 and PyQt6
- exp12 restores Ricopad-style touchscreen Ribbon panning through Qt `QScroller.TouchGesture`; stationary taps remain ordinary button/selector taps, while finger drags pan horizontally.
- exp10 softens the explicit Light application palette to the approved neutral-gray reference: Window `#D4D4D4`, editable Base `#F4F4F4`, Button `#E4E4E4`, with the Rico brick accent retained. System and Dark themes are unchanged.
- exp9-r7 restores **F3** to Find Next, maps **Ctrl+Shift+L** to Bullet List, moves unbound **Launch New Window…** between Page Setup and Exit, and makes the Keyboard Shortcuts catalogue recursively complete (including nested formatting shortcuts).
- exp9-r6 assigns **F3** to **New Window**; Find Next remains available from the Find bar without F3.
- exp9-r5 maps **Font…** to **Ctrl+Shift+F**, **Increase Font Size** to **Ctrl+Shift+]**, and **Decrease Font Size** to **Ctrl+Shift+[**.
- exp9-r4 renames **Show File Header** to **File Header** and assigns **Ctrl+Alt+Shift+F** to toggle it; the shortcut is removed from the shell Font action to avoid ambiguity.
- exp9-r2 removes the expensive live word counter, reorders editor status to Insert/Overwrite | percentage | Chars | flexible message, and normalizes runtime/desktop identity to `rico-plus`.
- Document format: `.rtf` only
- Repository: https://github.com/brunonlinespace/rico-plus
- License: GPL-3.0-or-later
- Accent: Rico brick `#B24A3B`

The official logo uses a lifted white page exposing a Breeze-blue plus beneath
it. The two approved command-icon families are Rico Icons Classic and Rico
Icons New.

## Product boundary

Rico Plus is a workspace-scale rich-text application. It uses the Plus-family
workspace shell and the Ricopad RTF engine. The editor uses the Ribbon only;
there are no transferable document layouts or alternate editor chrome.

## Invariants

- No-argument startup opens the Dashboard and creates no file.
- New document creation belongs to Rico Plus, even when initiated by Suite.
- New files are complete valid RTF payloads, never empty placeholders.
- `Ctrl+O` opens workspace management.
- Dashboard cards offer Open and View Only only.
- External OS-open files remain external and transient.
- Explicit external drag-and-drop remains an import workflow.
- Save/reopen must preserve deliberate spaces at formatting and list boundaries.
- Untouched documents remain clean and never cause a save prompt.
- Both Rico icon families remain complete and selectable.
- The Ribbon is a shell-level surface above the whole sidebar/content splitter,
  never an editor-local strip to the right of the sidebar.
- Registered Workspaces are available through a dynamic quick selector and
  only the active Workspace is scanned.
- The repository/sidebar dirty marker follows QTextDocument's modified state
  and must clear immediately after Ribbon Save.
- Shell shortcuts remain enabled while editing; managed editor QAction
  duplicates carry no shortcuts and hidden pages cannot claim document keys.
- There is exactly one shell-owned Ribbon object; no hidden Dashboard editor
  and no editor Ribbon reparenting are permitted.
- The shell owns one stable application menu (`File`, `Edit`, `Format`,
  `Insert`, `View`, `Settings`, `Help`); embedded pages never install or
  advertise a menu bar.
- The shell does not force a non-native `QMenuBar`; desktop global-menu
  integration is allowed to export the authoritative application menu.
- The Settings icon-family submenu is labeled `App Icons`.

- exp6 hosting rule: managed pages use a real `RicopadEditorWidget(QWidget)`; no nested `RtfEditorWindow`, fake QMainWindow compatibility API, dynamic method transplantation, or hidden Ricopad Ribbon/menu bar is permitted.
- exp6-r3 source rule: the retired `RtfEditorWindow` implementation is removed from production source entirely; QA targets the one live `RicopadEditorWidget` instead of retaining dead code as a parity oracle.
- exp7 closing rule: application shutdown follows the authoritative Marko Plus staged `ClosingDialog` sequence: unsaved check → save preferences/state → hide the heavy shell → cancel/stop the workspace scanner responsively → final exit.
- exp8 external-change rule: watcher/repository metadata changes are connected to every open `EditorPage`; the page confirms the disk bytes against Ricopad's exact content signature and shows an independent external-change warning surface that is never tied to File Header or Collapsed Mode visibility. Reload protects unsaved editor changes.
- exp8-r1 preservation rule: the former Keep My Version acknowledgement is removed. **Save Version As…** must save the Rico editor payload to a different path and must never allow the externally changed source path as its target; the external disk copy remains untouched.
- exp8-r2 rename rule: F2 follows Marko Plus semantics—rename the active document when editing, otherwise rename the selected/open Workspace subfolder; the active Workspace root is never renameable.
- exp8-r3 mode rule: user-facing **Lock Editor** is renamed **Locked Mode** and **Collapsed Mode** is renamed **Focused Mode**. The View AppMenu places Focused Mode immediately before Locked Mode, with the separator after Locked Mode. Opening a document while Locked Mode is active resets the editor cursor/viewport to the top. Internal `view_only`/`collapsed_mode` identifiers remain implementation details.
- exp9 editor-status rule: the editor status bar contains **Insert/Overwrite | Chars, Words | percentage | flexible status** only. The filepath is shown only in the file header. Fixed fields reserve their longest supported widths; the right-hand message field is elastic with zero minimum width and must never increase the application minimum width.
- exp6 narrow-window rule: keep sidebar horizontal scrolling and use the proven Plus-family `QToolBar` overflow model for the shell Ribbon.
- The approved empty-paragraph/cell codec fix is treated as a Ricopad upstream bugfix and must be backported to Ricopad rather than maintained as an independent Rico Plus semantic fork.

## Current structure

```text
main.py
  -> RuntimePaths / ConfigService / ProjectRegistry
  -> MainWindow
     -> Repository / StateStore / Scanner / Watcher
     -> Navigation / Dashboards / FileActions / EditorManager
     -> ShellRibbon + shell-owned QAction command model
        -> EditorPage -> private RicopadEditorWidget(QWidget) -> RichTextEdit / rtf_codec
```

## Version-line direction

- `0.0.3` is the canonical release that closes the 0.0.3 experimental line.
- The next `0.0.4` line is reserved for stabilizing tabs.

## Release policy

Run the source release check, Qt RTF suite, workspace integration suite, and an
extracted-archive check before issuing a version. AppImage publication also
requires host desktop, print/PDF, and file-association testing.

- r8/r9 review: retain the Plus-family file heading; managed editors must never own QApplication theme; editor canvas follows App Theme until explicit Dark Editor override; Classic/New selector icons share the four-square Rico background with C/N target badges; editor focus indication uses the native transient focus-frame primitive rather than an invented permanent border.
