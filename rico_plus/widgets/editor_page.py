# Rico Plus
# Copyright (C) 2026 Bruno Machado
# SPDX-License-Identifier: GPL-3.0-or-later
"""One lazy, Ribbon-only Ricopad editor page."""

from __future__ import annotations

from html import escape
from pathlib import Path

from PyQt6.QtCore import QEvent, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence, QPainter, QPalette
from PyQt6.QtWidgets import QApplication, QLabel, QStyle, QStyleOptionFocusRect, QVBoxLayout, QWidget

from rico_plus.models.document import DocumentEntry
from rico_plus.models.document_repository import DocumentRepository
from rico_plus.services.config_service import ConfigService
from rico_plus.widgets.rtf_editor import RtfEditorWindow


class _PersistentNativeFocusFrame(QWidget):
    """Paint Qt's own focus primitive continuously over the editor viewport.

    This deliberately reuses the platform style instead of inventing a colour.
    On Breeze it preserves the same dimmer focus-frame treatment that appears
    transiently when the Ricopad editor owns keyboard focus.
    """

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
        return super().eventFilter(watched, event)

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
    """Embed the canonical RTF editor without duplicating its command surface."""

    status_message = pyqtSignal(str)
    external_editor_requested = pyqtSignal(object)
    containing_folder_requested = pyqtSignal(object)
    rename_requested = pyqtSignal(object)
    remove_requested = pyqtSignal(object)
    duplicate_requested = pyqtSignal(object)
    undo_redo_changed = pyqtSignal(bool, bool)
    formatting_state_changed = pyqtSignal()
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

        # Preserve the authoritative Plus-family document-page heading: the
        # display name and full path sit above the editor surface.
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.title_label = QLabel(self)
        self.title_label.setWordWrap(True)
        layout.addWidget(self.title_label)

        self.engine = RtfEditorWindow(
            str(document.path),
            config_directory=config.path.parent,
            embedded=True,
            parent=self,
        )
        self.loaded_successfully = (
            self.engine.file_path is not None
            and Path(self.engine.file_path).resolve(strict=False)
            == document.path
        )
        self.engine.save_as_target_validator = self._save_as_target_available
        theme = str(config.get("app_theme", "system"))
        if theme in {"system", "dark", "light"}:
            # Rico Plus owns the application palette.  Keep Ricopad's hidden
            # engine preference in sync for icon/dialog lookups, but never let
            # an embedded editor re-theme QApplication.
            self.engine.appimage_theme = theme
        icon_set = str(config.get("editor_icon_set", "new"))
        if icon_set in {"classic", "new"}:
            self.engine.appimage_icon_set = icon_set
            self.engine.refresh_portable_icons()
        # Managed Rico Plus pages use the same follow/override contract as
        # the established Plus contract. Ricopad remains the renderer, but its standalone saved
        # canvas choice is not allowed to compete with the Plus preference.
        self.engine.managed_canvas_light_provider = self._canvas_is_light
        self.apply_theme()
        # Rico Plus owns the application Ribbon/menu/shortcuts. The embedded
        # Ricopad instance is retained only as the canonical RTF document engine.
        # Its own application chrome is never mounted or published by the shell.
        self.engine.ribbon_tabs.hide()
        self.engine.toolbar_stack.hide()
        self.engine.app_menu_bar.hide()
        layout.addWidget(self.engine, 1)
        self.editor = self.engine.visual_editor
        self._native_focus_frame = _PersistentNativeFocusFrame(self.editor.viewport())

        self._connect_engine()
        self._configure_shortcut_scope()
        self.editor.document().modificationChanged.connect(
            self._on_modification_changed
        )
        self.editor.document().undoAvailable.connect(self._emit_history)
        self.editor.document().redoAvailable.connect(self._emit_history)
        self.editor.currentCharFormatChanged.connect(
            lambda *_args: self.formatting_state_changed.emit()
        )
        self.editor.cursorPositionChanged.connect(
            self.formatting_state_changed.emit
        )
        self._on_modification_changed(False)
        self._refresh_header()

    @property
    def view_only(self) -> bool:
        return bool(self.engine.view_only)

    @property
    def is_modified(self) -> bool:
        return bool(
            not self.engine.content_saved
            or self.editor.document().isModified()
        )

    def _connect_engine(self) -> None:
        self.engine.new_requested.connect(
            lambda: self.new_requested.emit(self.document.path.parent)
        )
        self.engine.workspace_requested.connect(self.workspace_requested)
        self.engine.dashboard_requested.connect(self.dashboard_requested)
        self.engine.exit_requested.connect(self.exit_requested)
        self.engine.save_and_new_requested.connect(
            lambda: self.save_and_new_requested.emit(self)
        )
        self.engine.save_and_dashboard_requested.connect(
            lambda: self.save_and_dashboard_requested.emit(self)
        )
        self.engine.save_and_exit_requested.connect(
            lambda: self.save_and_exit_requested.emit(self)
        )
        self.engine.external_editor_requested.connect(
            lambda: self.external_editor_requested.emit(self.document)
        )
        self.engine.containing_folder_requested.connect(
            lambda: self.containing_folder_requested.emit(self.document)
        )
        self.engine.rename_requested.connect(
            lambda: self.rename_requested.emit(self.document)
        )
        self.engine.delete_requested.connect(
            lambda: self.remove_requested.emit(self.document)
        )
        self.engine.duplicate_requested.connect(
            lambda: self.duplicate_requested.emit(self.document)
        )
        self.engine.files_dropped.connect(
            lambda paths: self.external_files_dropped.emit(
                paths, self.document.path.parent
            )
        )
        self.engine.file_path_changed.connect(self._on_file_path_changed)

    def _configure_shortcut_scope(self) -> None:
        """Make the Plus shell the single QAction shortcut owner."""
        for action in self.engine.findChildren(QAction):
            action.setShortcut(QKeySequence())
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)

    def _save_as_target_available(self, path: Path) -> bool:
        """Reject only targets owned by a different live editor page."""
        target = self.repository.get(path)
        return bool(
            target is None
            or target is self.document
            or not target.loaded
        )

    def _on_file_path_changed(self, old_path: str, new_path: str) -> None:
        self.path_changed.emit(
            self,
            Path(old_path).resolve(strict=False),
            Path(new_path).resolve(strict=False),
        )
        # The repository rebind happens in the manager; refresh once that
        # synchronous signal path has completed so the visible path is current.
        QTimer.singleShot(0, self._refresh_header)

    def _emit_history(self, *_args) -> None:
        document = self.editor.document()
        self.undo_redo_changed.emit(
            document.isUndoAvailable(), document.isRedoAvailable()
        )

    def _on_modification_changed(self, modified: bool) -> None:
        # QTextDocument is authoritative. During a successful save Ricopad
        # clears this flag while its internal synchronization guard is active;
        # content_saved is updated immediately afterwards. Consulting its old
        # value here left the sidebar permanently marked "edited".
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

    def save_to_disk(self) -> bool:
        saved = bool(self.engine.save_file())
        if saved:
            self.repository.set_dirty(self.document.path, False)
            self._refresh_metadata()
            self.status_message.emit(f"Saved {self.document.filename}")
        return saved

    def load_from_disk(self, *, show_errors: bool = True) -> bool:
        loaded = bool(
            self.engine.load_file(
                str(self.document.path),
                check_changes=False,
                show_error=show_errors,
            )
        )
        if loaded:
            self.repository.set_dirty(self.document.path, False)
            self._refresh_metadata()
        return loaded

    def can_close(self) -> bool:
        if not self.is_modified:
            return True
        accepted = bool(self.engine.check_save_changes())
        if accepted and not self.is_modified:
            self.repository.set_dirty(self.document.path, False)
            self._refresh_metadata()
        return accepted

    def set_view_only(self, enabled: bool) -> None:
        enabled = bool(enabled)
        self.engine.view_only = enabled
        self.engine.persist_view_only = enabled
        self.engine._view_only_prompt_shown = False
        self.engine.view_only_action.blockSignals(True)
        self.engine.view_only_action.setChecked(enabled)
        self.engine.view_only_action.blockSignals(False)
        self.engine._update_mode_capabilities()
        self.engine.update_title()
        self.engine.update_status_counts()
        self.engine.statusBar().showMessage(
            "Lock Editor enabled."
            if enabled
            else "Editing mode enabled.",
            2500,
        )

    def set_view_mode(self, mode: str, *, persist: bool = True) -> None:
        del persist
        self.set_view_only(mode == "view")
        self.view_mode = "view" if self.view_only else "edit"

    def apply_preferences(self) -> None:
        self.engine.apply_preferences()
        # Ricopad may load its standalone canvas preference above.  Rico Plus
        # immediately reapplies its own shared follow/override preference.
        self.apply_theme()

    def _canvas_is_light(self) -> bool:
        stored = self.config.get("editor_canvas_light")
        follows_app = bool(
            self.config.get("editor_canvas_follows_app_theme", True)
        )
        if not follows_app and isinstance(stored, bool):
            return stored
        base = QApplication.instance().palette().color(QPalette.ColorRole.Base)
        return base.lightness() >= 140

    def apply_theme(self) -> None:
        self.engine.refresh_portable_icons()
        # Preserve single-owner Plus behavior: derive the managed canvas from the
        # Plus config/application palette on every apply.  The embedded Ricopad
        # action state is only a reflection of that value, never a second source.
        self.engine.editor_canvas_theme = (
            "light" if self._canvas_is_light() else "dark"
        )
        self.engine.apply_editor_canvas_theme(update_action=True)
        frame = getattr(self, "_native_focus_frame", None)
        if frame is not None:
            frame.update()

    def _refresh_header(self) -> None:
        # Exact Plus-family heading grammar, adapted only from Markdown module
        # naming to Rico's RTF DocumentEntry model.
        dirty = " [Unsaved]" if self.document.dirty else ""
        display_name = escape(self.document.display_name)
        path_text = escape(str(self.document.path))
        self.title_label.setText(
            f"<h2>{display_name}{dirty}</h2>"
            f"{path_text}"
        )
        self.engine.file_path = str(self.document.path)
        self.engine.update_title()
        self.engine.update_status_counts()

    def _refresh_metadata(self) -> None:
        try:
            info = self.document.path.stat()
        except OSError:
            return
        self.document.modified = info.st_mtime
        self.document.size = info.st_size
        self.repository.document_changed.emit(self.document)
