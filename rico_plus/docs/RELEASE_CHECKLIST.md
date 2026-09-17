# Rico Plus 0.0.2 Release Checklist

## Source

- [ ] `python main.py --version` reports `Rico Plus 0.0.2`
- [ ] `python -m rico_plus.tools.release_check` passes
- [ ] `SOURCE_MANIFEST.sha256` verifies from the package directory
- [ ] Freshly extracted archive passes the same release check
- [ ] No caches, generated builds, or obsolete editor modules are present

## Runtime

- [ ] No-argument startup creates no document
- [ ] New RTF is valid, non-empty, immediately reopenable, and initially clean
- [ ] Bold-boundary spaces and list-boundary spaces survive save/reopen
- [ ] Dashboard cards show Open and View Only only
- [ ] Ribbon spans the window above both sidebar and content
- [ ] Embedded editor and document canvas are visibly rendered beneath it
- [ ] Workspace(s) quick selector lists every registered Workspace once
- [ ] Ribbon Save clears `[edited]` immediately in the sidebar
- [ ] Shortcut audit reports no active shell/editor collisions
- [ ] Ribbon is the only editor command surface
- [ ] App menu remains `File/Edit/Format/Insert/View/Settings/Help` across
      Dashboard, editor, and sidebar focus changes
- [ ] No embedded editor or Dashboard command provider advertises a menu bar
- [ ] Classic/New icons work in light and dark themes
- [ ] `Ctrl+O` opens workspace management
- [ ] All five save workflows behave correctly
- [ ] External OS-open files remain transient and uncopied

## AppImage

- [ ] Desktop file validates and advertises RTF MIME types with `%F`
- [ ] AppStream metadata validates
- [ ] Official icons render at each installed size
- [ ] Source and AppImage use writable external configuration/workspaces
- [ ] Host editor, folder, browser, print, and PDF routes work
- [ ] `--appimage-extract-and-run --version` reports 0.0.2

## Publish

- [ ] Tag `v0.0.2`
- [ ] Build from the tagged source
- [ ] Publish source, AppImage, checksum, build information, and release notes
