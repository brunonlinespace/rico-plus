<p align="center">
  <a href="https://github.com/brunonlinespace/rico-plus">
    <img
      src="rico_plus/assets/icons/ricopad-about.png"
      alt="Rico Plus"
      width="256"
    >
  </a>
</p>

# Rico Plus

**Friendly. Fast. Focused.**

Rico Plus is a workspace-scale Rich Text Format editor built around Ricopad's standards-based RTF engine and Ribbon interface. It adds managed workspaces, folder navigation, dashboards, persistent application settings, and Plus-family shell behavior while continuing to read and write ordinary `.rtf` files.

Current release: **0.0.3**

Repository: <https://github.com/brunonlinespace/rico-plus>

## What Rico Plus is

Rico Plus is designed for people who want Ricopad's rich-text editing in a larger, persistent workspace. A workspace is an ordinary folder containing RTF documents and subfolders; Rico Plus does not introduce a private document format or require documents to be imported into a database.

Only the active workspace is scanned and watched. Files opened from outside that workspace can be edited as external sessions without being copied into it.

Version **0.0.3** is the canonical release that closes the 0.0.3 experimental line.

## Highlights

- Standards-based **RTF editing** powered by Ricopad's RTF engine.
- Managed **Workspaces** with fast switching and recursive folder navigation.
- **My Workspace** sidebar with expandable folders and adjacent-file navigation.
- Workspace and folder **Dashboards** with List and Grid views.
- Full-width **Ribbon** with **File, Home, Insert, Configure, and Help** tabs.
- Touch-friendly horizontal Ribbon panning and kinetic touch panning on the main Dashboard.
- **Rico Icons Classic** and **Rico Icons New**, each with light and dark variants.
- Application themes: **System, Dark, and Light**.
- Editor canvas follows the application theme by default, with a persistent **Dark Editor** override when requested.
- Persistent **Locked Mode** to protect documents from accidental changes while keeping navigation, search, selection, and copying available.
- Temporary **Focused Mode** to hide the sidebar, status surfaces, file header, and expanded Ribbon without overwriting the user's normal view preferences.
- Persistent **File Header** visibility control.
- **Find**, Find and Replace, formatting, lists, alignment, tables, links, images, symbols, horizontal rules, dates, and times.
- Safe file operations including create, rename, duplicate, move, import, and removal.
- Atomic RTF saving and proactive external-change detection.
- **Save**, **Save As**, **Save and New**, **Save and Dashboard**, and **Save and Exit** workflows.
- Configurable **App Drag-and-Drop** behavior for opening dropped RTFs in the active window or a new window.
- First-run **Tutorial Wizard** plus searchable Keyboard Shortcuts grouped by AppMenu menu.
- Plasma/Linux desktop integration, including Rico Plus application identity for the active window.

## Interface

### Ribbon

The Ribbon is the primary editing command surface and remains above the workspace sidebar and content area.

- **File** — create, save, print, export, workspace/session actions.
- **Home** — clipboard, font, formatting, paragraph, alignment, and editing commands.
- **Insert** — links, images, tables, horizontal rules, symbols, dates, and times.
- **Configure** — view controls, editor settings, theme/icon settings, Dashboard behavior, launch behavior, and drag-and-drop behavior.
- **Help** — documentation, tutorial, shortcuts, GitHub, issues, and About.

Hover over a Ribbon command to see its name and keyboard shortcut. Use **Ctrl+Tab** and **Ctrl+Shift+Tab** to move between Ribbon tabs. Double-click a tab title to collapse or expand the Ribbon controls.

Ribbon pages support touch dragging for horizontal panning while stationary taps remain normal command interactions. Horizontal mouse-wheel and trackpad panning are also supported when the Ribbon is wider than the window.

### AppMenu

The application menu is organised as:

**File · Edit · Format · Insert · View · Settings · Help**

The Keyboard Shortcuts dialog uses these menu groups as its filter categories and retains an **All** view.

<p align="center">
  <img
      src="Screenshots/Screenshot_20260918_130630.png"
      alt="Rico Plus Dashboard"
      width="780"
  >
</p>

## Workspaces

Rico Plus keeps workspace management separate from the files themselves.

- **Open / Manage Workspaces…** registers, relabels, relinks, or removes workspace registrations.
- Removing a workspace registration does **not** delete its files.
- Only the active workspace is scanned and watched.
- The **Workspace(s)** menu provides fast switching between registered workspaces.
- **Refresh Workspace** rescans the active workspace.
- **New Window…** launches another Rico Plus window.
- The Dashboard and **My Workspace** sidebar provide navigation around the active workspace.
- **F2** renames the active RTF document when editing, or the selected/open workspace subfolder when no document is active. The workspace root itself is protected from rename.

An RTF opened by the operating system from outside the active workspace is treated as an external session. It is not automatically copied or registered.

The main Dashboard supports kinetic touch panning in both List and Grid views. The folder tree and Folder Dashboard deliberately retain their existing interaction model.

### Drag and drop

Rico Plus distinguishes between opening dropped documents, importing external documents, and moving documents inside a workspace.

- **Settings → App Drag-and-Drop** selects **Open on Active Window** or **Open on New Window**.
- Holding **Shift** while dropping temporarily reverses that saved choice for that drop only.
- External RTF files dropped into the application are imported into the applicable active workspace/folder target before being opened.
- External RTF files dropped onto a Folder Dashboard are explicitly imported into that folder.
- Internal document drag-and-drop onto workspace folders moves documents through Rico Plus's managed file operations.

When several RTF files are dropped while **Open on Active Window** is selected, the first opens in the active window and additional files open in new windows.

## Rich-text editing

Rico Plus keeps Ricopad's RTF editing model. Supported editing features include:

- font family and size
- bold, italic, underline, strikethrough
- superscript and subscript
- text colour and highlighting
- paragraph styles and line spacing
- left, centre, right, and justified alignment
- bullet lists and indentation
- links and images
- tables and table editing
- horizontal rules
- symbols
- date and time insertion
- print and PDF export

Rico Plus writes standards-based RTF and includes interoperability checks covering common LibreOffice workflows.

New workspace documents are generated as complete RTF documents from the configured **New Document Defaults** rather than as empty placeholder files.

<p align="center">
  <img
      src="Screenshots/Screenshot_20260918_135636.png"
      alt="Rico Plus Editor"
      width="780"
  >
</p>

## Locked Mode

**Locked Mode** provides a persistent read-only editing state for the managed editor. When enabled, document-mutating commands are disabled, including Symbols, while navigation, search, selection, and copying remain available.

The mode follows the user across files and sessions until changed. An open locked document is identified in the window title with **— Locked Mode**.

## Focused Mode

**Focused Mode** (`F10`) is a temporary reading/editing layout. It hides the sidebar, status surfaces, and file header and collapses the Ribbon. Leaving Focused Mode restores the independent visibility state that was active before it was enabled.

Focused Mode does not overwrite those normal view preferences.

## Appearance

Rico Plus provides two separate but related appearance layers.

### App Theme

Choose **System**, **Dark**, or **Light** for the application shell.

<p align="center">
  <img
      src="Screenshots/Screenshot_20260918_131226.png"
      alt="Rico Plus Light Theme"
      width="560"
  >
</p>

### Editor appearance

The editor canvas follows the active application theme by default. **Dark Editor** can be used to create a persistent editor-only light/dark override.

<p align="center">
  <img
      src="Screenshots/Screenshot_20260918_131214.png"
      alt="Rico Plus Light Editor"
      width="560"
  >
</p>

### App Icons

Choose between:

- **Rico Icons Classic**
- **Rico Icons New**

<p align="center">
  <img
      src="Screenshots/Screenshot_20260918_131847.png"
      alt="Rico Plus Light Classic"
      width="780"
  >
</p>
<p align="center">
  <img
      src="Screenshots/Screenshot_20260918_131920.png"
      alt="Rico Plus Light New"
      width="780"
  >
</p>

Both icon families provide light- and dark-interface variants.

## Useful keyboard shortcuts

| Shortcut | Action |
| --- | --- |
| `Ctrl+N` | New RTF File |
| `Ctrl+Shift+N` | New Folder |
| `Ctrl+Alt+Shift+N` | New Window |
| `Ctrl+O` | Open / Manage Workspaces |
| `Ctrl+Shift+F5` | Refresh Workspace |
| `Ctrl+S` | Save |
| `Ctrl+Shift+S` | Save and New |
| `Ctrl+W` | Show Dashboard |
| `Ctrl+Shift+W` | Save and Dashboard |
| `Ctrl+Shift+Q` | Save and Exit |
| `Ctrl+Up` / `Ctrl+Down` | Previous / Next File |
| `F2` | Rename File or Folder |
| `F3` / `Shift+F3` | Find Next / Previous Match |
| `Ctrl+D` | Duplicate Line / Selection |
| `Ctrl+Shift+D` | Duplicate File |
| `Ctrl+F` | Find Bar |
| `Ctrl+H` | Find and Replace |
| `Ctrl+Shift+F` | Font… |
| `Ctrl+Shift+]` / `Ctrl+Shift+[` | Increase / Decrease Font Size |
| `Ctrl+Shift+L` | Bullet List |
| `F4` | Properties |
| `F9` | Show / Hide Sidebar |
| `F10` | Focused Mode |
| `F11` | Full Screen |
| `F12` | Locked Mode |
| `Ctrl+Alt+Shift+D` | Toggle List / Grid View |
| `Ctrl+Alt+Shift+E` | Dark Editor |
| `Ctrl+Alt+Shift+F` | File Header |
| `Ctrl+Alt+Shift+S` | Show / Hide Status |
| `Ctrl+Tab` / `Ctrl+Shift+Tab` | Next / Previous Ribbon Tab |
| `Ctrl+Shift+/` | Keyboard Shortcuts |
| `Shift+F1` | Tutorial Wizard |

The complete live shortcut inventory is available from **Help → Keyboard Shortcuts**.

<p align="center">
  <img
      src="Screenshots/Screenshot_20260918_133002.png"
      alt="Rico Plus Shortcut Helper"
      width="560"
  >
</p>

## Running from source

Rico Plus requires Python 3 and PyQt6 6.9 or later within the supported PyQt6 6.x series.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r rico_plus/requirements.txt
python main.py
```

Other useful launch forms:

```bash
python main.py --version
python main.py --setup
python main.py document.rtf
python main.py --open-file document.rtf
```

Starting Rico Plus without a file opens the Dashboard and does not create a placeholder document.

## Building the AppImage

Fedora build helpers are included in the source tree:

```bash
./rico_plus/packaging/fedora/install-build-deps.sh
./rico_plus/packaging/fedora/build-appimage.sh
```

The public AppImage builder is currently for **x86_64** and is validated on **Fedora 43 and Fedora 44**.

Expected output:

```text
rico_plus/dist/Rico_Plus-0.0.3-x86_64.AppImage
rico_plus/dist/Rico_Plus-0.0.3-x86_64.AppImage.sha256
rico_plus/dist/Rico_Plus-0.0.3-x86_64.AppImage.build-info.txt
```

Run the AppImage builder as the normal desktop user. The dependency helper may invoke `sudo dnf`; the builder itself should not normally be run with `sudo`.

## Validation

Run the authoritative source-release gate with:

```bash
python -m rico_plus.tools.release_check
```

The release checks cover application identity, source architecture, bundled assets, RTF corpus behavior, security regressions, icon-family parity, interoperability, and the source manifest. With PyQt6 available, the Qt runtime and workspace integration checks are included as well.

Additional QA and release documentation is available under `rico_plus/docs/`.

## Configuration

Rico Plus stores its application configuration outside the document workspace. The exact configuration path is displayed in **Help → About Rico Plus**.

Documents remain ordinary `.rtf` files and are not embedded into the configuration.

## AppMenu

<p align="center">
  <img
      src="Screenshots/Screenshot_20260918_131459.png"
      alt="Rico Plus File"
      width="560"
  >
  <img
      src="Screenshots/Screenshot_20260918_131527.png"
      alt="Rico Plus File"
      width="560"
  >
  <img
      src="Screenshots/Screenshot_20260918_131533.png"
      alt="Rico Plus Edit"
      width="560"
  >
  <img
      src="Screenshots/Screenshot_20260918_131542.png"
      alt="Rico Plus Format"
      width="560"
  >
  <img
      src="Screenshots/Screenshot_20260918_131549.png"
      alt="Rico Plus Format"
      width="560"
  >
  <img
      src="Screenshots/Screenshot_20260918_131554.png"
      alt="Rico Plus Format"
      width="560"
  >
  <img
      src="Screenshots/Screenshot_20260918_131601.png"
      alt="Rico Plus Insert"
      width="560"
  >
  <img
      src="Screenshots/Screenshot_20260918_131636.png"
      alt="Rico Plus Insert"
      width="560"
  >
  <img
      src="Screenshots/Screenshot_20260918_131644.png"
      alt="Rico Plus View"
      width="560"
  >
  <img
      src="Screenshots/Screenshot_20260918_131649.png"
      alt="Rico Plus View"
      width="560"
  >
  <img
      src="Screenshots/Screenshot_20260918_131659.png"
      alt="Rico Plus Settings"
      width="560"
  >
  <img
      src="Screenshots/Screenshot_20260918_131707.png"
      alt="Rico Plus Settings"
      width="560"
  >
  <img
      src="Screenshots/Screenshot_20260918_131712.png"
      alt="Rico Plus Settings"
      width="560"
  >
</p>

## Quick Tour

<p align="center">
  <img
      src="Screenshots/Screenshot_20260918_132222.png"
      alt="Rico Plus Quick Tour 1"
      width="560"
  >
  <img
      src="Screenshots/Screenshot_20260918_132256.png"
      alt="Rico Plus Quick Tour 2"
      width="560"
  >
  <img
      src="Screenshots/Screenshot_20260918_132300.png"
      alt="Rico Plus Quick Tour 3"
      width="560"
  >
  <img
      src="Screenshots/Screenshot_20260918_132310.png"
      alt="Rico Plus Quick Tour 4"
      width="560"
  >
  <img
      src="Screenshots/Screenshot_20260918_132312.png"
      alt="Rico Plus Quick Tour 5"
      width="560"
  >
  <img
      src="Screenshots/Screenshot_20260918_132315.png"
      alt="Rico Plus Quick Tour 6"
      width="560"
  >
  <img
      src="Screenshots/Screenshot_20260918_131337.png"
      alt="Rico Plus Mini Dashboard"
      width="560"
  >
</p>

## More Screenshots

<p align="center">
  <img
      src="Screenshots/Screenshot_20260918_131337.png"
      alt="Rico Plus Mini Dashboard"
      width="560"
  >
   <img
      src="Screenshots/Screenshot_20260918_135830.png"
      alt="Rico Plus Collapsed Mode"
      width="560"
  >
</p>

## License

Rico Plus is licensed under the **GNU General Public License v3.0 or later**.

See `rico_plus/LICENSE` for the complete license text.

## Links

- Rico Plus: <https://github.com/brunonlinespace/rico-plus>
- Issues: <https://github.com/brunonlinespace/rico-plus/issues>
- GitHub profile: <https://github.com/brunonlinespace/>

Copyright © 2026 Bruno Machado.
<p align="center">
  <a href="https://github.com/brunonlinespace/rico-plus">
    <img
      src="rico_plus/assets/icons/ricopad-about.png"
      alt="Rico Plus"
      width="256"
    >
  </a>
</p>

# Rico Plus

**Friendly. Fast. Focused.**

Rico Plus is a workspace-scale Rich Text Format editor built around Ricopad's standards-based RTF engine and Ribbon interface. It adds managed workspaces, folder navigation, dashboards, persistent application settings, and Plus-family shell behavior while continuing to read and write ordinary `.rtf` files.

Current release: **0.0.2**

Repository: <https://github.com/brunonlinespace/rico-plus>

## What Rico Plus is

Rico Plus is designed for people who want Ricopad's rich-text editing in a larger, persistent workspace. A workspace is an ordinary folder containing RTF documents and subfolders; Rico Plus does not introduce a private document format or require documents to be imported into a database.

Only the active workspace is scanned and watched. Files opened from outside that workspace can be edited as external sessions without being copied into it.

Ricopad is the spiritual successor of the defunct Microsoft Wordpad but for Linux, with a modern interface.

## Highlights

- Standards-based **RTF editing** powered by Ricopad's RTF engine.
- Managed **Workspaces** with fast switching and recursive folder navigation.
- **My Workspace** sidebar with expandable folders and adjacent-file navigation.
- Workspace and folder **Dashboards** with List and Grid views.
- Full-width **Ribbon** with **File, Home, Insert, Configure, and Help** tabs.
- **Rico Icons Classic** and **Rico Icons New**, each with light and dark variants.
- Application themes: **System, Dark, and Light**.
- Editor canvas follows the application theme by default, with a persistent **Dark Editor** override when requested.
- Persistent **Lock Editor** mode to protect documents from accidental changes while keeping navigation, search, and copying available.
- **Find**, Find and Replace, formatting, lists, alignment, tables, links, images, symbols, horizontal rules, dates, and times.
- Safe file operations including create, rename, duplicate, move, import, and removal.
- Atomic RTF saving and external-change detection.
- **Save**, **Save As**, **Save and New**, **Save and Dashboard**, and **Save and Exit** workflows.
- First-run **Tutorial Wizard** plus searchable Keyboard Shortcuts grouped by AppMenu menu.
- Plasma/Linux desktop integration, including Rico Plus application identity for the active window.

## Interface

### Ribbon

The Ribbon is the primary editing command surface and remains above the workspace sidebar and content area.

- **File** — create, save, print, export, workspace/session actions.
- **Home** — clipboard, font, formatting, paragraph, alignment, and editing commands.
- **Insert** — links, images, tables, horizontal rules, symbols, dates, and times.
- **Configure** — view controls, editor settings, theme/icon settings, and application behavior.
- **Help** — documentation, tutorial, shortcuts, GitHub, issues, and About.

Hover over a Ribbon command to see its name and keyboard shortcut. Use **Ctrl+Tab** and **Ctrl+Shift+Tab** to move between Ribbon tabs. Double-click a tab title to collapse the Ribbon controls.

### AppMenu

The application menu is organised as:

**File · Edit · Format · Insert · View · Settings · Help**

The Keyboard Shortcuts dialog uses these menu groups as its filter categories and retains an **All** view.

## Workspaces

Rico Plus keeps workspace management separate from the files themselves.

- **Manage Workspaces…** registers, relabels, relinks, or removes workspace registrations.
- Removing a workspace registration does **not** delete its files.
- Only the active workspace is scanned and watched.
- The **Workspace(s)** menu provides fast switching between registered workspaces.
- The Dashboard and **My Workspace** sidebar provide navigation around the active workspace.

An RTF opened by the operating system from outside the active workspace is treated as an external session. It is not automatically copied or registered.

External drag-and-drop onto a dashboard or folder is an explicit import operation. Internal drag-and-drop moves documents between workspace folders.

<p align="center">
  <img
      src="Screenshots/Screenshot_20260918_130630.png"
      alt="Rico Plus Dashboard"
      width="780"
  >
</p>

## Rich-text editing

Rico Plus keeps Ricopad's RTF editing model. Supported editing features include:

- font family and size
- bold, italic, underline, strikethrough
- superscript and subscript
- text colour and highlighting
- paragraph styles and line spacing
- left, centre, right, and justified alignment
- bullet lists and indentation
- links and images
- tables and table editing
- horizontal rules
- symbols
- date and time insertion
- print and PDF export

Rico Plus writes standards-based RTF and includes interoperability checks covering common LibreOffice workflows.

<p align="center">
  <img
      src="Screenshots/Screenshot_20260918_135636.png"
      alt="Rico Plus Editor"
      width="780"
  >
</p>

## Lock Editor

**Lock Editor** provides a persistent read-only editing state for the managed editor. When enabled, document-mutating commands are disabled, including Symbols, while navigation, search, selection, and copying remain available.

The lock follows the user across files and sessions until changed.

## Appearance

Rico Plus provides two separate but related appearance layers.

### App Theme

Choose **System**, **Dark**, or **Light** for the application shell.

<p align="center">
  <img
      src="Screenshots/Screenshot_20260918_131226.png"
      alt="Rico Plus Light Theme"
      width="560"
  >
</p>

### Editor appearance

The editor canvas follows the active application theme by default. **Dark Editor** can be used to create a persistent editor-only light/dark override.

<p align="center">
  <img
      src="Screenshots/Screenshot_20260918_131214.png"
      alt="Rico Plus Light Editor"
      width="560"
  >
</p>

### App Icons

Choose between:

- **Rico Icons Classic**
- **Rico Icons New**

<p align="center">
  <img
      src="Screenshots/Screenshot_20260918_131847.png"
      alt="Rico Plus Light Classic"
      width="780"
  >
</p>
<p align="center">
  <img
      src="Screenshots/Screenshot_20260918_131920.png"
      alt="Rico Plus Light New"
      width="780"
  >
</p>

Both icon families provide light- and dark-interface variants.

## Useful keyboard shortcuts

| Shortcut | Action |
| --- | --- |
| `Ctrl+N` | New RTF File |
| `Ctrl+Shift+N` | New Folder |
| `Ctrl+O` | Manage Workspaces |
| `Ctrl+S` | Save |
| `Ctrl+Shift+S` | Save and New |
| `Ctrl+W` | Show Dashboard |
| `Ctrl+Shift+W` | Save and Dashboard |
| `Ctrl+Shift+Q` | Save and Exit |
| `Ctrl+Up` / `Ctrl+Down` | Previous / Next File |
| `Ctrl+D` | Duplicate Line / Selection |
| `Ctrl+Shift+D` | Duplicate File |
| `Ctrl+F` | Find Bar |
| `Ctrl+H` | Find and Replace |
| `F4` | Properties |
| `F9` | Show / Hide Sidebar |
| `F11` | Full Screen |
| `F12` | Lock Editor |
| `Ctrl+Alt+Shift+D` | Toggle List / Grid View |
| `Ctrl+Alt+Shift+E` | Dark Editor |
| `Ctrl+Alt+Shift+S` | Show / Hide Status |
| `Ctrl+Tab` / `Ctrl+Shift+Tab` | Next / Previous Ribbon Tab |
| `Shift+F1` | Tutorial Wizard |

The complete live shortcut inventory is available from **Help → Keyboard Shortcuts**.

<p align="center">
  <img
      src="Screenshots/Screenshot_20260918_133002.png"
      alt="Rico Plus Shortcut Helper"
      width="560"
  >
</p>

## Running from source

Rico Plus requires Python and PyQt6.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r rico_plus/requirements.txt
python main.py
```

Other useful launch forms:

```bash
python main.py --version
python main.py --setup
python main.py document.rtf
python main.py --open-file document.rtf
```

Starting Rico Plus without a file opens the Dashboard and does not create a placeholder document.

## Building the AppImage

Fedora build helpers are included in the source tree:

```bash
./rico_plus/packaging/fedora/install-build-deps.sh
./rico_plus/packaging/fedora/build-appimage.sh
```

Expected output:

```text
rico_plus/dist/Rico_Plus-0.0.2-x86_64.AppImage
rico_plus/dist/Rico_Plus-0.0.2-x86_64.AppImage.sha256
rico_plus/dist/Rico_Plus-0.0.2-x86_64.AppImage.build-info.txt
```

Run the AppImage builder as the normal desktop user. The dependency helper may invoke `sudo dnf`; the builder itself should not normally be run with `sudo`.

## Validation

Run the authoritative source-release gate with:

```bash
python -m rico_plus.tools.release_check
```

The release checks cover application identity, source architecture, bundled assets, RTF corpus behavior, security regressions, icon-family parity, interoperability, and the source manifest. With PyQt6 available, the Qt runtime and workspace integration checks are included as well.

Additional QA and release documentation is available under `rico_plus/docs/`.

## Configuration

Rico Plus stores its application configuration outside the document workspace. The exact configuration path is displayed in **Help → About Rico Plus**.

Documents remain ordinary `.rtf` files and are not embedded into the configuration.

## AppMenu

<p align="center">
  <img
      src="Screenshots/Screenshot_20260918_131459.png"
      alt="Rico Plus File"
      width="560"
  >
  <img
      src="Screenshots/Screenshot_20260918_131527.png"
      alt="Rico Plus File"
      width="560"
  >
  <img
      src="Screenshots/Screenshot_20260918_131533.png"
      alt="Rico Plus Edit"
      width="560"
  >
  <img
      src="Screenshots/Screenshot_20260918_131542.png"
      alt="Rico Plus Format"
      width="560"
  >
  <img
      src="Screenshots/Screenshot_20260918_131549.png"
      alt="Rico Plus Format"
      width="560"
  >
  <img
      src="Screenshots/Screenshot_20260918_131554.png"
      alt="Rico Plus Format"
      width="560"
  >
  <img
      src="Screenshots/Screenshot_20260918_131601.png"
      alt="Rico Plus Insert"
      width="560"
  >
  <img
      src="Screenshots/Screenshot_20260918_131636.png"
      alt="Rico Plus Insert"
      width="560"
  >
  <img
      src="Screenshots/Screenshot_20260918_131644.png"
      alt="Rico Plus View"
      width="560"
  >
  <img
      src="Screenshots/Screenshot_20260918_131649.png"
      alt="Rico Plus View"
      width="560"
  >
  <img
      src="Screenshots/Screenshot_20260918_131659.png"
      alt="Rico Plus Settings"
      width="560"
  >
  <img
      src="Screenshots/Screenshot_20260918_131707.png"
      alt="Rico Plus Settings"
      width="560"
  >
  <img
      src="Screenshots/Screenshot_20260918_131712.png"
      alt="Rico Plus Settings"
      width="560"
  >
</p>

## Quick Tour

<p align="center">
  <img
      src="Screenshots/Screenshot_20260918_132222.png"
      alt="Rico Plus Quick Tour 1"
      width="560"
  >
  <img
      src="Screenshots/Screenshot_20260918_132256.png"
      alt="Rico Plus Quick Tour 2"
      width="560"
  >
  <img
      src="Screenshots/Screenshot_20260918_132300.png"
      alt="Rico Plus Quick Tour 3"
      width="560"
  >
  <img
      src="Screenshots/Screenshot_20260918_132310.png"
      alt="Rico Plus Quick Tour 4"
      width="560"
  >
  <img
      src="Screenshots/Screenshot_20260918_132312.png"
      alt="Rico Plus Quick Tour 5"
      width="560"
  >
  <img
      src="Screenshots/Screenshot_20260918_132315.png"
      alt="Rico Plus Quick Tour 6"
      width="560"
  >
  <img
      src="Screenshots/Screenshot_20260918_131337.png"
      alt="Rico Plus Mini Dashboard"
      width="560"
  >
</p>


## More Screenshots

<p align="center">
  <img
      src="Screenshots/Screenshot_20260918_131337.png"
      alt="Rico Plus Mini Dashboard"
      width="560"
  >
   <img
      src="Screenshots/Screenshot_20260918_135830.png"
      alt="Rico Plus Collapsed Mode"
      width="560"
  >
</p>

## License

Rico Plus is licensed under the **GNU General Public License v3.0 or later**.

See `rico_plus/LICENSE` for the complete license text.

## Links

- Rico Plus: <https://github.com/brunonlinespace/rico-plus>
- Issues: <https://github.com/brunonlinespace/rico-plus/issues>
- GitHub profile: <https://github.com/brunonlinespace/>

Copyright © 2026 Bruno Machado.
