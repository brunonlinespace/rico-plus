# Rico Plus 0.0.3-exp6-r3 integration rebase

## exp6-r3 source purge

The dormant `RtfEditorWindow(QMainWindow)` implementation has been deleted from `widgets/rtf_editor.py`. QA now validates the single live `RicopadEditorWidget(QWidget)` directly; there is no duplicate production implementation retained as a test oracle. No shell taxonomy, RTF codec, or editor behavior was intentionally changed by this cleanup.

## Authorities

- **Python Lair r1.5.6 / Marko Plus 0.0.1-r3**: application ownership, `MainWindow`, managed `EditorPage`, workspace lifecycle, command-surface placement and shrinkable window geometry.
- **Ricopad 0.7.2-r5.4 theme-exp4**: RichTextEdit, RTF parsing/serialization, formatting semantics, dialogs and editor behavior.
- **Approved Ricopad upstream fix**: preserve final paragraph + typing state for empty RTF paragraphs/cells (the exp5 18-line codec correction).

## Required managed path

```text
MainWindow
└── EditorManager
    └── EditorPage
        └── RicopadEditorWidget(QWidget)
            └── RichTextEdit
```

The managed path must not contain `RtfEditorWindow(QMainWindow)`, a fake QMainWindow API, dynamic method transplantation, or a hidden Ricopad Ribbon/menu bar.

## Ownership

**Rico Plus owns:** application menu, shell Ribbon, workspace/sidebar/Dashboard, application shortcuts, window title, application theme/icons, Focused Mode and workspace file placement.

**Ricopad-derived editor owns:** RTF semantics, editing/formatting commands, Find Bar, editor-specific dialogs, word wrap/zoom, read-only enforcement, save/load and editor document state.

`MainWindow` talks only to `EditorPage`. `EditorPage` is the sole adapter to the Ricopad editor widget.

## Geometry

- One Plus outer page margin: 12 px.
- Editor component + QTextEdit + viewport minimum size: 0.
- No standalone Ricopad 720x500 minimum on the managed path.
- Ribbon pages use Marko's `QToolBar` overflow behavior rather than width-forcing horizontal Ribbon scroll areas.
- Sidebar tree retains explicit horizontal scrolling for long paths.

## Fidelity gate

`qa/editor-component-parity-qa.py` compares the extracted QWidget editor behavior with the Ricopad-derived implementation and fails on unapproved method drift. `rich_text_support.py` remains unchanged; `rtf_codec.py` differs from upstream Ricopad only by branding/import-path changes plus the approved blank-paragraph/cell fix.
