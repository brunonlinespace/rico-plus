# Rico Plus

Rico Plus 0.0.2 is a Ribbon-based RTF editor with workspace navigation,
folder dashboards, background discovery, and conservative file handling. It
stores ordinary `.rtf` files and does not introduce a private document format.

## Highlights

- Registered workspaces with a recursive sidebar and fast switching
- Dynamic Workspace(s) quick selector; inactive roots are never scanned
- Workspace and folder dashboards in List or Grid view
- Exactly two card actions: **Open** and **View Only**
- One rich-text Ribbon with File, Home, Insert, View, and Help tabs
- Full-width Ribbon above the sidebar and document/dashboard surface
- Rico Icons Classic and Rico Icons New, each with light and dark variants
- Searchable shortcuts with case-insensitive, modifier-order-independent matching
- Safe create, duplicate, rename, move, import, and removal operations
- Atomic RTF saving, external-change detection, and bounded file loading
- Save, Save As, Save and New, Save and Dashboard, and Save and Exit
- Standards-based RTF lists plus curated LibreOffice interoperability coverage

## Run from source

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r rico_plus/requirements.txt
python main.py
```

Useful launch forms:

```bash
python main.py --version
python main.py --setup
python main.py document.rtf
python main.py --open-file document.rtf
```

Starting without a file opens the Dashboard and creates no document. **New RTF
File** asks the editor layer to create a complete, valid RTF document; Rico Plus
never uses an empty placeholder file.

## Workspaces and OS file opening

Only the active workspace is scanned. An RTF opened by the operating system
inside that workspace uses its normal workspace entry. An RTF outside the
workspace opens as a transient external session: it is not copied, imported,
or added to workspace navigation or dashboards.

External drag-and-drop is intentionally different: dropping an external RTF
onto a dashboard or folder is an explicit import. Internal drag-and-drop moves
documents between workspace folders.

`Ctrl+O` opens workspace management. Rico Plus has no separate **Open RTF
Document** command; desktop file associations and workspace navigation cover
that workflow.

## AppImage

```bash
./rico_plus/packaging/fedora/install-build-deps.sh
./rico_plus/packaging/fedora/build-appimage.sh
chmod +x rico_plus/dist/Rico_Plus-0.0.2-x86_64.AppImage
./rico_plus/dist/Rico_Plus-0.0.2-x86_64.AppImage
```

The desktop launcher accepts multiple RTF paths through `%F`. AppImage mode
keeps configuration and documents outside the read-only bundle.

## Validation

```bash
python -m rico_plus.tools.release_check
```

See `QA.md`, `BUILDING.md`, and `RELEASE_CHECKLIST.md` for the complete gates.

## License and links

Rico Plus is GPL-3.0-or-later. See `LICENSE`.

- Repository: https://github.com/brunonlinespace/rico-plus
- Issues: https://github.com/brunonlinespace/rico-plus/issues
