#!/usr/bin/env python3
"""Audit callbacks used by the live Rico Plus rich-text component."""
from pathlib import Path
import ast

source = Path(__file__).resolve().parents[1] / "widgets" / "rtf_editor.py"
tree = ast.parse(source.read_text(encoding="utf-8"))
classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
if "RtfEditorWindow" in classes:
    raise SystemExit("Retired RtfEditorWindow implementation is still present")
cls = classes.get("RicopadEditorWidget")
if cls is None:
    raise SystemExit("RicopadEditorWidget is missing")
methods = {node.name for node in cls.body if isinstance(node, ast.FunctionDef)}
required = {
    "apply_tab_width", "open_tab_width_dialog", "formatted_system_date",
    "formatted_system_time", "formatted_system_timestamp", "insert_text_at_cursor",
    "insert_time_date", "insert_date", "insert_time", "show_replace_dialog",
    "replace_next", "replace_all", "focus_search", "active_search_text",
    "on_search_text_changed", "on_document_text_changed", "update_search_counter",
    "clear_search_results", "find_text_and_refocus", "find_text", "find_next",
    "find_previous", "set_word_wrap_mode", "increase_font_size", "decrease_font_size",
    "_adjacent_font_size", "_step_selected_font_size", "infer_editor_canvas_theme",
    "apply_editor_canvas_theme", "toggle_editor_canvas_light",
    "update_editor_canvas_theme_action", "save_and_exit", "set_selected_font_weight",
    "apply_font_weight_from_combo", "duplicate_current_line", "delete_current_line",
    "toggle_search_bar", "show_tutorial_wizard", "edit_link", "remove_link",
    "insert_table_row_above", "insert_table_row_below", "delete_table_row",
    "insert_table_column_left", "insert_table_column_right", "delete_table_column",
    "delete_table", "clear_highlight", "print_document", "export_pdf",
    "_print_document_with_header_footer",
}
missing = sorted(required - methods)
if missing:
    raise SystemExit(f"Missing Rico Plus editor runtime methods: {missing}")

# Every direct private self-call must resolve on the live component. This is
# more useful than retaining a dead QMainWindow implementation as a test oracle.
private_calls = {
    node.func.attr
    for node in ast.walk(cls)
    if isinstance(node, ast.Call)
    and isinstance(node.func, ast.Attribute)
    and isinstance(node.func.value, ast.Name)
    and node.func.value.id == "self"
    and node.func.attr.startswith("_")
}
missing_private = sorted(private_calls - methods)
if missing_private:
    raise SystemExit(f"Missing private editor methods referenced at runtime: {missing_private}")

for removed in (
    "build_ribbon", "build_retro_toolbar", "cycle_ribbon_tab",
    "set_ribbon_collapsed", "toggle_ribbon_collapsed", "toggle_source_mode",
    "paste_as_markdown", "new_markdown_file", "new_rtf_file",
    "export_portable_markdown", "go_to_line", "toggle_numbered_list",
):
    if removed in methods:
        raise SystemExit(f"Retired host/editor method unexpectedly present: {removed}")
print(f"PASS: live editor callback audit ({len(required)} required methods)")
