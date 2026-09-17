# Rico Plus Architecture

## Startup

1. `main.py` delegates to `rico_plus.app`.
2. `RuntimePaths` resolves source, frozen, or AppImage locations.
3. `ConfigService` loads bounded JSON settings.
4. `ProjectRegistry` selects one active workspace.
5. `MainWindow` creates the shell, navigation, and Dashboard.
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
- `RtfEditorWindow` owns RTF parsing, rendering, formatting, and serialization.
- `EditorPage` embeds that RTF document engine and keeps its standalone menu,
  Ribbon, and QAction shortcuts out of the managed-workspace command surface.
- `MainWindow` owns one stable application-menu/action model.
- `ShellRibbon` owns one persistent Ribbon above the complete workspace
  splitter and retargets shell commands to the active `EditorPage` when one
  exists. No hidden or synthetic editor is created for the Dashboard.

Workspace scans preserve transient external entries but Dashboard and Navigation
filter them out. Save As deliberately rebinds the live page to the new path;
the original managed file remains in the workspace, while an old transient
external record is retired.

## File-safety contracts

- New files are created from a bundled valid RTF template through a synced
  temporary file and no-replace installation.
- Saves use bounded serialization and atomic replacement.
- Dirty saves detect external disk changes before replacement.
- Save As rejects a target already owned by another open editor page.
- Imports and moves validate workspace containment.
- User-controlled rich text is sanitized and embedded objects are never run.

## Command surfaces

The shell owns workspace and document-command shortcuts permanently. One
static QAction vocabulary drives both the application menus and `ShellRibbon`;
those actions delegate document work to the active RTF engine without adopting
or moving editor-owned QAction objects. Embedded editors carry no QAction
shortcuts in managed pages. One Ribbon spans the window above both sidebar and
content and remains the same object on Dashboard, folder, and document views.
Retro and document-layout modes are not part of Rico Plus. Dashboard cards
expose only Open and View Only.

## Shutdown

1. Resolve unsaved documents.
2. Save window and active-workspace state.
3. Cancel and join the scanner.
4. Exit only after the scanner stops safely.
