# Rico Plus
# Copyright (C) 2026 Bruno Machado
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
"""Safe filesystem actions for Rico Plus RTF documents and folders."""

from __future__ import annotations

import shutil
import os
import tempfile
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QInputDialog, QMessageBox, QWidget

from rico_plus.app_constants import RTF_EXTENSIONS
from rico_plus.controllers.editor_manager import EditorManager
from rico_plus.models.document import DocumentEntry
from rico_plus.models.document_repository import DocumentRepository
from rico_plus.models.document_state_store import DocumentStateStore
from rico_plus.services.filesystem_watcher import FilesystemWatcher
from rico_plus.services.file_io import (
    FileStateChangedError,
    current_file_state,
    fsync_directory,
    install_new_file_from_temp,
    path_identity_matches,
    path_lexists,
    rename_path_no_replace,
)
from rico_plus.services.desktop_launcher import DesktopLauncher


class FileActionsController(QObject):
    """Coordinates safe file operations for repository documents."""

    status_message = pyqtSignal(str)
    document_renamed = pyqtSignal(object, object)
    document_removed = pyqtSignal(object)
    document_imported = pyqtSignal(object)
    document_created = pyqtSignal(object)
    folder_renamed = pyqtSignal(object, object)
    folder_removed = pyqtSignal(object)

    def __init__(
        self,
        library_root: str | Path,
        repository: DocumentRepository,
        states: DocumentStateStore,
        editor_manager: EditorManager,
        desktop_launcher: DesktopLauncher,
        watcher: FilesystemWatcher | None = None,
        parent_widget: QWidget | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.library_root = Path(library_root).expanduser().resolve(strict=False)
        self.repository = repository
        self.states = states
        self.editor_manager = editor_manager
        self.desktop_launcher = desktop_launcher
        self.watcher = watcher
        self.parent_widget = parent_widget
        self._move_in_progress = False

    def switch_workspace_root(
        self,
        library_root: str | Path,
        watcher: FilesystemWatcher,
    ) -> None:
        """Rebind the existing safe file actions to one newly active workspace."""
        self.library_root = Path(library_root).expanduser().resolve(strict=False)
        self.watcher = watcher

    def rename_document(self, document: DocumentEntry) -> bool:
        """Prompt for and safely apply a new RTF filename."""
        stored = self.repository.get(document.path)
        if stored is None:
            self._warn("Rename Failed", "The selected RTF file no longer exists.")
            return False

        if not self._prepare_open_editor(stored):
            return False

        new_name, accepted = QInputDialog.getText(
            self.parent_widget,
            "Rename RTF File",
            "Enter the new filename:",
            text=stored.filename,
        )
        if not accepted:
            return False

        normalized_name = self._normalise_document_name(new_name)
        if normalized_name is None:
            return False
        new_name = normalized_name
        if new_name == stored.filename:
            return True

        old_path = stored.path
        new_path = old_path.with_name(new_name)
        if path_lexists(new_path):
            self._warn(
                "Rename Failed",
                f"A file named '{new_name}' already exists in this folder.",
            )
            return False

        try:
            expected_state = current_file_state(old_path)
        except OSError as error:
            self._error("Rename Failed", f"Could not verify the RTF file:\n\n{error}")
            return False

        state = self.states.get(old_path)

        try:
            if current_file_state(old_path) != expected_state:
                raise FileStateChangedError(
                    "The RTF file changed before it could be renamed."
                )
            rename_path_no_replace(old_path, new_path)
            fsync_directory(new_path.parent)
            stat_result = new_path.stat()
        except FileStateChangedError as error:
            self._warn("Rename Cancelled", str(error))
            return False
        except OSError as error:
            self._error("Rename Failed", f"Could not rename the RTF file:\n\n{error}")
            return False

        self.repository.move_path(
            old_path,
            new_path,
            filename=new_path.name,
            display_name=self._display_name(new_path),
            folder=self._relative_folder(new_path),
            modified=stat_result.st_mtime,
            size=stat_result.st_size,
        )
        page = state.editor_page if state is not None else None
        if page is not None:
            page.document = stored
            page._refresh_header()

        self._request_rescan()
        self.document_renamed.emit(stored, old_path)
        self.status_message.emit(f"Renamed {old_path.name} to {new_name}")
        return True

    def remove_document(self, document: DocumentEntry) -> bool:
        """Confirm and permanently remove one RTF document."""
        stored = self.repository.get(document.path)
        if stored is None:
            return True

        if not self._prepare_open_editor(stored):
            return False

        try:
            expected_state = current_file_state(stored.path)
        except OSError as error:
            self._warn("Remove Cancelled", f"Could not verify the RTF file:\n\n{error}")
            return False

        response = QMessageBox.question(
            self.parent_widget,
            "Remove RTF File",
            f"Permanently remove '{stored.filename}' from the workspace?\n\n"
            "This deletes the file from disk and cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if response != QMessageBox.StandardButton.Yes:
            return False

        path = stored.path
        if not path_identity_matches(path, expected_state):
            self._warn(
                "Remove Cancelled",
                "The RTF file was replaced after the confirmation dialog. Nothing was deleted.",
            )
            return False
        try:
            path.unlink()
            fsync_directory(path.parent)
        except FileNotFoundError:
            pass
        except OSError as error:
            self._error("Remove Failed", f"Could not remove the RTF file:\n\n{error}")
            return False

        self.repository.remove(path)
        self._request_rescan()
        self.document_removed.emit(stored)
        self.status_message.emit(f"Removed {stored.filename}")
        return True

    def import_files(
        self,
        paths: list[str | Path],
        destination_folder: str | Path | None = None,
    ) -> int:
        """
        Copy external RTF files directly into one workspace folder.

        The whole batch triggers one asynchronous rescan. Existing internal
        move operations remain separate and continue using move_document().
        """
        folder = self._validated_folder(
            destination_folder or self.library_root,
            allow_root=True,
        )
        if folder is None:
            return 0

        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            self._error(
                "Import Failed",
                f"Could not prepare the destination folder:\n\n{error}",
            )
            return 0

        imported = 0
        skipped = 0

        for supplied in paths:
            source = Path(supplied).expanduser().resolve(strict=False)
            if not source.is_file() or source.suffix.casefold() not in RTF_EXTENSIONS:
                skipped += 1
                continue

            destination = (folder / source.name).resolve(strict=False)
            try:
                destination.relative_to(self.library_root)
            except ValueError:
                skipped += 1
                continue

            # Dropping a workspace file back onto its current folder is a
            # harmless no-op, not a conflict.
            try:
                same_file = source == destination or (
                    source.exists()
                    and destination.exists()
                    and source.samefile(destination)
                )
            except OSError:
                same_file = source == destination
            if same_file:
                skipped += 1
                continue

            if destination.exists():
                decision = self._resolve_import_conflict(source, destination)
                if decision is None:
                    skipped += 1
                    continue
                destination = decision

            temporary = destination.with_name(
                f".{destination.name}.importing"
            )
            try:
                shutil.copy2(source, temporary)
                temporary.replace(destination)
            except OSError as error:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
                self._error(
                    "Import Failed",
                    f"Could not import {source.name}:\n\n{error}",
                )
                skipped += 1
                continue

            imported += 1
            self.document_imported.emit(destination)

        if imported:
            self._request_rescan()
            relative = (
                "."
                if folder == self.library_root
                else folder.relative_to(self.library_root).as_posix()
            )
            message = (
                f"Imported {imported} RTF file"
                f"{'s' if imported != 1 else ''} into {relative}"
            )
            if skipped:
                message += f" · {skipped} skipped"
            self.status_message.emit(message)
        elif skipped:
            self.status_message.emit(
                f"No RTF files imported · {skipped} item"
                f"{'s' if skipped != 1 else ''} skipped"
            )
        return imported

    def open_external_editor(self, document: DocumentEntry) -> bool:
        """Open a document in a host graphical editor or desktop default."""
        stored = self.repository.get(document.path)
        if stored is None or not stored.path.exists():
            self._warn("Open Failed", "The RTF file no longer exists.")
            return False

        if self.desktop_launcher.open_in_external_editor(stored.path):
            self.status_message.emit(
                f"Opened {stored.filename} in an external editor."
            )
            return True

        self._error(
            "External Editor Failed",
            "No suitable host editor or desktop file opener could be started.",
        )
        return False



    def open_document_folder(self, document: DocumentEntry) -> bool:
        """Open the selected document's containing folder in the file manager."""
        stored = self.repository.get(document.path)
        if stored is None or not stored.path.exists():
            self._warn("Open Folder Failed", "The RTF file no longer exists.")
            return False

        folder = stored.path.parent
        if self.desktop_launcher.open_path(folder):
            self.status_message.emit(
                f"Opened the folder containing {stored.filename}."
            )
            return True

        self._error(
            "Open Folder Failed",
            "The host system file manager could not be started.",
        )
        return False


    def _normalise_document_name(self, value: str) -> str | None:
        """Validate and normalize a user-entered RTF filename."""
        filename = value.strip()
        if not filename:
            return None

        if Path(filename).suffix.casefold() not in RTF_EXTENSIONS:
            filename += ".rtf"

        if (
            Path(filename).name != filename
            or "/" in filename
            or "\\" in filename
            or "\x00" in filename
        ):
            self._warn(
                "Invalid Filename",
                "Enter a filename only, without folder separators.",
            )
            return None

        if filename.casefold() in RTF_EXTENSIONS or filename.casefold() == "..rtf":
            self._warn(
                "Invalid Filename",
                "Enter a valid RTF filename.",
            )
            return None

        return filename

    def duplicate_document(self, document: DocumentEntry) -> Path | None:
        """Create a safe copy beside the selected document."""
        stored = self.repository.get(document.path)
        if stored is None or not stored.path.is_file():
            self._warn("Duplicate Failed", "The RTF file no longer exists.")
            return None

        default_name = f"{stored.path.stem}-copy{stored.path.suffix}"
        name, accepted = QInputDialog.getText(
            self.parent_widget,
            "Duplicate RTF File",
            "New RTF filename:",
            text=default_name,
        )
        if not accepted:
            return None

        filename = self._normalise_document_name(name)
        if filename is None:
            return None

        destination = stored.path.with_name(filename).resolve(strict=False)
        if not stored.external:
            try:
                destination.relative_to(self.library_root)
            except ValueError:
                self._warn(
                    "Duplicate Failed",
                    "The destination would be outside the active workspace.",
                )
                return None

        if destination.exists():
            self._warn(
                "Duplicate Failed",
                f"'{destination.name}' already exists.",
            )
            return None

        try:
            shutil.copy2(stored.path, destination)
        except OSError as error:
            self._error("Duplicate Failed", str(error))
            return None

        self.status_message.emit(f"Created {destination.name}.")
        self._request_rescan()
        return destination


    def create_file(self, folder_path: str | Path) -> Path | None:
        """Create a new RTF document inside a workspace folder."""
        folder = self._validated_folder(folder_path, allow_root=True)
        if folder is None:
            return None

        name, accepted = QInputDialog.getText(
            self.parent_widget,
            "New RTF File",
            f"RTF filename in {folder.name or 'workspace'}:",
            text="new_document.rtf",
        )
        if not accepted or not name.strip():
            return None

        normalized_name = self._normalise_document_name(name)
        if normalized_name is None:
            return None
        name = normalized_name

        destination = (folder / name).resolve(strict=False)
        if destination.exists():
            self._warn(
                "RTF File Exists",
                f"A file named '{name}' already exists in this folder.",
            )
            return None

        template = (
            Path(__file__).resolve().parent.parent
            / "assets"
            / "templates"
            / "default-document.rtf"
        )
        temporary: Path | None = None
        descriptor: int | None = None
        try:
            payload = template.read_bytes()
            if not payload.startswith(b"{\\rtf") or not payload.rstrip().endswith(b"}"):
                raise ValueError("The bundled new-document template is invalid.")
            descriptor, raw_path = tempfile.mkstemp(
                prefix=f".{destination.name}.",
                suffix=".creating",
                dir=folder,
            )
            temporary = Path(raw_path)
            with os.fdopen(descriptor, "wb") as handle:
                descriptor = None
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            install_new_file_from_temp(temporary, destination)
            temporary = None
            fsync_directory(folder)
        except (OSError, ValueError) as error:
            self._error(
                "Create RTF File Failed",
                f"Could not create the RTF file:\n\n{error}",
            )
            return None
        finally:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            if temporary is not None:
                try:
                    temporary.unlink()
                except OSError:
                    pass

        self._request_rescan()
        self.document_created.emit(destination)
        self.status_message.emit(f"Created {destination.name} in {folder.name}")
        return destination

    def create_folder(self, parent_path: str | Path) -> Path | None:
        """Create a new subfolder inside a workspace folder."""
        parent = self._validated_folder(parent_path, allow_root=True)
        if parent is None:
            return None

        name, accepted = QInputDialog.getText(
            self.parent_widget,
            "New Folder",
            f"Folder name inside {parent.name or 'workspace'}:",
            text="New Folder",
        )
        if not accepted or not name.strip():
            return None

        name = name.strip()
        if Path(name).name != name or name in {".", ".."}:
            self._warn(
                "Invalid Folder Name",
                "Enter one folder name without path separators.",
            )
            return None

        destination = (parent / name).resolve(strict=False)
        if destination.exists():
            self._warn(
                "Folder Exists",
                f"A file or folder named '{name}' already exists here.",
            )
            return None

        try:
            destination.mkdir()
        except OSError as error:
            self._error(
                "Create Folder Failed",
                f"Could not create the folder:\n\n{error}",
            )
            return None

        self._request_rescan()
        self.status_message.emit(f"Created folder {destination.name}")
        return destination


    def move_document(self, source_path: str | Path, destination_folder: str | Path) -> bool:
        """Move a RTF document atomically to another workspace folder."""
        if self._move_in_progress:
            self.status_message.emit("A document move is already in progress.")
            return False

        self._move_in_progress = True
        try:
            document = self.repository.get(source_path)
            if document is None:
                self._warn(
                    "Move Failed",
                    "The dragged RTF file is no longer in the workspace.",
                )
                return False

            folder = self._validated_folder(destination_folder, allow_root=True)
            if folder is None:
                return False
            current_parent = document.path.parent.resolve(strict=False)
            destination_parent = folder.resolve(strict=False)
            same_folder = current_parent == destination_parent
            if not same_folder:
                try:
                    same_folder = (
                        current_parent.exists()
                        and destination_parent.exists()
                        and current_parent.samefile(destination_parent)
                    )
                except OSError:
                    same_folder = False
            if same_folder:
                self.status_message.emit(
                    f"{document.filename} is already in {folder.name or 'the workspace root'}."
                )
                return True

            old_path = document.path.resolve(strict=False)
            destination = (folder / document.filename).resolve(strict=False)

            # Final defensive guard. Even if a symlink or alternate path
            # spelling bypassed the parent comparison, never perform or emit
            # a move when source and destination identify the same file.
            same_destination = old_path == destination
            if not same_destination and old_path.exists() and destination.exists():
                try:
                    same_destination = old_path.samefile(destination)
                except OSError:
                    same_destination = False
            if same_destination:
                self.status_message.emit(
                    f"{document.filename} is already in {folder.name or 'the workspace root'}."
                )
                return True

            if destination.exists():
                box = QMessageBox(self.parent_widget)
                box.setIcon(QMessageBox.Icon.Warning)
                box.setWindowTitle("RTF File Already Exists")
                box.setText(
                    f"'{document.filename}' already exists in '{folder.name}'."
                )
                keep_both = box.addButton(
                    "Keep Both", QMessageBox.ButtonRole.AcceptRole
                )
                replace = box.addButton(
                    "Replace", QMessageBox.ButtonRole.DestructiveRole
                )
                cancel = box.addButton(
                    "Cancel", QMessageBox.ButtonRole.RejectRole
                )
                box.exec()
                clicked = box.clickedButton()

                if clicked not in (keep_both, replace):
                    # Cancel, title-bar close, and unknown results are all
                    # conservative no-ops. Never replace a file implicitly.
                    return False
                if clicked is keep_both:
                    counter = 2
                    while destination.exists():
                        destination = folder / (
                            f"{old_path.stem} ({counter}){old_path.suffix}"
                        )
                        counter += 1
                elif clicked is replace:
                    existing = self.repository.get(destination)
                    if existing is not None and not self.editor_manager.close_document(existing):
                        return False

                    try:
                        destination.unlink()
                    except OSError as error:
                        self._error(
                            "Move Failed",
                            f"Could not replace the destination file:\n\n{error}",
                        )
                        return False

                    # Remove the replaced repository entry before re-keying
                    # the source document to the same destination path.
                    if existing is not None:
                        self.repository.remove(existing.path)

            try:
                shutil.move(str(old_path), str(destination))
                stat_result = destination.stat()
            except OSError as error:
                self._error(
                    "Move Failed",
                    f"Could not move the RTF file:\n\n{error}",
                )
                return False

            # Re-key the same canonical DocumentEntry and all connected UI state.
            # This avoids the destructive remove/add cycle that previously
            # accumulated stale widgets during repeated moves.
            moved = self.repository.move_path(
                old_path,
                destination,
                filename=destination.name,
                display_name=self._display_name(destination),
                folder=self._relative_folder(destination),
                modified=stat_result.st_mtime,
                size=stat_result.st_size,
            )
            if moved is None:
                self._error(
                    "Move Failed",
                    "The file moved on disk, but its workspace state could "
                    "not be updated. Refresh the workspace.",
                )
                self._request_rescan()
                return False

            self._request_rescan()
            self.status_message.emit(
                f"Moved {old_path.name} to {folder.name}"
            )
            return True
        finally:
            self._move_in_progress = False

    def open_folder_external(self, folder_path: str | Path) -> bool:
        """Open a workspace folder in the host system file manager."""
        folder = self._validated_folder(folder_path, allow_root=True)
        if folder is None:
            return False

        if self.desktop_launcher.open_path(folder):
            self.status_message.emit(f"Opened {folder.name} externally.")
            return True

        self._error(
            "Open Folder Failed",
            "The host system file manager could not be started.",
        )
        return False

    def rename_folder(self, folder_path: str | Path) -> bool:
        """Safely rename a workspace subfolder."""
        folder = self._validated_folder(folder_path, allow_root=False)
        if folder is None:
            return False
        if not self.editor_manager.close_pages_in_folder(folder):
            return False
        new_name, accepted = QInputDialog.getText(
            self.parent_widget, "Rename Folder", "New folder name:", text=folder.name
        )
        if not accepted or not new_name.strip():
            return False
        new_name = new_name.strip()
        if Path(new_name).name != new_name or new_name in {".", ".."}:
            self._warn("Invalid Folder Name", "Enter a folder name without path separators.")
            return False
        destination = folder.with_name(new_name).resolve(strict=False)
        if destination.exists():
            self._warn("Rename Failed", f"'{new_name}' already exists in this location.")
            return False
        try:
            folder.rename(destination)
        except OSError as error:
            self._error("Rename Failed", f"Could not rename the folder:\n\n{error}")
            return False
        self.editor_manager.close_folder_page(folder)
        self._request_rescan()
        self.folder_renamed.emit(folder, destination)
        self.status_message.emit(f"Renamed {folder.name} to {new_name}")
        return True

    def remove_folder(self, folder_path: str | Path) -> bool:
        """Permanently remove a workspace subfolder after a typed confirmation."""
        folder = self._validated_folder(folder_path, allow_root=False)
        if folder is None:
            return False
        if not self.editor_manager.close_pages_in_folder(folder):
            return False
        files = sum(1 for path in folder.rglob("*") if path.is_file())
        directories = sum(1 for path in folder.rglob("*") if path.is_dir())
        typed, accepted = QInputDialog.getText(
            self.parent_widget,
            "Remove Folder Permanently",
            f"This will permanently delete '{folder.name}', including {files} file(s) "
            f"and {directories} subfolder(s).\n\nType the folder name to confirm:",
        )
        if not accepted or typed.strip() != folder.name:
            return False
        try:
            shutil.rmtree(folder)
        except OSError as error:
            self._error("Remove Folder Failed", f"Could not remove the folder:\n\n{error}")
            return False
        self.editor_manager.close_folder_page(folder)
        self._request_rescan()
        self.folder_removed.emit(folder)
        self.status_message.emit(f"Removed folder {folder.name}")
        return True

    def _validated_folder(self, folder_path: str | Path, *, allow_root: bool) -> Path | None:
        folder = Path(folder_path).expanduser().resolve(strict=False)
        try:
            folder.relative_to(self.library_root)
        except ValueError:
            self._error("Unsafe Folder Operation", "The selected folder is outside the workspace.")
            return None
        if folder == self.library_root and not allow_root:
            self._warn("Workspace Protected", "The workspace root cannot be renamed or removed here.")
            return None
        if not folder.is_dir():
            self._warn("Folder Not Found", "The selected folder no longer exists.")
            return None
        return folder

    def _prepare_open_editor(self, document: DocumentEntry) -> bool:
        state = self.states.get(document.path)
        page = state.editor_page if state is not None else None
        if page is None:
            return True
        if not page.can_close():
            return False
        # can_close() may permit discarding while leaving the page alive.
        # Reload here so discarded text cannot follow a rename operation.
        if page.is_modified:
            return page.load_from_disk(show_errors=False)
        return True

    def _resolve_import_conflict(
        self,
        source: Path,
        destination: Path,
    ) -> Path | None:
        box = QMessageBox(self.parent_widget)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("RTF File Already Exists")
        box.setText(
            f"'{destination.name}' already exists in "
            f"'{destination.parent.name or 'the workspace root'}'."
        )
        replace = box.addButton("Replace", QMessageBox.ButtonRole.DestructiveRole)
        rename = box.addButton("Keep Both", QMessageBox.ButtonRole.AcceptRole)
        cancel = box.addButton("Skip", QMessageBox.ButtonRole.RejectRole)
        box.exec()

        clicked = box.clickedButton()
        if clicked is replace:
            return destination
        if clicked is rename:
            return self._unique_destination(
                destination.parent,
                source.stem,
                source.suffix,
            )
        if clicked is cancel:
            return None
        return None

    @staticmethod
    def _unique_destination(folder: Path, stem: str, suffix: str) -> Path:
        """Return an unused sibling path in the requested destination folder."""
        counter = 2
        candidate = folder / f"{stem} ({counter}){suffix}"
        while candidate.exists():
            counter += 1
            candidate = folder / f"{stem} ({counter}){suffix}"
        return candidate.resolve(strict=False)

    def _request_rescan(self) -> None:
        if self.watcher is not None:
            self.watcher.request_rescan()

    def _relative_folder(self, path: Path) -> str:
        try:
            parent = path.parent.relative_to(self.library_root)
        except ValueError:
            return str(path.parent)
        return "" if str(parent) == "." else str(parent)

    @staticmethod
    def _display_name(path: Path) -> str:
        return path.stem.replace("-", " ").replace("_", " ").title()

    def _warn(self, title: str, message: str) -> None:
        QMessageBox.warning(self.parent_widget, title, message)

    def _error(self, title: str, message: str) -> None:
        QMessageBox.critical(self.parent_widget, title, message)


# Backwards-compatible name for any earlier imports.
FileActions = FileActionsController
