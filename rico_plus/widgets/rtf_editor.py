#!/usr/bin/env python3
# ==============================================================================
# Rico Plus - workspace RTF editor
# Copyright (C) 2026 Bruno Machado
#
# GPLv3-or-later
#
# Version: 0.0.3
# ==============================================================================

import base64
import html
import json
import hashlib
import locale
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PyQt6.QtCore import (
    QBuffer, QByteArray, QDateTime, QEvent, QIODevice, QLocale, QMimeData, QRect, QRectF,
    QRegularExpression, QSize, QSizeF, Qt, QTimer, QUrl, pyqtSignal,
)
from PyQt6.QtGui import (
    QAction, QActionGroup, QBrush, QColor, QDesktopServices, QFont, QFontDatabase, QIcon,
    QImage, QImageReader, QKeySequence, QPainter, QPalette, QPixmap, QTextBlockFormat, QTextCharFormat,
    QTextCursor, QTextDocument, QTextDocumentFragment, QTextFormat, QTextImageFormat, QTextListFormat, QTextTableFormat,
)
from PyQt6.QtPrintSupport import QPrintDialog, QPrinter
from PyQt6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QColorDialog,
    QComboBox,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFontComboBox,
    QFontDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QInputDialog,
    QMenu,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QSizePolicy,
    QSpinBox,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QToolTip,
    QVBoxLayout,
    QWizard,
    QWizardPage,
    QWidget,
)

from rico_plus.rich_text_support import is_safe_link_target, sanitise_qt_html
from rico_plus.services.rtf_new_document import (
    NewDocumentDefaults, build_new_document_rtf_payload,
)
from rico_plus.rtf_codec import (
    _qt_brush_colour, _rtf_clear_automatic_foreground,
    decode_rtf, document_to_rtf_with_properties, populate_qtextdocument_from_rtf_model,
    RTF_SYNTHETIC_STRUCTURE_BLOCK, RTF_TABLE_AUTOFIT_PROPERTY,
    RTF_AUTOMATIC_CONTRAST_PROPERTY,
    MAX_RTF_TABLE_ROWS, MAX_RTF_TABLE_COLUMNS, MAX_RTF_TABLE_CELLS,
)

APP_NAME = "Rico Plus"
APP_VERSION = "0.0.3"
RIBBON_BUTTON_SIZE = 52
RIBBON_ICON_SIZE = 32
RIBBON_FONT_FAMILY_WIDTH = RIBBON_BUTTON_SIZE * 2

FONT_SIZE_STEPS = (
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 16, 18, 20,
    22, 24, 26, 28, 32, 36, 40, 44, 48, 54, 60, 66, 72, 80, 88,
    96, 108, 120, 144, 168, 192, 216, 240, 288, 320, 384, 448, 512,
)
MAX_SEARCH_MATCHES = 10_000
MAX_PASTE_CHARACTERS = 5_000_000
MAX_DOCUMENT_CHARACTERS = 25_000_000
MAX_CLIPBOARD_HTML_CHARACTERS = 10_000_000
RICOPAD_INLINE_RICH_MIME = "application/x-ricopad-inline-richtext"
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MiB responsiveness limit
MAX_CONFIG_FILE_SIZE = 1024 * 1024  # 1 MiB; preferences should remain tiny.
MAX_EMBEDDED_IMAGE_SIZE = 12 * 1024 * 1024
MAX_IMAGE_SOURCE_SIZE = 48 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
RTF_EXTENSIONS = {".rtf"}
DOCUMENT_EXTENSIONS = RTF_EXTENSIONS
IMAGE_EXTENSIONS = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
GITHUB_URL = "https://github.com/brunonlinespace/rico-plus"
ISSUES_URL = GITHUB_URL + "/issues"



def read_bounded_bytes(file_path, limit, *, label="file"):
    """Read at most ``limit`` bytes and fail if the file grows beyond it."""
    with open(file_path, "rb") as handle:
        data = handle.read(int(limit) + 1)
    if len(data) > int(limit):
        raise ValueError(f"The {label} exceeds Rico Plus's safety limit.")
    return data


def fsync_directory(path):
    """Best-effort directory sync after an atomic replacement on POSIX."""
    if os.name == "nt":
        return
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    try:
        descriptor = os.open(path, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError:
        pass


def preference_bool(data, key, default):
    value = data.get(key, default)
    return value if isinstance(value, bool) else bool(default)


def preference_text(data, key, default, *, limit=512):
    value = data.get(key, default)
    if not isinstance(value, str):
        return str(default)
    return value[:limit]




def normalise_windows_organisation_directory(appdata):
    """Migrate the earlier organisation directory spelling without data loss."""
    desired_name = "brunonlinespace"
    desired_path = os.path.join(appdata, desired_name)
    legacy_names = ("BrunoOnlineSpace", "brunoonlinespace")

    try:
        entries = list(os.scandir(appdata))
    except OSError:
        return desired_path

    if any(
        entry.is_dir(follow_symlinks=False) and entry.name == desired_name
        for entry in entries
    ):
        return desired_path

    legacy_entry = next(
        (
            entry for entry in entries
            if entry.is_dir(follow_symlinks=False) and entry.name in legacy_names
        ),
        None,
    )
    if legacy_entry is None:
        return desired_path

    temporary_path = None
    for counter in range(100):
        candidate = os.path.join(
            appdata,
            f".ricopad-org-migration-{os.getpid()}-{counter}",
        )
        if not os.path.exists(candidate):
            temporary_path = candidate
            break
    if temporary_path is None:
        return desired_path

    try:
        os.rename(legacy_entry.path, temporary_path)
        os.rename(temporary_path, desired_path)
    except OSError:
        try:
            if os.path.exists(temporary_path) and not os.path.exists(legacy_entry.path):
                os.rename(temporary_path, legacy_entry.path)
        except OSError:
            pass
    return desired_path


def platform_config_locations():
    """Return Rico Plus's private editor-preference location."""
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA") or os.path.join(
            os.path.expanduser("~"), "AppData", "Roaming"
        )
        organisation_directory = normalise_windows_organisation_directory(appdata)
        return os.path.join(organisation_directory, "Rico Plus"), ()

    config_directory = os.path.expanduser(
        "~/.config/brunonlinespace/rico-plus"
    )
    return config_directory, ()


def configure_platform_identity():
    """Apply a stable Windows shell identity while remaining cross-platform."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "brunonlinespace.RicoPlus"
        )
    except (AttributeError, OSError):
        pass


def host_process_environment():
    """Return a clean environment for launching host desktop applications."""
    environment = os.environ.copy()

    if sys.platform == "win32":
        return environment

    # Portable source runs should inherit the user's environment unchanged.
    if not (
        environment.get("APPDIR")
        or getattr(sys, "frozen", False)
    ):
        return environment

    appdir = environment.get("APPDIR")
    original_library_path = environment.pop(
        "LD_LIBRARY_PATH_ORIG",
        None,
    )
    if original_library_path is None:
        environment.pop("LD_LIBRARY_PATH", None)
    else:
        environment["LD_LIBRARY_PATH"] = original_library_path

    # Do not leak the bundled application's Qt/plugin configuration into a
    # character-map utility supplied by the host operating system.
    for variable in (
        "APPDIR",
        "APPIMAGE",
        "QT_PLUGIN_PATH",
        "QT_QPA_PLATFORM",
        "QT_QPA_PLATFORM_PLUGIN_PATH",
        "QT_QPA_PLATFORMTHEME",
        "QT_STYLE_OVERRIDE",
        "QML_IMPORT_PATH",
        "QML2_IMPORT_PATH",
    ):
        environment.pop(variable, None)

    if appdir and environment.get("PATH"):
        appdir_real = os.path.realpath(appdir)
        clean_path = []
        for entry in environment["PATH"].split(os.pathsep):
            if not entry:
                continue
            try:
                entry_real = os.path.realpath(entry)
                inside_appdir = os.path.commonpath(
                    (appdir_real, entry_real)
                ) == appdir_real
            except (OSError, ValueError):
                inside_appdir = False
            if not inside_appdir:
                clean_path.append(entry)
        environment["PATH"] = os.pathsep.join(clean_path)

    return environment


def appimage_theme_resources():
    """Return Rico Plus's bundled theme-resource locations.

    The historical helper name and packaged QSS resources are retained for
    preference/backward compatibility and AppImage availability detection.
    Dark and Light chrome follow the Plus-family palette-only theme model in
    both Portable/source and AppImage runtimes.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = []
    appdir = os.environ.get("APPDIR")
    if appdir:
        candidates.append(os.path.join(appdir, "usr", "share", "rico-plus", "styles"))
    candidates.extend((
        os.path.join(script_dir, "styles"),
        os.path.join(script_dir, "assets", "styles"),
        os.path.join(script_dir, "packaging", "appimage", "styles"),
        os.path.normpath(os.path.join(script_dir, "..", "assets", "styles")),
    ))
    for style_directory in candidates:
        resources = {
            "dark": os.path.join(style_directory, "breeze-dark.qss"),
            "light": os.path.join(style_directory, "breeze-light.qss"),
        }
        if all(os.path.isfile(path) for path in resources.values()):
            return resources
    return {}


def resource_path(*parts):
    """Return an asset path in source, portable, legacy, and AppImage layouts."""
    candidates = []
    appdir = os.environ.get("APPDIR")
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # PyInstaller places bundled data beside the frozen script location.
    candidates.append(os.path.join(script_dir, *parts))

    # Source-portable layout: implementation modules and assets share the
    # Rico Plus package directory.
    candidates.append(os.path.join(script_dir, "assets", *parts))

    # Compatibility with the earlier RC3 source/ subdirectory layout.
    candidates.append(
        os.path.normpath(os.path.join(script_dir, "..", "assets", *parts))
    )

    # Retain compatibility with the unpublished 2.3.x development layout.
    candidates.append(os.path.join(script_dir, "ricopad-assets", *parts))

    if appdir:
        candidates.append(os.path.join(appdir, *parts))
        candidates.append(
            os.path.join(appdir, "usr", "share", "rico-plus", *parts)
        )

    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return candidates[0]


# ---------- Rich editor widgets ----------

class SafeTextDocument(QTextDocument):
    """QTextDocument that never auto-loads external document resources."""

    def loadResource(self, resource_type, name):
        if resource_type in (
            QTextDocument.ResourceType.ImageResource,
            QTextDocument.ResourceType.StyleSheetResource,
        ):
            url = QUrl(name)
            if url.scheme().lower() != "data":
                return None
        return super().loadResource(resource_type, name)


class RichTextEdit(QTextEdit):
    """Visual editor with bounded clipboard/drop handling and safe resources."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDocument(SafeTextDocument(self))
        self.setAcceptDrops(True)
        # QTextEdit receives drop events primarily through its viewport.  Keep
        # both surfaces enabled so RTF file drops work consistently on Plasma,
        # X11/Wayland and in the frozen AppImage.
        self.viewport().setAcceptDrops(True)
        self.setUndoRedoEnabled(True)
        self._pending_full_paste = None
        self._full_paste_generation = 0

    def _reject_paste(self, message):
        window = self.window()
        if hasattr(window, "statusBar"):
            window.statusBar().showMessage(message, 5000)
        QApplication.beep()

    def _resulting_character_count(self, inserted_text_length):
        cursor = self.textCursor()
        current = max(0, self.document().characterCount() - 1)
        selected = abs(cursor.selectionEnd() - cursor.selectionStart())
        return current - selected + max(0, int(inserted_text_length))

    def _selection_is_full_document(self):
        cursor = self.textCursor()
        if not cursor.hasSelection():
            return False
        document_length = max(0, self.document().characterCount() - 1)
        return min(cursor.selectionStart(), cursor.selectionEnd()) == 0 and max(cursor.selectionStart(), cursor.selectionEnd()) >= document_length

    def _schedule_full_paste(self, kind, payload):
        self._full_paste_generation += 1
        generation = self._full_paste_generation
        self._pending_full_paste = (str(kind), str(payload))
        QTimer.singleShot(0, lambda: self._apply_pending_full_paste(generation))

    def _apply_pending_full_paste(self, generation):
        if generation != self._full_paste_generation or self.isReadOnly():
            return
        pending = self._pending_full_paste
        self._pending_full_paste = None
        if not pending:
            return
        kind, payload = pending
        if kind == "html":
            self.setHtml(payload)
        else:
            self.setPlainText(payload)
        self.document().setModified(True)
        self.moveCursor(QTextCursor.MoveOperation.End)
        self.setFocus()

    def dragEnterEvent(self, event):
        mime = event.mimeData()
        if mime.hasUrls() and any(url.isLocalFile() for url in mime.urls()):
            event.acceptProposedAction()
        elif mime.hasImage() or mime.hasText() or mime.hasHtml():
            super().dragEnterEvent(event)
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        mime = event.mimeData()
        if mime.hasUrls() and any(url.isLocalFile() for url in mime.urls()):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        files = [
            url.toLocalFile() for url in event.mimeData().urls()
            if url.isLocalFile() and os.path.isfile(url.toLocalFile())
        ]
        if files:
            image_files = [
                path for path in files
                if Path(path).suffix.lower() in IMAGE_EXTENSIONS
            ]
            document_files = [path for path in files if path not in image_files]
            window = self.window()
            for path in image_files:
                if hasattr(window, "insert_image_path"):
                    window.insert_image_path(path)
            if document_files and hasattr(window, "open_dropped_files"):
                window.open_dropped_files(document_files)
            event.acceptProposedAction()
            return
        super().dropEvent(event)

    def _insert_inline_rich_html(self, safe_html):
        """Insert one Rico Plus-copied paragraph selection without its HTML block wrapper."""
        fragment = QTextDocumentFragment.fromHtml(safe_html)
        temporary = QTextDocument()
        temporary_cursor = QTextCursor(temporary)
        temporary_cursor.insertFragment(fragment)
        block = temporary.begin()
        target = self.textCursor()
        target.beginEditBlock()
        iterator = block.begin()
        while not iterator.atEnd():
            source_fragment = iterator.fragment()
            if source_fragment.isValid():
                fmt = source_fragment.charFormat()
                if fmt.isImageFormat():
                    target.insertImage(fmt.toImageFormat())
                else:
                    target.insertText(source_fragment.text().replace("\u2029", ""), fmt)
            iterator += 1
        target.endEditBlock()
        self.setTextCursor(target)

    def insertFromMimeData(self, source):
        if self.isReadOnly():
            window = self.window()
            if hasattr(window, "explain_view_only_block"):
                window.explain_view_only_block()
            return
        if source.hasImage():
            image = source.imageData()
            if isinstance(image, QPixmap):
                image = image.toImage()
            if isinstance(image, QImage) and not image.isNull():
                window = self.window()
                if hasattr(window, "insert_image_data"):
                    window.insert_image_data(image)
                    return
        if source.hasHtml():
            try:
                raw_html = source.html()
            except Exception as exc:
                self._reject_paste(f"Clipboard HTML could not be read: {exc}")
                return
            if len(raw_html) > MAX_CLIPBOARD_HTML_CHARACTERS:
                self._reject_paste("Clipboard rich text is too large to paste safely.")
                return
            safe_html = sanitise_qt_html(raw_html)
            fragment = QTextDocumentFragment.fromHtml(safe_html)
            plain_length = len(fragment.toPlainText().replace("\x00", ""))
            if plain_length > MAX_PASTE_CHARACTERS or self._resulting_character_count(plain_length) > MAX_DOCUMENT_CHARACTERS:
                self._reject_paste("The rich-text paste would exceed Rico Plus's document safety limit.")
                return
            if self._selection_is_full_document():
                self._schedule_full_paste("html", safe_html)
                return
            if source.hasFormat(RICOPAD_INLINE_RICH_MIME):
                self._insert_inline_rich_html(safe_html)
                return
            self.textCursor().insertFragment(fragment)
            return
        if source.hasText():
            try:
                text = source.text().replace("\x00", "")
            except Exception as exc:
                self._reject_paste(f"Clipboard text could not be read: {exc}")
                return
            if len(text) > MAX_PASTE_CHARACTERS or self._resulting_character_count(len(text)) > MAX_DOCUMENT_CHARACTERS:
                self._reject_paste("The paste would exceed Rico Plus's document safety limit.")
                return
            if self._selection_is_full_document():
                self._schedule_full_paste("text", text)
                return
            self.textCursor().insertText(text)
            return
        self._reject_paste("Clipboard content could not be inserted safely.")

    def keyPressEvent(self, event):
        # WordPad-style visual shortcut: type three underscores and press Enter.
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            cursor = self.textCursor()
            block = cursor.block()
            if (
                not self.isReadOnly()
                and not cursor.hasSelection()
                and cursor.positionInBlock() == len(block.text())
                and block.text().strip() == "___"
            ):
                cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
                cursor.removeSelectedText()
                self.setTextCursor(cursor)
                window = self.window()
                if hasattr(window, "insert_horizontal_rule"):
                    window.insert_horizontal_rule()
                    event.accept()
                    return
        was_return=(event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter) and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier))
        previous_block=self.textCursor().block() if was_return else None
        previous_heading=(previous_block.headingLevel() if previous_block is not None and hasattr(previous_block,"headingLevel") else 0)
        previous_line_height=0.0
        previous_line_type=None
        previous_was_list=False
        previous_had_text=False
        if previous_block is not None:
            previous_format=previous_block.blockFormat()
            previous_was_list=previous_block.textList() is not None
            previous_had_text=bool(previous_block.text())
            try:
                previous_line_height=float(previous_format.lineHeight() or 0.0)
                previous_line_type=int(previous_format.lineHeightType())
            except Exception:
                pass
        super().keyPressEvent(event)
        if was_return and not self.isReadOnly() and previous_line_height>0 and previous_line_type is not None:
            # Qt normally inherits paragraph spacing on Return.  Only repair it
            # when inheritance actually changed.  In particular, do not rewrite
            # every newly-created *empty* body paragraph: repeated Return on a
            # clean document must stay native QTextEdit behaviour.  The repair
            # remains available for populated paragraphs and list transitions,
            # the cases that originally exposed spacing loss.
            cursor=self.textCursor(); current_format=cursor.blockFormat()
            try:
                current_line_height=float(current_format.lineHeight() or 0.0)
                current_line_type=int(current_format.lineHeightType())
            except Exception:
                current_line_height=0.0; current_line_type=None
            spacing_changed=(
                abs(current_line_height-previous_line_height)>0.01
                or current_line_type!=previous_line_type
            )
            if spacing_changed and (previous_had_text or previous_was_list):
                spacing=QTextBlockFormat()
                spacing.setLineHeight(previous_line_height, previous_line_type)
                cursor.mergeBlockFormat(spacing); self.setTextCursor(cursor)
        if was_return and previous_heading>0 and not self.isReadOnly():
            # Heading paragraphs end in Normal, WordPad-style. Qt can clear the
            # heading level while still inheriting the heading's block character
            # baseline; explicitly restore the document baseline so a second
            # Enter cannot resurrect 24 pt heading text.
            cursor=self.textCursor(); block_format=QTextBlockFormat(cursor.blockFormat())
            if hasattr(block_format,"setHeadingLevel"):
                block_format.setHeadingLevel(0)
            cursor.setBlockFormat(block_format)
            font=self.document().defaultFont(); plain=QTextCharFormat()
            try:
                families=font.families()
                if families: plain.setFontFamilies(families)
                elif font.family(): plain.setFontFamily(font.family())
            except Exception:
                if font.family(): plain.setFontFamily(font.family())
            if font.pointSizeF()>0: plain.setFontPointSize(font.pointSizeF())
            plain.setFontWeight(font.weight()); plain.setFontItalic(font.italic()); plain.setFontUnderline(font.underline()); plain.setFontStrikeOut(font.strikeOut())
            cursor.setBlockCharFormat(plain); self.setCurrentCharFormat(plain); self.setTextCursor(cursor)
        if was_return and not self.isReadOnly():
            # Block formatting can trigger another layout after QTextEdit has already
            # scrolled for Enter. Keep trailing empty paragraphs/caret visible.
            self.ensureCursorVisible()
            QTimer.singleShot(0, self.ensureCursorVisible)

    def mouseReleaseEvent(self, event):
        href = ""
        try:
            href = self.anchorAt(event.position().toPoint())
        except Exception:
            href = ""
        follow = bool(href) and (
            self.isReadOnly()
            or bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        )
        if follow:
            window = self.window()
            if hasattr(window, "open_document_link") and window.open_document_link(href):
                event.accept()
                self.setFocus()
                return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        window = self.window()
        if (
            event.modifiers() & Qt.KeyboardModifier.ControlModifier
            and hasattr(window, "adjust_zoom_from_wheel")
        ):
            window.adjust_zoom_from_wheel(event.angleDelta().y())
            event.accept()
            return
        super().wheelEvent(event)




class _EmbeddedMenuRegistry:
    """Non-widget menu registry used by embedded Ricopad engines.

    Rico Plus owns the only QMenuBar.  Embedded editors still construct their
    QMenus/QActions for command behavior, but never instantiate a child menu
    bar that Plasma can mistake for the application's global menu.
    """

    def __init__(self) -> None:
        self._menus = []

    def addMenu(self, menu):
        self._menus.append(menu)
        return menu

    def clear(self) -> None:
        self._menus.clear()

    def hide(self) -> None:
        return

    def setVisible(self, _visible: bool) -> None:
        return


# The retired standalone/embedded RtfEditorWindow implementation was removed in
# 0.0.3-exp6-r3. Rico Plus has one live rich-text host only:
# MainWindow -> EditorPage -> RicopadEditorWidget(QWidget).


# ============================================================================
# Extracted Ricopad editor component for Plus-family hosting
# ============================================================================

class RicopadEditorWidget(QWidget):
    """Ricopad's rich-text editor hosted as a real QWidget component.

    The component owns document/RTF/editing semantics. Rico Plus owns all
    application chrome (MainWindow, AppMenu, Ribbon, workspace and window title).
    No QMainWindow compatibility API and no hidden Ricopad Ribbon/menu bar are
    constructed on the managed-document path.
    """

    new_requested = pyqtSignal()
    workspace_requested = pyqtSignal()
    dashboard_requested = pyqtSignal()
    exit_requested = pyqtSignal()
    save_and_new_requested = pyqtSignal()
    save_and_dashboard_requested = pyqtSignal()
    save_and_exit_requested = pyqtSignal()
    external_editor_requested = pyqtSignal()
    containing_folder_requested = pyqtSignal()
    rename_requested = pyqtSignal()
    delete_requested = pyqtSignal()
    duplicate_requested = pyqtSignal()
    file_path_changed = pyqtSignal(str, str)
    files_dropped = pyqtSignal(object)
    status_message = pyqtSignal(str)

    def __init__(self, initial_file=None, *, config_directory=None, parent=None):
        QWidget.__init__(self, parent)
        self.setObjectName("ricopadEditorWidget")
        self.setMinimumSize(0, 0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAcceptDrops(True)

        self.file_path = None
        self.file_format = "rtf"
        self.file_encoding = "rtf"
        self.file_bom = b""
        self.file_newline = "\n"
        self.file_disk_signature = None
        self._source_rtf_payload = None
        self._source_rtf_semantic_signature = None
        self.content_saved = True
        self._loading = False
        self._syncing_editors = False
        self.view_only = False
        self._view_only_prompt_shown = False
        self.rtf_compatibility_warnings = ()
        self.rtf_document_properties = {}
        self._rtf_save_warning_acknowledged = False
        self.replace_dialog = None
        self.shortcuts_dialog = None
        self.about_dialog = None
        self.tutorial_dialog = None
        self.new_document_defaults_dialog = None
        self.search_matches = []
        self.search_results_truncated = False
        self.current_search_index = -1
        self.icon_bindings = []
        self.format_actions = []
        self.format_widgets = []
        self.visual_insert_actions = []
        self.editing_actions = []
        self.file_dependent_actions = []
        self.zoom_percent = 100
        self._visual_document_zoom_percent = 100
        self._visual_zoom_device = None
        self._skip_close_save_prompt = False
        self.save_as_target_validator = None

        default_config_directory, _import_candidates = platform_config_locations()
        self.config_directory = os.fspath(config_directory or default_config_directory)
        self.config_import_candidates = ()
        self.config_file = os.path.join(self.config_directory, "editor.json")
        self.new_document_template_file = os.path.join(self.config_directory, "new-document-template.rtf")

        self.appimage_theme_files = appimage_theme_resources()
        self.appimage_theme_available = bool(self.appimage_theme_files)
        requested_theme = os.environ.get("RICO_PLUS_APP_THEME", "").strip().lower()
        self.appimage_theme_override = requested_theme if requested_theme in ("system", "dark", "light") else None
        requested_icon_set = os.environ.get("RICO_PLUS_ICON_SET", "").strip().lower()
        self.appimage_icon_set_override = requested_icon_set if requested_icon_set in ("classic", "new") else None

        self.load_preferences()
        self.view_only = bool(self.persist_view_only)
        icon_path = resource_path("icons", "ricopad.png")
        if os.path.isfile(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        self.build_ui()
        self.bind_shortcuts()
        self._loading = True
        try:
            self.apply_preferences()
            self.visual_editor.document().setModified(False)
            self.content_saved = True
        finally:
            self._loading = False
        self.apply_native_style()
        self.update_title()
        self.update_status_counts()
        self.update_search_counter()
        self.update_formatting_state()

        if initial_file:
            self.load_file(initial_file, check_changes=False)
        QTimer.singleShot(0, self._focus_editor_after_startup)

    def build_ui(self):
        """Build only Ricopad's editor component; application chrome belongs to Rico Plus."""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Construct Ricopad's authoritative QActions/QMenus as command objects only.
        # No QMenuBar, QMainWindow, Ricopad Ribbon or standalone toolbar is created.
        self.app_menu_bar = _EmbeddedMenuRegistry()
        self.make_file_menu(); self.make_edit_menu(); self.make_format_menu()
        self.make_insert_menu(); self.make_view_menu(); self.make_help_menu()

        # The Find Bar is genuine editor UI and remains inside the editor component.
        self.search_container = QWidget(self)
        self.search_container.setObjectName("searchContainer")
        self.search_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        search_layout = QHBoxLayout(self.search_container)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(6)
        self.search_entry = QLineEdit(self.search_container); self.search_entry.setPlaceholderText("Find text")
        self.search_entry.returnPressed.connect(self.find_next); self.search_entry.textChanged.connect(self.on_search_text_changed)
        self.search_button = QPushButton(self.search_container); self.bind_custom_icon(self.search_button, "find"); self.search_button.setToolTip("Highlight all matches"); self.search_button.setFocusPolicy(Qt.FocusPolicy.NoFocus); self.search_button.clicked.connect(self.find_text_and_refocus)
        self.search_count_label = QLabel("0/0", self.search_container); self.search_count_label.setMinimumWidth(42); self.search_count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.search_previous_button = QToolButton(self.search_container); self.bind_custom_icon(self.search_previous_button, "previous"); self.search_previous_button.setToolTip("Previous Match (Shift+F3)"); self.search_previous_button.setShortcut(QKeySequence("Shift+F3")); self.search_previous_button.setFocusPolicy(Qt.FocusPolicy.NoFocus); self.search_previous_button.clicked.connect(self.find_previous)
        self.search_next_button = QToolButton(self.search_container); self.bind_custom_icon(self.search_next_button, "next"); self.search_next_button.setToolTip("Next Match (F3)"); self.search_next_button.setShortcut(QKeySequence("F3")); self.search_next_button.setFocusPolicy(Qt.FocusPolicy.NoFocus); self.search_next_button.clicked.connect(self.find_next)
        search_layout.addWidget(self.search_entry, 1); search_layout.addWidget(self.search_button); search_layout.addWidget(self.search_count_label); search_layout.addWidget(self.search_previous_button); search_layout.addWidget(self.search_next_button)
        self.main_layout.addWidget(self.search_container, 0)

        # Ricopad formatting-state widgets are retained as editor state/control objects.
        # They are not a second toolbar: Rico Plus presents them through ShellRibbon.
        self.format_controls = QWidget(self)
        self.format_controls.hide()
        self.format_toolbar = self.format_controls
        self.font_combo = QFontComboBox(self.format_controls); self.font_combo.setEditable(True); self.font_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        if self.font_combo.lineEdit() is not None:
            e = self.font_combo.lineEdit(); e.setReadOnly(True); e.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.font_combo.currentTextChanged.connect(self._reset_font_face_display); self.font_combo.currentFontChanged.connect(self.set_selected_font); self.font_combo.currentFontChanged.connect(lambda _font:self._reset_font_face_display())
        self.font_size_combo = QComboBox(self.format_controls); self.font_size_combo.setEditable(True); self.font_size_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert); self.font_size_combo.addItems(["8","9","10","11","12","14","16","18","20","24","28","32","36","48","72"]); self.font_size_combo.currentTextChanged.connect(self.set_selected_font_size)
        self.font_weight_combo = QComboBox(self.format_controls)
        for text, weight in (("Thin",QFont.Weight.Thin),("Extra Light",QFont.Weight.ExtraLight),("Light",QFont.Weight.Light),("Regular",QFont.Weight.Normal),("Medium",QFont.Weight.Medium),("Demi Bold",QFont.Weight.DemiBold),("Bold",QFont.Weight.Bold),("Extra Bold",QFont.Weight.ExtraBold),("Black",QFont.Weight.Black)):
            self.font_weight_combo.addItem(text, int(weight))
        self.font_weight_combo.currentIndexChanged.connect(self.apply_font_weight_from_combo)
        self.heading_combo = QComboBox(self.format_controls)
        for text, level in (("Normal",0),("Heading 1",1),("Heading 2",2),("Heading 3",3),("Heading 4",4),("Heading 5",5),("Heading 6",6)):
            self.heading_combo.addItem(text, level)
        self.heading_combo.currentIndexChanged.connect(self.apply_heading_from_combo)
        self.line_spacing_combo = QComboBox(self.format_controls)
        for label, value in (("1",100),("1.15",115),("1.5",150),("2",200)):
            self.line_spacing_combo.addItem(label, value)
        self.line_spacing_combo.currentIndexChanged.connect(self.apply_line_spacing_from_combo)

        def state_button(callback, *, checkable=False):
            button = QToolButton(self.format_controls); button.setCheckable(checkable); button.clicked.connect(callback); return button
        self.bold_button = state_button(self.toggle_bold, checkable=True)
        self.italic_button = state_button(self.toggle_italic, checkable=True)
        self.underline_button = state_button(self.toggle_underline, checkable=True)
        self.strike_button = state_button(self.toggle_strikethrough, checkable=True)
        self.text_colour_button = state_button(self.choose_text_colour)
        self.highlight_button = state_button(self.choose_highlight_colour)
        self.align_left_button = state_button(lambda:self.set_alignment(Qt.AlignmentFlag.AlignLeft), checkable=True)
        self.align_center_button = state_button(lambda:self.set_alignment(Qt.AlignmentFlag.AlignHCenter), checkable=True)
        self.align_right_button = state_button(lambda:self.set_alignment(Qt.AlignmentFlag.AlignRight), checkable=True)
        self.align_justify_button = state_button(lambda:self.set_alignment(Qt.AlignmentFlag.AlignJustify), checkable=True)
        self.bullet_button = state_button(self.toggle_bullet_list, checkable=True)
        self.symbols_button = state_button(self.show_symbols_popup)
        self.indent_button = state_button(lambda:self.change_indent(1))
        self.outdent_button = state_button(lambda:self.change_indent(-1))
        self.format_widgets.extend([self.font_combo,self.font_size_combo,self.font_weight_combo,self.heading_combo,self.line_spacing_combo,self.text_colour_button,self.highlight_button,self.bold_button,self.italic_button,self.underline_button,self.strike_button,self.align_left_button,self.align_center_button,self.align_right_button,self.align_justify_button,self.bullet_button,self.symbols_button,self.indent_button,self.outdent_button])

        self.visual_editor = RichTextEdit(self)
        self.visual_editor.setObjectName("visualEditor")
        self.visual_editor.setAcceptRichText(True)
        self.visual_editor.setAutoFormatting(QTextEdit.AutoFormattingFlag.AutoNone)
        self.visual_editor.setFrameShape(QFrame.Shape.NoFrame)
        self.visual_editor.setContentsMargins(0,0,0,0)
        self.visual_editor.setViewportMargins(0,0,0,0)
        self.visual_editor.setMinimumSize(0,0)
        self.visual_editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.visual_editor.document().setDocumentMargin(4.0)
        self.visual_editor.viewport().setMinimumSize(0,0)
        self.visual_editor.viewport().installEventFilter(self)
        self.visual_editor.currentCharFormatChanged.connect(self.update_formatting_state)
        self.visual_editor.cursorPositionChanged.connect(self.update_formatting_state)
        self.visual_editor.document().modificationChanged.connect(self.on_modification_changed)
        self.visual_editor.textChanged.connect(self.on_document_text_changed)
        self.visual_editor.installEventFilter(self)
        self.text_area = self.visual_editor
        self.main_layout.addWidget(self.visual_editor, 1)

        # Editor-specific information stays a normal child widget, never a nested
        # application status bar/QMainWindow surface.
        self.app_status_bar = QStatusBar(self)
        self.app_status_bar.setObjectName("ricopadEditorStatus")
        self.app_status_bar.setSizeGripEnabled(False)

        # Keep the persistent editor statistics geometrically stable.  Fixed
        # fields reserve their longest supported display; the message field
        # takes (and yields) all remaining horizontal space.  Word count is
        # deliberately absent: rescanning the full document on every edit made
        # multi-million-character RTF documents unnecessarily expensive.
        self.operation_mode_label = QLabel("Insert", self.app_status_bar)
        self.operation_mode_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        operation_width = self.operation_mode_label.fontMetrics().horizontalAdvance("Overwrite") + 4
        self.operation_mode_label.setFixedWidth(operation_width)

        self.zoom_label = QLabel("100%", self.app_status_bar)
        zoom_width = self.zoom_label.fontMetrics().horizontalAdvance("300%") + 4
        self.zoom_label.setFixedWidth(zoom_width)

        self.counter_label = QLabel("Chars 0", self.app_status_bar)
        maximum_counter_text = f"Chars {MAX_DOCUMENT_CHARACTERS:,}"
        counter_width = self.counter_label.fontMetrics().horizontalAdvance(maximum_counter_text) + 4
        self.counter_label.setFixedWidth(counter_width)

        self.status_message_label = QLabel("", self.app_status_bar)
        self.status_message_label.setMinimumWidth(0)
        self.status_message_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        self.status_message_label.setToolTip("")

        self._status_message_timer = QTimer(self)
        self._status_message_timer.setSingleShot(True)
        self._status_message_timer.timeout.connect(self._clear_status_message)

        self.app_status_bar.addWidget(self.operation_mode_label)
        self.app_status_bar.addWidget(self.zoom_label)
        self.app_status_bar.addWidget(self.counter_label)
        self.app_status_bar.addWidget(self.status_message_label, 1)
        self.main_layout.addWidget(self.app_status_bar, 0)

    def _clear_status_message(self):
        self.status_message_label.clear()
        self.status_message_label.setToolTip("")

    def _show_status_message(self, message, timeout=0):
        text = str(message)
        self.status_message_label.setText(text)
        self.status_message_label.setToolTip(text)
        if int(timeout) > 0:
            self._status_message_timer.start(int(timeout))
        else:
            self._status_message_timer.stop()
        self.status_message.emit(text)

    def apply_preferences(self):
        self.apply_editor_font()
        self.set_word_wrap_mode()
        self.search_bar_action.setChecked(self.show_search_bar)
        self.search_container.setVisible(self.show_search_bar)
        self.status_bar_action.blockSignals(True)
        self.status_bar_action.setChecked(bool(self.show_status_bar))
        self.status_bar_action.blockSignals(False)
        self.app_status_bar.setVisible(self.show_status_bar)
        self._update_mode_capabilities()
        self.apply_tab_width()
        self.apply_zoom_preference()

    def update_title(self):
        # Window titles are exclusively owned by Rico Plus MainWindow.
        self.editor_title = os.path.basename(self.file_path) if self.file_path else "Untitled.rtf"


    def load_preferences(self):
        self.word_wrap = True
        self.show_status_bar = True
        self.show_search_bar = True
        self.base_font_family = "Sans Serif"
        self.base_font_size = 12
        self.base_font_weight = "normal"
        self.base_font_slant = "roman"
        self.new_document_line_spacing = 115
        self.new_document_alignment = "left"
        self.appimage_theme = "system"
        self.appimage_icon_set = "new"
        self.editor_canvas_theme = None
        self.managed_canvas_light_provider = None
        self.zoom_percent = 100
        self.tab_width_spaces = 4
        self.persist_view_only = False
        self.print_header_enabled = True
        self.print_header_left = "&F"
        self.print_header_center = ""
        self.print_header_right = ""
        self.print_footer_enabled = True
        self.print_footer_left = ""
        self.print_footer_center = "Page &P of &N"
        self.print_footer_right = ""
        self.tutorial_seen = False

        source_file = self.config_file
        migrating_preferences = False
        if not os.path.isfile(source_file):
            for candidate in self.config_import_candidates:
                if candidate != self.config_file and os.path.isfile(candidate):
                    source_file = candidate
                    migrating_preferences = True
                    break
        try:
            raw = read_bounded_bytes(source_file, MAX_CONFIG_FILE_SIZE, label="preferences file")
            data = json.loads(raw.decode("utf-8", errors="strict"))
            if not isinstance(data, dict):
                raise ValueError("Preferences must contain a JSON object.")
            self.word_wrap = preference_bool(data, "word_wrap", True)
            status_default = data.get("show_counters", True)
            if not isinstance(status_default, bool):
                status_default = True
            self.show_status_bar = preference_bool(data, "show_status_bar", status_default)
            self.show_search_bar = preference_bool(data, "show_search_bar", True)
            self.base_font_family = preference_text(data, "font_family", "Sans Serif", limit=256)
            self.base_font_size = max(6, min(72, int(data.get("font_size", 12))))
            self.base_font_weight = preference_text(data, "font_weight", "normal", limit=32)
            self.base_font_slant = preference_text(data, "font_slant", "roman", limit=32)
            self.new_document_line_spacing = max(50, min(400, int(data.get("new_document_line_spacing", 115))))
            saved_alignment = preference_text(data, "new_document_alignment", "left", limit=16).lower()
            if saved_alignment in ("left", "centre", "right", "justify"):
                self.new_document_alignment = saved_alignment
            self.zoom_percent = max(50, min(300, int(data.get("zoom_percent", 100))))
            self.tab_width_spaces = max(1, min(16, int(data.get("tab_width_spaces", 4))))
            self.persist_view_only = preference_bool(data, "view_only", False)
            saved_theme = preference_text(
                data, "appimage_theme",
                preference_text(data, "overall_theme", "", limit=16),
                limit=16,
            ).lower()
            if saved_theme in ("system", "dark", "light"):
                self.appimage_theme = saved_theme
            saved_icon_set = preference_text(data, "appimage_icon_set", "new", limit=16).lower()
            if saved_icon_set in ("classic", "new"):
                self.appimage_icon_set = saved_icon_set
            saved_canvas = preference_text(data, "editor_canvas_theme", "", limit=16).lower()
            if saved_canvas in ("dark", "light"):
                self.editor_canvas_theme = saved_canvas
            self.print_header_enabled = preference_bool(data, "print_header_enabled", True)
            old_header = preference_text(data, "print_header_text", "&F")
            self.print_header_left = preference_text(data, "print_header_left", old_header)
            self.print_header_center = preference_text(data, "print_header_center", "")
            self.print_header_right = preference_text(data, "print_header_right", "")
            self.print_footer_enabled = preference_bool(data, "print_footer_enabled", True)
            old_footer = preference_text(data, "print_footer_text", "Page &P of &N")
            self.print_footer_left = preference_text(data, "print_footer_left", "")
            self.print_footer_center = preference_text(data, "print_footer_center", old_footer)
            self.print_footer_right = preference_text(data, "print_footer_right", "")
            self.tutorial_seen = preference_bool(data, "tutorial_seen", False)
        except (OSError, UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError):
            migrating_preferences = False
        if migrating_preferences:
            self.save_preferences()

    def save_preferences(self):
        data = {
            "word_wrap": self.word_wrap,
            "show_status_bar": self.show_status_bar,
            "show_counters": self.show_status_bar,
            "show_search_bar": self.show_search_bar,
            "font_family": self.base_font_family,
            "font_size": self.base_font_size,
            "font_weight": self.base_font_weight,
            "font_slant": self.base_font_slant,
            "new_document_line_spacing": int(self.new_document_line_spacing),
            "new_document_alignment": self.new_document_alignment,
            "zoom_percent": self.zoom_percent,
            "tab_width_spaces": self.tab_width_spaces,
            "view_only": bool(self.view_only),
            "print_header_enabled": self.print_header_enabled,
            "print_header_left": self.print_header_left,
            "print_header_center": self.print_header_center,
            "print_header_right": self.print_header_right,
            "print_header_text": self.print_header_left,
            "print_footer_enabled": self.print_footer_enabled,
            "print_footer_left": self.print_footer_left,
            "print_footer_center": self.print_footer_center,
            "print_footer_right": self.print_footer_right,
            "print_footer_text": self.print_footer_center,
            "tutorial_seen": bool(self.tutorial_seen),
        }
        data["appimage_theme"] = self.appimage_theme
        data["appimage_icon_set"] = self.appimage_icon_set
        if self.editor_canvas_theme in ("dark", "light"):
            data["editor_canvas_theme"] = self.editor_canvas_theme
        temporary = None
        descriptor = None
        try:
            os.makedirs(self.config_directory, mode=0o700, exist_ok=True)
            if os.name != "nt":
                try: os.chmod(self.config_directory, 0o700)
                except OSError: pass
            descriptor, temporary = tempfile.mkstemp(prefix=".ricopad-", suffix=".json.tmp", dir=self.config_directory, text=True)
            os.chmod(temporary, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                descriptor = None
                json.dump(data, handle, indent=2)
                handle.write("\n")
                handle.flush(); os.fsync(handle.fileno())
            os.replace(temporary, self.config_file); temporary = None
            fsync_directory(self.config_directory)
        except OSError:
            pass
        finally:
            if descriptor is not None:
                try: os.close(descriptor)
                except OSError: pass
            if temporary:
                try: os.remove(temporary)
                except OSError: pass

    def custom_icon_variant(self):
        """Choose icons from the active AppImage theme or the host system palette."""
        if self.appimage_theme_available:
            selected=self.effective_appimage_theme()
            if selected in ("light","dark"):
                return selected
        try:
            application=QApplication.instance()
            palette=application.palette() if application is not None else self.palette()
            colour=palette.color(QPalette.ColorRole.Window)
            return "dark" if colour.lightness()<128 else "light"
        except (AttributeError,RuntimeError):
            return "light"

    def effective_appimage_icon_set(self):
        """Return the one-launch override or saved AppImage icon-family choice."""
        return self.appimage_icon_set_override or self.appimage_icon_set

    def custom_icon(self, icon_name):
        """Load one bundled Rico Plus icon without consulting the host theme."""
        variant = self.custom_icon_variant()
        family = "ribbon-icons"
        if self.appimage_theme_available and self.effective_appimage_icon_set() == "classic":
            family = "ribbon-icons-classic"
        icon_path = resource_path(family, variant, f"{icon_name}.png")
        if os.path.isfile(icon_path):
            return QIcon(icon_path)
        # A branded application icon is safer than silently falling back to a
        # platform-dependent native glyph if a package is damaged.
        fallback = resource_path("icons", "ricopad.png")
        return QIcon(fallback) if os.path.isfile(fallback) else QIcon()

    def bind_custom_icon(self, target, icon_name):
        """Assign and register a bundled icon for theme-variant refreshes."""
        target.setIcon(self.custom_icon(icon_name))
        self.icon_bindings.append((target, icon_name))

    def refresh_portable_icons(self):
        """Refresh bundled icons after an AppImage theme change or host repaint."""
        for target, icon_name in tuple(self.icon_bindings):
            try:
                target.setIcon(self.custom_icon(icon_name))
            except RuntimeError:
                continue

    def add_menu_action(
        self, menu, label, callback, shortcut=None, *, checkable=False,
    ):
        """Create a shared command action used by the Ribbon."""
        action = QAction(label, self)
        action.setCheckable(bool(checkable))
        action.triggered.connect(callback)
        if shortcut:
            action.setShortcut(shortcut)
        menu.addAction(action)
        # Register the shared action on the window as well so its shortcut
        # remains active even though the legacy menu bar is hidden.
        self.addAction(action)
        return action

    def make_file_menu(self):
        menu = QMenu("&File", self); self.file_menu = menu; self.app_menu_bar.addMenu(menu)
        self.new_action = self.add_menu_action(
            menu, "New RTF File…", self.new_requested.emit,
            QKeySequence.StandardKey.New,
        )
        self.workspace_action = self.add_menu_action(
            menu, "Open / Manage Workspace…", self.workspace_requested.emit,
            QKeySequence.StandardKey.Open,
        )
        self.dashboard_action = self.add_menu_action(
            menu, "Show Dashboard", self.dashboard_requested.emit,
            QKeySequence("Ctrl+W"),
        )
        menu.addSeparator()
        self.save_action = self.add_menu_action(menu, "Save", self.save_file, QKeySequence.StandardKey.Save)
        self.save_as_action = self.add_menu_action(menu, "Save As…", self.save_as_file, QKeySequence.StandardKey.SaveAs)
        menu.addSeparator()
        self.properties_action = self.add_menu_action(menu, "Properties", self.show_properties_dialog)
        self.more_actions_menu = menu.addMenu("More Actions")
        self.external_editor_action = self.add_menu_action(self.more_actions_menu, "Open in External Editor", self.external_editor_requested.emit, QKeySequence("Ctrl+Shift+E"))
        self.more_actions_menu.addSeparator()
        self.rename_action = self.add_menu_action(self.more_actions_menu, "Rename…", self.rename_requested.emit, QKeySequence("F2"))
        self.delete_file_action = self.add_menu_action(self.more_actions_menu, "Delete File", self.delete_requested.emit)
        self.more_actions_menu.addSeparator()
        self.duplicate_file_action = self.add_menu_action(self.more_actions_menu, "Duplicate File", self.duplicate_requested.emit, QKeySequence("Ctrl+Shift+D"))
        self.open_folder_action = self.add_menu_action(self.more_actions_menu, "Open Containing Folder", self.containing_folder_requested.emit, QKeySequence("Ctrl+Shift+O"))
        self.file_dependent_actions.extend([self.external_editor_action,self.rename_action,self.delete_file_action,self.duplicate_file_action,self.open_folder_action])
        menu.addSeparator()
        self.print_action = self.add_menu_action(menu, "Print…", self.print_document, QKeySequence.StandardKey.Print)
        self.export_pdf_action = self.add_menu_action(menu, "Export PDF…", self.export_pdf, QKeySequence("Ctrl+Shift+P"))
        self.page_setup_action = self.add_menu_action(menu, "Page Setup…", self.show_page_setup_dialog)
        menu.addSeparator()
        self.save_new_action = self.add_menu_action(
            menu, "Save and New", self.save_and_new_requested.emit,
        )
        self.save_dashboard_action = self.add_menu_action(
            menu, "Save and Dashboard", self.save_and_dashboard_requested.emit,
            QKeySequence("Ctrl+Shift+W"),
        )
        self.save_exit_action = self.add_menu_action(
            menu, "Save and Exit", self.save_and_exit_requested.emit,
            QKeySequence("Ctrl+Shift+Q"),
        )
        self.exit_action = self.add_menu_action(
            menu, "Exit", self.exit_requested.emit,
            QKeySequence.StandardKey.Quit,
        )

    def make_edit_menu(self):
        menu=QMenu("&Edit",self); self.edit_menu=menu; self.app_menu_bar.addMenu(menu)
        self.undo_action=self.add_menu_action(menu,"Undo",self.text_area_undo,QKeySequence.StandardKey.Undo)
        self.redo_action=self.add_menu_action(menu,"Redo",self.text_area_redo,QKeySequence("Ctrl+Y")); menu.addSeparator()
        self.cut_action=self.add_menu_action(menu,"Cut",self.cut_selection,QKeySequence.StandardKey.Cut)
        self.copy_action=self.add_menu_action(menu,"Copy",self.copy_selection,QKeySequence.StandardKey.Copy)
        self.paste_action=self.add_menu_action(menu,"Paste",lambda:self.text_area.paste(),QKeySequence.StandardKey.Paste)
        self.paste_plain_action=self.add_menu_action(menu,"Paste Plain Text",self.paste_plain_text,QKeySequence("Ctrl+Shift+V")); menu.addSeparator()
        self.delete_text_action=self.add_menu_action(menu,"Delete",self.delete_selection,QKeySequence.StandardKey.Delete); menu.addSeparator()
        self.duplicate_line_action=self.add_menu_action(menu,"Duplicate Line / Selection",self.duplicate_current_line,QKeySequence("Ctrl+D"))
        self.delete_line_action=self.add_menu_action(menu,"Delete Line",self.delete_current_line,QKeySequence("Ctrl+Shift+K")); menu.addSeparator()
        self.select_all_action=self.add_menu_action(menu,"Select All",lambda:self.text_area.selectAll(),QKeySequence.StandardKey.SelectAll); menu.addSeparator()
        self.search_bar_action=QAction("Find Bar",self,checkable=True); self.search_bar_action.setShortcut(QKeySequence.StandardKey.Find); self.search_bar_action.setToolTip("Toggle the Find Bar"); self.search_bar_action.setStatusTip("Toggle the Find Bar"); self.search_bar_action.triggered.connect(self.toggle_search_bar); self.addAction(self.search_bar_action)
        self.replace_action=self.add_menu_action(menu,"Find and Replace…",self.show_replace_dialog,QKeySequence("Ctrl+H"))
        self.editing_actions.extend([self.undo_action,self.redo_action,self.cut_action,self.paste_action,self.paste_plain_action,self.delete_text_action,self.duplicate_line_action,self.delete_line_action,self.replace_action])

    def make_view_menu(self):
        menu=QMenu("&View",self); self.view_menu=menu; self.app_menu_bar.addMenu(menu)
        self.view_only_action=self.add_menu_action(menu,"Locked Mode",self.toggle_view_only,QKeySequence("F12"),checkable=True)
        self.status_bar_action=self.add_menu_action(menu,"Status Bar",self.toggle_status_bar,QKeySequence("Ctrl+Alt+Shift+S"),checkable=True)
        menu.addSeparator()
        self.wrap_action=self.add_menu_action(menu,"Word Wrap",self.toggle_word_wrap,QKeySequence("Ctrl+Alt+Shift+W"),checkable=True)
        menu.addAction(self.search_bar_action)
        self.editor_canvas_theme_action=self.add_menu_action(menu,"Dark Editor",self.toggle_editor_canvas_light,checkable=True)
        menu.addSeparator()
        zoom_menu=menu.addMenu("Zoom")
        self.zoom_in_action=self.add_menu_action(zoom_menu,"Zoom In",self.zoom_in,QKeySequence.StandardKey.ZoomIn)
        self.zoom_out_action=self.add_menu_action(zoom_menu,"Zoom Out",self.zoom_out,QKeySequence.StandardKey.ZoomOut)
        zoom_menu.addSeparator()
        self.zoom_reset_action=self.add_menu_action(zoom_menu,"Reset Zoom",self.zoom_reset,QKeySequence("Ctrl+0"))
        self.more_settings_menu=menu.addMenu("More Settings")
        self.tab_width_action=self.add_menu_action(self.more_settings_menu,"Tab Width…",self.open_tab_width_dialog)
        self.more_settings_menu.addSeparator()
        self.default_font_action=self.add_menu_action(self.more_settings_menu,"New Document Defaults…",self.show_new_document_defaults_dialog)
        menu.addSeparator()
        self.theme_menu=None; self.appimage_theme_group=None; self.appimage_theme_actions={}; self.appimage_icon_group=None; self.appimage_icon_actions={}
        if self.appimage_theme_available:
            self.theme_menu=menu.addMenu("App Theme")
            self.appimage_theme_group=QActionGroup(self); self.appimage_theme_group.setExclusive(True)
            for theme,label in (("system","System"),("dark","Dark"),("light","Light")):
                action=QAction(label,self,checkable=True)
                action.triggered.connect(lambda _checked=False,selected=theme:self.set_appimage_theme(selected))
                self.appimage_theme_group.addAction(action); self.theme_menu.addAction(action); self.addAction(action); self.appimage_theme_actions[theme]=action
            self.theme_menu.addSeparator()
            self.appimage_icon_group=QActionGroup(self); self.appimage_icon_group.setExclusive(True)
            for icon_set,label in (("classic","Rico Icons Classic"),("new","Rico Icons New")):
                action=QAction(label,self,checkable=True)
                action.triggered.connect(lambda _checked=False,selected=icon_set:self.set_appimage_icon_set(selected))
                self.appimage_icon_group.addAction(action); self.theme_menu.addAction(action); self.addAction(action); self.appimage_icon_actions[icon_set]=action
        self.appimage_dark_mode_action=None

    def make_insert_menu(self):
        menu=QMenu("&Insert",self); self.insert_menu=menu; self.app_menu_bar.addMenu(menu)
        link_menu=menu.addMenu("Link")
        self.link_action=self.add_menu_action(link_menu,"Insert Link…",self.insert_link,QKeySequence("Ctrl+K"))
        self.edit_link_action=self.add_menu_action(link_menu,"Edit Link…",self.edit_link)
        link_menu.addSeparator()
        self.remove_link_action=self.add_menu_action(link_menu,"Remove Link",self.remove_link)
        menu.addSeparator()
        self.horizontal_rule_action=self.add_menu_action(menu,"Horizontal Rule",self.insert_horizontal_rule,QKeySequence("Ctrl+Shift+H"))
        self.image_action=self.add_menu_action(menu,"Image…",self.insert_image,QKeySequence("Ctrl+Shift+I"))
        menu.addSeparator()
        self.table_action=self.add_menu_action(menu,"Table…",self.insert_table,QKeySequence("Ctrl+Shift+T"))
        table_edit_menu=menu.addMenu("Table Editing")
        self.table_row_above_action=self.add_menu_action(table_edit_menu,"Insert Row Above",self.insert_table_row_above)
        self.table_row_below_action=self.add_menu_action(table_edit_menu,"Insert Row Below",self.insert_table_row_below)
        self.table_delete_row_action=self.add_menu_action(table_edit_menu,"Delete Row",self.delete_table_row); table_edit_menu.addSeparator()
        self.table_column_left_action=self.add_menu_action(table_edit_menu,"Insert Column Left",self.insert_table_column_left)
        self.table_column_right_action=self.add_menu_action(table_edit_menu,"Insert Column Right",self.insert_table_column_right)
        self.table_delete_column_action=self.add_menu_action(table_edit_menu,"Delete Column",self.delete_table_column); table_edit_menu.addSeparator()
        self.table_delete_action=self.add_menu_action(table_edit_menu,"Delete Table",self.delete_table)
        menu.addSeparator()
        self.insert_date_time_action=self.add_menu_action(menu,"Date and Time",self.insert_time_date,QKeySequence("F5"))
        self.date_action=self.add_menu_action(menu,"Date Only",self.insert_date,QKeySequence("Ctrl+;"))
        self.time_action=self.add_menu_action(menu,"Time Only",self.insert_time,QKeySequence("Ctrl+:"))
        menu.addSeparator()
        self.symbol_action=self.add_menu_action(menu,"Symbol…",self.show_symbols_popup,QKeySequence("Shift+F5"))
        self.table_edit_actions=[self.table_row_above_action,self.table_row_below_action,self.table_delete_row_action,self.table_column_left_action,self.table_column_right_action,self.table_delete_column_action,self.table_delete_action]
        self.visual_insert_actions.extend([self.insert_date_time_action,self.date_action,self.time_action,self.symbol_action,self.image_action,self.link_action,self.edit_link_action,self.remove_link_action,self.horizontal_rule_action,self.table_action,*self.table_edit_actions])

    def make_format_menu(self):
        menu=QMenu("F&ormat",self); self.format_menu=menu; self.app_menu_bar.addMenu(menu)
        def add(label,callback,shortcut=None):
            action=self.add_menu_action(menu,label,callback,shortcut); self.format_actions.append(action); return action
        self.font_dialog_action=add("Font…",self.choose_selection_font,QKeySequence("Ctrl+Shift+F"))
        self.increase_font_size_action=add("Increase Font Size",self.increase_font_size,QKeySequence("Ctrl+Shift+]"))
        self.decrease_font_size_action=add("Decrease Font Size",self.decrease_font_size,QKeySequence("Ctrl+Shift+["))
        self.text_colour_action=add("Text Colour…",self.choose_text_colour,QKeySequence("Ctrl+Alt+Shift+C"))
        self.highlight_colour_action=add("Highlight Colour…",self.choose_highlight_colour,QKeySequence("Ctrl+Alt+Shift+H"))
        self.clear_highlight_action=add("Clear Highlight",self.clear_highlight)
        menu.addSeparator()
        self.bold_action=add("Bold",self.toggle_bold,QKeySequence.StandardKey.Bold); self.bold_action.setCheckable(True)
        self.italic_action=add("Italic",self.toggle_italic,QKeySequence.StandardKey.Italic); self.italic_action.setCheckable(True)
        self.underline_action=add("Underline",self.toggle_underline,QKeySequence.StandardKey.Underline); self.underline_action.setCheckable(True)
        self.strike_action=add("Strikethrough",self.toggle_strikethrough,QKeySequence("Ctrl+Shift+X")); self.strike_action.setCheckable(True)
        self.superscript_action=add("Superscript",self.toggle_superscript,QKeySequence("Ctrl+.")); self.superscript_action.setCheckable(True)
        self.subscript_action=add("Subscript",self.toggle_subscript,QKeySequence("Ctrl+,")); self.subscript_action.setCheckable(True)
        menu.addSeparator()
        heading_menu=menu.addMenu("Paragraph Style"); self.heading_actions={}
        for label,level,shortcut in (("Normal Paragraph",0,"Ctrl+Shift+0"),("Heading 1",1,"Ctrl+Shift+1"),("Heading 2",2,"Ctrl+Shift+2"),("Heading 3",3,"Ctrl+Shift+3"),("Heading 4",4,"Ctrl+Shift+4"),("Heading 5",5,"Ctrl+Shift+5"),("Heading 6",6,"Ctrl+Shift+6")):
            action=QAction(label,self,checkable=True); action.setShortcut(QKeySequence(shortcut)); action.triggered.connect(lambda _checked=False,selected=level:self.apply_heading(selected)); heading_menu.addAction(action); self.addAction(action); self.heading_actions[level]=action; self.format_actions.append(action)
        alignment_menu=menu.addMenu("Alignment"); self.alignment_actions={}
        for label,alignment,shortcut in (("Left",Qt.AlignmentFlag.AlignLeft,"Ctrl+L"),("Centre",Qt.AlignmentFlag.AlignHCenter,"Ctrl+E"),("Right",Qt.AlignmentFlag.AlignRight,"Ctrl+R"),("Justify",Qt.AlignmentFlag.AlignJustify,"Ctrl+J")):
            action=QAction(label,self,checkable=True); action.setShortcut(QKeySequence(shortcut)); action.triggered.connect(lambda _checked=False,selected=alignment:self.set_alignment(selected)); alignment_menu.addAction(action); self.addAction(action); self.alignment_actions[alignment]=action; self.format_actions.append(action)
        self.alignment_left_action=self.alignment_actions[Qt.AlignmentFlag.AlignLeft]; self.alignment_center_action=self.alignment_actions[Qt.AlignmentFlag.AlignHCenter]; self.alignment_right_action=self.alignment_actions[Qt.AlignmentFlag.AlignRight]; self.alignment_justify_action=self.alignment_actions[Qt.AlignmentFlag.AlignJustify]
        spacing_menu=menu.addMenu("Line Spacing"); self.line_spacing_actions={}
        for label,percent,shortcut in (("1.0",100,"Ctrl+1"),("1.15",115,"Ctrl+2"),("1.5",150,"Ctrl+3"),("2.0",200,"Ctrl+4")):
            action=QAction(label,self,checkable=True); action.setShortcut(QKeySequence(shortcut)); action.triggered.connect(lambda _checked=False,selected=percent:self.set_line_spacing(selected)); spacing_menu.addAction(action); self.addAction(action); self.line_spacing_actions[percent]=action; self.format_actions.append(action)
        menu.addSeparator()
        self.bulleted_list_action=add("Bullet List",self.toggle_bullet_list,QKeySequence("Ctrl+Shift+L")); self.bulleted_list_action.setCheckable(True)
        self.increase_indent_action=add("Indent",lambda:self.change_indent(1),QKeySequence("Ctrl+]"))
        self.decrease_indent_action=add("Outdent",lambda:self.change_indent(-1),QKeySequence("Ctrl+[")); menu.addSeparator()
        self.paragraph_action=add("Paragraph…",self.show_paragraph_dialog,QKeySequence("Ctrl+Alt+Shift+P"))
        self.clear_formatting_action=add("Clear Formatting",self.clear_formatting,QKeySequence("Ctrl+Space"))

    def make_help_menu(self):
        menu = QMenu("&Help", self)
        self.help_menu = menu
        self.app_menu_bar.addMenu(menu)
        self.documentation_action = self.add_menu_action(
            menu, "Documentation", self.open_documentation, QKeySequence("F1")
        )
        menu.addSeparator()
        self.tutorial_action = self.add_menu_action(
            menu, "Tutorial Wizard", self.show_tutorial_wizard,
            QKeySequence("Shift+F1")
        )
        self.tutorial_action.setToolTip("Tutorial Wizard (Shift+F1)")
        self.shortcuts_action = self.add_menu_action(
            menu, "Keyboard Shortcuts", self.show_keyboard_shortcuts_dialog,
            QKeySequence("Ctrl+Shift+/")
        )
        menu.addSeparator()
        self.github_action = self.add_menu_action(
            menu, "GitHub Repository", self.open_github_repository
        )
        self.issue_action = self.add_menu_action(
            menu, "Raise an Issue", self.report_an_issue
        )
        menu.addSeparator()
        self.about_action = self.add_menu_action(
            menu, "About Rico Plus", self.show_about_dialog
        )
        self.about_action.setMenuRole(QAction.MenuRole.AboutRole)

    def bind_shortcuts(self):
        """Shortcuts are owned by the shared actions used by the ribbon."""
        return

    def _focus_editor_after_startup(self):
        """Give normal startup focus to the document after Ribbon is shown."""
        if not hasattr(self, "visual_editor") or not self.visual_editor.isEnabled():
            return
        # Do not steal focus from a first-run/tutorial window.
        if self.tutorial_dialog is not None and self.tutorial_dialog.isVisible():
            return
        self.visual_editor.setFocus(Qt.FocusReason.OtherFocusReason)
        self.visual_editor.ensureCursorVisible()

    def toggle_view_only(self, checked):
        checked=bool(checked)
        if not checked and self.view_only:
            dialog=QMessageBox(self); dialog.setWindowTitle("Disable Locked Mode? — Rico Plus"); dialog.setIcon(QMessageBox.Icon.Warning); dialog.setText("Locked Mode protects files from accidental changes."); dialog.setInformativeText("Continue only when you intend to edit the document.")
            keep=dialog.addButton("Keep Locked",QMessageBox.ButtonRole.RejectRole); cont=dialog.addButton("Continue",QMessageBox.ButtonRole.AcceptRole); dialog.setDefaultButton(keep); dialog.setEscapeButton(keep); dialog.exec()
            if dialog.clickedButton() is not cont:
                self.view_only_action.blockSignals(True); self.view_only_action.setChecked(True); self.view_only_action.blockSignals(False); return
        self.view_only=checked; self.persist_view_only=checked; self._view_only_prompt_shown=False; self.view_only_action.blockSignals(True); self.view_only_action.setChecked(checked); self.view_only_action.blockSignals(False); self._update_mode_capabilities(); self.update_title(); self.update_status_counts(); self.save_preferences(); self._show_status_message("Locked Mode enabled." if checked else "Locked Mode disabled.",3000)

    def explain_view_only_block(self):
        self._show_status_message("Editing is disabled while Locked Mode is enabled.",4000)
        if self._view_only_prompt_shown: return
        self._view_only_prompt_shown=True
        QMessageBox.information(self,"Locked Mode — Rico Plus","Editing is disabled because Locked Mode is enabled.\n\nClear View → Locked Mode and confirm Continue to edit the document.")

    def eventFilter(self, watched, event):
        if bool(watched.property("ricopad_instant_tooltip")):
            if event.type()==QEvent.Type.Enter and watched.toolTip(): QToolTip.showText(watched.mapToGlobal(watched.rect().bottomLeft()),watched.toolTip(),watched,watched.rect(),7000)
            elif event.type()==QEvent.Type.Leave: QToolTip.hideText()
        editor=getattr(self,"visual_editor",None)
        viewport=editor.viewport() if editor is not None else None
        if watched is viewport and event.type() in (QEvent.Type.DragEnter,QEvent.Type.DragMove,QEvent.Type.Drop):
            mime=event.mimeData()
            local_files=[url.toLocalFile() for url in mime.urls() if url.isLocalFile() and os.path.isfile(url.toLocalFile())] if mime.hasUrls() else []
            if local_files:
                event.acceptProposedAction()
                if event.type()==QEvent.Type.Drop:
                    images=[path for path in local_files if Path(path).suffix.lower() in IMAGE_EXTENSIONS]
                    documents=[path for path in local_files if path not in images]
                    for path in images: self.insert_image_path(path)
                    if documents:
                        QTimer.singleShot(
                            0,
                            lambda paths=list(documents):
                                self.files_dropped.emit(paths),
                        )
                return True
        if watched is editor and event.type()==QEvent.Type.KeyPress and event.key()==Qt.Key.Key_Insert:
            editor.setOverwriteMode(not editor.overwriteMode()); self.update_status_counts(); return True
        if self.view_only and watched is editor:
            if event.type()==QEvent.Type.InputMethod and (event.commitString() or event.preeditString()): self.explain_view_only_block(); return True
            if event.type()==QEvent.Type.KeyPress:
                modifiers=event.modifiers(); mutating=event.key() in {Qt.Key.Key_Backspace,Qt.Key.Key_Delete,Qt.Key.Key_Return,Qt.Key.Key_Enter,Qt.Key.Key_Tab}; printable=bool(event.text()) and not (modifiers&(Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.AltModifier|Qt.KeyboardModifier.MetaModifier)); standard=any(event.matches(k) for k in (QKeySequence.StandardKey.Cut,QKeySequence.StandardKey.Paste,QKeySequence.StandardKey.Undo,QKeySequence.StandardKey.Redo))
                if mutating or printable or standard: self.explain_view_only_block(); return True
        return QWidget.eventFilter(self, watched, event)

    def infer_editor_canvas_theme(self):
        """Infer the existing editor appearance without changing it.

        First launch therefore follows the active host or bundled AppImage
        theme. After the user presses the toggle, the explicit light/dark
        choice is persisted independently of the application chrome.
        """
        if self.appimage_theme_available:
            selected = self.effective_appimage_theme()
            if selected in ("light", "dark"):
                return selected
        colour = self.visual_editor.palette().color(QPalette.ColorRole.Base)
        return "light" if colour.lightness() >= 128 else "dark"

    def update_editor_canvas_theme_action(self):
        action = getattr(self, "editor_canvas_theme_action", None)
        if action is None:
            return
        is_dark = self.editor_canvas_theme == "dark"
        current = "Dark" if is_dark else "Light"
        target = "light" if is_dark else "dark"
        shortcut=action.shortcut().toString(QKeySequence.SequenceFormat.NativeText)
        tooltip = (
            f"Dark Editor ({shortcut}) — editor canvas: {current}. Click for {target}; "
            "the ribbon and the rest of the interface will not change."
        ) if shortcut else (
            f"Dark Editor — editor canvas: {current}. Click for {target}; "
            "the ribbon and the rest of the interface will not change."
        )
        action.blockSignals(True)
        action.setChecked(is_dark)
        action.setToolTip(tooltip)
        action.setStatusTip(f"Editor canvas appearance: {current}")
        action.blockSignals(False)

    def apply_editor_canvas_theme(self, update_action=True):
        """Apply a display-only light/dark canvas override without rewriting RTF formatting."""
        if not hasattr(self,"visual_editor"): return
        provider = getattr(self, "managed_canvas_light_provider", None)
        if callable(provider):
            # This class is inherently the managed Plus editor component; there
            # is no standalone/embedded mode flag on this path.  Plus owns the
            # canvas follow/override preference and the editor consumes it.
            self.editor_canvas_theme = "light" if bool(provider()) else "dark"
        elif self.editor_canvas_theme not in ("light","dark"):
            self.editor_canvas_theme=self.infer_editor_canvas_theme()
        editor=self.visual_editor
        # Exact canonical Ricopad canvas-palette model.  Managed Rico Plus does
        # not add a QSS border here; its persistent frame is rendered separately
        # with Qt's native focus primitive so the system's dimmer treatment is kept.
        palette=QPalette(editor.palette())
        if self.editor_canvas_theme == "light":
            palette.setColor(QPalette.ColorRole.Base,QColor("#FFFFFF"))
            palette.setColor(QPalette.ColorRole.Text,QColor("#202124"))
            palette.setColor(QPalette.ColorRole.Highlight,QColor("#B24A3B"))
            palette.setColor(QPalette.ColorRole.HighlightedText,QColor("#FFFFFF"))
        else:
            palette.setColor(QPalette.ColorRole.Base,QColor("#151719"))
            palette.setColor(QPalette.ColorRole.Text,QColor("#F1F3F4"))
            palette.setColor(QPalette.ColorRole.Highlight,QColor("#B24A3B"))
            palette.setColor(QPalette.ColorRole.HighlightedText,QColor("#FFFFFF"))
        editor.setPalette(palette)
        editor.viewport().setPalette(palette)
        editor.setStyleSheet("")
        editor.viewport().setAutoFillBackground(True)
        editor.setContentsMargins(0,0,0,0)
        editor.setViewportMargins(0,0,0,0)
        editor.document().setDocumentMargin(4.0)
        editor.viewport().update()
        if update_action: self.update_editor_canvas_theme_action()

    def toggle_editor_canvas_light(self, checked):
        # The View action is named "Dark Editor": checked means dark.
        self.editor_canvas_theme = "dark" if bool(checked) else "light"
        self.apply_editor_canvas_theme(update_action=True)
        self.save_preferences()
        self._show_status_message(
            "Editor canvas switched to a dark background."
            if self.editor_canvas_theme == "dark"
            else "Editor canvas switched to a light background.",
            3000,
        )

    def effective_appimage_theme(self):
        """Return the explicit launch override or saved AppImage System/Dark/Light choice."""
        return self.appimage_theme_override or self.appimage_theme

    def _portable_rico_palette(self, theme):
        """Return the Plus-family Dark/Light palette with Rico's brick accent."""
        palette=QPalette()
        if theme == "dark":
            palette.setColor(QPalette.ColorRole.Window,QColor("#202326"))
            palette.setColor(QPalette.ColorRole.WindowText,QColor("#F1F3F4"))
            palette.setColor(QPalette.ColorRole.Base,QColor("#151719"))
            palette.setColor(QPalette.ColorRole.AlternateBase,QColor("#202326"))
            palette.setColor(QPalette.ColorRole.ToolTipBase,QColor("#F1F3F4"))
            palette.setColor(QPalette.ColorRole.ToolTipText,QColor("#101214"))
            palette.setColor(QPalette.ColorRole.Text,QColor("#F1F3F4"))
            palette.setColor(QPalette.ColorRole.Button,QColor("#292D31"))
            palette.setColor(QPalette.ColorRole.ButtonText,QColor("#F1F3F4"))
            palette.setColor(QPalette.ColorRole.Highlight,QColor("#B24A3B"))
            palette.setColor(QPalette.ColorRole.HighlightedText,QColor("#FFFFFF"))
            palette.setColor(QPalette.ColorRole.PlaceholderText,QColor("#8E969E"))
        else:
            application=QApplication.instance()
            palette=QPalette(application.style().standardPalette()) if application is not None else QPalette()
            palette.setColor(QPalette.ColorRole.Window,QColor("#D4D4D4"))
            palette.setColor(QPalette.ColorRole.WindowText,QColor("#2A2A2A"))
            palette.setColor(QPalette.ColorRole.Base,QColor("#F4F4F4"))
            palette.setColor(QPalette.ColorRole.AlternateBase,QColor("#E4E4E4"))
            palette.setColor(QPalette.ColorRole.ToolTipBase,QColor("#F4F4F4"))
            palette.setColor(QPalette.ColorRole.ToolTipText,QColor("#2A2A2A"))
            palette.setColor(QPalette.ColorRole.Text,QColor("#2A2A2A"))
            palette.setColor(QPalette.ColorRole.Button,QColor("#E4E4E4"))
            palette.setColor(QPalette.ColorRole.ButtonText,QColor("#2A2A2A"))
            palette.setColor(QPalette.ColorRole.Light,QColor("#F4F4F4"))
            palette.setColor(QPalette.ColorRole.Midlight,QColor("#D0D0D0"))
            palette.setColor(QPalette.ColorRole.Mid,QColor("#B2B2B2"))
            palette.setColor(QPalette.ColorRole.Dark,QColor("#767676"))
            palette.setColor(QPalette.ColorRole.Shadow,QColor("#545454"))
            palette.setColor(QPalette.ColorRole.Highlight,QColor("#B24A3B"))
            palette.setColor(QPalette.ColorRole.HighlightedText,QColor("#FFFFFF"))
            palette.setColor(QPalette.ColorRole.PlaceholderText,QColor("#767676"))
        return palette

    def _appimage_palette(self, theme):
        """Return a complete AppImage palette independent of the host theme."""
        application = QApplication.instance()
        base_palette = QPalette(application.palette()) if application is not None else QPalette()
        if theme == "dark":
            colours = {
                QPalette.ColorRole.Window: QColor("#232629"),
                QPalette.ColorRole.WindowText: QColor("#EFF0F1"),
                QPalette.ColorRole.Base: QColor("#1B1E20"),
                QPalette.ColorRole.AlternateBase: QColor("#252A2E"),
                QPalette.ColorRole.ToolTipBase: QColor("#31363B"),
                QPalette.ColorRole.ToolTipText: QColor("#EFF0F1"),
                QPalette.ColorRole.Text: QColor("#EFF0F1"),
                QPalette.ColorRole.Button: QColor("#31363B"),
                QPalette.ColorRole.ButtonText: QColor("#EFF0F1"),
                QPalette.ColorRole.BrightText: QColor("#FFFFFF"),
                QPalette.ColorRole.Highlight: QColor("#3DAEE9"),
                QPalette.ColorRole.HighlightedText: QColor("#FFFFFF"),
                QPalette.ColorRole.Link: QColor("#3DAEE9"),
                QPalette.ColorRole.LinkVisited: QColor("#9B7BD5"),
                QPalette.ColorRole.PlaceholderText: QColor("#A7AFB7"),
                QPalette.ColorRole.Light: QColor("#555B60"),
                QPalette.ColorRole.Midlight: QColor("#454A4F"),
                QPalette.ColorRole.Mid: QColor("#3D4246"),
                QPalette.ColorRole.Dark: QColor("#202326"),
                QPalette.ColorRole.Shadow: QColor("#111315"),
            }
            disabled = QColor("#70777D")
        else:
            colours = {
                QPalette.ColorRole.Window: QColor("#EFF0F1"),
                QPalette.ColorRole.WindowText: QColor("#232629"),
                QPalette.ColorRole.Base: QColor("#FFFFFF"),
                QPalette.ColorRole.AlternateBase: QColor("#F2F4F6"),
                QPalette.ColorRole.ToolTipBase: QColor("#FFFFDC"),
                QPalette.ColorRole.ToolTipText: QColor("#232629"),
                QPalette.ColorRole.Text: QColor("#232629"),
                QPalette.ColorRole.Button: QColor("#F7F7F8"),
                QPalette.ColorRole.ButtonText: QColor("#232629"),
                QPalette.ColorRole.BrightText: QColor("#FFFFFF"),
                QPalette.ColorRole.Highlight: QColor("#3DAEE9"),
                QPalette.ColorRole.HighlightedText: QColor("#FFFFFF"),
                QPalette.ColorRole.Link: QColor("#0068A6"),
                QPalette.ColorRole.LinkVisited: QColor("#6B4BA3"),
                QPalette.ColorRole.PlaceholderText: QColor("#6C757D"),
                QPalette.ColorRole.Light: QColor("#FFFFFF"),
                QPalette.ColorRole.Midlight: QColor("#E4E7E9"),
                QPalette.ColorRole.Mid: QColor("#B8BDC2"),
                QPalette.ColorRole.Dark: QColor("#92999F"),
                QPalette.ColorRole.Shadow: QColor("#687078"),
            }
            disabled = QColor("#9BA1A6")
        for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
            for role, colour in colours.items():
                base_palette.setColor(group, role, colour)
        for role, colour in colours.items():
            base_palette.setColor(QPalette.ColorGroup.Disabled, role, colour)
        for role in (
            QPalette.ColorRole.WindowText, QPalette.ColorRole.Text,
            QPalette.ColorRole.ButtonText, QPalette.ColorRole.PlaceholderText,
        ):
            base_palette.setColor(QPalette.ColorGroup.Disabled, role, disabled)
        return base_palette

    def apply_appimage_theme(self, theme, update_actions=True):
        """Apply System/Dark/Light chrome without touching document formatting."""
        if not self.appimage_theme_available or theme not in ("system","dark","light"):
            return
        application=QApplication.instance()
        if application is None:
            return
        # Plus-family implementation in every runtime: keep the active Qt
        # style, remove application QSS, reset to that style's standard palette,
        # then apply only the Dark/Light palette. Rico changes only the accent.
        application.setStyleSheet("")
        application.setPalette(application.style().standardPalette())
        if theme in ("dark","light"):
            application.setPalette(self._portable_rico_palette(theme))
        if update_actions:
            for selected,action in getattr(self,"appimage_theme_actions",{}).items():
                action.blockSignals(True); action.setChecked(selected==theme); action.blockSignals(False)
            self.refresh_portable_icons()
            self.apply_editor_canvas_theme(update_action=True)

    def set_appimage_theme(self, theme):
        """Persist System/Dark/Light application chrome across shipped runtimes."""
        theme=str(theme).strip().lower()
        if theme not in ("system","dark","light") or not self.appimage_theme_available:
            return
        os.environ.pop("RICO_PLUS_APP_THEME",None)
        self.appimage_theme=theme
        self.appimage_theme_override=None
        self.apply_appimage_theme(theme)
        self.save_preferences()
        label="System" if theme=="system" else theme.title()
        self._show_status_message(f"Theme: {label}.",2500)

    def set_appimage_icon_set(self, icon_set):
        """Persist the Rico Classic/New command-icon family choice."""
        icon_set=str(icon_set).strip().lower()
        if icon_set not in ("classic","new") or not self.appimage_theme_available:
            return
        os.environ.pop("RICO_PLUS_ICON_SET",None)
        self.appimage_icon_set=icon_set
        self.appimage_icon_set_override=None
        for selected,action in getattr(self,"appimage_icon_actions",{}).items():
            action.blockSignals(True); action.setChecked(selected==icon_set); action.blockSignals(False)
        self.refresh_portable_icons()
        self.save_preferences()
        self._show_status_message(f"Rico icons: {'Classic' if icon_set=='classic' else 'New'}.",2500)

    def toggle_appimage_dark_mode(self, checked):
        """Compatibility hook for older shortcuts/configuration."""
        self.set_appimage_theme("dark" if checked else "light")

    def _new_document_alignment_flag(self):
        return {
            "left": Qt.AlignmentFlag.AlignLeft,
            "centre": Qt.AlignmentFlag.AlignHCenter,
            "right": Qt.AlignmentFlag.AlignRight,
            "justify": Qt.AlignmentFlag.AlignJustify,
        }.get(self.new_document_alignment, Qt.AlignmentFlag.AlignLeft)

    def _build_new_document_template_payload(self):
        """Build an interoperable RTF template containing the exact saved defaults."""
        return build_new_document_rtf_payload(
            NewDocumentDefaults(
                font_family=self.base_font_family,
                font_size=self.base_font_size,
                font_weight=self.base_font_weight,
                font_slant=self.base_font_slant,
                line_spacing=self.new_document_line_spacing,
                alignment=self.new_document_alignment,
            )
        )

    def _apply_new_document_defaults_direct(self):
        """Materialise new-document defaults directly in Qt without an RTF re-import."""
        document=self.visual_editor.document()
        document.clear()
        font=QFont()
        try:
            font.setFamilies([self.base_font_family])
        except Exception:
            font.setFamily(self.base_font_family)
        font.setPointSize(int(self.base_font_size))
        font.setBold(self.base_font_weight=="bold")
        font.setItalic(self.base_font_slant=="italic")
        document.setDefaultFont(font)
        document.setDocumentMargin(4.0)
        cursor=QTextCursor(document)
        block=QTextBlockFormat(cursor.blockFormat())
        block.setAlignment(self._new_document_alignment_flag())
        block.setLeftMargin(0.0); block.setRightMargin(0.0); block.setTextIndent(0.0)
        block.setTopMargin(0.0); block.setBottomMargin(0.0)
        block.setLineHeight(float(self.new_document_line_spacing),QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
        cursor.setBlockFormat(block)
        plain=QTextCharFormat()
        try:
            plain.setFontFamilies([self.base_font_family])
        except Exception:
            plain.setFontFamily(self.base_font_family)
        plain.setFontPointSize(float(self.base_font_size))
        plain.setFontWeight(QFont.Weight.Bold if self.base_font_weight=="bold" else QFont.Weight.Normal)
        plain.setFontItalic(self.base_font_slant=="italic")
        cursor.setBlockCharFormat(plain)
        self.visual_editor.setTextCursor(cursor)
        self.visual_editor.setCurrentCharFormat(plain)
        self.visual_editor.setCurrentFont(font)
        return True

    def _write_new_document_template(self, payload):
        """Atomically refresh the per-user generated new-document RTF template."""
        os.makedirs(self.config_directory, mode=0o700, exist_ok=True)
        if os.name != "nt":
            try:
                os.chmod(self.config_directory, 0o700)
            except OSError:
                pass
        descriptor = None
        temporary = None
        try:
            descriptor, temporary = tempfile.mkstemp(
                prefix=".new-document-template-", suffix=".rtf.tmp",
                dir=self.config_directory,
            )
            if hasattr(os, "fchmod"):
                os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                descriptor = None
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.new_document_template_file)
            temporary = None
            fsync_directory(self.config_directory)
        finally:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            if temporary:
                try:
                    os.remove(temporary)
                except OSError:
                    pass

    def _ensure_new_document_template(self):
        """Keep the generated RTF template exactly aligned with saved defaults."""
        try:
            expected = self._build_new_document_template_payload()
            current = None
            try:
                current = read_bounded_bytes(
                    self.new_document_template_file,
                    MAX_CONFIG_FILE_SIZE,
                    label="new-document template",
                )
            except OSError:
                pass
            if current != expected:
                self._write_new_document_template(expected)
            return expected
        except (OSError, ValueError, RuntimeError, MemoryError):
            factory = resource_path("templates", "default-document.rtf")
            try:
                return read_bounded_bytes(factory, MAX_CONFIG_FILE_SIZE, label="factory new-document template")
            except OSError:
                return None

    def _apply_new_document_template(self):
        """Apply saved defaults to a brand-new document and refresh its RTF template."""
        self._ensure_new_document_template()
        return self._apply_new_document_defaults_direct()

    def apply_editor_font(self):
        """Compatibility hook: apply the generated template only to a blank untitled document."""
        if self.file_path is not None or max(0, self.visual_editor.document().characterCount() - 1) != 0:
            return
        self._apply_new_document_template()

    def show_new_document_defaults_dialog(self):
        if self.new_document_defaults_dialog is not None:
            self.new_document_defaults_dialog.show()
            self.new_document_defaults_dialog.raise_()
            self.new_document_defaults_dialog.activateWindow()
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("New Document Defaults — Rico Plus")
        dialog.setWindowIcon(self.windowIcon())
        dialog.setModal(False)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        form = QFormLayout(dialog)

        family = QFontComboBox(dialog)
        family.setCurrentFont(QFont(self.base_font_family))
        size = QComboBox(dialog)
        size.setEditable(True)
        size.addItems(["8", "9", "10", "11", "12", "14", "16", "18", "20", "24", "28", "32", "36", "48", "72"])
        size.setEditText(str(self.base_font_size))
        style = QComboBox(dialog)
        for label, weight, slant in (
            ("Normal", "normal", "roman"),
            ("Bold", "bold", "roman"),
            ("Italic", "normal", "italic"),
            ("Bold Italic", "bold", "italic"),
        ):
            style.addItem(label, (weight, slant))
        for index in range(style.count()):
            if style.itemData(index) == (self.base_font_weight, self.base_font_slant):
                style.setCurrentIndex(index)
                break
        spacing = QComboBox(dialog)
        for label, value in (("1.0", 100), ("1.15", 115), ("1.5", 150), ("2.0", 200)):
            spacing.addItem(label, value)
        for index in range(spacing.count()):
            if int(spacing.itemData(index)) == int(self.new_document_line_spacing):
                spacing.setCurrentIndex(index)
                break
        alignment = QComboBox(dialog)
        for label, value in (("Left", "left"), ("Centre", "centre"), ("Right", "right"), ("Justify", "justify")):
            alignment.addItem(label, value)
        for index in range(alignment.count()):
            if alignment.itemData(index) == self.new_document_alignment:
                alignment.setCurrentIndex(index)
                break
        form.addRow("Font family:", family)
        form.addRow("Font size:", size)
        form.addRow("Font style:", style)
        form.addRow("Line spacing:", spacing)
        form.addRow("Alignment:", alignment)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel, dialog)
        form.addRow(buttons)

        def save_defaults():
            try:
                point_size = int(float(size.currentText().strip()))
            except ValueError:
                point_size = self.base_font_size
            point_size = max(6, min(72, point_size))
            weight, slant = style.currentData()
            self.base_font_family = family.currentText().strip() or family.currentFont().family() or "Sans Serif"
            self.base_font_size = point_size
            self.base_font_weight = weight
            self.base_font_slant = slant
            self.new_document_line_spacing = int(spacing.currentData() or 115)
            self.new_document_alignment = str(alignment.currentData() or "left")
            self.save_preferences()
            self._ensure_new_document_template()
            if self.file_path is None and max(0, self.visual_editor.document().characterCount() - 1) == 0:
                self._loading = True
                try:
                    self._apply_new_document_template()
                    self.visual_editor.document().setModified(False)
                    self.content_saved = True
                finally:
                    self._loading = False
                self.apply_editor_canvas_theme(update_action=True)
                self.apply_zoom_preference()
                self.update_formatting_state()
            else:
                self._show_status_message("New-document defaults saved; the open RTF was not reformatted.", 4500)
            dialog.close()

        buttons.accepted.connect(save_defaults)
        buttons.rejected.connect(dialog.close)
        dialog.finished.connect(lambda _result: setattr(self, "new_document_defaults_dialog", None))
        self.new_document_defaults_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def open_font_dialog(self):
        """Compatibility alias retained for older action bindings."""
        self.show_new_document_defaults_dialog()

    def text_area_undo(self):
        if self.document_editing_available():
            self.text_area.undo()

    def text_area_redo(self):
        if self.document_editing_available():
            self.text_area.redo()

    def insert_symbol(self, symbol, popup=None):
        """Insert one symbol at the caret and return focus to the active editor."""
        if not self.document_editing_available():
            if popup is not None:
                popup.reject()
            return False
        cursor = self.text_area.textCursor()
        cursor.insertText(symbol)
        self.text_area.setTextCursor(cursor)
        if popup is not None:
            popup.accept()
        self.text_area.setFocus()
        self.text_area.ensureCursorVisible()

    def open_more_symbols(self, popup=None):
        """Open the operating system's available character-map utility."""
        if popup is not None:
            popup.accept()

        host_environment = host_process_environment()
        host_path = host_environment.get("PATH")

        if sys.platform == "win32":
            system_root = os.environ.get("SystemRoot", r"C:\Windows")
            candidates = (
                (os.path.join(system_root, "System32", "charmap.exe"), []),
                ("charmap.exe", []),
            )
            missing_message = (
                "Windows Character Map could not be found on this system."
            )
        else:
            candidates = (
                ("kcharselect", []),
                ("gucharmap", []),
                ("gnome-characters", []),
                ("charmap", []),
            )
            missing_message = (
                "No supported character-map application was found.\n\n"
                "Install KCharSelect, GNOME Characters, or Gucharmap "
                "to use this option."
            )

        for command, arguments in candidates:
            executable = (
                command
                if os.path.isfile(command)
                else shutil.which(command, path=host_path)
            )
            if executable:
                try:
                    subprocess.Popen(
                        [executable, *arguments],
                        env=host_environment,
                        start_new_session=(sys.platform != "win32"),
                    )
                    self.text_area.setFocus()
                    return
                except OSError:
                    continue

        QMessageBox.information(
            self,
            "More Symbols",
            missing_message,
        )
        self.text_area.setFocus()

    def show_symbols_popup(self):
        """Show the curated symbol grid centred on the active screen."""
        if not self.visual_editing_available():
            return
        popup = QDialog(self)
        popup.setWindowTitle("Symbols")
        popup.setModal(True)

        layout = QGridLayout(popup)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setHorizontalSpacing(5)
        layout.setVerticalSpacing(5)

        symbols = (
            "©", "®", "™", "°", "•", "·", "—", "–",
            "…", "→", "←", "↑", "↓", "✓", "✗", "§",
            "£", "€", "$", "¥", "¢", "±", "×", "÷",
            "≠", "≤", "≥", "≈", "∞", "µ", "¶", "№",
        )

        columns = 8
        for index, symbol in enumerate(symbols):
            button = QToolButton(popup)
            button.setText(symbol)
            button.setToolTip(f"Insert {symbol}")
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setFixedSize(34, 30)
            button.clicked.connect(
                lambda _checked=False, value=symbol: self.insert_symbol(value, popup)
            )
            layout.addWidget(button, index // columns, index % columns)

        separator = QFrame(popup)
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(
            separator,
            (len(symbols) + columns - 1) // columns,
            0,
            1,
            columns,
        )

        more_button = QPushButton("More Symbols…", popup)
        more_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        more_button.clicked.connect(
            lambda _checked=False: self.open_more_symbols(popup)
        )
        layout.addWidget(
            more_button,
            (len(symbols) + columns - 1) // columns + 1,
            0,
            1,
            columns,
        )

        popup.adjustSize()
        screen=self.screen() or QApplication.primaryScreen()
        if screen is not None:
            geometry=screen.availableGeometry()
            popup.move(
                geometry.center().x()-popup.width()//2,
                geometry.center().y()-popup.height()//2,
            )
        popup.exec()

        # Always restore editor focus after the centred symbol chooser closes.
        self.text_area.setFocus()

    def document_editing_available(self, show_message=True):
        """Return whether document mutation is allowed in the active window."""
        if not self.view_only:
            return True
        if show_message:
            self.explain_view_only_block()
        return False

    def visual_editing_available(self, show_message=True):
        return self.document_editing_available(show_message)

    def merge_character_format(self, char_format):
        """Apply character formatting to selection, current word, or future typing.

        WordPad-style editing should not force a precise drag-selection for a
        single word.  When there is no selection and the caret touches a word,
        format that word while leaving the caret where it was.  In whitespace
        or an empty paragraph, change only the typing format for future text.
        """
        if not self.visual_editing_available():
            return
        editor=self.visual_editor; cursor=editor.textCursor()
        original_position=cursor.position(); original_anchor=cursor.anchor()
        target=QTextCursor(cursor)
        if not target.hasSelection():
            word=self._word_cursor_at_caret(cursor)
            if word is not None:
                target=word
        if target.hasSelection():
            target.mergeCharFormat(char_format)
            restored=QTextCursor(editor.document()); restored.setPosition(original_anchor)
            if original_position!=original_anchor:
                restored.setPosition(original_position,QTextCursor.MoveMode.KeepAnchor)
            editor.setTextCursor(restored)
        else:
            editor.mergeCurrentCharFormat(char_format)
        editor.setFocus(); self.update_formatting_state()

    def _effective_character_format(self):
        """Return the format that a no-selection character command will toggle."""
        editor=self.visual_editor; cursor=editor.textCursor()
        if not cursor.hasSelection():
            word=self._word_cursor_at_caret(cursor)
            if word is not None:
                return word.charFormat()
        return cursor.charFormat() if cursor.hasSelection() else editor.currentCharFormat()

    def _reset_font_face_display(self, _text=""):
        """Keep the collapsed font-family field pinned to the start of its name."""
        line_edit = self.font_combo.lineEdit() if hasattr(self, "font_combo") else None
        if line_edit is None:
            return
        line_edit.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        line_edit.deselect()
        line_edit.setCursorPosition(0)

    def set_selected_font(self, font):
        if not self.visual_editing_available(False):
            return
        fmt = QTextCharFormat()
        fmt.setFontFamily(font.family())
        self.merge_character_format(fmt)

    def set_selected_font_size(self, value):
        if not self.visual_editing_available(False):
            return
        try:
            size = float(str(value).strip())
        except ValueError:
            return
        if not 1 <= size <= 512:
            return
        fmt = QTextCharFormat()
        fmt.setFontPointSize(size)
        self.merge_character_format(fmt)

    def apply_font_weight_from_combo(self, _index):
        if self.font_weight_combo.signalsBlocked():
            return
        weight = self.font_weight_combo.currentData()
        if weight is None:
            return
        self.set_selected_font_weight(int(weight))

    def set_selected_font_weight(self, weight):
        if not self.visual_editing_available(False):
            return
        try:
            value = max(1, min(1000, int(weight)))
        except (TypeError, ValueError):
            return
        fmt = QTextCharFormat()
        fmt.setFontWeight(value)
        self.merge_character_format(fmt)

    @staticmethod
    def _adjacent_font_size(current_size, direction):
        """Return the next standard point size in the requested direction."""
        current = max(float(FONT_SIZE_STEPS[0]), min(float(FONT_SIZE_STEPS[-1]), float(current_size)))
        if direction > 0:
            return next(
                (size for size in FONT_SIZE_STEPS if size > current + 0.01),
                FONT_SIZE_STEPS[-1],
            )
        return next(
            (size for size in reversed(FONT_SIZE_STEPS) if size < current - 0.01),
            FONT_SIZE_STEPS[0],
        )

    def _word_cursor_at_caret(self, cursor):
        """Return WordUnderCursor when the caret touches real word text."""
        probe=QTextCursor(cursor)
        probe.select(QTextCursor.SelectionType.WordUnderCursor)
        if probe.hasSelection() and probe.selectedText().strip():
            return probe
        if cursor.position()>cursor.block().position():
            probe=QTextCursor(cursor); probe.movePosition(QTextCursor.MoveOperation.Left); probe.select(QTextCursor.SelectionType.WordUnderCursor)
            if probe.hasSelection() and probe.selectedText().strip():
                return probe
        return None

    def _step_selected_font_size(self, direction):
        """Step selected runs, or the word under the caret when there is one."""
        if not self.visual_editing_available():
            return
        editor=self.visual_editor; cursor=editor.textCursor()
        if not cursor.hasSelection():
            word=self._word_cursor_at_caret(cursor)
            if word is not None:
                current=self._logical_char_size(word.charFormat())
                target=self._adjacent_font_size(current,direction)
                fmt=QTextCharFormat(); fmt.setFontPointSize(float(target)); word.mergeCharFormat(fmt)
                editor.setTextCursor(cursor); editor.setFocus(); self.update_formatting_state(); return
            current=self._logical_char_size(editor.currentCharFormat())
            target=self._adjacent_font_size(current,direction)
            fmt=QTextCharFormat(); fmt.setFontPointSize(float(target)); editor.mergeCurrentCharFormat(fmt)
            self.font_size_combo.blockSignals(True); self.font_size_combo.setEditText(f"{target:g}"); self.font_size_combo.blockSignals(False)
            editor.setFocus(); self.update_formatting_state(); return
        start_pos=min(cursor.selectionStart(),cursor.selectionEnd()); end_pos=max(cursor.selectionStart(),cursor.selectionEnd())
        document=editor.document(); probe=QTextCursor(document); runs=[]; pos=start_pos
        while pos<end_pos:
            probe.setPosition(pos)
            fmt=probe.charFormat(); size=self._logical_char_size(fmt)
            # Grow a run while the effective point size is the same.
            run_end=pos+1
            while run_end<end_pos:
                q=QTextCursor(document); q.setPosition(run_end)
                if abs(self._logical_char_size(q.charFormat())-size)>0.01:
                    break
                run_end+=1
            runs.append((pos,run_end,self._adjacent_font_size(size,direction))); pos=run_end
        cursor.beginEditBlock()
        try:
            for run_start,run_end,target in runs:
                run=QTextCursor(document); run.setPosition(run_start); run.setPosition(run_end,QTextCursor.MoveMode.KeepAnchor)
                fmt=QTextCharFormat(); fmt.setFontPointSize(float(target)); run.mergeCharFormat(fmt)
        finally:
            cursor.endEditBlock()
        editor.setTextCursor(cursor); self.update_formatting_state()

    def increase_font_size(self, _checked=False):
        self._step_selected_font_size(1)

    def decrease_font_size(self, _checked=False):
        self._step_selected_font_size(-1)

    def choose_selection_font(self):
        if not self.visual_editing_available():
            return
        effective=self._effective_character_format()
        current = effective.font()
        current_size = self._logical_char_size(effective)
        current.setPointSizeF(current_size)
        selected, accepted = QFontDialog.getFont(current, self, "Font")
        if not accepted:
            return
        logical_size = selected.pointSizeF()
        if logical_size <= 0:
            logical_size = current_size
        fmt = QTextCharFormat()
        fmt.setFontFamily(selected.family())
        fmt.setFontWeight(selected.weight())
        fmt.setFontItalic(selected.italic())
        fmt.setFontUnderline(selected.underline())
        fmt.setFontStrikeOut(selected.strikeOut())
        fmt.setFontPointSize(logical_size)
        self.merge_character_format(fmt)

    def toggle_bold(self, _checked=False):
        if not self.visual_editing_available(): return
        current=self._effective_character_format().fontWeight(); fmt=QTextCharFormat(); fmt.setFontWeight(QFont.Weight.Normal if int(current)>=int(QFont.Weight.Bold) else QFont.Weight.Bold); self.merge_character_format(fmt)

    def toggle_italic(self, _checked=False):
        if not self.visual_editing_available(): return
        fmt=QTextCharFormat(); fmt.setFontItalic(not self._effective_character_format().fontItalic()); self.merge_character_format(fmt)

    def toggle_underline(self, _checked=False):
        if not self.visual_editing_available():
            return
        fmt = QTextCharFormat()
        fmt.setFontUnderline(not self._effective_character_format().fontUnderline())
        self.merge_character_format(fmt)

    def toggle_strikethrough(self, _checked=False):
        if not self.visual_editing_available(): return
        fmt=QTextCharFormat(); fmt.setFontStrikeOut(not self._effective_character_format().fontStrikeOut()); self.merge_character_format(fmt)

    def _toggle_vertical_alignment(self, alignment):
        """Toggle superscript or subscript without changing the logical font size."""
        if not self.visual_editing_available():
            return
        current = self._effective_character_format().verticalAlignment()
        target = (
            QTextCharFormat.VerticalAlignment.AlignNormal
            if current == alignment
            else alignment
        )
        fmt = QTextCharFormat()
        fmt.setVerticalAlignment(target)
        self.merge_character_format(fmt)

    def toggle_superscript(self, _checked=False):
        self._toggle_vertical_alignment(
            QTextCharFormat.VerticalAlignment.AlignSuperScript
        )

    def toggle_subscript(self, _checked=False):
        self._toggle_vertical_alignment(
            QTextCharFormat.VerticalAlignment.AlignSubScript
        )

    @staticmethod
    def _highlight_contrast_colour(colour):
        luminance=(299*colour.red()+587*colour.green()+114*colour.blue())/1000.0
        return QColor(Qt.GlobalColor.black if luminance>=145 else Qt.GlobalColor.white)

    def _apply_highlight(self, colour=None, clear=False):
        editor=self.visual_editor; original=editor.textCursor(); cursor=QTextCursor(original); document=editor.document()
        if not cursor.hasSelection():
            word=self._word_cursor_at_caret(cursor)
            if word is not None:
                cursor=word
        start=min(cursor.selectionStart(),cursor.selectionEnd()); end=max(cursor.selectionStart(),cursor.selectionEnd())
        ranges=[]
        if cursor.hasSelection():
            position=start
            while position<end:
                probe=QTextCursor(document); probe.setPosition(position)
                current=probe.charFormat(); tagged=bool(current.property(RTF_AUTOMATIC_CONTRAST_PROPERTY))
                explicit=_qt_brush_colour(current.foreground()) is not None and not tagged
                run_end=position+1
                while run_end<end:
                    q=QTextCursor(document); q.setPosition(run_end); qfmt=q.charFormat()
                    qtagged=bool(qfmt.property(RTF_AUTOMATIC_CONTRAST_PROPERTY))
                    qexplicit=_qt_brush_colour(qfmt.foreground()) is not None and not qtagged
                    if qexplicit!=explicit or qtagged!=tagged:
                        break
                    run_end+=1
                ranges.append((position,run_end,explicit,tagged)); position=run_end
        else:
            current=editor.currentCharFormat(); tagged=bool(current.property(RTF_AUTOMATIC_CONTRAST_PROPERTY))
            explicit=_qt_brush_colour(current.foreground()) is not None and not tagged
            ranges=[(None,None,explicit,tagged)]
        original.beginEditBlock()
        try:
            for run_start,run_end,explicit,tagged in ranges:
                fmt=QTextCharFormat()
                if clear:
                    fmt.setBackground(QBrush(Qt.BrushStyle.NoBrush))
                    if tagged:
                        fmt.setForeground(QBrush(Qt.BrushStyle.NoBrush))
                        fmt.setProperty(RTF_AUTOMATIC_CONTRAST_PROPERTY,False)
                else:
                    fmt.setBackground(colour)
                    if not explicit:
                        fmt.setForeground(self._highlight_contrast_colour(colour))
                        fmt.setProperty(RTF_AUTOMATIC_CONTRAST_PROPERTY,True)
                if run_start is None:
                    editor.mergeCurrentCharFormat(fmt)
                else:
                    run=QTextCursor(document); run.setPosition(run_start); run.setPosition(run_end,QTextCursor.MoveMode.KeepAnchor); run.mergeCharFormat(fmt)
        finally:
            original.endEditBlock()
        editor.setTextCursor(original); editor.setFocus(); self.update_formatting_state()

    def choose_text_colour(self, _checked=False):
        if not self.visual_editing_available(): return
        current=_qt_brush_colour(self._effective_character_format().foreground()) or QColor(Qt.GlobalColor.black)
        colour=QColorDialog.getColor(current,self,"Text Colour")
        if colour.isValid():
            fmt=QTextCharFormat(); fmt.setForeground(colour); fmt.setProperty(RTF_AUTOMATIC_CONTRAST_PROPERTY,False); self.merge_character_format(fmt)

    def choose_highlight_colour(self, _checked=False):
        if not self.visual_editing_available():
            return
        dialog=QDialog(self); dialog.setWindowTitle("Highlight Colour — Rico Plus")
        outer=QVBoxLayout(dialog)
        label=QLabel("Standard highlight colours",dialog); outer.addWidget(label)
        grid=QGridLayout(); outer.addLayout(grid)
        palette=(
            ("Yellow", "#fff200"), ("Green", "#92d050"),
            ("Blue", "#5b9bd5"), ("Cyan", "#66ffff"),
            ("Pink", "#ff99cc"), ("Red", "#ff6666"),
            ("Orange", "#f4b183"), ("Black", "#000000"),
        )
        chosen={"colour":None,"clear":False}
        def choose(hex_colour):
            chosen["colour"]=QColor(hex_colour); dialog.accept()
        for index,(name,hex_colour) in enumerate(palette):
            button=QPushButton(name,dialog); button.setMinimumWidth(92)
            colour=QColor(hex_colour); text="#ffffff" if colour.lightness()<110 else "#000000"
            button.setStyleSheet(f"QPushButton {{ background:{hex_colour}; color:{text}; padding:6px; }}")
            button.clicked.connect(lambda _checked=False,value=hex_colour:choose(value))
            grid.addWidget(button,index//4,index%4)
        row=QHBoxLayout(); outer.addLayout(row)
        clear_button=QPushButton("Clear Highlight",dialog); clear_button.clicked.connect(lambda: (chosen.__setitem__("clear",True),dialog.accept())); row.addWidget(clear_button)
        custom_button=QPushButton("Custom…",dialog)
        def custom():
            current=_qt_brush_colour(self.visual_editor.currentCharFormat().background()) or QColor(Qt.GlobalColor.yellow)
            colour=QColorDialog.getColor(current,self,"Custom Highlight Colour")
            if colour.isValid(): chosen["colour"]=colour; dialog.accept()
        custom_button.clicked.connect(custom); row.addWidget(custom_button); row.addStretch(1)
        cancel=QPushButton("Cancel",dialog); cancel.clicked.connect(dialog.reject); row.addWidget(cancel)
        if dialog.exec()!=QDialog.DialogCode.Accepted:
            return
        if chosen["clear"]:
            self.clear_highlight(); return
        colour=chosen["colour"]
        if isinstance(colour,QColor) and colour.isValid():
            self._apply_highlight(colour=colour)

    def clear_highlight(self, _checked=False):
        if not self.visual_editing_available():
            return
        self._apply_highlight(clear=True)

    def _blocks_touched_by_cursor(self, cursor):
        """Return each QTextBlock touched by a selection exactly once."""
        document=self.visual_editor.document()
        if cursor.hasSelection():
            start=min(cursor.selectionStart(),cursor.selectionEnd())
            end=max(cursor.selectionStart(),cursor.selectionEnd())
            probe_end=max(start,end-1)
        else:
            start=cursor.position(); end=start; probe_end=start
        block=document.findBlock(start)
        last=document.findBlock(probe_end)
        blocks=[]
        while block.isValid():
            blocks.append(block)
            if block==last:
                break
            block=block.next()
        return blocks,start,end

    def _document_plain_char_format(self):
        """Return the open document's plain-text baseline, never an app preference."""
        font=self.visual_editor.document().defaultFont()
        plain=QTextCharFormat()
        try:
            families=font.families()
            if families:
                plain.setFontFamilies(families)
            elif font.family():
                plain.setFontFamily(font.family())
        except Exception:
            if font.family():
                plain.setFontFamily(font.family())
        size=float(font.pointSizeF() or 0.0)
        if size>0:
            plain.setFontPointSize(size)
        plain.setFontWeight(font.weight())
        plain.setFontItalic(font.italic())
        plain.setFontUnderline(font.underline())
        plain.setFontStrikeOut(font.strikeOut())
        try:
            plain.setFontOverline(False)
        except Exception:
            pass
        plain.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignNormal)
        plain.setBackground(QBrush(Qt.BrushStyle.NoBrush))
        return plain

    def clear_formatting(self, _checked=False):
        """Reset selected text/paragraph formatting while preserving document objects.

        Links keep their targets; images/inline objects and table structure are not
        destroyed. Paragraph alignment, indents, tabs, spacing, line spacing,
        heading state and list membership are reset to the open document's plain
        baseline. The application New Document Defaults preference is never imposed
        on an existing RTF.
        """
        if not self.visual_editing_available(): return
        editor=self.visual_editor; cursor=editor.textCursor(); blocks,start,end=self._blocks_touched_by_cursor(cursor)
        if not blocks: return
        if not cursor.hasSelection():
            start=blocks[0].position(); end=start+max(0,blocks[0].length()-1)
        document=editor.document(); cursor.beginEditBlock()
        try:
            # Clear direct character formatting only over the selected text. An
            # empty QTextCharFormat inherits the document's own RTF default.
            for block in blocks:
                iterator=block.begin()
                while not iterator.atEnd():
                    fragment=iterator.fragment(); iterator+=1
                    if not fragment.isValid(): continue
                    frag_start=fragment.position(); frag_end=frag_start+fragment.length()
                    sel_start=max(start,frag_start); sel_end=min(end,frag_end)
                    if sel_start>=sel_end: continue
                    original=fragment.charFormat()
                    try:
                        if original.isImageFormat() or int(original.objectType())!=0:
                            continue
                    except (TypeError,ValueError):
                        if original.isImageFormat(): continue
                    plain=self._document_plain_char_format()
                    if original.isAnchor():
                        plain.setAnchor(True); plain.setAnchorHref(original.anchorHref()); plain.setAnchorNames(original.anchorNames())
                    run_cursor=QTextCursor(document); run_cursor.setPosition(sel_start); run_cursor.setPosition(sel_end,QTextCursor.MoveMode.KeepAnchor); run_cursor.setCharFormat(plain)
            # Paragraph formatting is block-scoped, so every touched paragraph
            # is reset even when the user selected only part of its text.
            for block in blocks:
                old=block.blockFormat()
                try:
                    if old.property(QTextFormat.Property.BlockTrailingHorizontalRulerWidth):
                        continue
                except Exception:
                    pass
                block_cursor=QTextCursor(block)
                plain_block=QTextBlockFormat()
                try:
                    plain_block.setPageBreakPolicy(old.pageBreakPolicy())
                except Exception:
                    pass
                block_cursor.setBlockFormat(plain_block)
                block_cursor.setBlockCharFormat(self._document_plain_char_format())
        finally:
            cursor.endEditBlock()
        restored=QTextCursor(document); restored.setPosition(start)
        if end>start: restored.setPosition(end,QTextCursor.MoveMode.KeepAnchor)
        editor.setTextCursor(restored); editor.setFocus(); self.update_formatting_state()

    def _mutate_touched_block_formats(self, mutator):
        """Change only requested properties on each selected paragraph's own format."""
        editor=self.visual_editor; cursor=editor.textCursor(); blocks,start,end=self._blocks_touched_by_cursor(cursor)
        if not blocks:
            return
        cursor.beginEditBlock()
        try:
            for block in blocks:
                block_cursor=QTextCursor(block); block_format=QTextBlockFormat(block.blockFormat())
                mutator(block_format,block)
                block_cursor.setBlockFormat(block_format)
        finally:
            cursor.endEditBlock()
        restored=QTextCursor(editor.document()); restored.setPosition(start)
        if end>start:
            restored.setPosition(end,QTextCursor.MoveMode.KeepAnchor)
        editor.setTextCursor(restored); editor.setFocus(); self.update_formatting_state()

    def set_alignment(self, alignment):
        if not self.visual_editing_available():
            return
        self._mutate_touched_block_formats(lambda fmt,_block: fmt.setAlignment(alignment))

    def apply_heading_from_combo(self, _index):
        if self.heading_combo.signalsBlocked():
            return
        self.apply_heading(int(self.heading_combo.currentData() or 0))

    def apply_heading(self, level):
        """Apply a paragraph style immediately to every paragraph touched by the selection."""
        level=max(0,min(6,int(level)))
        if not self.visual_editing_available(): return
        editor=self.visual_editor; cursor=editor.textCursor(); blocks,start,end=self._blocks_touched_by_cursor(cursor)
        if not blocks: return
        normal_size=float(editor.document().defaultFont().pointSizeF() or 11.0)
        sizes={0:normal_size,1:24,2:20,3:17,4:15,5:13,6:12}
        default_font=editor.document().defaultFont()
        char_format=QTextCharFormat(); char_format.setFontPointSize(float(sizes[level]))
        char_format.setFontWeight(default_font.weight() if level==0 else QFont.Weight.Bold)
        char_format.setFontItalic(default_font.italic() if level==0 else False)
        cursor.beginEditBlock()
        try:
            for block in blocks:
                block_cursor=QTextCursor(block); block_format=QTextBlockFormat(block.blockFormat())
                if hasattr(block_format,"setHeadingLevel"): block_format.setHeadingLevel(level)
                block_cursor.setBlockFormat(block_format)
                block_cursor.setBlockCharFormat(char_format)
                text_length=max(0,block.length()-1)
                if text_length:
                    text_cursor=QTextCursor(editor.document()); text_cursor.setPosition(block.position()); text_cursor.setPosition(block.position()+text_length,QTextCursor.MoveMode.KeepAnchor); text_cursor.mergeCharFormat(char_format)
        finally:
            cursor.endEditBlock()
        restored=QTextCursor(editor.document()); restored.setPosition(start)
        if end>start: restored.setPosition(end,QTextCursor.MoveMode.KeepAnchor)
        editor.setTextCursor(restored); editor.setFocus(); self.update_formatting_state()

    def _remove_list_from_blocks(self, blocks):
        for block in blocks:
            block_cursor=QTextCursor(block); block_format=QTextBlockFormat(block.blockFormat())
            block_format.setObjectIndex(-1); block_format.setIndent(0); block_format.setLeftMargin(0.0); block_format.setTextIndent(0.0)
            block_cursor.setBlockFormat(block_format)

    def _sync_list_marker_format(self, block):
        """Make Qt's list marker use the paragraph's first real text formatting."""
        iterator=block.begin()
        while not iterator.atEnd():
            fragment=iterator.fragment(); iterator+=1
            if not fragment.isValid() or not fragment.text():
                continue
            try:
                if fragment.charFormat().isImageFormat():
                    continue
            except Exception:
                pass
            QTextCursor(block).setBlockCharFormat(fragment.charFormat())
            return
        QTextCursor(block).setBlockCharFormat(self._document_plain_char_format())

    def _toggle_list_style(self, style):
        if not self.visual_editing_available(): return
        editor=self.visual_editor; cursor=editor.textCursor(); blocks,start,end=self._blocks_touched_by_cursor(cursor)
        if not blocks: return
        already=all(block.textList() is not None and block.textList().format().style()==style for block in blocks)
        cursor.beginEditBlock()
        try:
            self._remove_list_from_blocks(blocks)
            if not already:
                fmt=QTextListFormat(); fmt.setStyle(style); fmt.setIndent(1)
                for block in blocks:
                    self._sync_list_marker_format(block)
                first_cursor=QTextCursor(blocks[0]); text_list=first_cursor.createList(fmt)
                for block in blocks[1:]: text_list.add(block)
        finally:
            cursor.endEditBlock()
        restored=QTextCursor(editor.document()); restored.setPosition(start)
        if end>start: restored.setPosition(end,QTextCursor.MoveMode.KeepAnchor)
        editor.setTextCursor(restored); editor.setFocus(); self.update_formatting_state()

    def _remove_current_list(self, cursor):
        blocks,_,_=self._blocks_touched_by_cursor(cursor); self._remove_list_from_blocks(blocks)

    def toggle_bullet_list(self, _checked=False):
        self._toggle_list_style(QTextListFormat.Style.ListDisc)

    def change_indent(self, amount):
        if not self.visual_editing_available():
            return
        delta=int(amount)
        if not delta:
            return
        editor=self.visual_editor; cursor=editor.textCursor(); blocks,start,end=self._blocks_touched_by_cursor(cursor)
        if not blocks:
            return

        try:
            indent_width=float(editor.document().indentWidth() or 40.0)
        except Exception:
            indent_width=40.0

        selected_positions={block.position() for block in blocks}
        entries=[]
        for block in blocks:
            block_format=QTextBlockFormat(block.blockFormat()); text_list=block.textList()
            if text_list is None:
                visual_left=float(block_format.leftMargin())+max(0,int(block_format.indent()))*indent_width
                entries.append({"block":block,"format":block_format,"list":None,"left":max(0.0,visual_left+delta*indent_width)})
                continue
            list_format=QTextListFormat(text_list.format())
            current_level=max(1,int(list_format.indent() or 1))
            legacy_block_indent=max(0,int(block_format.indent()))
            target_level=max(1,min(9,current_level+legacy_block_indent+delta))
            entries.append({
                "block":block,
                "format":block_format,
                "list":text_list,
                "list_index":text_list.objectIndex(),
                "list_format":list_format,
                "current_level":current_level,
                "target_level":target_level,
                "legacy_block_indent":legacy_block_indent,
            })

        def compatible_list(text_list, source_format, target_level):
            if text_list is None:
                return False
            candidate=text_list.format()
            return (
                int(candidate.indent() or 1)==target_level
                and candidate.style()==source_format.style()
                and candidate.numberPrefix()==source_format.numberPrefix()
                and candidate.numberSuffix()==source_format.numberSuffix()
                and candidate.start()==source_format.start()
            )

        cursor.beginEditBlock()
        try:
            for entry in entries:
                if entry["list"] is not None:
                    continue
                block_format=entry["format"]
                block_format.setIndent(0)
                block_format.setLeftMargin(entry["left"])
                QTextCursor(entry["block"]).setBlockFormat(block_format)

            index=0
            while index<len(entries):
                entry=entries[index]
                if entry["list"] is None:
                    index+=1
                    continue
                group=[entry]; following=index+1
                while following<len(entries):
                    candidate=entries[following]
                    if (
                        candidate["list"] is None
                        or candidate["list_index"]!=entry["list_index"]
                        or candidate["target_level"]!=entry["target_level"]
                        or group[-1]["block"].next()!=candidate["block"]
                    ):
                        break
                    group.append(candidate); following+=1

                unchanged=(
                    entry["target_level"]==entry["current_level"]
                    and all(item["legacy_block_indent"]==0 for item in group)
                )
                if not unchanged:
                    for item in group:
                        block_format=item["format"]
                        block_format.setIndent(0)
                        QTextCursor(item["block"]).setBlockFormat(block_format)

                    target_format=QTextListFormat(entry["list_format"])
                    target_format.setIndent(entry["target_level"])
                    target_list=None
                    previous=group[0]["block"].previous()
                    if previous.isValid() and previous.position() not in selected_positions:
                        candidate=previous.textList()
                        if compatible_list(candidate,target_format,entry["target_level"]):
                            target_list=candidate
                    if target_list is None:
                        next_block=group[-1]["block"].next()
                        if next_block.isValid() and next_block.position() not in selected_positions:
                            candidate=next_block.textList()
                            if compatible_list(candidate,target_format,entry["target_level"]):
                                target_list=candidate
                    if target_list is None:
                        target_list=QTextCursor(group[0]["block"]).createList(target_format)
                    else:
                        target_list.add(group[0]["block"])
                    for item in group[1:]:
                        target_list.add(item["block"])
                index=following
        finally:
            cursor.endEditBlock()
        restored=QTextCursor(editor.document()); restored.setPosition(start)
        if end>start:
            restored.setPosition(end,QTextCursor.MoveMode.KeepAnchor)
        editor.setTextCursor(restored); editor.setFocus(); self.update_formatting_state()

    def apply_line_spacing_from_combo(self, _index):
        if self.line_spacing_combo.signalsBlocked():
            return
        self.set_line_spacing(int(self.line_spacing_combo.currentData() or 100))

    def set_line_spacing(self, percent):
        if not self.visual_editing_available():
            return
        percent=max(50,min(400,int(percent)))
        self._mutate_touched_block_formats(
            lambda fmt,_block: fmt.setLineHeight(float(percent),QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
        )

    def show_paragraph_dialog(self):
        if not self.visual_editing_available():
            return
        current = self.visual_editor.textCursor().blockFormat()
        dialog = QDialog(self)
        dialog.setWindowTitle("Paragraph")
        form = QFormLayout(dialog)
        alignment = QComboBox(dialog)
        for label, value in (
            ("Left", Qt.AlignmentFlag.AlignLeft),
            ("Centre", Qt.AlignmentFlag.AlignHCenter),
            ("Right", Qt.AlignmentFlag.AlignRight),
            ("Justify", Qt.AlignmentFlag.AlignJustify),
        ):
            alignment.addItem(label, value)
        current_alignment = current.alignment()
        for idx in range(alignment.count()):
            if current_alignment & alignment.itemData(idx):
                alignment.setCurrentIndex(idx)
                break
        # Qt stores paragraph margins/indents in layout pixels, while RTF and
        # this dialog present document measurements in points.  Convert at the
        # boundary instead of relabelling raw pixels as points.
        px_to_pt = lambda value: float(value) * 72.0 / 96.0
        pt_to_px = lambda value: float(value) * 96.0 / 72.0
        left = QSpinBox(dialog); left.setRange(0, 1000); left.setValue(round(px_to_pt(current.leftMargin())))
        right = QSpinBox(dialog); right.setRange(0, 1000); right.setValue(round(px_to_pt(current.rightMargin())))
        first = QSpinBox(dialog); first.setRange(-500, 1000); first.setValue(round(px_to_pt(current.textIndent())))
        before = QSpinBox(dialog); before.setRange(0, 500); before.setValue(round(px_to_pt(current.topMargin())))
        after = QSpinBox(dialog); after.setRange(0, 500); after.setValue(round(px_to_pt(current.bottomMargin())))
        spacing = QComboBox(dialog)
        for label, value in (("1.0", 100), ("1.15", 115), ("1.5", 150), ("2.0", 200)):
            spacing.addItem(label, value)
        current_spacing=round(current.lineHeight()) if current.lineHeight() else 100
        spacing.setCurrentIndex(min(range(spacing.count()),key=lambda i:abs(int(spacing.itemData(i))-current_spacing)))
        form.addRow("Alignment:", alignment)
        form.addRow("Left indent (pt):", left)
        form.addRow("Right indent (pt):", right)
        form.addRow("First line (pt):", first)
        form.addRow("Space before (pt):", before)
        form.addRow("Space after (pt):", after)
        form.addRow("Line spacing:", spacing)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, parent=dialog)
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        def apply_paragraph(fmt,_block):
            fmt.setAlignment(alignment.currentData())
            fmt.setLeftMargin(pt_to_px(left.value()))
            fmt.setRightMargin(pt_to_px(right.value()))
            fmt.setTextIndent(pt_to_px(first.value()))
            fmt.setTopMargin(pt_to_px(before.value()))
            fmt.setBottomMargin(pt_to_px(after.value()))
            fmt.setLineHeight(float(spacing.currentData()), QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
        self._mutate_touched_block_formats(apply_paragraph)

    def update_formatting_state(self, _format=None):
        if not hasattr(self, "visual_editor"):
            return
        fmt = self.visual_editor.currentCharFormat()
        block = self.visual_editor.textCursor().blockFormat()
        controls = [
            self.font_combo, self.font_size_combo, self.font_weight_combo, self.heading_combo,
            self.line_spacing_combo, self.bold_button, self.italic_button,
            self.underline_button, self.strike_button, self.align_left_button,
            self.align_center_button, self.align_right_button,
            self.align_justify_button, self.bullet_button,
        ]
        for control in controls:
            control.blockSignals(True)
        try:
            self.font_combo.setCurrentFont(fmt.font())
            self._reset_font_face_display()
            size = self._logical_char_size(fmt)
            self.font_size_combo.setEditText(f"{size:g}")
            current_weight = int(fmt.fontWeight())
            weight_idx = min(
                range(self.font_weight_combo.count()),
                key=lambda i: abs(int(self.font_weight_combo.itemData(i)) - current_weight),
            )
            self.font_weight_combo.setCurrentIndex(weight_idx)
            level = block.headingLevel() if hasattr(block, "headingLevel") else 0
            idx = self.heading_combo.findData(level)
            self.heading_combo.setCurrentIndex(max(0, idx))
            bold = int(fmt.fontWeight()) >= int(QFont.Weight.Bold)
            self.bold_button.setChecked(bold)
            self.italic_button.setChecked(fmt.fontItalic())
            self.underline_button.setChecked(fmt.fontUnderline())
            self.strike_button.setChecked(fmt.fontStrikeOut())
            alignment = block.alignment()
            self.align_left_button.setChecked(bool(alignment & Qt.AlignmentFlag.AlignLeft))
            self.align_center_button.setChecked(bool(alignment & Qt.AlignmentFlag.AlignHCenter))
            self.align_right_button.setChecked(bool(alignment & Qt.AlignmentFlag.AlignRight))
            self.align_justify_button.setChecked(bool(alignment & Qt.AlignmentFlag.AlignJustify))
            current_list = self.visual_editor.textCursor().currentList()
            style = current_list.format().style() if current_list else None
            self.bullet_button.setChecked(style == QTextListFormat.Style.ListDisc)
            line_height = round(block.lineHeight()) if block.lineHeight() else 100
            spacing_idx = min(
                range(self.line_spacing_combo.count()),
                key=lambda i: abs(
                    int(self.line_spacing_combo.itemData(i)) - line_height
                ),
            )
            self.line_spacing_combo.setCurrentIndex(spacing_idx)
        finally:
            for control in controls:
                control.blockSignals(False)
        self._reset_font_face_display()
        QTimer.singleShot(0, self._reset_font_face_display)
        for action, checked in (
            (getattr(self, "bold_action", None), int(fmt.fontWeight()) >= int(QFont.Weight.Bold)),
            (getattr(self, "italic_action", None), fmt.fontItalic()),
            (getattr(self, "underline_action", None), fmt.fontUnderline()),
            (getattr(self, "strike_action", None), fmt.fontStrikeOut()),
            (
                getattr(self, "superscript_action", None),
                fmt.verticalAlignment()
                == QTextCharFormat.VerticalAlignment.AlignSuperScript,
            ),
            (
                getattr(self, "subscript_action", None),
                fmt.verticalAlignment()
                == QTextCharFormat.VerticalAlignment.AlignSubScript,
            ),
        ):
            if action is not None:
                action.blockSignals(True)
                action.setChecked(checked)
                action.blockSignals(False)
        current_list = self.visual_editor.textCursor().currentList()
        list_style = current_list.format().style() if current_list else None
        for action, checked in (
            (getattr(self, "bulleted_list_action", None), list_style == QTextListFormat.Style.ListDisc),
            (getattr(self, "alignment_left_action", None), bool(block.alignment() & Qt.AlignmentFlag.AlignLeft)),
            (getattr(self, "alignment_center_action", None), bool(block.alignment() & Qt.AlignmentFlag.AlignHCenter)),
            (getattr(self, "alignment_right_action", None), bool(block.alignment() & Qt.AlignmentFlag.AlignRight)),
            (getattr(self, "alignment_justify_action", None), bool(block.alignment() & Qt.AlignmentFlag.AlignJustify)),
        ):
            if action is not None:
                action.blockSignals(True)
                action.setChecked(checked)
                action.blockSignals(False)
        current_level = (
            block.headingLevel() if hasattr(block, "headingLevel") else 0
        )
        for level, action in getattr(self, "heading_actions", {}).items():
            action.blockSignals(True)
            action.setChecked(level == current_level)
            action.blockSignals(False)
        if hasattr(self, "table_edit_actions"):
            in_table = (
                not self.view_only
                and self.visual_editor.textCursor().currentTable() is not None
            )
            for action in self.table_edit_actions:
                action.setEnabled(in_table)
        if hasattr(self, "edit_link_action"):
            in_link = (not self.view_only and self._visual_anchor_cursor() is not None)
            self.edit_link_action.setEnabled(in_link)
            self.remove_link_action.setEnabled(in_link)

    def insert_link(self, _checked=False):
        if not self.visual_editing_available(): return
        cursor=self.visual_editor.textCursor(); selected=cursor.selectedText().replace("\u2029","\n")
        dialog=QDialog(self); dialog.setWindowTitle("Insert Link — Rico Plus"); form=QFormLayout(dialog); text=QLineEdit(selected,dialog); url=QLineEdit("https://",dialog); form.addRow("Text:",text); form.addRow("Address:",url); buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel,parent=dialog); buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); form.addRow(buttons)
        if dialog.exec()!=QDialog.DialogCode.Accepted: return
        label=text.text().strip() or url.text().strip(); target=url.text().strip()
        if not target or not is_safe_link_target(target): QMessageBox.warning(self,"Link — Rico Plus","Use a safe http, https, mailto or local anchor target."); return
        fmt=QTextCharFormat(); fmt.setAnchor(True); fmt.setAnchorHref(target); fmt.setForeground(self.palette().color(QPalette.ColorRole.Link)); fmt.setFontUnderline(True); cursor.insertText(label,fmt); self.visual_editor.setTextCursor(cursor)

    @staticmethod
    def _image_dimensions_safe(image):
        if image.isNull():
            return False
        width = max(0, int(image.width()))
        height = max(0, int(image.height()))
        return width > 0 and height > 0 and width * height <= MAX_IMAGE_PIXELS

    def _image_data_url(self, image):
        if not self._image_dimensions_safe(image):
            return None
        array = QByteArray()
        buffer = QBuffer(array)
        if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
            return None
        try:
            if not image.save(buffer, "PNG"):
                return None
        finally:
            buffer.close()
        data = bytes(array)
        if len(data) > MAX_EMBEDDED_IMAGE_SIZE:
            return None
        return "data:image/png;base64," + base64.b64encode(data).decode("ascii")

    def _insert_image_resource(self, name, image):
        if image.isNull():
            return False
        resource_url = QUrl(name)
        self.visual_editor.document().addResource(
            QTextDocument.ResourceType.ImageResource, resource_url, image
        )
        image_format = QTextImageFormat()
        image_format.setName(name)
        max_width = max(200, self.visual_editor.viewport().width() * 0.9)
        width = image.width()
        height = image.height()
        if width > max_width:
            ratio = max_width / width
            width *= ratio
            height *= ratio
        image_format.setWidth(width)
        image_format.setHeight(height)
        cursor = self.visual_editor.textCursor()
        cursor.insertImage(image_format)
        self.visual_editor.setTextCursor(cursor)
        return True

    def insert_image_data(self, image):
        if not self.visual_editing_available():
            return False
        name = self._image_data_url(image)
        if not name:
            QMessageBox.warning(
                self, "Image Too Large",
                "The image is too large to decode or embed safely."
            )
            return False
        return self._insert_image_resource(name, image)

    def insert_image_path(self, path):
        if not self.visual_editing_available():
            return False
        try:
            if os.path.getsize(path) > MAX_IMAGE_SOURCE_SIZE:
                raise ValueError("The image file is too large to load safely.")
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Image Error", f"Could not inspect the image:\n{exc}")
            return False

        reader = QImageReader(path)
        dimensions = reader.size()
        if (
            dimensions.isValid()
            and dimensions.width() > 0
            and dimensions.height() > 0
            and dimensions.width() * dimensions.height() > MAX_IMAGE_PIXELS
        ):
            QMessageBox.warning(
                self, "Image Too Large",
                "The image dimensions are too large to decode safely."
            )
            return False
        reader.setAutoTransform(True)
        image = reader.read()
        if image.isNull():
            message = reader.errorString() or "Qt could not decode this image format."
            QMessageBox.warning(self, "Image Error", message)
            return False
        # Keep original PNG/JPEG bytes when possible.  RTF can embed both
        # formats natively, so decoding/re-encoding a photograph on every save
        # only discards metadata/colour-profile information and makes repeated
        # save cycles needlessly non-idempotent.  Other raster formats are
        # normalised once to PNG for portable RTF embedding.
        suffix = Path(path).suffix.lower()
        if suffix in {".png", ".jpg", ".jpeg"}:
            try:
                raw = read_bounded_bytes(path, MAX_EMBEDDED_IMAGE_SIZE, label="image")
            except (OSError, ValueError):
                raw = b""
            if raw:
                mime = "image/jpeg" if suffix in {".jpg", ".jpeg"} else "image/png"
                name = f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")
                return self._insert_image_resource(name, image)
        return self.insert_image_data(image)

    def insert_image(self):
        if not self.visual_editing_available():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Insert Image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp);;All Files (*)",
        )
        if path:
            self.insert_image_path(path)

    def _visual_anchor_cursor(self):
        """Return a cursor selecting the anchor under/adjacent to the caret."""
        document = self.visual_editor.document()
        cursor = self.visual_editor.textCursor()
        probe = QTextCursor(cursor)
        if cursor.hasSelection():
            fmt = cursor.charFormat()
            return cursor if fmt.isAnchor() and fmt.anchorHref() else None
        position = cursor.position()
        candidate_positions = [position]
        if position > 0:
            candidate_positions.append(position - 1)
        href = ""
        anchor_position = None
        for candidate in candidate_positions:
            probe.setPosition(candidate)
            fmt = probe.charFormat()
            if fmt.isAnchor() and fmt.anchorHref():
                href = fmt.anchorHref()
                anchor_position = candidate
                break
        if not href or anchor_position is None:
            return None
        start = anchor_position
        end = anchor_position
        max_position = max(0, document.characterCount() - 1)
        while start > 0:
            probe.setPosition(start - 1)
            fmt = probe.charFormat()
            if not (fmt.isAnchor() and fmt.anchorHref() == href):
                break
            start -= 1
        while end < max_position:
            probe.setPosition(end)
            fmt = probe.charFormat()
            if not (fmt.isAnchor() and fmt.anchorHref() == href):
                break
            end += 1
        if end <= start:
            return None
        result = QTextCursor(document)
        result.setPosition(start)
        result.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        return result

    def edit_link(self):
        if not self.visual_editing_available():
            return
        cursor = self._visual_anchor_cursor()
        if cursor is None:
            self._show_status_message("Place the caret inside a link to edit it.", 4000)
            return
        current = cursor.charFormat().anchorHref()
        url, accepted = QInputDialog.getText(self, "Edit Link", "Address:", text=current)
        if not accepted:
            return
        url = url.strip()
        if not url or not is_safe_link_target(url):
            QMessageBox.warning(
                self, "Unsupported Link — Rico Plus",
                "Use an HTTP, HTTPS, mailto, document-relative, or #fragment link.",
            )
            return
        fmt = QTextCharFormat()
        fmt.setAnchor(True)
        fmt.setAnchorHref(url)
        fmt.setForeground(self.palette().color(self.palette().ColorRole.Link))
        fmt.setFontUnderline(True)
        cursor.mergeCharFormat(fmt)
        self.visual_editor.setTextCursor(cursor)

    def remove_link(self):
        if not self.visual_editing_available():
            return
        cursor = self._visual_anchor_cursor()
        if cursor is None:
            self._show_status_message("Place the caret inside a link to remove it.", 4000)
            return
        fmt = QTextCharFormat()
        fmt.setAnchor(False)
        fmt.setAnchorHref("")
        fmt.setFontUnderline(False)
        try:
            fmt.clearForeground()
        except Exception:
            pass
        cursor.mergeCharFormat(fmt)
        self.visual_editor.setTextCursor(cursor)

    def _current_visual_table(self):
        cursor = self.visual_editor.textCursor()
        table = cursor.currentTable()
        if table is None:
            return None, None
        cell = table.cellAt(cursor)
        return table, cell

    def insert_table_row_above(self):
        table, cell = self._current_visual_table()
        if self.visual_editing_available() and table is not None and cell is not None:
            table.insertRows(cell.row(), 1)

    def insert_table_row_below(self):
        table, cell = self._current_visual_table()
        if self.visual_editing_available() and table is not None and cell is not None:
            table.insertRows(cell.row() + 1, 1)

    def delete_table_row(self):
        table, cell = self._current_visual_table()
        if self.visual_editing_available() and table is not None and cell is not None:
            table.removeRows(cell.row(), 1)

    def insert_table_column_left(self):
        table, cell = self._current_visual_table()
        if self.visual_editing_available() and table is not None and cell is not None:
            table.insertColumns(cell.column(), 1)

    def insert_table_column_right(self):
        table, cell = self._current_visual_table()
        if self.visual_editing_available() and table is not None and cell is not None:
            table.insertColumns(cell.column() + 1, 1)

    def delete_table_column(self):
        table, cell = self._current_visual_table()
        if self.visual_editing_available() and table is not None and cell is not None:
            table.removeColumns(cell.column(), 1)

    def delete_table(self):
        table, _cell = self._current_visual_table()
        if not self.visual_editing_available() or table is None:
            return
        table.removeRows(0, table.rows())

    def insert_horizontal_rule(self, _checked=False):
        if not self.visual_editing_available():
            return
        # A QTextCursor.insertBlock() normally inherits the current block format.
        # If the ruler property is left on that format, the paragraph created
        # after the rule inherits it and Qt draws two rules.  Preserve the
        # surrounding paragraph format explicitly, but clear the ruler property
        # on the before/after format so exactly one dedicated rule block exists.
        cursor = self.visual_editor.textCursor()
        base_format = QTextBlockFormat(cursor.blockFormat())
        base_format.clearProperty(QTextFormat.Property.BlockTrailingHorizontalRulerWidth)
        rule_format = QTextBlockFormat(base_format)
        rule_format.setProperty(QTextFormat.Property.BlockTrailingHorizontalRulerWidth, 100)
        cursor.beginEditBlock()
        cursor.insertBlock(base_format)
        cursor.setBlockFormat(rule_format)
        cursor.insertBlock(base_format)
        cursor.endEditBlock()
        self.visual_editor.setTextCursor(cursor)
        self.visual_editor.setFocus()
        self.visual_editor.ensureCursorVisible()

    def insert_table(self, _checked=False):
        if not self.visual_editing_available(): return
        dialog=QDialog(self); dialog.setWindowTitle("Insert Table — Rico Plus"); form=QFormLayout(dialog); rows=QSpinBox(dialog); rows.setRange(1,1000); rows.setValue(2); columns=QSpinBox(dialog); columns.setRange(1,64); columns.setValue(2); form.addRow("Rows:",rows); form.addRow("Columns:",columns); buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel,parent=dialog); buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); form.addRow(buttons)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            if rows.value()*columns.value()>20000: QMessageBox.warning(self,"Table — Rico Plus","Tables are limited to 20,000 cells."); return
            cursor = self.visual_editor.textCursor()
            table_format=QTextTableFormat()
            table_format.setProperty(RTF_TABLE_AUTOFIT_PROPERTY, True)
            table = cursor.insertTable(rows.value(),columns.value(),table_format)
            # QTextDocument keeps structural separator blocks around tables.
            # Mark only those generated empties so RTF export does not invent
            # user paragraphs around a table.
            for block in (table.firstCursorPosition().block().previous(), table.lastCursorPosition().block().next()):
                if block.isValid() and not block.text():
                    block_cursor = QTextCursor(block); fmt = QTextBlockFormat(block.blockFormat()); fmt.setProperty(RTF_SYNTHETIC_STRUCTURE_BLOCK, True); block_cursor.setBlockFormat(fmt)

    def _whole_list_selection_cursor(self, cursor):
        """Expand a whole-item list selection so clipboard HTML retains list semantics."""
        if not cursor.hasSelection():
            return None
        blocks,start,end=self._blocks_touched_by_cursor(cursor)
        if not blocks or any(block.textList() is None for block in blocks):
            return None
        first,last=blocks[0],blocks[-1]
        text_start=first.position()
        text_end=last.position()+max(0,last.length()-1)
        if start>text_start or end<text_end:
            return None
        expanded=QTextCursor(self.visual_editor.document())
        expanded.setPosition(text_start)
        document_end=max(0,self.visual_editor.document().characterCount()-1)
        expanded.setPosition(min(document_end,last.position()+last.length()),QTextCursor.MoveMode.KeepAnchor)
        return expanded

    def copy_selection(self):
        """Copy rich selections without moving the live cursor; preserve whole list items."""
        editor=self.visual_editor; cursor=editor.textCursor()
        position=cursor.position(); anchor=cursor.anchor()
        expanded=self._whole_list_selection_cursor(cursor)
        if expanded is not None:
            fragment=QTextDocumentFragment(expanded)
            mime=QMimeData(); mime.setText(fragment.toPlainText()); mime.setHtml(fragment.toHtml())
            QApplication.clipboard().setMimeData(mime)
        else:
            start=cursor.selectionStart(); end=cursor.selectionEnd()
            start_cursor=QTextCursor(editor.document()); start_cursor.setPosition(start)
            end_cursor=QTextCursor(editor.document()); end_cursor.setPosition(max(start,end-1))
            if (
                cursor.hasSelection()
                and start_cursor.block()==end_cursor.block()
                and "\ufffc" not in cursor.selectedText()
            ):
                # Text-only selections within one paragraph need their inline
                # formatting but not Qt's outer HTML paragraph wrapper. Keep
                # embedded objects/images on Qt's native clipboard path so their
                # resources remain available to the paste target.
                fragment=QTextDocumentFragment(cursor)
                mime=QMimeData(); mime.setText(fragment.toPlainText()); mime.setHtml(fragment.toHtml())
                mime.setData(RICOPAD_INLINE_RICH_MIME,QByteArray(b"1"))
                QApplication.clipboard().setMimeData(mime)
            else:
                editor.copy()
        restored=QTextCursor(editor.document()); restored.setPosition(anchor)
        if position!=anchor:
            restored.setPosition(position,QTextCursor.MoveMode.KeepAnchor)
        editor.setTextCursor(restored); editor.setFocus()

    def cut_selection(self):
        if not self.document_editing_available():
            return
        editor=self.visual_editor; cursor=editor.textCursor()
        if not cursor.hasSelection():
            return
        expanded=self._whole_list_selection_cursor(cursor)
        self.copy_selection()
        target=expanded if expanded is not None else cursor
        target.removeSelectedText()
        editor.setTextCursor(target); editor.setFocus(); self.update_formatting_state()

    def paste_plain_text(self):
        if not self.document_editing_available(): return
        text=QApplication.clipboard().text().replace("\x00","")
        if not text: return
        cursor=self.visual_editor.textCursor(); current=max(0,self.visual_editor.document().characterCount()-1); selected=abs(cursor.selectionEnd()-cursor.selectionStart())
        if len(text)>MAX_PASTE_CHARACTERS or current-selected+len(text)>MAX_DOCUMENT_CHARACTERS: self._show_status_message("The paste would exceed Rico Plus's document safety limit.",5000); QApplication.beep(); return
        cursor.insertText(text)

    def delete_selection(self):
        if not self.document_editing_available():
            return
        cursor = self.text_area.textCursor()
        if cursor.hasSelection():
            cursor.removeSelectedText()
        else:
            cursor.deleteChar()
        self.text_area.setTextCursor(cursor)

    def duplicate_current_line(self):
        """Duplicate the rich selection, or the current logical paragraph."""
        if not self.document_editing_available():
            return
        editor=self.visual_editor; cursor=editor.textCursor()
        if cursor.hasSelection():
            start=min(cursor.selectionStart(),cursor.selectionEnd()); end=max(cursor.selectionStart(),cursor.selectionEnd())
            source=QTextCursor(editor.document()); source.setPosition(start); source.setPosition(end,QTextCursor.MoveMode.KeepAnchor)
            fragment=QTextDocumentFragment(source); insertion=QTextCursor(editor.document()); insertion.setPosition(end); insertion.beginEditBlock()
            try: insertion.insertFragment(fragment)
            finally: insertion.endEditBlock()
            insertion.setPosition(end); insertion.setPosition(end+(end-start),QTextCursor.MoveMode.KeepAnchor); editor.setTextCursor(insertion); editor.ensureCursorVisible(); return
        block=cursor.block(); start=block.position(); end=start+max(0,block.length()-1); source=QTextCursor(editor.document()); source.setPosition(start); source.setPosition(end,QTextCursor.MoveMode.KeepAnchor); fragment=QTextDocumentFragment(source); insertion=QTextCursor(editor.document()); insertion.setPosition(end); insertion.beginEditBlock()
        try: insertion.insertBlock(block.blockFormat(),block.charFormat()); insertion.insertFragment(fragment)
        finally: insertion.endEditBlock()
        editor.setTextCursor(insertion); editor.ensureCursorVisible()

    def delete_current_line(self):
        """Delete the current logical line/block as one undoable operation.

        QTextCursor.BlockUnderCursor does not include the paragraph separator.
        Deleting the selected text and then calling deleteChar() therefore works
        for every block except the final one, where there is no following
        separator to delete.  For a final block with a predecessor, remove the
        preceding separator instead so the last line itself disappears.
        """
        if not self.document_editing_available():
            return
        cursor = self.text_area.textCursor()
        block = cursor.block()
        is_last = not block.next().isValid()
        has_previous = block.previous().isValid()
        cursor.beginEditBlock()
        try:
            cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
            cursor.removeSelectedText()
            if is_last and has_previous:
                cursor.deletePreviousChar()
            elif not is_last:
                cursor.deleteChar()
        finally:
            cursor.endEditBlock()
        self.text_area.setTextCursor(cursor)

    def _logical_char_size(self, char_format):
        displayed = float(char_format.fontPointSize() or 0.0)
        if displayed > 0:
            return displayed
        return float(
            self.visual_editor.document().defaultFont().pointSizeF()
            or self.base_font_size
        )

    @staticmethod
    def _zoom_dots_per_metre(dpi):
        # One inch is exactly 0.0254 metres. Qt's QImage DPI metadata is
        # expressed in integer pixels per metre.
        return max(1, round(float(dpi) / 0.0254))

    def _apply_layout_zoom(self, editor, target_percent, device_attribute):
        """Scale a QTextDocument through layout-device metrics only.

        Unlike rewriting every QTextCharFormat, this does not mutate document
        content, dirty the file, or place display-only changes on the undo stack.
        Explicit font sizes and the editor's base font are laid out against the
        same scaled DPI, so mixed-size rich documents zoom consistently.
        """
        target = max(50, min(300, int(target_percent)))
        layout = editor.document().documentLayout()
        if target == 100:
            layout.setPaintDevice(None)
            device = None
        else:
            device = QImage(1, 1, QImage.Format.Format_ARGB32_Premultiplied)
            scale = target / 100.0
            device.setDotsPerMeterX(
                self._zoom_dots_per_metre(editor.logicalDpiX() * scale)
            )
            device.setDotsPerMeterY(
                self._zoom_dots_per_metre(editor.logicalDpiY() * scale)
            )
            layout.setPaintDevice(device)
        # The layout keeps a raw paint-device pointer, so retain the QImage for
        # as long as that document uses it.
        setattr(self, device_attribute, device)
        document = editor.document()
        document.markContentsDirty(0, max(1, document.characterCount()))
        editor.viewport().update()
        return target

    def _apply_visual_document_zoom(self, target_percent):
        self._visual_document_zoom_percent = self._apply_layout_zoom(
            self.visual_editor, target_percent, "_visual_zoom_device"
        )

    def _unzoomed_visual_document(self):
        # The zoom paint device belongs to the live editor layout. A clone gets
        # its own unscaled layout and therefore serialises logical formatting.
        clone = self.visual_editor.document().clone(self)
        clone.documentLayout().setPaintDevice(None)
        return clone

    def toggle_format_bar(self, checked):
        """Compatibility no-op: formatting is permanently part of Home."""
        self.show_format_bar = True

    def apply_zoom_preference(self):
        self._apply_visual_document_zoom(self.zoom_percent)
        self.update_status_counts()

    def set_zoom_percent(self, value, *, persist=True):
        target = max(50, min(300, int(value)))
        if target == self.zoom_percent and self._visual_document_zoom_percent == target:
            return
        self.zoom_percent = target
        self._apply_visual_document_zoom(target)
        self.update_status_counts()
        self.update_formatting_state()
        if persist:
            self.save_preferences()

    def adjust_zoom_from_wheel(self, angle_delta_y):
        if angle_delta_y > 0:
            self.zoom_in()
        elif angle_delta_y < 0:
            self.zoom_out()

    def zoom_in(self):
        self.set_zoom_percent(self.zoom_percent + 10)

    def zoom_out(self):
        self.set_zoom_percent(self.zoom_percent - 10)

    def zoom_reset(self):
        self.set_zoom_percent(100)

    def apply_tab_width(self):
        distance=self.visual_editor.fontMetrics().horizontalAdvance(" ")*self.tab_width_spaces; option=self.visual_editor.document().defaultTextOption(); option.setTabStopDistance(float(distance)); self.visual_editor.document().setDefaultTextOption(option)

    def open_tab_width_dialog(self):
        value, accepted = QInputDialog.getInt(
            self, "Tab Width", "Spaces per tab:", self.tab_width_spaces, 1, 16, 1
        )
        if accepted:
            self.tab_width_spaces = value
            self.apply_tab_width()
            self.save_preferences()

    def formatted_system_date(self):
        """Return the current date using the desktop's locale."""
        return QLocale.system().toString(
            QDateTime.currentDateTime().date(),
            QLocale.FormatType.ShortFormat,
        )

    def formatted_system_time(self):
        """Return the current time using the desktop's locale."""
        return QLocale.system().toString(
            QDateTime.currentDateTime().time(),
            QLocale.FormatType.ShortFormat,
        )

    def formatted_system_timestamp(self):
        """Return the current locale-aware date and time."""
        return QLocale.system().toString(
            QDateTime.currentDateTime(),
            QLocale.FormatType.ShortFormat,
        )

    def insert_text_at_cursor(self, text):
        """Insert text at the caret and return focus to the editor."""
        if not self.document_editing_available():
            return False
        cursor = self.text_area.textCursor()
        cursor.insertText(text)
        self.text_area.setTextCursor(cursor)
        self.text_area.setFocus()
        self.text_area.ensureCursorVisible()

    def insert_time_date(self):
        """Insert the current system-local date and time at the caret (F5)."""
        self.insert_text_at_cursor(self.formatted_system_timestamp())

    def insert_date(self):
        """Insert the current system-local date at the caret (Ctrl+;)."""
        self.insert_text_at_cursor(self.formatted_system_date())

    def insert_time(self):
        """Insert the current system-local time at the caret (Ctrl+:)."""
        self.insert_text_at_cursor(self.formatted_system_time())

    def show_replace_dialog(self):
        """Show one reusable, modeless Replace dialog."""
        if self.replace_dialog is not None:
            self.replace_dialog.show()
            self.replace_dialog.raise_()
            self.replace_find_entry.setFocus()
            self.replace_find_entry.selectAll()
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Find and Replace — Rico Plus")
        dialog.setModal(False)
        dialog.setMinimumWidth(420)

        outer = QVBoxLayout(dialog)
        form = QFormLayout()
        self.replace_find_entry = QLineEdit(dialog)
        self.replace_with_entry = QLineEdit(dialog)
        form.addRow("Find:", self.replace_find_entry)
        form.addRow("Replace with:", self.replace_with_entry)
        outer.addLayout(form)

        self.replace_case_checkbox = QCheckBox("Match case", dialog)
        outer.addWidget(self.replace_case_checkbox)

        buttons = QHBoxLayout()
        replace_button = QPushButton("Replace", dialog)
        replace_all_button = QPushButton("Replace All", dialog)
        close_button = QPushButton("Close", dialog)
        buttons.addStretch(1)
        buttons.addWidget(replace_button)
        buttons.addWidget(replace_all_button)
        buttons.addWidget(close_button)
        outer.addLayout(buttons)

        replace_button.clicked.connect(self.replace_next)
        replace_all_button.clicked.connect(self.replace_all)
        close_button.clicked.connect(dialog.close)
        self.replace_find_entry.returnPressed.connect(self.replace_next)
        dialog.finished.connect(self._replace_dialog_closed)

        selected = self.text_area.textCursor().selectedText()
        if selected and "\u2029" not in selected:
            self.replace_find_entry.setText(selected)

        self.replace_dialog = dialog
        dialog.show()
        self.replace_find_entry.setFocus()
        self.replace_find_entry.selectAll()

    def _replace_dialog_closed(self, _result):
        if self.replace_dialog is not None:
            self.replace_dialog.deleteLater()
        self.replace_dialog = None

    def _replace_flags(self):
        flags = QTextDocument.FindFlag(0)
        if self.replace_case_checkbox.isChecked():
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        return flags

    def _selection_matches_replace_query(self, cursor, query):
        if not cursor.hasSelection():
            return False
        selected = cursor.selectedText()
        if self.replace_case_checkbox.isChecked():
            return selected == query
        return selected.casefold() == query.casefold()

    def _find_replace_match(self, query, start_cursor=None):
        document = self.text_area.document()
        flags = self._replace_flags()
        start = QTextCursor(start_cursor or self.text_area.textCursor())
        if start.hasSelection():
            start.setPosition(start.selectionEnd())
        match = document.find(query, start, flags)
        if match.isNull():
            match = document.find(query, QTextCursor(document), flags)
        return match

    def replace_next(self):
        """Replace the selected matching occurrence, or select the next one."""
        if not self.document_editing_available():
            return
        query = self.replace_find_entry.text()
        if not query:
            self.replace_find_entry.setFocus()
            return

        cursor = self.text_area.textCursor()
        if self._selection_matches_replace_query(cursor, query):
            cursor.insertText(self.replace_with_entry.text())
            self.text_area.setTextCursor(cursor)

        match = self._find_replace_match(query, self.text_area.textCursor())
        if match.isNull():
            QMessageBox.information(self, "Replace", "No matches found.")
            return

        self.text_area.setTextCursor(match)
        self.text_area.ensureCursorVisible()
        self.text_area.setFocus()

    def replace_all(self):
        """Replace all matches as one undoable edit operation."""
        if not self.document_editing_available():
            return
        query = self.replace_find_entry.text()
        if not query:
            self.replace_find_entry.setFocus()
            return

        replacement = self.replace_with_entry.text()
        document = self.text_area.document()
        flags = self._replace_flags()
        scan = QTextCursor(document)
        edit_cursor = QTextCursor(document)
        count = 0

        edit_cursor.beginEditBlock()
        try:
            while True:
                match = document.find(query, scan, flags)
                if match.isNull():
                    break
                match.insertText(replacement)
                scan = QTextCursor(match)
                count += 1
        finally:
            edit_cursor.endEditBlock()

        self.clear_search_results()
        if count == 0:
            QMessageBox.information(self, "Replace", "No matches found.")
        else:
            QMessageBox.information(self, "Replace", f"Replaced {count} occurrence{'s' if count != 1 else ''}.")
        self.replace_find_entry.setFocus(Qt.FocusReason.OtherFocusReason)
        self.replace_find_entry.selectAll()

    def focus_search(self):
        """Reveal, focus and select the optional ribbon search field."""
        if not self.show_search_bar:
            self.show_search_bar = True
            self.search_container.setVisible(True)
            self.search_bar_action.blockSignals(True)
            self.search_bar_action.setChecked(True)
            self.search_bar_action.blockSignals(False)
            self.save_preferences()
        self.search_entry.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.search_entry.selectAll()

    def active_search_text(self):
        return self.search_entry.text()

    def on_search_text_changed(self, _text):
        """Invalidate previous matches when the single ribbon query changes."""
        self.clear_search_results()

    def update_search_counter(self):
        total = len(self.search_matches)
        current = (
            self.current_search_index + 1
            if 0 <= self.current_search_index < total
            else 0
        )
        total_text = f"{total:,}+" if self.search_results_truncated else f"{total:,}"
        value = f"{current:,}/{total_text}"
        tooltip = (
            f"Showing the first {MAX_SEARCH_MATCHES:,} matches."
            if self.search_results_truncated
            else ""
        )
        self.search_count_label.setText(value)
        self.search_count_label.setToolTip(tooltip)
        enabled = total > 0
        self.search_previous_button.setEnabled(enabled)
        self.search_next_button.setEnabled(enabled)

    def find_text_and_refocus(self, _checked=False):
        """Run Find and return focus to the ribbon search field."""
        self.find_text()
        self.search_entry.setFocus(Qt.FocusReason.OtherFocusReason)

    def on_document_text_changed(self):
        if self._loading: return
        self.update_status_counts(); self.clear_search_results()

    def clear_search_results(self):
        self.search_matches.clear(); self.search_results_truncated=False; self.current_search_index=-1
        if hasattr(self,"visual_editor"): self.visual_editor.setExtraSelections([])
        if hasattr(self,"search_count_label"): self.update_search_counter()

    def refresh_search_highlights(self):
        if not hasattr(self,"visual_editor"): return
        palette=self.visual_editor.palette(); active_bg=QColor("#FFD54F"); active_fg=QColor("#111111"); passive_bg=QColor(palette.color(palette.ColorRole.Highlight)); passive_bg=passive_bg.lighter(150) if passive_bg.lightness()<128 else passive_bg.darker(115); passive_fg=QColor(palette.color(palette.ColorRole.Text)); selections=[]
        for index,match_cursor in enumerate(self.search_matches):
            sel=QTextEdit.ExtraSelection(); sel.cursor=QTextCursor(match_cursor); sel.format=QTextCharFormat(); sel.format.setBackground(active_bg if index==self.current_search_index else passive_bg); sel.format.setForeground(active_fg if index==self.current_search_index else passive_fg); selections.append(sel)
        self.visual_editor.setExtraSelections(selections)

    def find_text(self, show_message=True):
        query=self.active_search_text(); self.search_matches=[]; self.search_results_truncated=False; self.current_search_index=-1; self.visual_editor.setExtraSelections([])
        if not query: self.update_search_counter(); self.focus_search(); return False
        expression=QRegularExpression(QRegularExpression.escape(query),QRegularExpression.PatternOption.CaseInsensitiveOption); document=self.visual_editor.document(); cursor=QTextCursor(document)
        while len(self.search_matches)<MAX_SEARCH_MATCHES:
            cursor=document.find(expression,cursor)
            if cursor.isNull(): break
            self.search_matches.append(QTextCursor(cursor))
        if len(self.search_matches)==MAX_SEARCH_MATCHES: self.search_results_truncated=not document.find(expression,cursor).isNull()
        self.refresh_search_highlights(); self.update_search_counter()
        if not self.search_matches and show_message: QMessageBox.information(self,"Find","No matches found.")
        return bool(self.search_matches)

    def _ensure_search_matches(self):
        query = self.active_search_text()
        if not query:
            self.focus_search()
            return False
        if not self.search_matches:
            return self.find_text(show_message=True)
        return True

    def _show_search_match(self, index):
        if not self.search_matches:
            return
        self.current_search_index = index % len(self.search_matches)
        cursor = QTextCursor(self.search_matches[self.current_search_index])
        # Keep the caret at the active hit without creating a native selected
        # range, otherwise the platform selection colour can hide Rico Plus's
        # yellow active-match ExtraSelection.
        navigation_cursor = QTextCursor(cursor)
        navigation_cursor.setPosition(cursor.selectionStart())
        self.text_area.setTextCursor(navigation_cursor)
        self.refresh_search_highlights()
        self.text_area.ensureCursorVisible()
        self.text_area.setFocus()
        self.update_search_counter()

    def find_next(self):
        """Move to the next match, wrapping to the first."""
        if not self._ensure_search_matches():
            return
        self._show_search_match(self.current_search_index + 1)

    def find_previous(self):
        """Move to the previous match, wrapping to the last."""
        if not self._ensure_search_matches():
            return
        if self.current_search_index < 0:
            self._show_search_match(len(self.search_matches) - 1)
        else:
            self._show_search_match(self.current_search_index - 1)

    def set_word_wrap_mode(self):
        self.visual_editor.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth if self.word_wrap else QTextEdit.LineWrapMode.NoWrap)
        actual=self.visual_editor.lineWrapMode()!=QTextEdit.LineWrapMode.NoWrap
        self.word_wrap=bool(actual)
        action=getattr(self,"wrap_action",None)
        if action is not None:
            action.blockSignals(True); action.setChecked(self.word_wrap); action.blockSignals(False)

    def toggle_word_wrap(self, checked):
        self.word_wrap = bool(checked)
        self.set_word_wrap_mode()
        self.save_preferences()

    def toggle_search_bar(self, checked):
        """Toggle the bottom Find bar; Ctrl+F invokes this same action."""
        self.show_search_bar = bool(checked)
        self.search_container.setVisible(self.show_search_bar)
        if self.show_search_bar:
            self.search_entry.setFocus(Qt.FocusReason.ShortcutFocusReason)
            self.search_entry.selectAll()
        else:
            self.clear_search_results()
            self.text_area.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.save_preferences()

    def toggle_status_bar(self, checked):
        self.show_status_bar = bool(checked)
        self.app_status_bar.setVisible(self.show_status_bar)
        if self.show_status_bar:
            self.update_status_counts()
        self.save_preferences()

    def toggle_menu_style(self, checked):
        """Compatibility hook retained for older configuration imports."""
        self.use_app_menu = False
        self.app_menu_bar.setVisible(False)

    def apply_menu_style(self):
        self.use_app_menu = False
        self.app_menu_bar.setVisible(False)

    def apply_native_style(self):
        """Keep source/portable chrome system-native; editor canvas stays independent."""
        self.setStyleSheet("")
        self.apply_editor_canvas_theme(update_action=True)

    def show_page_setup_dialog(self):
        """Configure compact left, centre and right header/footer fields."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Page Setup")
        dialog.setModal(True)
        dialog.setMinimumWidth(590)

        outer = QVBoxLayout(dialog)
        outer.setContentsMargins(20, 18, 20, 16)
        outer.setSpacing(14)

        explanation = QLabel(
            "Headers and footers are added only when printing.<br>"
            "<b>Placeholders:</b> &amp;F filename, &amp;P page, &amp;N total pages, "
            "&amp;D date, &amp;T time, &amp;A application, &amp;C Confidential.",
            dialog,
        )
        explanation.setWordWrap(True)
        outer.addWidget(explanation)

        def build_section(title, enabled, left_value, center_value, right_value):
            group = QGroupBox(dialog)
            group_layout = QVBoxLayout(group)
            group_layout.setContentsMargins(12, 10, 12, 12)
            group_layout.setSpacing(7)

            enabled_check = QCheckBox(f"Enable {title.lower()}", group)
            enabled_check.setChecked(enabled)
            group_layout.addWidget(enabled_check)

            labels_row = QHBoxLayout()
            labels_row.setSpacing(8)
            for label_text in ("Left", "Centre", "Right"):
                label = QLabel(label_text, group)
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                labels_row.addWidget(label, 1)
            group_layout.addLayout(labels_row)

            fields_row = QHBoxLayout()
            fields_row.setSpacing(8)
            left_edit = QLineEdit(left_value, group)
            center_edit = QLineEdit(center_value, group)
            right_edit = QLineEdit(right_value, group)
            fields_row.addWidget(left_edit, 1)
            fields_row.addWidget(center_edit, 1)
            fields_row.addWidget(right_edit, 1)
            group_layout.addLayout(fields_row)

            def update_enabled():
                active = enabled_check.isChecked()
                left_edit.setEnabled(active)
                center_edit.setEnabled(active)
                right_edit.setEnabled(active)

            enabled_check.toggled.connect(update_enabled)
            update_enabled()

            return group, enabled_check, left_edit, center_edit, right_edit

        (
            header_group,
            self.page_setup_header_check,
            self.page_setup_header_left,
            self.page_setup_header_center,
            self.page_setup_header_right,
        ) = build_section(
            "Header",
            self.print_header_enabled,
            self.print_header_left,
            self.print_header_center,
            self.print_header_right,
        )
        outer.addWidget(header_group)

        (
            footer_group,
            self.page_setup_footer_check,
            self.page_setup_footer_left,
            self.page_setup_footer_center,
            self.page_setup_footer_right,
        ) = build_section(
            "Footer",
            self.print_footer_enabled,
            self.print_footer_left,
            self.print_footer_center,
            self.print_footer_right,
        )
        outer.addWidget(footer_group)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        outer.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self.print_header_enabled = self.page_setup_header_check.isChecked()
        self.print_header_left = self.page_setup_header_left.text()
        self.print_header_center = self.page_setup_header_center.text()
        self.print_header_right = self.page_setup_header_right.text()
        self.print_footer_enabled = self.page_setup_footer_check.isChecked()
        self.print_footer_left = self.page_setup_footer_left.text()
        self.print_footer_center = self.page_setup_footer_center.text()
        self.print_footer_right = self.page_setup_footer_right.text()
        self.save_preferences()

    def _expand_print_template(self, template, page_number, page_count):
        """Expand the small set of Rico Plus print placeholders."""
        now = QDateTime.currentDateTime()
        system_locale = QLocale.system()
        filename = os.path.basename(self.file_path) if self.file_path else "Untitled"
        replacements = {
            "&F": filename,
            "&P": str(page_number),
            "&N": str(page_count),
            "&D": system_locale.toString(now.date(), QLocale.FormatType.ShortFormat),
            "&T": system_locale.toString(now.time(), QLocale.FormatType.ShortFormat),
            "&A": APP_NAME,
            "&C": "Confidential",
        }
        result = template
        for token, value in replacements.items():
            result = result.replace(token, value)
        return result

    def _draw_print_line(
        self, painter, rect, left_text, center_text, right_text, page_number, page_count
    ):
        """Draw three independently aligned fields within one header/footer line."""
        third = rect.width() / 3.0
        fields = (
            (
                QRectF(rect.left(), rect.top(), third, rect.height()),
                left_text,
                Qt.AlignmentFlag.AlignLeft,
            ),
            (
                QRectF(rect.left() + third, rect.top(), third, rect.height()),
                center_text,
                Qt.AlignmentFlag.AlignCenter,
            ),
            (
                QRectF(rect.left() + third * 2, rect.top(), third, rect.height()),
                right_text,
                Qt.AlignmentFlag.AlignRight,
            ),
        )

        for field_rect, template, horizontal_alignment in fields:
            if not template:
                continue
            text = self._expand_print_template(template, page_number, page_count)
            painter.drawText(
                field_rect,
                int(horizontal_alignment | Qt.AlignmentFlag.AlignVCenter),
                text,
            )

    def current_print_document(self):
        """Return a print clone with only automatic/unset body text normalized black.

        This ports Nuxpad's legibility lesson without flattening explicit RTF
        colours: user-selected foreground colours remain document content.
        """
        document=self._unzoomed_visual_document()
        cursor=QTextCursor(document)
        block=document.begin()
        while block.isValid():
            iterator=block.begin()
            while not iterator.atEnd():
                fragment=iterator.fragment()
                if fragment.isValid() and fragment.length()>0 and _qt_brush_colour(fragment.charFormat().foreground()) is None:
                    cursor.setPosition(fragment.position()); cursor.setPosition(fragment.position()+fragment.length(),QTextCursor.MoveMode.KeepAnchor)
                    fmt=QTextCharFormat(); fmt.setForeground(QColor(Qt.GlobalColor.black)); cursor.mergeCharFormat(fmt)
                iterator+=1
            block=block.next()
        return document

    def export_pdf(self):
        default_name=os.path.splitext(self.file_path)[0]+".pdf" if self.file_path else os.path.join(os.path.expanduser("~"),"Untitled.pdf")
        file_path,_=QFileDialog.getSaveFileName(self,"Export PDF",default_name,"PDF Documents (*.pdf)")
        if not file_path: return False
        if not file_path.lower().endswith(".pdf"): file_path += ".pdf"
        parent=os.path.dirname(os.path.abspath(file_path)) or os.curdir; descriptor=None; temporary=None
        try:
            descriptor,temporary=tempfile.mkstemp(prefix=".ricopad-pdf-",suffix=".pdf.tmp",dir=parent); os.close(descriptor); descriptor=None; os.remove(temporary)
            printer=QPrinter(QPrinter.PrinterMode.ScreenResolution); printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat); printer.setOutputFileName(temporary)
            if not self._print_document_with_header_footer(printer): return False
            if not os.path.isfile(temporary) or os.path.getsize(temporary)<=0: raise RuntimeError("The PDF print engine produced no output.")
            os.replace(temporary,file_path); temporary=None; fsync_directory(parent); self._show_status_message(f"Exported PDF to {file_path}",4000); return True
        except (OSError,RuntimeError) as exc:
            QMessageBox.critical(self,"PDF Export Error",f"Could not export PDF:\n{exc}"); return False
        finally:
            if descriptor is not None:
                try: os.close(descriptor)
                except OSError: pass
            if temporary and os.path.exists(temporary):
                try: os.remove(temporary)
                except OSError: pass

    def _print_document_with_header_footer(self, printer):
        """Paginate the rendered rich document with Nuxpad-style metadata bands."""
        painter = QPainter()
        if not painter.begin(printer):
            QMessageBox.critical(self, "Print Error", "Rico Plus could not start the print or PDF job.")
            return False
        completed = False
        try:
            page_rect = QRectF(printer.pageLayout().paintRectPixels(printer.resolution()))
            if page_rect.width() <= 0 or page_rect.height() <= 0:
                raise RuntimeError("The selected printer returned an invalid page size.")
            dpi_x = max(72, printer.logicalDpiX())
            dpi_y = max(72, printer.logicalDpiY())
            side_margin = dpi_x * 0.25
            vertical_gap = dpi_y * 0.12
            body_padding = dpi_y * 0.10
            painter.setFont(QApplication.font())
            metrics = painter.fontMetrics()
            line_height = max(metrics.height(), int(dpi_y * 0.14))
            header_space = line_height * 2 + vertical_gap + body_padding if self.print_header_enabled else body_padding
            footer_space = line_height * 2 + vertical_gap + body_padding if self.print_footer_enabled else body_padding
            content_width = page_rect.width() - side_margin * 2
            content_height = page_rect.height() - header_space - footer_space
            if content_width <= 1 or content_height <= 1:
                raise RuntimeError("The printable page area is too small for the selected settings.")
            content_rect = QRectF(
                page_rect.left() + side_margin,
                page_rect.top() + header_space,
                content_width,
                content_height,
            )

            document = self.current_print_document()
            document.documentLayout().setPaintDevice(printer)
            document.setDocumentMargin(0)
            document.setPageSize(QSizeF(content_width, content_height))
            page_count = max(1, int(document.pageCount()))

            for page_index in range(page_count):
                if page_index and not printer.newPage():
                    raise RuntimeError("The print engine stopped before all pages were produced.")
                page_number = page_index + 1
                painter.setFont(QApplication.font())
                painter.setPen(QColor(Qt.GlobalColor.black))
                if self.print_header_enabled:
                    header_rect = QRectF(
                        page_rect.left() + side_margin,
                        page_rect.top() + vertical_gap,
                        content_width,
                        line_height,
                    )
                    self._draw_print_line(
                        painter, header_rect,
                        self.print_header_left, self.print_header_center, self.print_header_right,
                        page_number, page_count,
                    )
                if self.print_footer_enabled:
                    footer_rect = QRectF(
                        page_rect.left() + side_margin,
                        page_rect.bottom() - line_height - vertical_gap,
                        content_width,
                        line_height,
                    )
                    self._draw_print_line(
                        painter, footer_rect,
                        self.print_footer_left, self.print_footer_center, self.print_footer_right,
                        page_number, page_count,
                    )
                painter.save()
                painter.setPen(QColor(160, 160, 160))
                if self.print_header_enabled:
                    y = content_rect.top() - body_padding / 2
                    painter.drawLine(int(content_rect.left()), int(y), int(content_rect.right()), int(y))
                if self.print_footer_enabled:
                    y = content_rect.bottom() + body_padding / 2
                    painter.drawLine(int(content_rect.left()), int(y), int(content_rect.right()), int(y))
                painter.restore()
                painter.save()
                painter.translate(content_rect.left(), content_rect.top())
                painter.setClipRect(QRectF(0, 0, content_width, content_height))
                painter.translate(0, -page_index * content_height)
                document.drawContents(
                    painter,
                    QRectF(0, page_index * content_height, content_width, content_height),
                )
                painter.restore()
            completed = True
            return True
        except Exception as exc:
            QMessageBox.critical(self, "Print Error", f"Rico Plus could not complete the output.\n\n{exc}")
            return False
        finally:
            if painter.isActive():
                painter.end()
            if not completed and printer.outputFileName():
                try:
                    output_path = printer.outputFileName()
                    if os.path.isfile(output_path) and os.path.getsize(output_path) == 0:
                        os.remove(output_path)
                except OSError:
                    pass

    def print_document(self):
        # Nuxpad lesson: ScreenResolution keeps QTextDocument pagination/font metrics
        # aligned with Qt's printer/PDF paint engine while remaining vector/searchable.
        printer=QPrinter(QPrinter.PrinterMode.ScreenResolution); dialog=QPrintDialog(printer,self); dialog.setWindowTitle("Print")
        if dialog.exec()!=QDialog.DialogCode.Accepted: return False
        return self._print_document_with_header_footer(printer)

    def _format_file_size(self, size):
        size = int(size)
        if size < 1024:
            return f"{size} byte" if size == 1 else f"{size} bytes"
        value = float(size)
        for unit in ("KiB", "MiB", "GiB", "TiB"):
            value /= 1024.0
            if value < 1024.0 or unit == "TiB":
                return f"{value:.1f} {unit} ({size:,} bytes)"
        return f"{size:,} bytes"

    @staticmethod
    def _format_file_datetime(seconds):
        """Return a locale-aware timestamp across supported PyQt6 releases."""
        date_time = QDateTime.fromSecsSinceEpoch(int(seconds))
        format_type_enum = getattr(QLocale, "FormatType", None)
        long_format = getattr(format_type_enum, "LongFormat", None)
        if long_format is not None:
            try:
                return QLocale.system().toString(date_time, long_format)
            except (AttributeError, TypeError):
                pass
        # Newer Qt 6 bindings removed the old locale date-format member, so
        # use an explicit stable pattern as the final compatibility fallback.
        return date_time.toString("dddd, d MMMM yyyy HH:mm:ss t")

    def show_properties_dialog(self):
        dialog=QDialog(self); dialog.setWindowTitle("Properties — Rico Plus"); dialog.setWindowIcon(self.windowIcon()); dialog.setMinimumWidth(640); layout=QVBoxLayout(dialog); layout.setContentsMargins(18,16,18,14); layout.setSpacing(12)
        def add_group(title,rows):
            box=QGroupBox(title,dialog); form=QFormLayout(box); form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            for label,value in rows:
                field=QLineEdit(str(value),box); field.setReadOnly(True); field.setCursorPosition(0); form.addRow(label,field)
            layout.addWidget(box)
        if self.file_path:
            path=os.path.abspath(self.file_path)
            try:
                st=os.stat(path); rows=(("Name",os.path.basename(path)),("Document type","Rich Text Format (.rtf)"),("Location",os.path.dirname(path)),("Full path",path),("Size",self._format_file_size(st.st_size)),("Modified",self._format_file_datetime(st.st_mtime)),("Permissions",oct(st.st_mode&0o777)),("Symbolic link","Yes" if os.path.islink(path) else "No"))
            except OSError as exc: rows=(("File",path),("Status",f"Could not inspect: {exc}"))
        else: rows=(("Name","Untitled.rtf"),("Location","Not saved yet"))
        add_group("File",rows)
        text=self.text_area.toPlainText(); compatibility="Fully supported by Rico Plus's RTF subset" if not self.rtf_compatibility_warnings else "; ".join(self.rtf_compatibility_warnings)
        add_group("Document",(("Format","Rich Text Format (RTF)"),("Lines",max(1,self.text_area.document().blockCount())),("Characters",len(text)),("Unsaved changes","No" if self.content_saved else "Yes"),("Locked Mode","Yes" if self.view_only else "No"),("Compatibility",compatibility)))
        if self.rtf_document_properties:
            add_group("Preserved RTF page properties",tuple((k,str(v)) for k,v in sorted(self.rtf_document_properties.items())))
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok,dialog); buttons.accepted.connect(dialog.accept); layout.addWidget(buttons); dialog.exec()

    def open_external_editor(self):
        if not self.file_path:
            QMessageBox.information(self, "External Editor — Rico Plus", "Save the file first.")
            return False
        if not self.content_saved and not self.save_file():
            return False
        opened = self._open_host_target(self.file_path, local=True)
        if not opened:
            QMessageBox.warning(self, "External Editor — Rico Plus", "The desktop could not open this file.")
        return bool(opened)

    def open_containing_folder(self):
        if not self.file_path:
            QMessageBox.information(self, "Open Containing Folder — Rico Plus", "Save the file first.")
            return False
        folder = os.path.dirname(os.path.abspath(self.file_path))
        opened = self._open_host_target(folder, local=True)
        if not opened:
            QMessageBox.warning(self, "Open Containing Folder — Rico Plus", "The desktop could not open this folder.")
        return bool(opened)

    def duplicate_current_file(self):
        if not self.file_path: QMessageBox.information(self,"Duplicate File — Rico Plus","Save the file first."); return False
        source=os.path.abspath(self.file_path); stem,suffix=os.path.splitext(source); candidate=stem+" copy"+suffix; counter=2
        while os.path.exists(candidate): candidate=f"{stem} copy {counter}{suffix}"; counter+=1
        destination,_=QFileDialog.getSaveFileName(self,"Duplicate File — Rico Plus",candidate,"Rich Text Format (*.rtf)")
        if not destination: return False
        if not destination.lower().endswith(".rtf"): destination+=".rtf"
        try:
            payload=self._document_payload("rtf")
            if len(payload)>MAX_FILE_SIZE: raise ValueError(f"The duplicate would exceed Rico Plus's {MAX_FILE_SIZE//(1024*1024)} MiB reopen limit.")
            parent=os.path.dirname(os.path.abspath(destination)) or os.curdir; os.makedirs(parent,exist_ok=True); descriptor,temporary=tempfile.mkstemp(prefix=".ricopad-duplicate-",dir=parent)
            try:
                with os.fdopen(descriptor,"wb") as handle: handle.write(payload); handle.flush(); os.fsync(handle.fileno())
                if os.path.exists(source): os.chmod(temporary,os.stat(source).st_mode&0o777)
                os.replace(temporary,destination); fsync_directory(parent)
            except Exception:
                try: os.remove(temporary)
                except OSError: pass
                raise
        except (OSError,ValueError) as exc: QMessageBox.critical(self,"Duplicate File — Rico Plus",f"Could not duplicate the file:\n{exc}"); return False
        return True

    def delete_current_file(self):
        if not self.file_path:
            QMessageBox.information(self, "Delete File — Rico Plus", "Save the file first.")
            return False
        path = os.path.abspath(self.file_path)
        answer = QMessageBox.warning(
            self, "Delete File? — Rico Plus",
            f"Permanently delete {os.path.basename(path)}?\n\nThis action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return False
        try:
            os.remove(path)
        except OSError as exc:
            QMessageBox.critical(self, "Delete File — Rico Plus", f"Could not delete the file:\n{exc}")
            return False
        self.content_saved = True
        self.new_file()
        return True

    def _documentation_path(self):
        candidates = (
            Path(resource_path("docs", "README.md")),
            Path(__file__).resolve().parent.parent / "docs" / "README.md",
        )
        appdir = os.environ.get("APPDIR")
        if appdir:
            candidates += (
                Path(appdir) / "usr" / "share" / "doc" / "rico-plus" / "README.md",
            )
        for candidate in candidates:
            try:
                if candidate.is_file():
                    return candidate.resolve()
            except OSError:
                continue
        return None

    def open_documentation(self):
        """Open the bundled Rico Plus documentation with the host desktop."""
        path = self._documentation_path()
        if path is None:
            QMessageBox.information(
                self,
                "Documentation — Rico Plus",
                "The bundled Rico Plus documentation could not be found.",
            )
            return False
        return self._open_host_target(str(path), local=True)

    def _open_host_target(self, target, *, local=False):
        """Open a URL/path with the host desktop, outside AppImage Qt/library env."""
        target=str(target)
        environment=host_process_environment(); host_path=environment.get("PATH")
        if sys.platform=="win32":
            try:
                os.startfile(target)
                return True
            except (AttributeError,OSError):
                pass
        candidates=[]
        if sys.platform=="darwin":
            candidates=[("open",[target])]
        elif sys.platform!="win32":
            candidates=[("xdg-open",[target]),("gio",["open",target])]
        for command,args in candidates:
            executable=shutil.which(command,path=host_path)
            if not executable:
                continue
            try:
                subprocess.Popen([executable,*args],env=environment,start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                return True
            except OSError:
                continue
        url=QUrl.fromLocalFile(target) if local else QUrl(target)
        return bool(QDesktopServices.openUrl(url))

    def open_document_link(self, href):
        href=str(href or "").strip()
        if not href or not is_safe_link_target(href):
            return False
        if href.startswith("#"):
            try:
                self.visual_editor.scrollToAnchor(href[1:])
                self.visual_editor.setFocus()
                return True
            except Exception:
                return False
        parsed=QUrl(href)
        if parsed.scheme().lower() in ("http","https","mailto"):
            return self._open_host_target(href)
        if parsed.isLocalFile():
            path=parsed.toLocalFile()
        else:
            base=os.path.dirname(os.path.abspath(self.file_path)) if self.file_path else os.getcwd()
            path=os.path.abspath(os.path.join(base,href))
        if os.path.exists(path):
            return self._open_host_target(path,local=True)
        self._show_status_message("The linked file could not be found.",4000)
        return False

    def open_github_repository(self):
        opened=self._open_host_target(GITHUB_URL)
        if not opened: QMessageBox.warning(self,"GitHub Repository — Rico Plus","The host desktop could not open the repository URL.")
        return opened

    def report_an_issue(self):
        opened=self._open_host_target(ISSUES_URL)
        if not opened: QMessageBox.warning(self,"Raise an Issue — Rico Plus","The host desktop could not open the issue-report URL.")
        return opened

    def show_tutorial_wizard(self):
        if self.tutorial_dialog is not None:
            self.tutorial_dialog.show(); self.tutorial_dialog.raise_(); self.tutorial_dialog.activateWindow(); return
        wizard=QWizard(self); wizard.setWindowTitle("Rico Plus Tutorial Wizard"); wizard.setWindowIcon(self.windowIcon()); wizard.setModal(False); wizard.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose,True)
        def add_page(title,body,button=None):
            page=QWizardPage(wizard); page.setTitle(title); layout=QVBoxLayout(page)
            label=QLabel(body,page); label.setWordWrap(True); label.setTextFormat(Qt.TextFormat.RichText); layout.addWidget(label)
            if button is not None: layout.addWidget(button,0,Qt.AlignmentFlag.AlignLeft)
            layout.addStretch(1); wizard.addPage(page)
        add_page("Welcome to Rico Plus","<p>Rico Plus combines a workspace dashboard with a Rich Text Format (.rtf) editor. The editor uses one Ribbon with five tabs: <b>File, Home, Insert, View and Help</b>, with Home open by default.</p><p>Hover a command for its name/shortcut. Use <b>Ctrl+Tab</b> and <b>Ctrl+Shift+Tab</b> to move between tabs. Double-click a tab title to collapse Ribbon controls; click a tab title once to reveal them again.</p>")
        add_page("Create, open and save","<p><b>File</b> contains New RTF File, Open / Manage Workspace, Save, Save As, Print, Export PDF and file-management commands. Rico Plus edits RTF only, so there is no private document format to choose.</p><p>Files opened by the operating system outside the active workspace remain external and are not copied or registered.</p>")
        add_page("Format rich text","<p><b>Home</b> provides font face, size, paragraph style, emphasis, colours/highlights, bullets, indentation, alignment, paragraph settings and line spacing.</p><p><b>Insert</b> contains tables, links, symbols, images, horizontal rules, dates and times. Character formatting operates on the selection, or on the current word when there is no selection; whitespace changes the typing format for future text.</p>")
        add_page("Find and navigate","<p><b>Ctrl+F</b> toggles Find. Use <b>F3</b> for the next result and <b>Shift+F3</b> for the previous result. Home also provides Find and Replace.</p><p>Locked Mode protects a document from accidental changes while navigation, copying and search remain available.</p>")
        add_page("View and reading comfort","<p><b>View</b> controls Locked Mode, Word Wrap, Dark Editor, zoom, status bar and document defaults.</p><p>Ctrl+mouse-wheel zooms the document. Dark Editor changes only the editing surface; App Theme controls the rest of Rico Plus where packaged theme support is available.</p>")
        add_page("Make it yours!","<p>Rico Plus uses the Ribbon exclusively. Double-click any Ribbon tab to collapse it, and choose either Rico Icons Classic or Rico Icons New from App Theme.</p><p>New Document Defaults controls the exact font, size, style, line spacing and alignment used by future new documents.</p>")
        shortcuts_button=QPushButton("Open Keyboard Shortcuts…",wizard); shortcuts_button.setAutoDefault(False); shortcuts_button.clicked.connect(self.show_keyboard_shortcuts_dialog)
        add_page("RTF interoperability and help","<p>Rico Plus writes standards-based RTF intended to interoperate with other RTF applications. Bullet lists are stored with standard RTF list tables/overrides rather than Rico Plus-only markers.</p><p>Use <b>F1</b> for the bundled RTF Documentation. Help also provides GitHub, Raise an Issue, Keyboard Shortcuts and About.</p>",shortcuts_button)
        def tutorial_finished(_result):
            self.tutorial_dialog=None
            QTimer.singleShot(0,self._focus_editor_after_startup)
        wizard.finished.connect(tutorial_finished); self.tutorial_dialog=wizard; wizard.show(); wizard.raise_(); wizard.activateWindow()

    def show_keyboard_shortcuts_dialog(self):
        """Show the Plus-family modifier-order-independent fuzzy search."""
        if self.shortcuts_dialog is not None:
            self.shortcuts_dialog.show()
            self.shortcuts_dialog.raise_()
            self.shortcuts_dialog.activateWindow()
            return
        from rico_plus.widgets.shortcuts_dialog import ShortcutsDialog

        catalog = {}
        for category, menu in (
            ("File", self.file_menu),
            ("Edit", self.edit_menu),
            ("Format", self.format_menu),
            ("Insert", self.insert_menu),
            ("View", self.view_menu),
            ("Help", self.help_menu),
        ):
            entries = []
            stack = list(menu.actions())
            while stack:
                action = stack.pop(0)
                submenu = action.menu()
                if submenu is not None:
                    stack[0:0] = submenu.actions()
                    continue
                if not action.isSeparator():
                    entries.append((action.text(), action))
            catalog[category] = entries
        dialog = ShortcutsDialog(catalog, self)
        dialog.finished.connect(
            lambda _result: setattr(self, "shortcuts_dialog", None)
        )
        self.shortcuts_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        dialog.search.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def show_format_support_dialog(self):
        QMessageBox.information(self,"RTF Support — Rico Plus","Rico Plus edits Rich Text Format (.rtf) only.\n\nSupported core: fonts and character formatting, colours/highlights, paragraphs, lists, hyperlinks, embedded PNG/JPEG images, horizontal rules and bounded simple non-nested tables.\n\nUnsupported or partially supported constructs such as OLE objects, shapes, comments, footnotes, headers/footers and nested tables are reported in Properties and warned before a destructive save.\n\nPrint and Export PDF are output operations; Rico Plus is not a PDF reader.")

    def show_about_dialog(self):
        # Keep the Pad-family modeless About presentation from the Ricopad lineage.
        # Avoid QMessageBox.about(): the bespoke dialog is consistent with the
        # sibling Pads and has proven more reliable across packaged Qt themes.
        if self.about_dialog is not None:
            self.about_dialog.show()
            self.about_dialog.raise_()
            self.about_dialog.activateWindow()
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("About — Rico Plus")
        dialog.setWindowIcon(self.windowIcon())
        dialog.setModal(False)
        dialog.setMinimumSize(700, 470)
        dialog.resize(700, 470)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(10)

        icon_path = resource_path("icons", "ricopad.png")
        if os.path.isfile(icon_path):
            logo = QLabel(dialog)
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pixmap = QPixmap(icon_path)
            if not pixmap.isNull():
                logo.setPixmap(pixmap.scaled(
                    112, 112,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ))
                layout.addWidget(logo)

        title = QLabel(f"<h2>{APP_NAME}</h2>", dialog)
        title.setTextFormat(Qt.TextFormat.RichText)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        version = QLabel(f"Version {APP_VERSION}", dialog)
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)
        tagline = QLabel("<b>Friendly. Fast. Focused.</b>", dialog)
        tagline.setTextFormat(Qt.TextFormat.RichText)
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(tagline)
        description = QLabel(
            "A lightweight Rich Text Format editor focused on portable, "
            "predictable rich documents.",
            dialog,
        )
        description.setWordWrap(True)
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(description)
        details = QLabel(
            f"<a href='{GITHUB_URL}'>{GITHUB_URL}</a><br>"
            "Built on Python, PyQt6, Nuxpad 2 and WordPad-inspired document features.<br>"
            f"<b>Configuration:</b> {html.escape(str(self.config_file))}<br><br>"
            "Copyright © 2026 Bruno Machado<br>"
            "[<a href='https://github.com/brunonlinespace/'>"
            "https://github.com/brunonlinespace/</a>]<br>"
            "Licensed under the GNU General Public License v3 or later.",
            dialog,
        )
        details.setTextFormat(Qt.TextFormat.RichText)
        details.setAlignment(Qt.AlignmentFlag.AlignCenter)
        details.setOpenExternalLinks(False)
        details.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        details.linkActivated.connect(lambda href:self._open_host_target(href))
        layout.addWidget(details)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok, dialog)
        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setText("OK")
        buttons.accepted.connect(dialog.close)
        layout.addWidget(buttons)
        dialog.finished.connect(lambda _result: setattr(self, "about_dialog", None))
        self.about_dialog = dialog
        dialog.show()

    def on_modification_changed(self, _modified):
        if self._loading or self._syncing_editors:
            return
        active_modified = self.text_area.document().isModified()
        self.content_saved = not active_modified
        self.update_title()

    def update_status_counts(self):
        if not hasattr(self, "text_area"):
            return
        self.operation_mode_label.setText(
            "Overwrite" if self.text_area.overwriteMode() else "Insert"
        )
        characters = max(0, self.text_area.document().characterCount() - 1)
        self.zoom_label.setText(f"{self.zoom_percent}%")
        self.counter_label.setText(f"Chars {characters:,}")

    @staticmethod
    def _content_signature(data):
        """Return a stable signature for the exact encoded file bytes."""
        return (
            len(data),
            hashlib.sha256(data).digest(),
        )

    @classmethod
    def _disk_signature(cls, file_path):
        """Hash a file so same-size or timestamp-preserved edits are found."""
        if not file_path:
            return None

        digest = hashlib.sha256()
        size = 0
        try:
            stat = os.stat(file_path)
            if stat.st_size > MAX_FILE_SIZE:
                return ("oversize", stat.st_size)
            with open(file_path, "rb") as handle:
                while True:
                    chunk = handle.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > MAX_FILE_SIZE:
                        return ("oversize", size)
                    digest.update(chunk)
        except OSError:
            return None

        return (
            size,
            digest.digest(),
        )

    def _external_change_action(self):
        """Ask what to do when the open file changed after it was loaded."""
        if not self.file_path or self.file_disk_signature is None:
            return "overwrite"

        current_signature = self._disk_signature(self.file_path)
        if current_signature == self.file_disk_signature:
            return "overwrite"

        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle("File Changed on Disk")
        dialog.setText(
            "This file has changed on disk since Rico Plus opened or saved it."
        )
        dialog.setInformativeText(
            "Choose Reload to discard the edits currently in Rico Plus and use "
            "the disk copy, Save As to keep both versions, or Overwrite to "
            "replace the disk copy with the text currently in Rico Plus."
        )

        reload_button = dialog.addButton(
            "Reload",
            QMessageBox.ButtonRole.ActionRole,
        )
        reload_button.setEnabled(current_signature is not None)
        save_as_button = dialog.addButton(
            "Save As…",
            QMessageBox.ButtonRole.ActionRole,
        )
        overwrite_button = dialog.addButton(
            "Overwrite",
            QMessageBox.ButtonRole.DestructiveRole,
        )
        cancel_button = dialog.addButton(QMessageBox.StandardButton.Cancel)
        dialog.setDefaultButton(cancel_button)
        dialog.exec()

        clicked = dialog.clickedButton()
        if clicked is reload_button:
            return "reload"
        if clicked is save_as_button:
            return "save_as"
        if clicked is overwrite_button:
            return "overwrite"
        return "cancel"

    def check_save_changes(self):
        if self.content_saved:
            return True
        answer = QMessageBox.question(
            self,
            APP_NAME,
            "Do you want to save changes?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if answer == QMessageBox.StandardButton.Save:
            return self.save_file()
        if answer == QMessageBox.StandardButton.Discard:
            return True
        return False

    @staticmethod
    def format_for_path(file_path):
        return "rtf" if Path(file_path).suffix.lower() in RTF_EXTENSIONS else None

    def _update_mode_capabilities(self):
        editing=not self.view_only
        self.visual_editor.setAcceptRichText(True); self.visual_editor.setReadOnly(self.view_only)
        self.format_menu.setEnabled(editing)
        for action in self.format_actions: action.setEnabled(editing)
        for widget in self.format_widgets: widget.setEnabled(editing)
        for action in self.visual_insert_actions: action.setEnabled(editing)
        for action in self.editing_actions: action.setEnabled(editing)
        for action in self.file_dependent_actions: action.setEnabled(bool(self.file_path))
        self.copy_action.setEnabled(True); self.select_all_action.setEnabled(True)
        if hasattr(self,"table_edit_actions"):
            in_table=editing and self.visual_editor.textCursor().currentTable() is not None
            for action in self.table_edit_actions: action.setEnabled(in_table)
        if hasattr(self,"edit_link_action"):
            in_link=editing and self._visual_anchor_cursor() is not None; self.edit_link_action.setEnabled(in_link); self.remove_link_action.setEnabled(in_link)
        self.view_only_action.blockSignals(True); self.view_only_action.setChecked(self.view_only); self.view_only_action.blockSignals(False)

    def _document_payload(self, target_format=None):
        if (target_format or self.file_format) != "rtf": raise ValueError("Rico Plus saves RTF documents only.")
        return document_to_rtf_with_properties(self._unzoomed_visual_document(), self.rtf_document_properties)

    def _synchronise_after_save(self, payload, *, semantic_signature=None, preserve_warnings=False):
        self._loading=True
        try: self.visual_editor.document().setModified(False)
        finally: self._loading=False
        self._source_rtf_payload=bytes(payload)
        if semantic_signature is None:
            try:
                semantic_signature=self._content_signature(self._document_payload("rtf"))
            except Exception:
                semantic_signature=None
        self._source_rtf_semantic_signature=semantic_signature
        if not preserve_warnings:
            self.rtf_compatibility_warnings=()
        self._rtf_save_warning_acknowledged=False

    def _write_payload_atomically(self, payload):
        if os.path.islink(self.file_path):
            with open(self.file_path, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            return

        parent = os.path.dirname(self.file_path) or "."
        basename = os.path.basename(self.file_path)
        try:
            existing_mode = os.stat(self.file_path).st_mode & 0o7777
        except FileNotFoundError:
            existing_mode = self._default_created_file_mode()

        descriptor = None
        temporary = None
        try:
            descriptor, temporary = tempfile.mkstemp(
                prefix=f".{basename}.ricopad-", suffix=".tmp", dir=parent
            )
            if hasattr(os, "fchmod"):
                os.fchmod(descriptor, existing_mode)
            with os.fdopen(descriptor, "wb") as handle:
                descriptor = None
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.file_path)
            temporary = None
            fsync_directory(parent)
        finally:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            if temporary:
                try:
                    os.remove(temporary)
                except OSError:
                    pass

    def new_file(self):
        if not self.check_save_changes(): return False
        self._loading=True
        try:
            self.clear_search_results(); self.visual_editor.clear(); self.file_path=None; self.file_format="rtf"; self.file_encoding="rtf"; self.file_bom=b""; self.file_newline="\n"; self.file_disk_signature=None; self._source_rtf_payload=None; self._source_rtf_semantic_signature=None; self.content_saved=True; self.rtf_compatibility_warnings=(); self.rtf_document_properties={}; self._rtf_save_warning_acknowledged=False; self._view_only_prompt_shown=False; self._visual_document_zoom_percent=100; self.apply_editor_font(); self._apply_visual_document_zoom(self.zoom_percent); self.visual_editor.document().setModified(False)
        finally: self._loading=False
        self.view_only=bool(self.persist_view_only); self._update_mode_capabilities(); self.update_title(); self.update_status_counts(); self.update_formatting_state(); self.visual_editor.setFocus(); return True

    def save_and_exit(self):
        """Offer save-and-exit, exit-without-saving, or cancel explicitly."""
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setWindowTitle("Save and Exit — Rico Plus")
        dialog.setText("Do you want to save the current document before exiting Rico Plus?")
        save_button = dialog.addButton(
            "Yes, save and exit", QMessageBox.ButtonRole.AcceptRole
        )
        discard_button = dialog.addButton(
            "No, exit without saving", QMessageBox.ButtonRole.DestructiveRole
        )
        cancel_button = dialog.addButton(QMessageBox.StandardButton.Cancel)
        dialog.setDefaultButton(cancel_button)
        dialog.setEscapeButton(cancel_button)
        dialog.exec()

        clicked = dialog.clickedButton()
        if clicked is cancel_button or clicked is None:
            return False
        if clicked is save_button:
            if not self.save_file():
                return False
        elif clicked is not discard_button:
            return False

        self._skip_close_save_prompt = True
        self.close()
        return True

    @staticmethod
    def inspect_text_file(file_path):
        try:
            if not os.path.isfile(file_path): return False,"The selected path is not a regular file."
            size=os.path.getsize(file_path)
            if size>MAX_FILE_SIZE: return False,f"The file is larger than Rico Plus's {MAX_FILE_SIZE//(1024*1024)} MiB safety limit."
        except OSError as exc: return False,f"Could not inspect the file:\n{exc}"
        if Path(file_path).suffix.lower() not in RTF_EXTENSIONS: return False,"Rico Plus edits Rich Text Format (.rtf) documents only."
        return True,""

    def load_file(self, file_path, check_changes=True, show_error=True):
        if check_changes and not self.check_save_changes(): return False
        is_safe,reason=self.inspect_text_file(file_path)
        if not is_safe:
            if show_error: QMessageBox.information(self,"Unsupported File — Rico Plus",f"Rico Plus did not open:\n{os.path.basename(file_path)}\n\n{reason}")
            return False
        try:
            data=read_bounded_bytes(file_path,MAX_FILE_SIZE,label="document"); decoded=decode_rtf(data)
        except (ValueError,MemoryError,OSError) as exc:
            if show_error: QMessageBox.warning(self,"RTF Import Error — Rico Plus",f"The RTF document could not be opened safely:\n{exc}")
            return False
        except Exception as exc:
            if show_error: QMessageBox.critical(self,"RTF Import Error — Rico Plus",f"Rico Plus could not import this RTF document:\n{exc}")
            return False
        self._loading=True
        try:
            self.clear_search_results()
            direct_import = populate_qtextdocument_from_rtf_model(
                self.visual_editor.document(), decoded.model
            )
            if not direct_import:
                # Conservative table fallback.  Ordinary paragraphs, blank blocks,
                # indentation and embedded-image provenance no longer pass through
                # Qt's lossy HTML normalization layer.
                document_html=sanitise_qt_html(decoded.html)
                self.visual_editor.setHtml(document_html)
                if decoded.automatic_foreground:
                    _rtf_clear_automatic_foreground(self.visual_editor.document(),decoded.automatic_foreground)
            self.apply_editor_canvas_theme(update_action=True); self._visual_document_zoom_percent=100; self._apply_visual_document_zoom(self.zoom_percent); self.visual_editor.document().setModified(False)
            self.file_path=os.path.abspath(file_path); self.file_format="rtf"; self.file_encoding="rtf"; self.file_bom=b""; self.file_newline="\n"; self.file_disk_signature=self._content_signature(data); self._source_rtf_payload=bytes(data); self.content_saved=True; self.rtf_compatibility_warnings=tuple(decoded.warnings); self.rtf_document_properties=dict(decoded.document_properties); self._rtf_save_warning_acknowledged=False; self.view_only=bool(self.persist_view_only); self._view_only_prompt_shown=False
            try:
                self._source_rtf_semantic_signature=self._content_signature(self._document_payload("rtf"))
            except Exception:
                self._source_rtf_semantic_signature=None
        finally: self._loading=False
        self._update_mode_capabilities(); self.update_title(); self.update_status_counts(); self.update_formatting_state(); self.visual_editor.setFocus()
        if self.rtf_compatibility_warnings: self._show_status_message("RTF opened with compatibility warnings. Review File → Properties before saving.",7000)
        return True

    @staticmethod
    def _default_created_file_mode():
        """Return the normal 0666 mode after applying the process umask."""
        current_umask = os.umask(0)
        os.umask(current_umask)
        return 0o666 & ~current_umask

    def save_file(self, check_external_change=True):
        if not self.file_path: return self.save_as_file()
        if check_external_change:
            action=self._external_change_action()
            if action=="reload": self.load_file(self.file_path,check_changes=False,show_error=True); return False
            if action=="save_as": return self.save_as_file()
            if action!="overwrite": return False
        document_dirty = (not self.content_saved) or self.visual_editor.document().isModified()
        canonical_payload = None
        canonical_signature = None
        semantically_clean = False
        if (
            document_dirty
            and self._source_rtf_payload is not None
            and self._source_rtf_semantic_signature is not None
        ):
            try:
                canonical_payload = self._document_payload("rtf")
                canonical_signature = self._content_signature(canonical_payload)
                semantically_clean = canonical_signature == self._source_rtf_semantic_signature
            except (ValueError, RuntimeError, MemoryError):
                canonical_payload = None
                canonical_signature = None
                semantically_clean = False
        clean_source = (
            self._source_rtf_payload is not None
            and ((not document_dirty) or semantically_clean)
        )
        if (
            clean_source
            and self.file_disk_signature == self._content_signature(self._source_rtf_payload)
            and self._disk_signature(self.file_path) == self.file_disk_signature
        ):
            # A plain Save on an unchanged loaded document is deliberately a
            # no-op.  A net-zero edit (type/delete back to the loaded supported
            # semantics) is treated the same way, so foreign RTF scaffolding is
            # not destroyed merely because Qt's modified flag stayed sticky.
            self._synchronise_after_save(
                self._source_rtf_payload,
                semantic_signature=self._source_rtf_semantic_signature,
                preserve_warnings=True,
            )
            self.content_saved=True
            self._update_mode_capabilities(); self.update_title(); self.update_status_counts(); return True
        if (not clean_source) and self.rtf_compatibility_warnings and not self._rtf_save_warning_acknowledged:
            details="\n• ".join(self.rtf_compatibility_warnings)
            box=QMessageBox(self); box.setIcon(QMessageBox.Icon.Warning); box.setWindowTitle("RTF Compatibility Warning — Rico Plus"); box.setText("This document contains RTF constructs that Rico Plus does not fully preserve."); box.setInformativeText("Saving will rewrite the document using Rico Plus's supported RTF subset. The following content may be discarded:\n\n• "+details+"\n\nContinue only if that is acceptable."); save_btn=box.addButton("Save Supported Content",QMessageBox.ButtonRole.AcceptRole); box.addButton(QMessageBox.StandardButton.Cancel); box.exec()
            if box.clickedButton() is not save_btn: return False
            self._rtf_save_warning_acknowledged=True
        try:
            if clean_source:
                payload=bytes(self._source_rtf_payload)
                semantic_signature=self._source_rtf_semantic_signature
            else:
                payload=canonical_payload if canonical_payload is not None else self._document_payload("rtf")
                semantic_signature=canonical_signature or self._content_signature(payload)
            if len(payload)>MAX_FILE_SIZE: raise ValueError(f"The saved document would exceed Rico Plus's {MAX_FILE_SIZE//(1024*1024)} MiB reopen limit.")
            self._write_payload_atomically(payload); self.file_disk_signature=self._content_signature(payload); self._synchronise_after_save(payload, semantic_signature=semantic_signature, preserve_warnings=clean_source); self.content_saved=True; self._update_mode_capabilities(); self.update_title(); self.update_status_counts(); return True
        except MemoryError: QMessageBox.critical(self,"Save Error","The document is too large to encode safely. No changes were written.")
        except (OSError,ValueError,RuntimeError) as exc: QMessageBox.critical(self,"Save Error",f"Could not save the document:\n{exc}")
        except Exception as exc: QMessageBox.critical(self,"Save Error",f"Rico Plus could not serialise this document safely:\n{exc}")
        return False

    def rename_current_file(self):
        if not self.file_path:
            QMessageBox.information(self, "Rename", "This document has not been saved yet. Use Save As to give it a name.")
            return False
        old_path = os.path.abspath(self.file_path)
        old_name = os.path.basename(old_path)
        parent_dir = os.path.dirname(old_path)
        new_name, accepted = QInputDialog.getText(
            self, "Rename", "New filename:", QLineEdit.EchoMode.Normal, old_name
        )
        if not accepted:
            return False
        new_name = new_name.strip()
        if not new_name or os.path.basename(new_name) != new_name or new_name in (".", ".."):
            QMessageBox.warning(self, "Rename", "Enter a filename only, without a folder path.")
            return False
        new_path = os.path.abspath(os.path.join(parent_dir, new_name))
        if new_path == old_path:
            return True
        new_format = self.format_for_path(new_path)
        if new_format != self.file_format:
            QMessageBox.warning(self, "Rename", "Rename cannot change the document format. Use Save As to convert it.")
            return False
        existing_target = os.path.exists(new_path)
        if existing_target:
            answer = QMessageBox.question(
                self, "Replace Existing File?",
                f'A file named "{new_name}" already exists.\n\nReplace it with the current file?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False
        try:
            os.replace(old_path, new_path) if existing_target else os.rename(old_path, new_path)
        except OSError as exc:
            QMessageBox.critical(self, "Rename Failed", f"Rico Plus could not rename the file.\n\n{exc}")
            return False
        self.file_path = new_path
        self.file_disk_signature = self._disk_signature(new_path)
        self._update_mode_capabilities()
        self.update_title()
        self.update_status_counts()
        return True

    def save_as_file(
        self,
        *,
        initial_path=None,
        forbidden_paths=(),
        dialog_title="Save As — Rico Plus",
        forbidden_message=None,
    ):
        initial_path=initial_path or self.file_path or os.path.join(os.path.expanduser("~"),"Untitled.rtf")
        file_path,_=QFileDialog.getSaveFileName(self,dialog_title,initial_path,"Rich Text Format (*.rtf)")
        if not file_path: return False
        if not Path(file_path).suffix: file_path += ".rtf"
        if Path(file_path).suffix.lower() not in RTF_EXTENSIONS:
            QMessageBox.warning(self,"Unsupported Extension — Rico Plus","Rico Plus saves .rtf documents only."); return False
        candidate = Path(file_path).expanduser().resolve(strict=False)
        forbidden = {Path(path).expanduser().resolve(strict=False) for path in forbidden_paths}
        if candidate in forbidden:
            QMessageBox.warning(
                self,
                dialog_title,
                forbidden_message or "Choose a different filename for this version.",
            )
            return False
        validator = getattr(self, "save_as_target_validator", None)
        if callable(validator) and not validator(candidate):
            QMessageBox.warning(
                self,
                dialog_title,
                "That RTF file is already open in another editor page. "
                "Close it before replacing it with Save As.",
            )
            return False
        previous=(self.file_path,self.file_disk_signature); old_path=self.file_path or ""; self.file_path=os.path.abspath(file_path); self.file_format="rtf"; self.file_encoding="rtf"; self.file_disk_signature=None
        if self.save_file(check_external_change=False):
            if old_path and os.path.abspath(old_path) != self.file_path:
                self.file_path_changed.emit(os.path.abspath(old_path), self.file_path)
            return True
        self.file_path,self.file_disk_signature=previous; self._update_mode_capabilities(); self.update_title(); self.update_status_counts(); return False

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        files = [
            url.toLocalFile() for url in event.mimeData().urls()
            if url.isLocalFile() and os.path.isfile(url.toLocalFile())
        ]
        if not files:
            return
        images = [path for path in files if Path(path).suffix.lower() in IMAGE_EXTENSIONS]
        documents = [path for path in files if path not in images]
        for image in images:
            self.insert_image_path(image)
        if documents:
            self.files_dropped.emit(documents)
        event.acceptProposedAction()

    def closeEvent(self, event):
        if self._skip_close_save_prompt:
            self._skip_close_save_prompt = False
            event.accept()
            return
        if self.check_save_changes():
            event.accept()
        else:
            event.ignore()


