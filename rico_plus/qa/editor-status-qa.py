#!/usr/bin/env python3
"""Static regression contract for the exp9-r2 editor-status geometry."""

from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
SOURCE = (PACKAGE / "widgets" / "rtf_editor.py").read_text(encoding="utf-8")

required = (
    'self.operation_mode_label = QLabel("Insert", self.app_status_bar)',
    'horizontalAdvance("Overwrite") + 4',
    'self.operation_mode_label.setFixedWidth(operation_width)',
    'self.zoom_label = QLabel("100%", self.app_status_bar)',
    'horizontalAdvance("300%") + 4',
    'self.zoom_label.setFixedWidth(zoom_width)',
    'self.counter_label = QLabel("Chars 0", self.app_status_bar)',
    'f"Chars {MAX_DOCUMENT_CHARACTERS:,}"',
    'self.counter_label.setFixedWidth(counter_width)',
    'self.status_message_label = QLabel("", self.app_status_bar)',
    'self.status_message_label.setMinimumWidth(0)',
    'QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred',
    'self.app_status_bar.addWidget(self.operation_mode_label)',
    'self.app_status_bar.addWidget(self.zoom_label)',
    'self.app_status_bar.addWidget(self.counter_label)',
    'self.app_status_bar.addWidget(self.status_message_label, 1)',
    'characters = max(0, self.text_area.document().characterCount() - 1)',
    'self.zoom_label.setText(f"{self.zoom_percent}%")',
    'self.counter_label.setText(f"Chars {characters:,}")',
    'self.status_message_label.setText(text)',
)

for fragment in required:
    if fragment not in SOURCE:
        raise SystemExit(f"FAIL: missing exp9 editor-status contract: {fragment}")

for forbidden in (
    'self.path_label = QLabel(',
    'self.path_label.setText(',
    'self.path_label.setToolTip(',
    'self.app_status_bar.showMessage(',
    'self.visual_editor.cursorPositionChanged.connect(self.update_status_counts)',
    'self.zoom_label.setText(f"Zoom:',
    'self.counter_label.setText(f"Col:',
    'Words ',
    're.findall(',
    'plain_text = self.text_area.toPlainText()',
    'self.app_status_bar.addPermanentWidget(self.zoom_label)',
):
    if forbidden in SOURCE:
        raise SystemExit(f"FAIL: retired editor-status behavior remains: {forbidden}")

MAIN_WINDOW = (PACKAGE / "widgets" / "main_window.py").read_text(encoding="utf-8")
EDITOR_PAGE = (PACKAGE / "widgets" / "editor_page.py").read_text(encoding="utf-8")
EDITOR_MANAGER = (PACKAGE / "controllers" / "editor_manager.py").read_text(encoding="utf-8")

for fragment in (
    'def show_editor_status(self, message: str, timeout: int = 0)',
    'self._surface._show_status_message(message, timeout)',
):
    if fragment not in EDITOR_PAGE:
        raise SystemExit(f"FAIL: missing editor-status page bridge: {fragment}")

for fragment in (
    'def show_current_editor_status(self, message: str, timeout: int = 0)',
    'page.show_editor_status(message, timeout)',
):
    if fragment not in EDITOR_MANAGER:
        raise SystemExit(f"FAIL: missing current-editor status router: {fragment}")

for fragment in (
    'self.editor_manager.show_current_editor_status(',
    'Editor canvas switched to a dark background.',
    'Editor canvas switched to a light background.',
    'self.show_status(f"Theme: {label}.")',
):
    if fragment not in MAIN_WINDOW:
        raise SystemExit(f"FAIL: missing status-message ownership contract: {fragment}")

print("PASS: exp9-r2 editor-status geometry/message-routing contract")
