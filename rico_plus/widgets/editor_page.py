# Rico Plus
# Copyright (C) 2026 Bruno Machado
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This module deliberately follows the authoritative Plus implementation EditorPage ownership model:
# the page owns managed-document lifecycle/state and hosts one editor component.
# Ricopad remains authoritative for RTF semantics and rich-text commands.
"""One lazily-created editor page for an RTF document.

Responsibilities (restored from the authoritative Plus implementation integration pattern):
- load and save one managed document
- synchronize Qt's native modified flag with DocumentRepository
- expose one real editor component, never a nested application window
- own the Plus file heading and managed-document state
- expose editor commands/state to MainWindow without leaking editor internals
- detect/represent managed-page external-change state
- expose external-editor, rename, duplicate and remove signals

The page does not rename/delete workspace files itself. Those operations remain
with FileActionsController, matching the family ownership boundary.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

from PyQt6.QtCore import QEvent, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence, QPainter, QPalette, QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QStyle,
    QStyleOptionFocusRect,
    QVBoxLayout,
    QWidget,
)

from rico_plus.models.document import DocumentEntry
from rico_plus.models.document_repository import DocumentRepository
from rico_plus.services.config_service import ConfigService
from rico_plus.widgets.rtf_editor import RicopadEditorWidget


class _PersistentNativeFocusFrame(QWidget):
    """Use Qt's own focus primitive without inventing a Rico-specific border."""

    def __init__(self, target: QWidget) -> None:
        super().__init__(target)
        self._target = target
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        target.installEventFilter(self)
        self._sync_geometry()
        self.show()
        self.raise_()

    def _sync_geometry(self) -> None:
        self.setGeometry(self._target.rect())
        self.raise_()
        self.update()

    def eventFilter(self, watched, event):
        if watched is self._target and event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Show,
            QEvent.Type.PaletteChange,
            QEvent.Type.StyleChange,
        ):
            QTimer.singleShot(0, self._sync_geometry)
        return QWidget.eventFilter(self, watched, event)

    def paintEvent(self, event) -> None:
        del event
        option = QStyleOptionFocusRect()
        option.initFrom(self._target)
        option.rect = self.rect().adjusted(1, 1, -2, -2)
        option.state |= (
            QStyle.StateFlag.State_HasFocus
            | QStyle.StateFlag.State_KeyboardFocusChange
        )
        option.backgroundColor = self._target.palette().color(QPalette.ColorRole.Base)
        painter = QPainter(self)
        self._target.style().drawPrimitive(
            QStyle.PrimitiveElement.PE_FrameFocusRect,
            option,
            painter,
            self._target,
        )


class EditorPage(QWidget):
    """Managed RTF editor page following the authoritative Plus implementation page contract."""

    external_editor_requested = pyqtSignal(object)
    containing_folder_requested = pyqtSignal(object)
    rename_requested = pyqtSignal(object)
    remove_requested = pyqtSignal(object)
    duplicate_requested = pyqtSignal(object)
    undo_redo_changed = pyqtSignal(bool, bool)
    formatting_state_changed = pyqtSignal()
    status_message = pyqtSignal(str)
    preferences_changed = pyqtSignal()
    external_files_dropped = pyqtSignal(object, object)
    new_requested = pyqtSignal(object)
    workspace_requested = pyqtSignal()
    dashboard_requested = pyqtSignal()
    exit_requested = pyqtSignal()
    save_and_new_requested = pyqtSignal(object)
    save_and_dashboard_requested = pyqtSignal(object)
    save_and_exit_requested = pyqtSignal(object)
    path_changed = pyqtSignal(object, object, object)

    def __init__(
        self,
        document: DocumentEntry,
        repository: DocumentRepository,
        config: ConfigService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.document = document
        self.repository = repository
        self.config = config
        self.view_mode = "edit"
        self._header_visible = bool(config.get("show_file_header", True))
        self._status_visible = bool(config.get("show_status_bar", True))
        self._external_change_pending = False

        # Ricopad is an editor component here, not the owner of the application.
        # Keep this private: MainWindow talks to EditorPage, just as authoritative Plus implementation
        # talks to its EditorPage rather than reaching into CodeEditor internals.
        self._surface = RicopadEditorWidget(
            str(document.path),
            config_directory=config.path.parent,
            parent=self,
        )
        self.editor = self._surface.visual_editor
        self.loaded_successfully = (
            self._surface.file_path is not None
            and Path(self._surface.file_path).resolve(strict=False) == document.path
        )
        self._surface.save_as_target_validator = self._save_as_target_available

        self._build_ui()
        self._connect_signals()
        self._configure_editor_shortcut_scope()
        self._apply_managed_preferences()
        self._on_modification_changed(False)
        self._refresh_header()

    # ------------------------------------------------------------------
    # Marko-style page construction / ownership
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        self.title_label = QLabel(self)
        self.title_label.setWordWrap(True)
        self.title_label.setVisible(self._header_visible)
        root.addWidget(self.title_label)

        self.external_banner = QFrame(self)
        self.external_banner.setFrameShape(QFrame.Shape.StyledPanel)
        banner_layout = QHBoxLayout(self.external_banner)
        self.external_label = QLabel(
            "This file changed on disk after it was opened.", self.external_banner
        )
        self.external_label.setWordWrap(True)
        banner_layout.addWidget(self.external_label, 1)
        reload_external = QPushButton("Reload from Disk", self.external_banner)
        reload_external.clicked.connect(self._reload_external_change)
        save_version_as = QPushButton("Save Version As…", self.external_banner)
        save_version_as.clicked.connect(self._save_editor_version_as)
        banner_layout.addWidget(reload_external)
        banner_layout.addWidget(save_version_as)
        self.external_banner.hide()
        root.addWidget(self.external_banner)

        # No second Ricopad application gutter. The 12 px Plus page margin above
        # is the one and only managed-page outer margin, matching authoritative Plus implementation.
        self._surface.setMinimumSize(0, 0)
        self.editor.setMinimumSize(0, 0)
        root.addWidget(self._surface, 1)

        self._native_focus_frame = _PersistentNativeFocusFrame(self.editor.viewport())

    def _connect_signals(self) -> None:
        self._surface.new_requested.connect(
            lambda: self.new_requested.emit(self.document.path.parent)
        )
        self._surface.workspace_requested.connect(self.workspace_requested)
        self._surface.dashboard_requested.connect(self.dashboard_requested)
        self._surface.exit_requested.connect(self.exit_requested)
        self._surface.save_and_new_requested.connect(
            lambda: self.save_and_new_requested.emit(self)
        )
        self._surface.save_and_dashboard_requested.connect(
            lambda: self.save_and_dashboard_requested.emit(self)
        )
        self._surface.save_and_exit_requested.connect(
            lambda: self.save_and_exit_requested.emit(self)
        )
        self._surface.external_editor_requested.connect(
            lambda: self.external_editor_requested.emit(self.document)
        )
        self._surface.containing_folder_requested.connect(
            lambda: self.containing_folder_requested.emit(self.document)
        )
        self._surface.rename_requested.connect(
            lambda: self.rename_requested.emit(self.document)
        )
        self._surface.delete_requested.connect(
            lambda: self.remove_requested.emit(self.document)
        )
        self._surface.duplicate_requested.connect(
            lambda: self.duplicate_requested.emit(self.document)
        )
        self._surface.files_dropped.connect(
            lambda paths: self.external_files_dropped.emit(
                paths, self.document.path.parent
            )
        )
        self._surface.file_path_changed.connect(self._on_file_path_changed)

        self.editor.document().modificationChanged.connect(self._on_modification_changed)
        self.editor.document().undoAvailable.connect(self._emit_history)
        self.editor.document().redoAvailable.connect(self._emit_history)
        self.editor.currentCharFormatChanged.connect(
            lambda *_args: self.formatting_state_changed.emit()
        )
        self.editor.cursorPositionChanged.connect(self.formatting_state_changed.emit)

        # The workspace watcher updates scanner metadata in the repository.
        # EditorPage, not the file header, owns the external-change warning:
        # this connection remains active even when File Header or Collapsed
        # Mode hides title_label.
        self.repository.document_changed.connect(
            self._on_repository_document_changed
        )

    # ------------------------------------------------------------------
    # Public editor interface. MainWindow must use this interface only.
    # ------------------------------------------------------------------
    @property
    def view_only(self) -> bool:
        return bool(self._surface.view_only)

    @property
    def is_modified(self) -> bool:
        return bool(
            not self._surface.content_saved
            or self.editor.document().isModified()
        )

    def editor_action(self, name: str) -> QAction | None:
        action = getattr(self._surface, name, None)
        return action if isinstance(action, QAction) else None

    def trigger_editor_action(self, name: str) -> None:
        action = self.editor_action(name)
        if action is not None and action.isEnabled():
            action.trigger()

    def call_editor(self, method: str, *args):
        callback = getattr(self._surface, method, None)
        if callable(callback):
            result = callback(*args)
            self.formatting_state_changed.emit()
            return result
        return None

    def set_selected_font(self, font) -> None:
        self.call_editor("set_selected_font", font)

    def set_selected_font_size(self, text: str) -> None:
        self.call_editor("set_selected_font_size", text)

    def set_alignment(self, value) -> None:
        self.call_editor("set_alignment", value)

    def apply_heading(self, level: int) -> None:
        self.call_editor("apply_heading", int(level))

    def set_line_spacing(self, value: int) -> None:
        self.call_editor("set_line_spacing", int(value))

    def show_properties_dialog(self) -> None:
        self.call_editor("show_properties_dialog")

    def show_page_setup_dialog(self) -> None:
        self.call_editor("show_page_setup_dialog")

    def print_document(self) -> None:
        self.call_editor("print_document")

    def export_pdf(self) -> None:
        self.call_editor("export_pdf")

    def save_as_file(self) -> None:
        self.call_editor("save_as_file")

    def open_documentation(self) -> None:
        self.call_editor("open_documentation")

    def refresh_editor_icons(self) -> None:
        self._surface.refresh_portable_icons()

    def set_editor_icon_set(self, icon_set: str) -> None:
        icon_set = str(icon_set).strip().lower()
        if icon_set not in {"classic", "new"}:
            return
        self._surface.appimage_icon_set = icon_set
        self._surface.appimage_icon_set_override = None
        self._surface.refresh_portable_icons()

    def set_editor_app_theme(self, theme: str) -> None:
        self._surface.appimage_theme = theme
        self._surface.refresh_portable_icons()

    def editor_action_state(self, name: str) -> tuple[bool, bool]:
        action = self.editor_action(name)
        if action is None:
            return False, False
        return bool(action.isEnabled()), bool(action.isChecked())

    def editor_group_action(self, group_name: str, key) -> QAction | None:
        group = getattr(self._surface, group_name, None)
        if isinstance(group, dict):
            action = group.get(key)
            return action if isinstance(action, QAction) else None
        return None

    def sync_ribbon_selectors(self, ribbon) -> None:
        # ShellRibbon's compatibility routine expects the Ricopad command
        # component. This adapter keeps that dependency inside EditorPage.
        ribbon.sync_from_engine(self._surface)

    # ------------------------------------------------------------------
    # Managed-document lifecycle
    # ------------------------------------------------------------------
    def _configure_editor_shortcut_scope(self) -> None:
        """The Plus MainWindow is the only application shortcut owner."""
        for action in self._surface.findChildren(QAction):
            action.setShortcut(QKeySequence())
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)

    def _save_as_target_available(self, path: Path) -> bool:
        target = self.repository.get(path)
        return bool(target is None or target is self.document or not target.loaded)

    def _on_file_path_changed(self, old_path: str, new_path: str) -> None:
        self.path_changed.emit(
            self,
            Path(old_path).resolve(strict=False),
            Path(new_path).resolve(strict=False),
        )
        QTimer.singleShot(0, self._refresh_header)

    def _emit_history(self, *_args) -> None:
        document = self.editor.document()
        self.undo_redo_changed.emit(
            document.isUndoAvailable(), document.isRedoAvailable()
        )

    def _on_modification_changed(self, modified: bool) -> None:
        dirty = bool(modified)
        self.repository.set_dirty(self.document.path, dirty)
        self._refresh_header()
        if not dirty:
            QTimer.singleShot(0, self._synchronise_clean_metadata)
        self._emit_history()

    def _synchronise_clean_metadata(self) -> None:
        if self.editor.document().isModified():
            return
        self.repository.set_dirty(self.document.path, False)
        self._refresh_metadata()

    def load_from_disk(self, *, show_errors: bool = True) -> bool:
        loaded = bool(
            self._surface.load_file(
                str(self.document.path),
                check_changes=False,
                show_error=show_errors,
            )
        )
        if loaded:
            self.repository.set_dirty(self.document.path, False)
            self._external_change_pending = False
            self.external_banner.hide()
            self._refresh_metadata()
        return loaded

    def save_to_disk(self) -> bool:
        saved = bool(self._surface.save_file())
        if saved:
            self.repository.set_dirty(self.document.path, False)
            self._external_change_pending = False
            self.external_banner.hide()
            self._refresh_metadata()
            self.status_message.emit(f"Saved {self.document.filename}")
        return saved

    def can_close(self) -> bool:
        if not self.is_modified:
            return True
        accepted = bool(self._surface.check_save_changes())
        if accepted and not self.is_modified:
            self.repository.set_dirty(self.document.path, False)
            self._refresh_metadata()
        return accepted

    def _current_disk_signature(self):
        """Return Ricopad's exact-byte signature for the managed disk copy."""
        return self._surface._disk_signature(str(self.document.path))

    def _on_repository_document_changed(self, changed: DocumentEntry) -> None:
        """Surface watcher-detected external changes for this open document.

        Scanner metadata is only the notification trigger.  The decision is
        made with Ricopad's exact byte signature, so timestamp-only touches do
        not produce a false warning and same-size content changes are detected
        whenever the watcher reports the file.
        """
        if changed is not self.document and changed.path != self.document.path:
            return

        self._refresh_header()
        loaded_signature = self._surface.file_disk_signature
        if loaded_signature is None:
            return

        disk_signature = self._current_disk_signature()
        if disk_signature is None:
            return

        if disk_signature == loaded_signature:
            if self._external_change_pending:
                self._external_change_pending = False
                self.external_banner.hide()
            return

        self._external_change_pending = True
        # This banner is a direct child of EditorPage's root layout, not of
        # title_label/file-header UI.  Header visibility must never suppress it.
        self.external_banner.show()

    def confirm_reload(self) -> None:
        self._reload_external_change()

    def _reload_external_change(self) -> None:
        if self.is_modified:
            response = QMessageBox.question(
                self,
                "Discard Editor Changes",
                "Reloading will discard your unsaved editor changes. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if response != QMessageBox.StandardButton.Yes:
                return
        self.load_from_disk(show_errors=True)

    def _save_editor_version_as(self) -> bool:
        """Preserve the Rico editor version without touching the changed disk copy.

        The source path that triggered the external-change warning is forbidden
        as a Save As target.  A successful Save As rebinds this editor page to
        the newly chosen path, while the externally modified source remains on
        disk and in the Workspace as a separate document.
        """
        source_path = self.document.path.resolve(strict=False)
        suffix = source_path.suffix or ".rtf"
        suggested = source_path.with_name(f"{source_path.stem} - Rico Version{suffix}")
        counter = 2
        while suggested.exists():
            suggested = source_path.with_name(
                f"{source_path.stem} - Rico Version {counter}{suffix}"
            )
            counter += 1

        saved = bool(
            self._surface.save_as_file(
                initial_path=str(suggested),
                forbidden_paths=(source_path,),
                dialog_title="Save Version As — Rico Plus",
                forbidden_message=(
                    "Choose a different filename. The original file changed "
                    "externally and will be left untouched."
                ),
            )
        )
        if not saved:
            return False

        saved_path = Path(self._surface.file_path).resolve(strict=False)
        self._external_change_pending = False
        self.external_banner.hide()
        self._refresh_metadata()
        self.status_message.emit(
            f"Saved Rico Plus version as {saved_path.name}; external disk copy preserved."
        )
        return True

    # ------------------------------------------------------------------
    # Plus-owned page presentation/preferences
    # ------------------------------------------------------------------
    def set_header_visible(self, visible: bool) -> None:
        self._header_visible = bool(visible)
        self.title_label.setVisible(self._header_visible)

    def set_status_visible(self, visible: bool) -> None:
        self._status_visible = bool(visible)
        self._surface.show_status_bar = self._status_visible
        bar = getattr(self._surface, "app_status_bar", None)
        if bar is not None:
            bar.setVisible(self._status_visible)
        action = getattr(self._surface, "status_bar_action", None)
        if isinstance(action, QAction):
            action.blockSignals(True)
            action.setChecked(self._status_visible)
            action.blockSignals(False)

    def scroll_to_top(self) -> None:
        """Reset the editor viewport to the document start.

        Locked Mode uses this when a document is opened, matching the Plus-family
        read-only opening behavior without changing normal editable reopening.
        """
        cursor = self.editor.textCursor()
        cursor.clearSelection()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.editor.setTextCursor(cursor)
        self.editor.ensureCursorVisible()
        bar = self.editor.verticalScrollBar()
        bar.setValue(bar.minimum())

    def set_view_only(self, enabled: bool) -> None:
        enabled = bool(enabled)
        self._surface.view_only = enabled
        self._surface.persist_view_only = enabled
        self._surface._view_only_prompt_shown = False
        action = getattr(self._surface, "view_only_action", None)
        if isinstance(action, QAction):
            action.blockSignals(True)
            action.setChecked(enabled)
            action.blockSignals(False)
        self._surface._update_mode_capabilities()
        self._surface.update_title()
        self._surface.update_status_counts()
        self.status_message.emit(
            "Locked Mode enabled." if enabled else "Editing mode enabled."
        )
        self.formatting_state_changed.emit()

    def set_view_mode(self, mode: str, *, persist: bool = True) -> None:
        del persist
        self.set_view_only(mode == "view")
        self.view_mode = "view" if self.view_only else "edit"

    def apply_preferences(self) -> None:
        self._apply_managed_preferences()

    def show_editor_status(self, message: str, timeout: int = 0) -> None:
        """Show a transient message in this document's editor status bar."""
        self._surface._show_status_message(message, timeout)

    def _apply_managed_preferences(self) -> None:
        theme = str(self.config.get("app_theme", "system"))
        if theme in {"system", "dark", "light"}:
            self._surface.appimage_theme = theme
        icon_set = str(self.config.get("editor_icon_set", "new"))
        if icon_set in {"classic", "new"}:
            self._surface.appimage_icon_set = icon_set
        self._surface.managed_canvas_light_provider = self._canvas_is_light
        self._surface.apply_preferences()
        self.set_status_visible(self._status_visible)
        self.apply_theme()

    def _canvas_is_light(self) -> bool:
        stored = self.config.get("editor_canvas_light")
        follows_app = bool(self.config.get("editor_canvas_follows_app_theme", True))
        if not follows_app and isinstance(stored, bool):
            return stored
        base = QApplication.instance().palette().color(QPalette.ColorRole.Base)
        return base.lightness() >= 140

    def apply_theme(self) -> None:
        self._surface.refresh_portable_icons()
        self._surface.editor_canvas_theme = "light" if self._canvas_is_light() else "dark"
        self._surface.apply_editor_canvas_theme(update_action=True)
        self._native_focus_frame.update()

    # ------------------------------------------------------------------
    # Heading / metadata, owned by the Plus page
    # ------------------------------------------------------------------
    def _refresh_header(self) -> None:
        dirty = " [Unsaved]" if self.document.dirty else ""
        display_name = escape(self.document.display_name)
        path_text = escape(str(self.document.path))
        self.title_label.setText(f"<h2>{display_name}{dirty}</h2>{path_text}")
        self._surface.file_path = str(self.document.path)
        self._surface.update_title()
        self._surface.update_status_counts()

    def _refresh_metadata(self) -> None:
        try:
            info = self.document.path.stat()
        except OSError:
            return
        self.document.modified = info.st_mtime
        self.document.size = info.st_size
        self.repository.document_changed.emit(self.document)
