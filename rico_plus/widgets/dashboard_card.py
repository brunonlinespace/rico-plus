# Rico Plus
# Copyright (C) 2026 Bruno Machado
# SPDX-License-Identifier: GPL-3.0-or-later
"""List/grid RTF dashboard cards with Ricopad-style document actions."""
from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path

from PyQt6.QtCore import QMimeData, QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QDrag, QIcon, QMouseEvent, QPalette
from PyQt6.QtWidgets import QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout

from rico_plus.models.document import DocumentEntry
from rico_plus.widgets.ui_styles import style_button


class DashboardCard(QFrame):
    """Persistent RTF card shared by the root and folder dashboards."""

    open_requested = pyqtSignal(object)
    view_only_requested = pyqtSignal(object)
    selected_requested = pyqtSignal(object)      # one click selects only
    remove_requested = pyqtSignal(object)

    VALID_MODES = {"list", "grid"}

    def __init__(self, document: DocumentEntry, parent=None, *, view_mode: str = "list") -> None:
        super().__init__(parent)
        self.document = document
        self._view_mode = view_mode if view_mode in self.VALID_MODES else "list"
        self._drag_start = QPoint()
        self._drag_active = False
        self._drag_performed = False
        self._selected = False

        self.setObjectName("dashboardCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Plain)
        self.setLineWidth(1)

        self._build_labels()
        self._build_buttons()
        self._build_fixed_layout()
        self.refresh()

    def _build_labels(self) -> None:
        self.title_label = QLabel()
        self.title_label.setTextFormat(Qt.TextFormat.RichText)
        self.title_label.setWordWrap(True)
        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        self.metadata_label = QLabel()
        self.metadata_label.setWordWrap(True)

    def _build_buttons(self) -> None:
        grid = self._view_mode == "grid"
        self.edit_button = self._button("Open", role="primary", grid=grid)
        self.view_only_button = self._button(
            "View Only", role="neutral", grid=grid
        )

        self.edit_button.setToolTip("Open this RTF file for editing")
        self.view_only_button.setToolTip(
            "Open this RTF file without allowing changes"
        )
        self.edit_button.clicked.connect(lambda: self.open_requested.emit(self.document))
        self.view_only_button.clicked.connect(
            lambda: self.view_only_requested.emit(self.document)
        )
        self.refresh_icons()

    def refresh_icons(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        scheme = "light" if app.palette().color(QPalette.ColorRole.Base).lightness() >= 140 else "dark"
        icon_set = str(app.property("rico_plus_icon_set") or "new")
        family = "ribbon-icons-classic" if icon_set == "classic" else "ribbon-icons"
        root = Path(__file__).resolve().parent.parent / "assets" / family / scheme
        for button, name in (
            (self.edit_button, "open"),
            (self.view_only_button, "view-only"),
        ):
            path = root / f"{name}.png"
            button.setIcon(QIcon(str(path)) if path.is_file() else QIcon())

    def _build_fixed_layout(self) -> None:
        if self._view_mode == "grid":
            self._build_grid_layout()
        else:
            self._build_list_layout()

    def _build_list_layout(self) -> None:
        self.setMinimumSize(0, 118)
        self.setMaximumWidth(16777215)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(8)
        header = QHBoxLayout(); header.setSpacing(8)
        header.addWidget(self.title_label, 1); header.addWidget(self.status_label)
        outer.addLayout(header); outer.addWidget(self.metadata_label)
        actions = QHBoxLayout(); actions.setSpacing(7); actions.addStretch(1)
        for button in (self.edit_button, self.view_only_button):
            actions.addWidget(button)
        outer.addLayout(actions)

    def _build_grid_layout(self) -> None:
        self.setMinimumSize(300, 245)
        self.setMaximumWidth(380)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        outer = QGridLayout(self)
        outer.setContentsMargins(14, 12, 12, 12)
        outer.setHorizontalSpacing(12); outer.setVerticalSpacing(8)
        outer.setColumnStretch(0, 1); outer.setColumnStretch(1, 0)
        content = QVBoxLayout(); content.setSpacing(8)
        header = QHBoxLayout(); header.setSpacing(8)
        header.addWidget(self.title_label, 1); header.addWidget(self.status_label)
        content.addLayout(header); content.addWidget(self.metadata_label); content.addStretch(1)
        actions = QVBoxLayout(); actions.setSpacing(6); actions.setAlignment(Qt.AlignmentFlag.AlignTop)
        for button in (self.edit_button, self.view_only_button):
            actions.addWidget(button, alignment=Qt.AlignmentFlag.AlignRight)
        actions.addStretch(1)
        outer.addLayout(content, 0, 0)
        outer.addLayout(actions, 0, 1, alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)

    @staticmethod
    def _button(text: str, *, role: str, grid: bool) -> QPushButton:
        button = style_button(QPushButton(text), role=role, size="compact", minimum_width=96 if grid else 96)
        if grid:
            button.setMinimumHeight(32)
        return button

    @staticmethod
    def format_size(size: int) -> str:
        if size < 1024: return f"{size} B"
        if size < 1024 * 1024: return f"{size / 1024:.1f} KB"
        return f"{size / (1024 * 1024):.1f} MB"

    def set_selected(self, selected: bool) -> None:
        self._selected = bool(selected)
        self.setFrameShadow(QFrame.Shadow.Sunken if self._selected else QFrame.Shadow.Plain)
        self.setLineWidth(2 if self._selected else 1)
        self.update()

    def refresh(self) -> None:
        display_name = escape(self.document.display_name)
        self.title_label.setText(f"<b>{display_name}</b>")
        self.status_label.setText("● Unsaved" if self.document.dirty else "")
        modified = datetime.fromtimestamp(self.document.modified).strftime("%Y-%m-%d %H:%M")
        folder = escape(self.document.folder or ".")
        filename = escape(self.document.filename)
        self.metadata_label.setText(
            f"{folder}/{filename}<br>Modified: {modified} · Size: {self.format_size(self.document.size)}"
        )

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.open_requested.emit(self.document)
            event.accept(); return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and not self._drag_active:
            self._drag_start = event.position().toPoint()
            self._drag_performed = False
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if not self._drag_active and not self._drag_performed:
                self.selected_requested.emit(self.document)
            self._drag_start = QPoint()
            self._drag_performed = False
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_active:
            event.accept(); return
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return super().mouseMoveEvent(event)
        if self._drag_start.isNull():
            return super().mouseMoveEvent(event)
        if (event.position().toPoint() - self._drag_start).manhattanLength() < 10:
            return super().mouseMoveEvent(event)
        self._drag_active = True
        self._drag_performed = True
        try:
            mime = QMimeData()
            mime.setData("application/x-rico-plus-document", str(self.document.path).encode("utf-8"))
            drag = QDrag(self); drag.setMimeData(mime); drag.exec(Qt.DropAction.MoveAction)
        finally:
            self._drag_active = False; self._drag_start = QPoint()
        event.accept()
