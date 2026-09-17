# Rico Plus
# Copyright (C) 2026 Bruno Machado
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
"""Stores Qt UI state separately from DocumentRepository."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

from .document import DocumentEntry
from .document_repository import DocumentRepository
from .document_state import DocumentState


class DocumentStateStore(QObject):
    """Owns one DocumentState per repository document path."""

    state_created = pyqtSignal(object, object)
    state_removed = pyqtSignal(object, object)
    states_reset = pyqtSignal()

    def __init__(
        self,
        repository: DocumentRepository,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.repository = repository
        self._states: dict[Path, DocumentState] = {}

        repository.document_added.connect(self._on_document_added)
        repository.document_removed.connect(self._on_document_removed)
        repository.document_path_changed.connect(self._on_document_path_changed)
        repository.repository_reset.connect(self.clear)

        for document in repository:
            self.ensure(document.path)

    def ensure(self, path: str | Path) -> DocumentState:
        """Return the state for a path, creating it when necessary."""
        normalized = self.repository.normalize_path(path)
        state = self._states.get(normalized)

        if state is None:
            state = DocumentState()
            self._states[normalized] = state
            document = self.repository.get(normalized)
            if document is not None:
                self.state_created.emit(document, state)

        return state

    def get(self, path: str | Path) -> DocumentState | None:
        normalized = self.repository.normalize_path(path)
        return self._states.get(normalized)


    def move_path(
        self,
        old_path: str | Path,
        new_path: str | Path,
    ) -> DocumentState | None:
        """Re-key UI state after a document rename."""
        old_normalized = self.repository.normalize_path(old_path)
        new_normalized = self.repository.normalize_path(new_path)
        state = self._states.pop(old_normalized, None)
        if state is not None:
            self._states[new_normalized] = state
        return state

    def remove(self, path: str | Path) -> DocumentState | None:
        normalized = self.repository.normalize_path(path)
        state = self._states.pop(normalized, None)
        return state

    def clear(self) -> None:
        if not self._states:
            return

        self._states.clear()
        self.states_reset.emit()

    def _on_document_added(self, document: DocumentEntry) -> None:
        self.ensure(document.path)


    def _on_document_path_changed(self, document: DocumentEntry, old_path: Path) -> None:
        """Move existing UI state to the document's new repository key."""
        self.move_path(old_path, document.path)

    def _on_document_removed(self, document: DocumentEntry) -> None:
        state = self.remove(document.path)
        if state is None:
            return

        self.state_removed.emit(document, state)

    def __iter__(self) -> Iterator[tuple[Path, DocumentState]]:
        return iter(self._states.items())

    def __len__(self) -> int:
        return len(self._states)
