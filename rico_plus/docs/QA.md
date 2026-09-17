# Rico Plus QA Guide

## Automated gate

```bash
python -m rico_plus.tools.release_check
```

The gate checks identity, imports, stale code, icon-family parity, shortcut
mapping, RTF semantic fixtures, Qt save/reopen behavior, workspace creation,
external opening, view-only behavior, and Save As rebinding. The workspace test
also requires the five-tab Ribbon to span the shell above the sidebar/content
splitter, checks the registered-Workspace quick selector, verifies shortcut
ownership, and exercises direct Ribbon Save against the sidebar dirty marker.
It also verifies that the shell remains the only application-menu owner and
that its complete menu inventory cannot change with Dashboard/editor/sidebar
focus.

## High-value manual sequences

### Startup and creation

- Start with no path: Dashboard appears and no RTF is created.
- Create a file from the Dashboard and a folder dashboard.
- Confirm each new file is non-empty, opens immediately, and is initially clean.
- Close an untouched new document: no save prompt appears.

### RTF editing

- Type text with a space immediately before and after a bold word; save/reopen.
- Exercise bullets, blank list items, formatted list runs, and a paragraph after
  a list; save/reopen in Rico Plus and LibreOffice.
- Test Unicode, links, images, simple tables, and repeated blank paragraphs.

### Commands

- Confirm File/Home/Insert/View/Help are the only editor tabs.
- Confirm File/Edit/Format/Insert/View/Settings/Help remain the only top-level
  application menus on the Dashboard, in a document, and after focus changes.
- Confirm no stray top-level Search menu appears.
- Confirm the Ribbon spans the full window and the sidebar begins underneath it.
- Confirm `Ctrl+O` opens workspace management.
- Confirm `Ctrl+D` / `Ctrl+Shift+D` operate on line/file respectively.
- Confirm `Ctrl+Alt+Shift+D` toggles List/Grid and `Ctrl+Alt+Shift+E` toggles Dark Editor.
- Confirm `F5` inserts Date and Time without refreshing the Workspace.
- Test Save, Save As, Save and New, Save and Dashboard, and Save and Exit.
- Edit and Ribbon-save a file; confirm `[edited]` clears immediately everywhere.
- Search shortcuts with reordered forms such as `shift ctrl s` and `ctl s`.

### Workspace and OS opening

- Open an internal file normally and in View Only from both card styles.
- Register a second Workspace and switch through the Workspace(s) quick selector.
- Open an external RTF through the desktop association; confirm it is not
  copied and does not appear in Dashboard or Navigation.
- Rescan while an external file is open; confirm the session survives.
- Drop an external RTF onto a dashboard and confirm the explicit import path.

### Safety and shutdown

- Replace a file externally before saving and verify the conflict prompt.
- Attempt Save As onto another open document and verify rejection.
- Close during an active scan and with unsaved content.
- Verify host browser, file manager, print, and PDF routes in the AppImage.
