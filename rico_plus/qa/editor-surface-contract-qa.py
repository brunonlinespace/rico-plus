#!/usr/bin/env python3
"""Static contract check for the exp6 Marko/Lair hosting rebase."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
editor_page = (ROOT / "widgets" / "editor_page.py").read_text(encoding="utf-8")
rtf_editor = (ROOT / "widgets" / "rtf_editor.py").read_text(encoding="utf-8")
navigation = (ROOT / "widgets" / "navigation.py").read_text(encoding="utf-8")
main_window = (ROOT / "widgets" / "main_window.py").read_text(encoding="utf-8")
shell_ribbon = (ROOT / "widgets" / "shell_ribbon.py").read_text(encoding="utf-8")

# Proven family ownership boundary: MainWindow -> EditorPage -> editor widget.
assert "class MainWindow(QMainWindow):" in main_window
assert "self.tabbed_container = QWidget(self.central_host)" in main_window
assert "self.central_layout.addWidget(self.tabbed_container)" in main_window
assert "self.central_layout.addWidget(self.splitter, 1)" in main_window
assert ".engine" not in main_window
assert "def _engine(" not in main_window

assert "class EditorPage(QWidget):" in editor_page
assert "self._surface = RicopadEditorWidget(" in editor_page
assert "self.editor = self._surface.visual_editor" in editor_page
assert "RtfEditorWindow(" not in editor_page
assert "self.title_label = QLabel(self)" in editor_page
assert "self.external_banner = QFrame(self)" in editor_page
assert "root.setContentsMargins(12, 12, 12, 12)" in editor_page

# The managed Ricopad component is a real QWidget, not a QMainWindow impersonator.
assert "class RicopadEditorWidget(QWidget):" in rtf_editor
assert "class RtfEditorWindow(QMainWindow):" not in rtf_editor
assert "class RibbonScrollArea(QScrollArea):" not in rtf_editor
assert "OPEN_WINDOWS = set()" not in rtf_editor
assert "def register_window(window):" not in rtf_editor
assert "self.setMinimumSize(0, 0)" in rtf_editor
assert "self.main_layout.setContentsMargins(0, 0, 0, 0)" in rtf_editor
assert "self.visual_editor.setMinimumSize(0,0)" in rtf_editor
assert "self.app_status_bar = QStatusBar(self)" in rtf_editor
assert "def setCentralWidget(self, widget):" not in rtf_editor
assert "def centralWidget(self):" not in rtf_editor
assert "def statusBar(self):" not in rtf_editor
assert "RtfEditorWindow.__dict__.items()" not in rtf_editor

# Narrow-width behavior: retain tree horizontal scroll and Rico's horizontally scrollable grouped Ribbon.
assert "setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)" in navigation
assert "Qt.ScrollBarPolicy.ScrollBarAsNeeded" in navigation
assert "class RibbonScrollArea(QScrollArea):" in shell_ribbon
assert "QScroller.grabGesture(" in shell_ribbon
assert "QScroller.ScrollerGestureType.TouchGesture" in shell_ribbon
assert "scroll = RibbonScrollArea(self.tabs)" in shell_ribbon
assert "ScrollBarPolicy.ScrollBarAsNeeded" in shell_ribbon
assert "def _sync_ribbon_page_height" in shell_ribbon
assert "bar_height = bar.sizeHint().height()" in shell_ribbon
assert "class RibbonPageBar(QToolBar):" not in shell_ribbon
assert "self.tabs.setMinimumWidth(0)" in shell_ribbon

assert 'lock_suffix = " — Locked Mode"' in main_window
print("PASS: exp6 Marko/Lair MainWindow -> EditorPage -> RicopadEditorWidget contract")

# r1: the managed QWidget must not retain old embedded-QMainWindow host state.
widget_source = rtf_editor.split("class RicopadEditorWidget(QWidget):", 1)[1]
assert "self.embedded" not in widget_source
assert "centralWidget()" not in widget_source
assert "self.ribbon_tabs" not in widget_source
assert "self.toolbar_stack" not in widget_source
