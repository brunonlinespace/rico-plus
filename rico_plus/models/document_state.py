# Rico Plus
# Copyright (C) 2026 Bruno Machado
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
"""Qt-facing UI state for one document.

Keeping this separate from DocumentEntry prevents the pure data model from depending
on widgets, editors, or tree items.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QTreeWidgetItem, QWidget

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QTextEdit


@dataclass(slots=True)
class DocumentState:
    """Lazily-created UI objects associated with one document."""

    editor: QTextEdit | None = None
    editor_page: QWidget | None = None
    dashboard_card: QWidget | None = None
    dashboard_grid_card: QWidget | None = None
    tree_item: QTreeWidgetItem | None = None

    page_created: bool = False

    def has_editor(self) -> bool:
        return self.editor is not None

    def clear_editor(self) -> None:
        self.editor = None
        self.editor_page = None
        self.page_created = False

    def clear_views(self) -> None:
        self.dashboard_card = None
        self.dashboard_grid_card = None
        self.tree_item = None
        self.clear_editor()
