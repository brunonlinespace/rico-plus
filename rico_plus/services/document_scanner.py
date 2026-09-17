# Rico Plus
# Copyright (C) 2026 Bruno Machado
# SPDX-License-Identifier: GPL-3.0-or-later
"""Fast workspace scanner used by Rico Plus."""

from __future__ import annotations

import fnmatch
import os
import time
from dataclasses import dataclass
from typing import Callable
from pathlib import Path

from rico_plus.app_constants import RTF_EXTENSIONS
from rico_plus.models.document import DocumentEntry


DEFAULT_IGNORED_DIRECTORY_NAMES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "env",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        ".nox",
        "node_modules",
        "site-packages",
        "build",
        "dist",
        ".idea",
    }
)

IGNORE_FILE_NAME = ".rico-plus-ignore"


class ScanCancelled(Exception):
    """Raised internally when application shutdown cancels a scan."""


@dataclass(slots=True, frozen=True)
class ScanSnapshot:
    """A complete result from one filesystem traversal."""

    documents: tuple[DocumentEntry, ...]
    folders: tuple[Path, ...]
    watch_directories: tuple[Path, ...]
    scanned_entries: int
    elapsed_seconds: float


class DocumentScanner:
    """
    Scan a workspace once and reuse the result for documents, folders and watches.

    Common dependency, cache and build directories are ignored by default.
    Additional relative paths or glob patterns can be listed in a
    `.rico-plus-ignore` file in the workspace root.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve(strict=False)

    def scan(self) -> list[DocumentEntry]:
        """Compatibility helper returning only discovered documents."""
        return list(self.scan_snapshot().documents)

    def scan_snapshot(
        self,
        should_cancel: Callable[[], bool] | None = None,
    ) -> ScanSnapshot:
        self.root.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()

        documents: list[DocumentEntry] = []
        folders: list[Path] = []
        document_directories: set[Path] = {self.root}
        scanned_entries = 0
        ignore_patterns = self._load_ignore_patterns()

        # Stack entries contain the absolute directory and its relative path.
        stack: list[tuple[Path, Path]] = [(self.root, Path())]

        while stack:
            if should_cancel is not None and should_cancel():
                raise ScanCancelled()

            directory, relative_directory = stack.pop()

            try:
                with os.scandir(directory) as entries:
                    for entry in entries:
                        if should_cancel is not None and should_cancel():
                            raise ScanCancelled()

                        scanned_entries += 1

                        try:
                            if entry.is_dir(follow_symlinks=False):
                                relative_child = relative_directory / entry.name
                                if self._should_ignore_directory(
                                    entry.name,
                                    relative_child,
                                    ignore_patterns,
                                ):
                                    continue

                                child = Path(entry.path)
                                folders.append(child)
                                stack.append((child, relative_child))
                                continue

                            if not entry.is_file(follow_symlinks=False):
                                continue

                            if Path(entry.name).suffix.casefold() not in RTF_EXTENSIONS:
                                continue

                            info = entry.stat(follow_symlinks=False)
                            path = Path(entry.path)
                            folder_text = relative_directory.as_posix()
                            if folder_text == ".":
                                folder_text = ""

                            documents.append(
                                DocumentEntry(
                                    path=path,
                                    filename=entry.name,
                                    display_name=(
                                        path.stem.replace("-", " ")
                                        .replace("_", " ")
                                        .title()
                                    ),
                                    folder=folder_text,
                                    created=info.st_ctime,
                                    modified=info.st_mtime,
                                    size=info.st_size,
                                )
                            )

                            # Watch the directory containing a document and all
                            # of its workspace ancestors.
                            current = directory
                            while True:
                                if (
                                    should_cancel is not None
                                    and should_cancel()
                                ):
                                    raise ScanCancelled()
                                document_directories.add(current)
                                if current == self.root:
                                    break
                                current = current.parent
                        except OSError:
                            continue
            except OSError:
                continue

        elapsed = time.monotonic() - started
        return ScanSnapshot(
            documents=tuple(documents),
            folders=tuple(folders),
            watch_directories=tuple(document_directories),
            scanned_entries=scanned_entries,
            elapsed_seconds=elapsed,
        )

    def _load_ignore_patterns(self) -> tuple[str, ...]:
        path = self.root / IGNORE_FILE_NAME
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return ()

        patterns: list[str] = []
        for raw in lines:
            value = raw.strip().replace("\\", "/")
            if value and not value.startswith("#"):
                patterns.append(value.strip("/"))
        return tuple(patterns)

    @staticmethod
    def _should_ignore_directory(
        name: str,
        relative_path: Path,
        patterns: tuple[str, ...],
    ) -> bool:
        if name.casefold() in DEFAULT_IGNORED_DIRECTORY_NAMES:
            return True

        relative = relative_path.as_posix()
        return any(
            fnmatch.fnmatch(relative, pattern)
            or fnmatch.fnmatch(name, pattern)
            for pattern in patterns
        )
