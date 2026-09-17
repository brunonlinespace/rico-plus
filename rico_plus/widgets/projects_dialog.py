# Rico Plus
# Copyright (C) 2026 Bruno Machado
# SPDX-License-Identifier: GPL-3.0-or-later
"""Lightweight registered-Workspace chooser; inactive folders are never scanned."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from rico_plus.services.project_registry import ProjectRecord, ProjectRegistry
from rico_plus.widgets.ui_styles import style_button


class ProjectsDialog(QDialog):
    """Manage folder registrations and choose one active Workspace."""

    PROJECT_ID_ROLE = Qt.ItemDataRole.UserRole

    def __init__(
        self,
        registry: ProjectRegistry,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.registry = registry
        self.selected_project_id: str | None = None
        self.setWindowTitle("Change Workspace — Rico Plus")
        self.setMinimumSize(720, 430)

        root = QVBoxLayout(self)
        description = QLabel(
            "Rico Plus scans and watches only the Workspace you open. "
            "Other registered folders remain inactive."
        )
        description.setWordWrap(True)
        root.addWidget(description)

        self.project_list = QListWidget(self)
        self.project_list.itemDoubleClicked.connect(
            lambda _item, _column: self._accept_selected()
        )
        self.project_list.itemSelectionChanged.connect(self._update_buttons)
        root.addWidget(self.project_list, 1)

        actions = QHBoxLayout()
        self.add_button = style_button(QPushButton("Add Existing Folder…"), size="compact")
        self.rename_button = style_button(QPushButton("Rename Label…"), size="compact")
        self.relink_button = style_button(QPushButton("Relink Folder…"), size="compact")
        self.remove_button = style_button(QPushButton("Remove from Rico Plus"), size="compact")
        actions.addWidget(self.add_button)
        actions.addWidget(self.rename_button)
        actions.addWidget(self.relink_button)
        actions.addWidget(self.remove_button)
        actions.addStretch(1)
        root.addLayout(actions)

        self.add_button.clicked.connect(self._add_folder)
        self.rename_button.clicked.connect(self._rename_selected)
        self.relink_button.clicked.connect(self._relink_selected)
        self.remove_button.clicked.connect(self._remove_selected)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Open
            | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        open_button = self.buttons.button(QDialogButtonBox.StandardButton.Open)
        if open_button is not None:
            open_button.setText("Open Workspace")
        self.buttons.accepted.connect(self._accept_selected)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)

        self._populate(self.registry.active_project_id)

    def _populate(self, selected_id: str | None = None) -> None:
        self.project_list.clear()
        selected_item: QListWidgetItem | None = None
        for project in self.registry.projects:
            item = QListWidgetItem(self._project_text(project))
            item.setData(self.PROJECT_ID_ROLE, project.project_id)
            item.setToolTip(str(project.folder))
            self.project_list.addItem(item)
            if project.project_id == selected_id:
                selected_item = item
        if selected_item is not None:
            self.project_list.setCurrentItem(selected_item)
        elif self.project_list.count():
            self.project_list.setCurrentRow(0)
        self._update_buttons()

    def _project_text(self, project: ProjectRecord) -> str:
        active = "  [Active]" if project.project_id == self.registry.active_project_id else ""
        unavailable = "  [Folder unavailable]" if not project.folder.is_dir() else ""
        return f"{project.name}{active}{unavailable}\n{project.folder}"

    def _selected_id(self) -> str | None:
        item = self.project_list.currentItem()
        return str(item.data(self.PROJECT_ID_ROLE)) if item is not None else None

    def _selected_project(self) -> ProjectRecord | None:
        project_id = self._selected_id()
        return self.registry.get(project_id) if project_id else None

    def _update_buttons(self) -> None:
        project = self._selected_project()
        selected = project is not None
        self.rename_button.setEnabled(selected)
        self.relink_button.setEnabled(
            selected
            and project.project_id != self.registry.active_project_id
        )
        self.remove_button.setEnabled(
            selected
            and len(self.registry.projects) > 1
            and project.project_id != self.registry.active_project_id
        )
        open_button = self.buttons.button(QDialogButtonBox.StandardButton.Open)
        if open_button is not None:
            open_button.setEnabled(selected and project.folder.is_dir())

    def _add_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Add Existing Workspace Folder",
            str(self.registry.active_project.folder.parent),
        )
        if not selected:
            return
        folder = Path(selected).expanduser().resolve(strict=False)
        existing = self.registry.find_folder(folder)
        if existing is not None:
            self._populate(existing.project_id)
            return
        name, accepted = QInputDialog.getText(
            self,
            "Workspace Name",
            "Workspace label:",
            text=folder.name or "Rico Plus Workspace",
        )
        if not accepted or not name.strip():
            return
        project = self.registry.add_folder(folder, name)
        self._populate(project.project_id)

    def _rename_selected(self) -> None:
        project = self._selected_project()
        if project is None:
            return
        name, accepted = QInputDialog.getText(
            self,
            "Rename Workspace Label",
            "Workspace label:",
            text=project.name,
        )
        if accepted and self.registry.rename(project.project_id, name):
            self._populate(project.project_id)

    def _relink_selected(self) -> None:
        project = self._selected_project()
        if (
            project is None
            or project.project_id == self.registry.active_project_id
        ):
            return
        selected = QFileDialog.getExistingDirectory(
            self,
            "Relink Workspace Folder",
            str(project.folder.parent),
        )
        if not selected:
            return
        if not self.registry.relink(project.project_id, selected):
            QMessageBox.warning(
                self,
                "Folder Already Registered",
                "That folder is already registered as another Workspace.",
            )
            return
        self._populate(project.project_id)

    def _remove_selected(self) -> None:
        project = self._selected_project()
        if project is None:
            return
        response = QMessageBox.question(
            self,
            "Remove Workspace Registration",
            f"Remove '{project.name}' from Rico Plus?\n\n"
            "The Workspace folder and its files will not be deleted.",
        )
        if response != QMessageBox.StandardButton.Yes:
            return
        if self.registry.remove(project.project_id):
            self._populate(self.registry.active_project_id)

    def _accept_selected(self) -> None:
        project = self._selected_project()
        if project is None:
            return
        if not project.folder.is_dir():
            QMessageBox.warning(
                self,
                "Workspace Folder Unavailable",
                "Relink this Workspace to an available folder before opening it.",
            )
            return
        self.selected_project_id = project.project_id
        self.accept()
