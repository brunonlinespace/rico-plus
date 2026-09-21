# Rico Plus Architecture

## Startup

1. `main.py` delegates to `rico_plus.app`.
2. `RuntimePaths` resolves source, frozen, or AppImage locations.
3. `ConfigService` loads bounded JSON settings.
4. `ProjectRegistry` selects one active workspace.
5. `MainWindow` creates the Plus-family shell, navigation, Dashboard, and one persistent Ribbon.
6. `FilesystemWatcher` runs a cancellable background RTF scan.
7. An optional positional path or `--open-file` request opens after startup.

No-argument startup creates no document. Paths outside the active workspace
are represented only by transient `DocumentEntry(external=True)` records.

## Ownership

- `DocumentRepository` is the canonical in-memory document inventory.
- `DocumentStateStore` owns lazy per-document Qt state.
- `EditorManager` owns Dashboard, folder, and editor pages.
- `FileActionsController` owns workspace file/folder mutations.
- `DocumentScanner` discovers `.rtf` files only.
- `EditorPage` is the managed-document integration boundary.
- `RicopadEditorWidget(QWidget)` owns Ricopad-derived RTF parsing, rendering,
  formatting, serialization, editor dialogs, and document/cursor state.
- `widgets/rtf_editor.py` contains no second `RtfEditorWindow`/QMainWindow editor implementation; the QWidget component is the sole live Ricopad-derived host.
- Managed pages never instantiate `RtfEditorWindow(QMainWindow)` and never
  construct a hidden Ricopad Ribbon or menu bar.
- `MainWindow` owns one stable application-menu/action model, window title,
  workspace shell, application shortcuts, and application theme.
- `ShellRibbon` owns one persistent Ribbon above the complete workspace
  splitter and retargets shell commands through the active `EditorPage`.

Workspace scans preserve transient external entries but Dashboard and Navigation
filter them out. Save As deliberately rebinds the live page to the new path;
the original managed file remains in the workspace, while an old transient
external record is retired.

## File-safety contracts

- Workspace New creates a real named `.rtf` immediately, following the
  Lair/Plus managed-workspace contract.
- Its initial RTF payload is generated from the current Ricopad New Document
  Defaults; workspace creation does not depend on a bundled static template.
- Saves use bounded serialization and atomic replacement.
- Dirty saves detect external disk changes before replacement.
- Save As rejects a target already owned by another open editor page.
- Imports and moves validate workspace containment.
- User-controlled rich text is sanitized and embedded objects are never run.

## Command surfaces

The shell owns workspace and document-command shortcuts permanently. One
static QAction vocabulary drives both the application menus and `ShellRibbon`.
Document work flows `MainWindow -> EditorPage -> RicopadEditorWidget`; the
shell never reaches through `EditorPage` into editor internals. Managed editor
QActions carry no competing application shortcuts. One Ribbon spans the window
above both sidebar and content and remains the same object on Dashboard, folder,
and document views. Narrow Ribbon pages use the Plus-family `QToolBar` overflow
mechanism rather than a width-forcing horizontal `QScrollArea`.

Retro and document-layout modes are not part of Rico Plus. Dashboard cards
expose only Open and View Only.

## Shutdown

Rico Plus follows the authoritative Plus staged-closing workflow:

1. Resolve unsaved documents before entering closing mode.
2. Show `ClosingDialog` and save window plus active-workspace state.
3. Hide the heavy application hierarchy while leaving the closing dialog responsive.
4. Cancel and join the workspace scanner while pumping Qt events.
5. If scanner shutdown fails, restore the application and cancel closing.
6. Otherwise show the final closing stage and exit only after the scanner has stopped safely.

Optional shutdown timing is enabled with `RICO_PLUS_PROFILE_SHUTDOWN=1`.
