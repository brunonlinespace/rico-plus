#!/usr/bin/env python3
"""Guard the single live Ricopad-derived QWidget component contract.

exp6-r3 deliberately removed the dormant RtfEditorWindow copy.  This check now
protects the live component directly instead of comparing it with dead code in
the production module.
"""
from __future__ import annotations
import ast
from pathlib import Path

source_path = Path(__file__).resolve().parents[1] / "widgets" / "rtf_editor.py"
source = source_path.read_text(encoding="utf-8")
tree = ast.parse(source)
classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}

assert "RtfEditorWindow" not in classes, "retired QMainWindow editor copy returned"
assert "RicopadEditorWidget" in classes, "live RicopadEditorWidget missing"
widget = classes["RicopadEditorWidget"]
methods = {
    node.name: node
    for node in widget.body
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
}

# Broad behavior inventory: these are the major Ricopad semantic families that
# the managed component must continue to own after the dead-host purge.
required = {
    "load_file", "save_file", "save_as_file", "new_file", "check_save_changes",
    "_document_payload", "_write_payload_atomically", "inspect_text_file",
    "toggle_bold", "toggle_italic", "toggle_underline", "toggle_strikethrough",
    "toggle_superscript", "toggle_subscript", "set_selected_font",
    "set_selected_font_size", "set_selected_font_weight", "set_alignment",
    "apply_heading", "set_line_spacing", "change_indent", "toggle_bullet_list",
    "clear_formatting", "choose_text_colour", "choose_highlight_colour",
    "insert_link", "edit_link", "remove_link", "insert_image", "insert_image_path",
    "insert_table", "insert_table_row_above", "insert_table_row_below",
    "delete_table_row", "insert_table_column_left", "insert_table_column_right",
    "delete_table_column", "delete_table", "insert_horizontal_rule",
    "show_replace_dialog", "replace_next", "replace_all", "find_text",
    "find_next", "find_previous", "toggle_search_bar", "set_word_wrap_mode",
    "apply_tab_width", "apply_zoom_preference", "zoom_in", "zoom_out", "zoom_reset",
    "show_properties_dialog", "show_page_setup_dialog", "print_document", "export_pdf",
    "toggle_view_only", "apply_editor_canvas_theme", "refresh_portable_icons",
    "show_new_document_defaults_dialog", "show_tutorial_wizard",
}
missing = sorted(required - set(methods))
assert not missing, f"live Ricopad behavior missing after purge: {missing}"
assert len(methods) >= 200, f"unexpectedly small live editor surface: {len(methods)} methods"

# Calling contracts that previously regressed during extraction must stay intact.
expected_decorators = {
    "_adjacent_font_size": ("staticmethod",),
    "_highlight_contrast_colour": ("staticmethod",),
    "_image_dimensions_safe": ("staticmethod",),
    "_zoom_dots_per_metre": ("staticmethod",),
    "_format_file_datetime": ("staticmethod",),
    "_content_signature": ("staticmethod",),
    "_disk_signature": ("classmethod",),
    "format_for_path": ("staticmethod",),
    "inspect_text_file": ("staticmethod",),
    "_default_created_file_mode": ("staticmethod",),
}
for name, expected in expected_decorators.items():
    node = methods[name]
    actual = tuple(ast.unparse(item) for item in node.decorator_list)
    assert actual == expected, f"{name} decorator contract changed: {actual!r}"

widget_source = source.split("class RicopadEditorWidget(QWidget):", 1)[1]
for retired in (
    "self.embedded", "self.ribbon_tabs", "self.toolbar_stack", "centralWidget()",
    "RtfEditorWindow.__dict__.items()", "def setCentralWidget(",
    "def centralWidget(", "def statusBar(",
):
    assert retired not in widget_source, f"retired host compatibility remains: {retired}"

print(f"PASS: single live RicopadEditorWidget contract ({len(methods)} methods)")
