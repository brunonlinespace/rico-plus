# Rico Plus
# Copyright (C) 2026 Bruno Machado
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
"""Event-driven repository for every RTF document.

The repository is the application's single source of truth.
It stores DocumentEntry objects and emits Qt signals when documents are
added, removed, changed, or reset.

This file contains no widget code.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

from .document import DocumentEntry


class DocumentRepository(QObject):
    """
    Stores and indexes every DocumentEntry in the workspace.

    Paths are normalized to absolute Path objects so the same file
    cannot accidentally appear in the repository more than once.
    """

    document_added = pyqtSignal(object)
    document_removed = pyqtSignal(object)
    document_changed = pyqtSignal(object)
    document_path_changed = pyqtSignal(object, object)
    repository_reset = pyqtSignal()
    dirty_count_changed = pyqtSignal(int)

    VALID_SORT_MODES = {
        "title_az",
        "title_za",
        "created",
        "modified",
    }

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._documents: dict[Path, DocumentEntry] = {}
        self._batch_depth = 0
        self._counts_pending = False

    @staticmethod
    def normalize_path(path: str | Path) -> Path:
        """Return a consistent absolute path without requiring it to exist."""
        return Path(path).expanduser().resolve(strict=False)

    def add(self, document: DocumentEntry) -> DocumentEntry:
        """
        Add a document or update the existing object for the same path.

        Returning the stored object ensures callers always use the
        repository's canonical DocumentEntry instance.
        """
        path = self.normalize_path(document.path)
        document.path = path

        existing = self._documents.get(path)
        if existing is None:
            self._documents[path] = document
            self.document_added.emit(document)
            self._emit_counts()
            return document

        changed = self._copy_metadata(existing, document)
        if changed:
            self.document_changed.emit(existing)
            self._emit_counts()

        return existing

    def add_many(self, documents: Iterable[DocumentEntry]) -> None:
        """Add or update several documents."""
        for document in documents:
            self.add(document)

    def remove(self, path: str | Path) -> DocumentEntry | None:
        """Remove and return a document, or return None when absent."""
        normalized = self.normalize_path(path)
        document = self._documents.pop(normalized, None)

        if document is not None:
            self.document_removed.emit(document)
            self._emit_counts()

        return document

    def clear(self) -> None:
        """Remove every document and notify repository observers once."""
        if not self._documents:
            return

        self._documents.clear()
        self.repository_reset.emit()
        self._emit_counts()

    def replace_all(self, documents: Iterable[DocumentEntry]) -> None:
        """
        Synchronize the repository with a complete filesystem scan.

        Existing DocumentEntry objects are preserved whenever possible. This is
        important because other parts of the program may hold references
        to them.
        """
        incoming: dict[Path, DocumentEntry] = {}

        for document in documents:
            path = self.normalize_path(document.path)
            document.path = path
            incoming[path] = document

        # A workspace scan must not discard transient files opened through the
        # operating system from outside the active workspace.
        external = {
            path: document
            for path, document in self._documents.items()
            if document.external
        }
        existing_paths = set(self._documents) - set(external)
        incoming_paths = set(incoming)

        # Individual add/remove/change signals still update the relevant UI,
        # while the aggregate dirty count is emitted only once.
        with self.batch_update():
            for removed_path in existing_paths - incoming_paths:
                self.remove(removed_path)

            for added_path in incoming_paths - existing_paths:
                self.add(incoming[added_path])

            for shared_path in existing_paths & incoming_paths:
                current = self._documents[shared_path]
                discovered = incoming[shared_path]

                if self._copy_metadata(current, discovered):
                    self.document_changed.emit(current)


    def move_path(
        self,
        old_path: str | Path,
        new_path: str | Path,
        **metadata: object,
    ) -> DocumentEntry | None:
        """Re-key an existing DocumentEntry after a successful filesystem rename."""
        old_normalized = self.normalize_path(old_path)
        new_normalized = self.normalize_path(new_path)

        # A drop onto the document's current folder is a no-op, not a path
        # migration. Emitting document_path_changed for an unchanged key can
        # detach a live navigation item unnecessarily.
        if old_normalized == new_normalized:
            document = self._documents.get(old_normalized)
            if document is None:
                return None
            metadata_changed = False
            for name, value in metadata.items():
                if hasattr(document, name) and getattr(document, name) != value:
                    setattr(document, name, value)
                    metadata_changed = True
            document.search_title = document.display_name.casefold()
            document.search_filename = document.filename.casefold()
            if metadata_changed:
                self.document_changed.emit(document)
            self._emit_counts()
            return document

        document = self._documents.pop(old_normalized, None)
        if document is None:
            return None
        if new_normalized in self._documents:
            self._documents[old_normalized] = document
            raise ValueError(f"Repository already contains {new_normalized}")

        document.path = new_normalized
        for name, value in metadata.items():
            if hasattr(document, name):
                setattr(document, name, value)
        document.search_title = document.display_name.casefold()
        document.search_filename = document.filename.casefold()
        self._documents[new_normalized] = document
        self.document_path_changed.emit(document, old_normalized)
        self._emit_counts()
        return document

    def get(self, path: str | Path) -> DocumentEntry | None:
        """Return a document by path."""
        return self._documents.get(self.normalize_path(path))

    def contains(self, path: str | Path) -> bool:
        """Return True when a path is already known."""
        return self.normalize_path(path) in self._documents

    def all(self) -> tuple[DocumentEntry, ...]:
        """Return an immutable snapshot of every document."""
        return tuple(self._documents.values())

    def search(self, text: str) -> list[DocumentEntry]:
        """Search cached title and filename strings."""
        query = text.casefold().strip()

        if not query:
            return list(self._documents.values())

        return [
            document
            for document in self._documents.values()
            if query in document.search_title
            or query in document.search_filename
        ]

    def sorted(
        self,
        documents: Iterable[DocumentEntry] | None = None,
        mode: str = "modified",
    ) -> list[DocumentEntry]:
        """Return documents in the requested display order."""
        selected = list(self._documents.values() if documents is None else documents)

        if mode not in self.VALID_SORT_MODES:
            mode = "modified"

        if mode == "title_az":
            return sorted(selected, key=lambda document: document.search_title)

        if mode == "title_za":
            return sorted(
                selected,
                key=lambda document: document.search_title,
                reverse=True,
            )

        if mode == "created":
            return sorted(
                selected,
                key=lambda document: document.created,
                reverse=True,
            )

        return sorted(
            selected,
            key=lambda document: document.modified,
            reverse=True,
        )

    @property
    def dirty(self) -> tuple[DocumentEntry, ...]:
        """Return documents with unsaved editor changes."""
        return tuple(document for document in self._documents.values() if document.dirty)

    def set_dirty(self, path: str | Path, dirty: bool) -> bool:
        """Update dirty state and emit a change only when needed."""
        document = self.get(path)
        if document is None or document.dirty == dirty:
            return False

        document.dirty = dirty
        self.document_changed.emit(document)
        self._emit_counts()
        return True

    @staticmethod
    def _copy_metadata(target: DocumentEntry, source: DocumentEntry) -> bool:
        """
        Copy scanner-controlled metadata while preserving editor state.

        Dirty and loaded are intentionally not overwritten.
        """
        changed = False

        fields = (
            "filename",
            "display_name",
            "folder",
            "created",
            "modified",
            "size",
            "external",
        )

        for field_name in fields:
            new_value = getattr(source, field_name)
            if getattr(target, field_name) != new_value:
                setattr(target, field_name, new_value)
                changed = True

        new_search_title = target.display_name.casefold()
        new_search_filename = target.filename.casefold()

        if target.search_title != new_search_title:
            target.search_title = new_search_title
            changed = True

        if target.search_filename != new_search_filename:
            target.search_filename = new_search_filename
            changed = True

        return changed

    @contextmanager
    def batch_update(self):
        """Coalesce aggregate count signals during multi-document updates."""
        self._batch_depth += 1
        try:
            yield
        finally:
            self._batch_depth -= 1
            if self._batch_depth == 0 and self._counts_pending:
                self._counts_pending = False
                self._emit_counts_now()

    def _emit_counts(self) -> None:
        if self._batch_depth:
            self._counts_pending = True
            return
        self._emit_counts_now()

    def _emit_counts_now(self) -> None:
        self.dirty_count_changed.emit(len(self.dirty))

    def __iter__(self) -> Iterator[DocumentEntry]:
        return iter(self._documents.values())

    def __len__(self) -> int:
        return len(self._documents)

    def __contains__(self, path: object) -> bool:
        if not isinstance(path, (str, Path)):
            return False
        return self.contains(path)
