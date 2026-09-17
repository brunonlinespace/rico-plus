# Rico Plus Project Memory

## Identity

- Product: Rico Plus 0.0.2
- Toolkit: Python 3 and PyQt6
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
- Shell shortcuts remain enabled while editing; embedded editor QAction
  duplicates carry no shortcuts and hidden pages cannot claim document keys.
- There is exactly one shell-owned Ribbon object; no hidden Dashboard editor
  and no editor Ribbon reparenting are permitted.
- The shell owns one stable application menu (`File`, `Edit`, `Format`,
  `Insert`, `View`, `Settings`, `Help`); embedded pages never install or
  advertise a menu bar.
- The shell does not force a non-native `QMenuBar`; desktop global-menu
  integration is allowed to export the authoritative application menu.
- The Settings icon-family submenu is labeled `App Icons`.

## Current structure

```text
main.py
  -> RuntimePaths / ConfigService / ProjectRegistry
  -> MainWindow
     -> Repository / StateStore / Scanner / Watcher
     -> Navigation / Dashboards / FileActions / EditorManager
     -> ShellRibbon + shell-owned QAction command model
        -> EditorPage -> embedded RtfEditorWindow (document engine only) -> rtf_codec
```

## Release policy

Run the source release check, Qt RTF suite, workspace integration suite, and an
extracted-archive check before issuing a version. AppImage publication also
requires host desktop, print/PDF, and file-association testing.

- r8 review: restore Marko-style file heading; embedded editors must never own QApplication theme; editor canvas follows App Theme until explicit Dark Editor override; Classic/New selector icons share the four-square Rico background with C/N target badges; managed editor canvas keeps the Rico red highlight border permanently visible.
