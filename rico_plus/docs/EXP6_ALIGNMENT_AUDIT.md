# Rico Plus 0.0.3-exp6-r2 alignment audit

## Sources actually compared

- Python Lair 2 `r1.5.6`: `python-lair-2-3.1-exp-sheepy-backport-menu-editor-r1.5.6.zip`
- Marko Plus `0.0.1-r3`: `Marko-Plus-0.0.1-r3-source`
- Ricopad `0.7.2-r5.4-theme-exp4`: authoritative source tree
- Rico Plus active/mainline `0.0.2-r1`
- Rico Plus experimental `0.0.3-exp6-r2`

Legend: ✅ aligned/pass · ❌ regression/problem · ◐ partial/indirect · ➖ not applicable by design.

| Contract / known problem | Python Lair | Marko Plus | Ricopad | Rico 0.0.2-r1 | Rico 0.0.3-exp6-r2 |
|---|---:|---:|---:|---:|---:|
| Main application owns shell/lifecycle | ✅ | ✅ | ✅ standalone | ✅ | ✅ |
| MainWindow reaches editor only through EditorPage | ✅ | ✅ | ➖ | ❌ `.engine` / `_engine()` access | ✅ no `.engine` access |
| EditorPage hosts an actual editor widget | ✅ `CodeEditor` | ✅ `CodeEditor` | ➖ | ❌ embeds `RtfEditorWindow(QMainWindow)` | ✅ `RicopadEditorWidget(QWidget)` |
| No nested/pretend QMainWindow on managed path | ✅ | ✅ | ➖ | ❌ | ✅ |
| No dynamic transplant of QMainWindow methods | ✅ | ✅ | ➖ | ➖ | ✅ exp1-exp5 shim removed |
| Managed editor may shrink with visible viewport | ✅ | ✅ | ✅ standalone viewport | ❌ embedded 720x500 minimum leaks | ✅ component/editor/viewport min 0 |
| Narrow Ribbon uses non-overlapping overflow | ➖ | ✅ native `QToolBar` overflow | ✅ horizontal Ribbon scroll | ❌ horizontal scroll could consume editor geometry | ✅ Rico horizontal scroll retained; scrollbar height reserved inside Ribbon |
| Long sidebar hierarchy has explicit horizontal scrolling | ◐ default | ◐ default | ➖ | ❌ no explicit contract | ✅ retained exp correction |
| Word Wrap measures actual visible editor width | ✅ | ✅ | ✅ | ❌ can wrap to oversized embedded editor | ✅ direct shrinkable widget |
| Lock/read-only warning represented in title | ➖ | ➖ | ✅ `— View Only` | ❌ shell title drops state | ✅ `— Lock Editor` |
| Application shortcut ownership is shell-level | ✅ | ✅ | ➖ standalone | ◐ editor shortcuts stripped, but shell reaches engine | ✅ shell -> EditorPage |
| Application theme ownership is shell-level | ✅ | ✅ | ➖ standalone owns itself | ◐ shell-owned but reaches engine directly | ✅ shell -> EditorPage; editor consumes state |
| Workspace New creates named file immediately | ✅ `.py` | ✅ `.md` | ➖ untitled-in-memory by design | ✅ `.rtf` | ✅ `.rtf` |
| New File independent of bundled static template | ✅ | ✅ | ✅ direct document defaults | ❌ hard dependency on `default-document.rtf` | ✅ generated from current defaults |
| New File honours user paragraph defaults after reopen | ➖ | ➖ | ◐ original codec blank-paragraph edge case | ❌ static factory path | ✅ approved codec correction + round-trip QA |
| `rich_text_support.py` remains Ricopad-authoritative | ➖ | ➖ | ✅ | ✅ | ✅ byte-for-byte identical |
| `RichTextEdit` behavior remains Ricopad-authoritative | ➖ | ➖ | ✅ | ✅ | ✅ ~99.9% source identity; only product wording differs |
| Empty RTF paragraph/cell preserves final alignment/spacing/typing state | ➖ | ➖ | ❌ original edge case | ❌ | ✅ approved 18-line fix; to backport to Ricopad |
| Extracted editor behavior protected from silent rewrite | ➖ | ➖ | source authority | ❌ whole window used instead | ✅ 208 behavior methods parity-checked |
| Unified Show Status / Collapsed Mode behavior | ➖ | Plus-family precedent | ➖ | ✅ | ✅ retained |

## Structural finding

The inherited Lair/Plus infrastructure remains strong: filesystem watcher, config, navigation, workspace/project registry, dashboard/file-action concepts and the splitter/central-host layout remain closely related. The historical failures cluster at the editor-host boundary: active Rico embeds a full Ricopad `QMainWindow`, while exp6 restores the family pattern `MainWindow -> EditorPage -> editor QWidget`.

## Ricopad core fidelity in exp6

- `rich_text_support.py`: byte-for-byte identical to Ricopad.
- `RichTextEdit`: behavior-identical apart from three Rico Plus wording strings.
- `rtf_codec.py`: Ricopad code plus package/import branding and the approved empty-paragraph/cell preservation patch only.
- `qa/editor-component-parity-qa.py`: confirms 209 extracted editor behavior methods remain AST-equivalent to the Ricopad-derived implementation after normalising the editor-status delivery hook.

## exp6 versus active Rico Plus 0.0.2-r1 — tree delta

Exact source-tree comparison after excluding bytecode/cache files: **7 files added, 27 files changed, 0 files removed, 925 files unchanged**. The changes are deliberately concentrated at the shell/editor integration seam, New File/defaults path, approved codec fix, QA, and release metadata.

## exp6 versus active Rico Plus 0.0.2-r1 — functional source changes

- `widgets/main_window.py` — removes direct `.engine` ownership, keeps MainWindow -> EditorPage boundary, adds shrinkable shell containers and Lock Editor title suffix.
- `widgets/editor_page.py` — replaces embedded `RtfEditorWindow` with `RicopadEditorWidget`, owns managed lifecycle/header/state and remains the only shell/editor adapter.
- `widgets/rtf_editor.py` — adds the real QWidget editor component; no fake `setCentralWidget/centralWidget/statusBar` API, no dynamic method transplant, no hidden Ricopad Ribbon/menu bar on the managed path.
- `widgets/shell_ribbon.py` — keeps Rico/Ricopad-style horizontal `QScrollArea` pages, makes the Ribbon width-shrinkable, and reserves scrollbar height inside the Ribbon so it cannot overlap the editor; groups/order/actions remain unchanged.
- `widgets/navigation.py` — keeps explicit horizontal sidebar scrolling (`ResizeToContents`, `ScrollBarAsNeeded`, no elision).
- `controllers/file_actions.py` + new `services/rtf_new_document.py` — create a valid named RTF immediately from current New Document Defaults instead of copying a bundled template.
- `rtf_codec.py` — retains the approved empty-paragraph/cell final-state fix.
- QA/release files — add editor-widget architecture, behavior-parity and new-document regression gates; update workspace integration expectations.
- Remaining changed files are version, packaging and documentation metadata for the experimental line.

## Runtime limitation

The packaging environment does not contain PyQt6. Architecture/source checks can be marked pass from code inspection and static QA, but actual window-resize, Ribbon horizontal scrolling, drag/drop and visual Word Wrap behavior still require manual GUI execution of exp6.

## Problem-area evidence

- Active Rico `widgets/rtf_editor.py` unconditionally applies `resize(980, 680)` and `setMinimumSize(720, 500)` even to its embedded `RtfEditorWindow`; exp6's managed `RicopadEditorWidget`, `visual_editor`, and editor viewport all explicitly permit 0x0 minimum geometry.
- Active Rico `widgets/main_window.py` contains `_engine()`, `_engine_action()`, `_engine_call()` and direct `page.engine` access. Exp6 contains no `.engine` or `_engine()` access in MainWindow; commands target EditorPage.
- Marko's central shell is `central_host -> tabbed_container + horizontal splitter`. Exp6 uses that same structural contract, with additional zero-minimum geometry on the shrinkable containers.
- Marko demonstrates the key shell requirement that the command surface must not force the editor width. Rico cannot literally use Marko's `QToolBar` extension popup because Rico's Ribbon pages contain grouped multi-row custom widgets; exp6-r2 therefore keeps the existing horizontal `QScrollArea` behavior while adopting the same shrinkable-shell constraint and reserving the scrollbar within Ribbon geometry.
- Active Rico `EditorPage` constructs `RtfEditorWindow(..., embedded=True)`. Exp6 constructs `RicopadEditorWidget(QWidget)` and has no managed `RtfEditorWindow` reference.
