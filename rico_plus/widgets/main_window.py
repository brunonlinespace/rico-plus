# Rico Plus
# Copyright (C) 2026 Bruno Machado
# SPDX-License-Identifier: GPL-3.0-or-later
"""Workspace shell for the Ribbon-only Rico Plus RTF editor."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import (
    QAction,
    QActionGroup,
    QCloseEvent,
    QDragEnterEvent,
    QDropEvent,
    QIcon,
    QKeySequence,
    QPalette,
)
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QLabel,
    QVBoxLayout,
    QWizard,
    QWizardPage,
    QWidget,
)

from rico_plus import APP_NAME
from rico_plus.app_constants import GITHUB_URL, ISSUES_URL, RTF_EXTENSIONS
from rico_plus.controllers.editor_manager import EditorManager
from rico_plus.controllers.file_actions import FileActionsController
from rico_plus.models.document import DocumentEntry
from rico_plus.models.document_repository import DocumentRepository
from rico_plus.models.document_state_store import DocumentStateStore
from rico_plus.services.config_service import ConfigService
from rico_plus.services.desktop_launcher import DesktopLauncher
from rico_plus.services.filesystem_watcher import FilesystemWatcher
from rico_plus.services.project_registry import ProjectRegistry
from rico_plus.services.runtime_paths import RuntimePaths
from rico_plus.widgets.about_dialog import AboutDialog
from rico_plus.widgets.editor_page import EditorPage
from rico_plus.widgets.navigation import NavigationWidget, SIDEBAR_MINIMUM_WIDTH
from rico_plus.widgets.projects_dialog import ProjectsDialog
from rico_plus.widgets.shortcuts_dialog import ShortcutsDialog
from rico_plus.widgets.rico_theme import apply_theme, effective_scheme
from rico_plus.widgets.shell_ribbon import ShellRibbon


class MainWindow(QMainWindow):
    """Own workspaces and transient OS-open sessions around Ricopad's RTF core."""

    def __init__(
        self,
        library_root: str | Path,
        config: ConfigService,
        project_registry: ProjectRegistry,
        runtime_paths: RuntimePaths,
        parent=None,
        *,
        icon_path: str | Path | None = None,
    ) -> None:
        super().__init__(parent)
        self.library_root = Path(library_root).expanduser().resolve(strict=False)
        self.config = config
        self.project_registry = project_registry
        self.runtime_paths = runtime_paths
        self.package_root = Path(__file__).resolve().parent.parent
        self.icon_path = Path(icon_path) if icon_path else (
            self.package_root / "assets" / "icons" / "ricopad.png"
        )
        if self.icon_path.is_file():
            self.setWindowIcon(QIcon(str(self.icon_path)))
        self.setAcceptDrops(True)

        self.repository = DocumentRepository(self)
        self.states = DocumentStateStore(self.repository, self)
        self.watcher = FilesystemWatcher(
            self.library_root, self.repository, parent=self
        )
        self.desktop_launcher = DesktopLauncher(self.runtime_paths, self)

        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.navigation = NavigationWidget(
            self.library_root, self.repository, self.states, self.splitter
        )
        self.stack = QStackedWidget(self.splitter)
        self.splitter.addWidget(self.navigation)
        self.splitter.addWidget(self.stack)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)
        self.splitter.setHandleWidth(8)
        self.splitter.setOpaqueResize(False)

        # The Plus workspace contract places one shell-owned command surface
        # across the whole window, with the sidebar/content splitter below it.
        # Document editors supply capabilities/state, never application chrome.
        self.central_host = QWidget(self)
        self.central_layout = QVBoxLayout(self.central_host)
        self.central_layout.setContentsMargins(0, 0, 0, 0)
        self.central_layout.setSpacing(0)
        self.ribbon_host = QWidget(self.central_host)
        self.ribbon_layout = QHBoxLayout(self.ribbon_host)
        self.ribbon_layout.setContentsMargins(0, 0, 0, 0)
        self.ribbon_layout.setSpacing(0)
        self.central_layout.addWidget(self.ribbon_host)
        self.central_layout.addWidget(self.splitter, 1)
        self.setCentralWidget(self.central_host)

        self.editor_manager = EditorManager(
            self.library_root,
            self.repository,
            self.states,
            self.stack,
            self.config,
            self,
        )
        self.file_actions = FileActionsController(
            self.library_root,
            self.repository,
            self.states,
            self.editor_manager,
            self.desktop_launcher,
            watcher=self.watcher,
            parent_widget=self,
            parent=self,
        )

        self._closing = False
        self._repair_navigation_after_scan = False
        self._startup_scan_pending = True
        self._startup_open_requested = False
        self._pending_open_path: Path | None = None
        self._drop_import_capture: list[Path] | None = None
        self.about_dialog: AboutDialog | None = None
        self.shortcuts_dialog: ShortcutsDialog | None = None
        self.quick_tour_dialog: QWizard | None = None

        self._status_label = QLabel("Ready.")
        status = QStatusBar(self)
        status.addWidget(self._status_label, 1)
        self.setStatusBar(status)

        self._build_menu_bar()
        self._create_shell_ribbon()
        self._connect_signals()
        self._restore_window_state()
        self._apply_active_project_state()
        self._update_window_title()
        self.watcher.start(initial_scan=True)
        self._update_action_states()

    def _action(
        self,
        text: str,
        slot,
        shortcut=None,
        *,
        checkable: bool = False,
    ) -> QAction:
        action = QAction(text, self)
        action.setCheckable(checkable)
        action.triggered.connect(slot)
        if shortcut:
            sequence = shortcut if isinstance(shortcut, QKeySequence) else QKeySequence(shortcut)
            action.setShortcut(sequence)
        clean = text.replace("&", "").replace("…", "").strip()
        rendered = action.shortcut().toString(QKeySequence.SequenceFormat.NativeText).strip()
        action.setToolTip(f"{clean} — {rendered}" if rendered else clean)
        return action

    def _build_menu_bar(self) -> None:
        self.new_action = self._action(
            "New RTF File…", self._new_rtf_file, QKeySequence.StandardKey.New
        )
        self.new_window_action = self._action(
            "New Window", self._new_window
        )
        self.new_folder_action = self._action(
            "New Folder…", self._new_folder, "Ctrl+Shift+N"
        )
        self.dashboard_action = self._action(
            "Show Dashboard", self.editor_manager.show_dashboard, "Ctrl+W"
        )
        self.manage_workspaces_action = self._action(
            "Manage Workspaces…", self._show_projects,
            QKeySequence.StandardKey.Open,
        )
        self.refresh_action = self._action(
            "Refresh Workspace", self._refresh_workspace
        )
        self.exit_action = self._action(
            "Exit", self.close, QKeySequence.StandardKey.Quit
        )

        self.list_action = self._action(
            "List View",
            lambda: self.editor_manager.set_view_mode("list"),
            checkable=True,
        )
        self.grid_action = self._action(
            "Grid View",
            lambda: self.editor_manager.set_view_mode("grid"),
            checkable=True,
        )
        dashboard_group = QActionGroup(self)
        dashboard_group.setExclusive(True)
        dashboard_group.addAction(self.list_action)
        dashboard_group.addAction(self.grid_action)
        self.toggle_dashboard_view_action = self._action(
            "Toggle List/Grid View",
            self.editor_manager.dashboard.toggle_view_mode,
            "Ctrl+Alt+Shift+D",
        )
        self.sidebar_action = self._action(
            "Show Sidebar", self._toggle_sidebar, "F9", checkable=True
        )
        self.sidebar_action.setChecked(True)
        self.status_bar_action = self._action(
            "Show Status", self._toggle_status_bar,
            "Ctrl+Alt+Shift+S", checkable=True,
        )
        self.status_bar_action.setChecked(
            bool(self.config.get("show_status_bar", True))
        )
        self.statusBar().setVisible(self.status_bar_action.isChecked())
        self.fullscreen_action = self._action(
            "Full Screen", self._toggle_fullscreen, "F11", checkable=True
        )

        self.previous_file_action = self._action(
            "Previous File",
            lambda: self.navigation.navigate_adjacent_document(-1),
            "Ctrl+Up",
        )
        self.next_file_action = self._action(
            "Next File",
            lambda: self.navigation.navigate_adjacent_document(1),
            "Ctrl+Down",
        )
        for action in (
            self.previous_file_action,
            self.next_file_action,
            self.toggle_dashboard_view_action,
        ):
            self.addAction(action)

        current_theme = str(self.config.get("app_theme", "system"))
        self.theme_actions: dict[str, QAction] = {}
        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)
        for value, label in (
            ("system", "System"),
            ("dark", "Dark"),
            ("light", "Light"),
        ):
            action = self._action(
                label,
                lambda _checked=False, selected=value:
                    self._set_theme(selected),
                checkable=True,
            )
            action.setChecked(value == current_theme)
            theme_group.addAction(action)
            self.theme_actions[value] = action

        current_icons = str(self.config.get("editor_icon_set", "new"))
        QApplication.instance().setProperty("rico_plus_icon_set", current_icons)
        self.icon_actions: dict[str, QAction] = {}
        icon_group = QActionGroup(self)
        icon_group.setExclusive(True)
        for value, label in (
            ("classic", "Rico Icons Classic"),
            ("new", "Rico Icons New"),
        ):
            action = self._action(
                label,
                lambda _checked=False, selected=value:
                    self._set_icon_set(selected),
                checkable=True,
            )
            action.setChecked(value == current_icons)
            icon_group.addAction(action)
            self.icon_actions[value] = action

        launch = str(self.config.get("app_launch_screen", "dashboard"))
        self.launch_actions: dict[str, QAction] = {}
        launch_group = QActionGroup(self)
        launch_group.setExclusive(True)
        for value, label in (
            ("dashboard", "Dashboard"),
            ("last_file", "Last File"),
        ):
            action = self._action(
                label,
                lambda _checked=False, selected=value:
                    self._set_launch_screen(selected),
                checkable=True,
            )
            action.setChecked(value == launch)
            launch_group.addAction(action)
            self.launch_actions[value] = action

        drop_mode = str(self.config.get("drop_open_mode", "active_window"))
        self.drop_actions: dict[str, QAction] = {}
        drop_group = QActionGroup(self)
        drop_group.setExclusive(True)
        for value, label in (
            ("active_window", "Open on Active Window"),
            ("new_window", "Open on New Window"),
        ):
            action = self._action(
                label,
                lambda _checked=False, selected=value:
                    self._set_drop_mode(selected),
                checkable=True,
            )
            action.setChecked(value == drop_mode)
            drop_group.addAction(action)
            self.drop_actions[value] = action

        self.shortcuts_action = self._action(
            "Keyboard Shortcuts", self._show_shortcuts, "Ctrl+Shift+/"
        )
        self.docs_action = self._action(
            "Documentation", self._open_documentation,
            QKeySequence.StandardKey.HelpContents,
        )
        self.github_action = self._action(
            "GitHub Repository",
            lambda: self.desktop_launcher.open_url(GITHUB_URL),
        )
        self.issue_action = self._action(
            "Raise an Issue",
            lambda: self.desktop_launcher.open_url(ISSUES_URL),
        )
        self.about_action = self._action(
            "About Rico Plus", self._show_about_dialog
        )
        self.about_action.setMenuRole(QAction.MenuRole.AboutRole)
        self._build_editor_shell_actions()

        bar = self.menuBar()
        # Ricopad's platform-menu contract is explicit: request the native
        # menu path so Plasma's Global Menu / Menu Only integration can export
        # this one authoritative Plus application menu.
        bar.setNativeMenuBar(True)
        self._build_static_menus(bar)
        bar.show()
        self._refresh_action_icons()

    def _engine(self):
        page = self._current_page()
        return page.engine if page is not None else None

    def _engine_action(self, name: str):
        engine = self._engine()
        action = getattr(engine, name, None) if engine is not None else None
        return action if isinstance(action, QAction) else None

    def _trigger_engine_action(self, name: str) -> None:
        action = self._engine_action(name)
        if action is not None and action.isEnabled():
            action.trigger()
        self._sync_editor_actions()

    def _engine_call(self, method: str, *args) -> None:
        engine = self._engine()
        if engine is not None:
            getattr(engine, method)(*args)
        self._sync_editor_actions()

    def _proxy(self, text: str, engine_action: str, shortcut=None, *, checkable=False) -> QAction:
        return self._action(
            text,
            lambda _checked=False, name=engine_action: self._trigger_engine_action(name),
            shortcut,
            checkable=checkable,
        )

    def _build_editor_shell_actions(self) -> None:
        self.save_action = self._action("Save", self._save_current, QKeySequence.StandardKey.Save)
        self.save_as_action = self._action("Save As…", lambda: self._engine_call("save_as_file"))
        self.save_new_action = self._action("Save and New", lambda: self._save_and_new(self._current_page()) if self._current_page() else None, "Ctrl+Shift+S")
        self.save_dashboard_action = self._action("Save and Dashboard", lambda: self._save_and_dashboard(self._current_page()) if self._current_page() else None, "Ctrl+Shift+W")
        self.save_exit_action = self._action("Save and Exit", lambda: self._save_and_exit(self._current_page()) if self._current_page() else None, "Ctrl+Shift+Q")
        self.properties_action = self._action("Properties", lambda: self._engine_call("show_properties_dialog"), "F4")
        self.external_editor_action = self._action("Open in External Editor", self._open_current_external, "Ctrl+Shift+E")
        self.rename_file_action = self._action("Rename…", self._rename_current, "F2")
        self.delete_file_action = self._action("Delete File", self._delete_current_file)
        self.duplicate_action = self._action("Duplicate File", self._duplicate_current, "Ctrl+Shift+D")
        self.open_document_folder_action = self._action("Open Containing Folder", self._open_current_document_folder, "Ctrl+Shift+O")
        self.print_action = self._action("Print…", lambda: self._engine_call("print_document"), QKeySequence.StandardKey.Print)
        self.export_pdf_action = self._action("Export PDF…", lambda: self._engine_call("export_pdf"), "Ctrl+Shift+P")
        self.page_setup_action = self._action("Page Setup…", lambda: self._engine_call("show_page_setup_dialog"))

        self.undo_action=self._proxy("Undo","undo_action",QKeySequence.StandardKey.Undo)
        self.redo_action=self._proxy("Redo","redo_action","Ctrl+Y")
        self.cut_action=self._proxy("Cut","cut_action",QKeySequence.StandardKey.Cut)
        self.copy_action=self._proxy("Copy","copy_action",QKeySequence.StandardKey.Copy)
        self.paste_action=self._proxy("Paste","paste_action",QKeySequence.StandardKey.Paste)
        self.paste_plain_action=self._proxy("Paste Plain Text","paste_plain_action","Ctrl+Shift+V")
        self.delete_text_action=self._proxy("Delete","delete_text_action",QKeySequence.StandardKey.Delete)
        self.duplicate_line_action=self._proxy("Duplicate Line / Selection","duplicate_line_action","Ctrl+D")
        self.delete_line_action=self._proxy("Delete Line","delete_line_action","Ctrl+Shift+K")
        self.select_all_action=self._proxy("Select All","select_all_action",QKeySequence.StandardKey.SelectAll)
        self.search_bar_action=self._proxy("Find Bar","search_bar_action",QKeySequence.StandardKey.Find,checkable=True)
        self.replace_action=self._proxy("Find and Replace…","replace_action","Ctrl+H")

        self.font_dialog_action=self._proxy("Font…","font_dialog_action","Ctrl+Alt+Shift+F")
        self.increase_font_size_action=self._proxy("Increase Font Size","increase_font_size_action")
        self.decrease_font_size_action=self._proxy("Decrease Font Size","decrease_font_size_action")
        self.text_colour_action=self._proxy("Text Colour…","text_colour_action","Ctrl+Alt+Shift+C")
        self.highlight_colour_action=self._proxy("Highlight Colour…","highlight_colour_action","Ctrl+Alt+Shift+H")
        self.clear_highlight_action=self._proxy("Clear Highlight","clear_highlight_action")
        self.bold_action=self._proxy("Bold","bold_action",QKeySequence.StandardKey.Bold,checkable=True)
        self.italic_action=self._proxy("Italic","italic_action",QKeySequence.StandardKey.Italic,checkable=True)
        self.underline_action=self._proxy("Underline","underline_action",QKeySequence.StandardKey.Underline,checkable=True)
        self.strike_action=self._proxy("Strikethrough","strike_action","Ctrl+Shift+X",checkable=True)
        self.superscript_action=self._proxy("Superscript","superscript_action","Ctrl+.",checkable=True)
        self.subscript_action=self._proxy("Subscript","subscript_action","Ctrl+,",checkable=True)
        self.bullet_action=self._proxy("Bullet List","bulleted_list_action","Ctrl+5",checkable=True)
        self.indent_action=self._proxy("Indent","increase_indent_action","Ctrl+]")
        self.outdent_action=self._proxy("Outdent","decrease_indent_action","Ctrl+[")
        self.paragraph_action=self._proxy("Paragraph…","paragraph_action","Ctrl+Alt+Shift+P")
        self.clear_formatting_action=self._proxy("Clear Formatting","clear_formatting_action","Ctrl+Space")
        self.alignment_left_action=self._action("Left",lambda:self._set_alignment(Qt.AlignmentFlag.AlignLeft),"Ctrl+L",checkable=True)
        self.alignment_center_action=self._action("Centre",lambda:self._set_alignment(Qt.AlignmentFlag.AlignHCenter),"Ctrl+E",checkable=True)
        self.alignment_right_action=self._action("Right",lambda:self._set_alignment(Qt.AlignmentFlag.AlignRight),"Ctrl+R",checkable=True)
        self.alignment_justify_action=self._action("Justify",lambda:self._set_alignment(Qt.AlignmentFlag.AlignJustify),"Ctrl+J",checkable=True)
        group=QActionGroup(self); group.setExclusive(True)
        for a in (self.alignment_left_action,self.alignment_center_action,self.alignment_right_action,self.alignment_justify_action): group.addAction(a)
        self.heading_actions={}
        heading_group=QActionGroup(self); heading_group.setExclusive(True)
        for level in range(7):
            label="Normal Paragraph" if level==0 else f"Heading {level}"
            action=self._action(label,lambda _checked=False,n=level:self._set_heading(n),f"Ctrl+Shift+{level}",checkable=True); self.heading_actions[level]=action; heading_group.addAction(action)
        self.line_spacing_actions={}
        spacing_group=QActionGroup(self); spacing_group.setExclusive(True)
        for label,value,shortcut in (("1.0",100,"Ctrl+1"),("1.15",115,"Ctrl+2"),("1.5",150,"Ctrl+3"),("2.0",200,"Ctrl+4")):
            action=self._action(label,lambda _checked=False,n=value:self._set_line_spacing(n),shortcut,checkable=True); self.line_spacing_actions[value]=action; spacing_group.addAction(action)

        self.link_action=self._proxy("Insert Link…","link_action","Ctrl+K")
        self.edit_link_action=self._proxy("Edit Link…","edit_link_action")
        self.remove_link_action=self._proxy("Remove Link","remove_link_action")
        self.rule_action=self._proxy("Horizontal Rule","horizontal_rule_action","Ctrl+Shift+H")
        self.image_action=self._proxy("Image…","image_action","Ctrl+Shift+I")
        self.table_action=self._proxy("Table…","table_action","Ctrl+Shift+T")
        self.table_row_above_action=self._proxy("Insert Row Above","table_row_above_action")
        self.table_row_below_action=self._proxy("Insert Row Below","table_row_below_action")
        self.table_delete_row_action=self._proxy("Delete Row","table_delete_row_action")
        self.table_column_left_action=self._proxy("Insert Column Left","table_column_left_action")
        self.table_column_right_action=self._proxy("Insert Column Right","table_column_right_action")
        self.table_delete_column_action=self._proxy("Delete Column","table_delete_column_action")
        self.table_delete_action=self._proxy("Delete Table","table_delete_action")
        self.date_time_action=self._proxy("Date and Time","insert_date_time_action","F5")
        self.date_action=self._proxy("Date Only","date_action","Ctrl+;")
        self.time_action=self._proxy("Time Only","time_action","Ctrl+:")
        self.symbol_action=self._proxy("Symbol…","symbol_action","Shift+F5")

        self.view_only_action=self._action("Lock Editor", self._toggle_lock_editor_current, "F12", checkable=True)
        self.word_wrap_action=self._proxy("Word Wrap","wrap_action","Ctrl+Alt+Shift+W",checkable=True)
        self.editor_canvas_theme_action=self._action(
            "Dark Editor", self._toggle_editor_canvas_light,
            "Ctrl+Alt+Shift+E", checkable=True,
        )
        self.editor_canvas_theme_action.setChecked(not self._canvas_is_light())
        self.zoom_in_action=self._proxy("Zoom In","zoom_in_action",QKeySequence.StandardKey.ZoomIn)
        self.zoom_out_action=self._proxy("Zoom Out","zoom_out_action",QKeySequence.StandardKey.ZoomOut)
        self.zoom_reset_action=self._proxy("Reset Zoom","zoom_reset_action","Ctrl+0")
        self.tab_width_action=self._proxy("Tab Width…","tab_width_action")
        self.default_font_action=self._proxy("New Document Defaults…","default_font_action")
        self.quick_start_action=self._action("Tutorial Wizard",self._show_quick_tour,"Shift+F1")
        self.next_ribbon_tab_action=self._action("Next Ribbon Tab",lambda:self.shell_ribbon.cycle_tab(1),"Ctrl+Tab")
        self.previous_ribbon_tab_action=self._action("Previous Ribbon Tab",lambda:self.shell_ribbon.cycle_tab(-1),"Ctrl+Shift+Tab")
        self.addAction(self.next_ribbon_tab_action); self.addAction(self.previous_ribbon_tab_action)
        self.theme_system_action=self.theme_actions["system"]; self.theme_dark_action=self.theme_actions["dark"]; self.theme_light_action=self.theme_actions["light"]
        self.icon_classic_action=self.icon_actions["classic"]; self.icon_new_action=self.icon_actions["new"]
        self.launch_dashboard_action=self.launch_actions["dashboard"]; self.launch_last_file_action=self.launch_actions["last_file"]
        self.drop_active_action=self.drop_actions["active_window"]; self.drop_new_window_action=self.drop_actions["new_window"]

    def _build_static_menus(self, bar) -> None:
        self.file_menu=bar.addMenu("&File"); self.edit_menu=bar.addMenu("&Edit"); self.format_menu=bar.addMenu("F&ormat"); self.insert_menu=bar.addMenu("&Insert"); self.view_menu=bar.addMenu("&View"); self.settings_menu=bar.addMenu("&Settings"); self.help_menu=bar.addMenu("&Help")
        for a in (self.new_action,self.new_window_action,self.new_folder_action): self.file_menu.addAction(a)
        self.file_menu.addSeparator(); self.file_menu.addAction(self.dashboard_action); self.file_menu.addAction(self.previous_file_action); self.file_menu.addAction(self.next_file_action)
        self.workspace_menu=self.file_menu.addMenu("Workspace(s)"); self.workspace_action_group=QActionGroup(self.workspace_menu); self.workspace_action_group.setExclusive(True); self.workspace_menu.aboutToShow.connect(self._rebuild_workspace_menu); self._rebuild_workspace_menu()
        self.file_menu.addSeparator()
        for a in (self.save_action,self.save_as_action,self.save_new_action,self.save_dashboard_action): self.file_menu.addAction(a)
        more=self.file_menu.addMenu("More Actions")
        more.addAction(self.external_editor_action); more.addSeparator()
        for a in (self.rename_file_action,self.delete_file_action,self.duplicate_action): more.addAction(a)
        more.addSeparator(); more.addAction(self.open_document_folder_action); more.addAction(self.properties_action)
        self.file_menu.addSeparator(); self.file_menu.addAction(self.print_action); self.file_menu.addAction(self.export_pdf_action); self.file_menu.addAction(self.page_setup_action); self.file_menu.addSeparator(); self.file_menu.addAction(self.exit_action); self.file_menu.addAction(self.save_exit_action)
        self.edit_menu.addAction(self.undo_action); self.edit_menu.addAction(self.redo_action); self.edit_menu.addSeparator()
        for a in (self.cut_action,self.copy_action,self.paste_action,self.paste_plain_action): self.edit_menu.addAction(a)
        self.edit_menu.addSeparator(); self.edit_menu.addAction(self.delete_text_action); self.edit_menu.addSeparator(); self.edit_menu.addAction(self.duplicate_line_action); self.edit_menu.addAction(self.delete_line_action); self.edit_menu.addSeparator(); self.edit_menu.addAction(self.select_all_action); self.edit_menu.addSeparator(); self.edit_menu.addAction(self.search_bar_action); self.edit_menu.addAction(self.replace_action)
        for a in (self.font_dialog_action,self.increase_font_size_action,self.decrease_font_size_action,self.text_colour_action,self.highlight_colour_action,self.clear_highlight_action): self.format_menu.addAction(a)
        self.format_menu.addSeparator()
        for a in (self.bold_action,self.italic_action,self.underline_action,self.strike_action,self.superscript_action,self.subscript_action): self.format_menu.addAction(a)
        headings=self.format_menu.addMenu("Paragraph Style")
        for n in range(7): headings.addAction(self.heading_actions[n])
        alignment=self.format_menu.addMenu("Alignment")
        for a in (self.alignment_left_action,self.alignment_center_action,self.alignment_right_action,self.alignment_justify_action): alignment.addAction(a)
        spacing=self.format_menu.addMenu("Line Spacing")
        for n in (100,115,150,200): spacing.addAction(self.line_spacing_actions[n])
        self.format_menu.addSeparator(); self.format_menu.addAction(self.bullet_action); self.format_menu.addAction(self.indent_action); self.format_menu.addAction(self.outdent_action); self.format_menu.addSeparator(); self.format_menu.addAction(self.paragraph_action); self.format_menu.addAction(self.clear_formatting_action)
        links=self.insert_menu.addMenu("Link"); links.addAction(self.link_action); links.addAction(self.edit_link_action); links.addSeparator(); links.addAction(self.remove_link_action)
        self.insert_menu.addSeparator(); self.insert_menu.addAction(self.rule_action); self.insert_menu.addAction(self.image_action); self.insert_menu.addSeparator(); self.insert_menu.addAction(self.table_action)
        table=self.insert_menu.addMenu("Table Editing")
        for a in (self.table_row_above_action,self.table_row_below_action,self.table_delete_row_action,self.table_column_left_action,self.table_column_right_action,self.table_delete_column_action,self.table_delete_action): table.addAction(a)
        self.insert_menu.addSeparator()
        for a in (self.date_time_action,self.date_action,self.time_action,self.symbol_action): self.insert_menu.addAction(a)
        self.view_menu.addAction(self.fullscreen_action); self.view_menu.addAction(self.sidebar_action); self.view_menu.addAction(self.status_bar_action); self.view_menu.addSeparator(); self.view_menu.addAction(self.word_wrap_action); self.view_menu.addAction(self.editor_canvas_theme_action); self.view_menu.addSeparator(); self.view_menu.addAction(self.view_only_action)
        zoom=self.view_menu.addMenu("Editor Zoom"); zoom.addAction(self.zoom_in_action); zoom.addAction(self.zoom_out_action); zoom.addSeparator(); zoom.addAction(self.zoom_reset_action)
        misc=self.view_menu.addMenu("Editor Miscellaneous"); misc.addAction(self.tab_width_action); misc.addAction(self.default_font_action)
        theme=self.settings_menu.addMenu("App Theme"); self.app_theme_menu_action=theme.menuAction()
        for n in ("system","dark","light"): theme.addAction(self.theme_actions[n])
        icons=self.settings_menu.addMenu("App Icons"); self.app_icons_menu_action=icons.menuAction()
        for n in ("classic","new"): icons.addAction(self.icon_actions[n])
        dash=self.settings_menu.addMenu("App Dashboard"); self.app_dashboard_menu_action=dash.menuAction(); dash.addAction(self.list_action); dash.addAction(self.grid_action)
        self.settings_menu.addSeparator(); launch=self.settings_menu.addMenu("App Launch Screen"); self.app_launch_screen_menu_action=launch.menuAction()
        for n in ("dashboard","last_file"): launch.addAction(self.launch_actions[n])
        drop=self.settings_menu.addMenu("App Drag-and-Drop"); self.app_drag_drop_menu_action=drop.menuAction()
        for n in ("active_window","new_window"): drop.addAction(self.drop_actions[n])
        self.help_menu.addAction(self.docs_action); self.help_menu.addSeparator(); self.help_menu.addAction(self.quick_start_action); self.help_menu.addAction(self.shortcuts_action); self.help_menu.addSeparator(); self.help_menu.addAction(self.github_action); self.help_menu.addAction(self.issue_action); self.help_menu.addSeparator(); self.help_menu.addAction(self.about_action)

    def _toolbar_icon_path(self, name: str) -> Path:
        scheme = effective_scheme(str(self.config.get("app_theme", "system")))
        icon_set = str(self.config.get("editor_icon_set", "new"))
        family = "ribbon-icons-classic" if icon_set == "classic" else "ribbon-icons"
        return self.package_root / "assets" / family / scheme / f"{name}.png"

    def _refresh_action_icons(self) -> None:
        mapping={
            "new_action":"new", "new_window_action":"new-window", "new_folder_action":"new-folder",
            "manage_workspaces_action":"manage-workspaces", "dashboard_action":"show-dashboard",
            "save_action":"save", "save_as_action":"save-as", "save_new_action":"save-new",
            "save_dashboard_action":"save-dashboard", "save_exit_action":"save-exit",
            "duplicate_action":"duplicate-file", "rename_file_action":"rename",
            "delete_file_action":"delete-file", "open_document_folder_action":"open-folder",
            "external_editor_action":"external-editor", "properties_action":"properties",
            "print_action":"print", "export_pdf_action":"export-pdf", "page_setup_action":"page-setup",
            "exit_action":"exit", "undo_action":"undo", "redo_action":"redo", "cut_action":"cut",
            "copy_action":"copy", "paste_action":"paste", "paste_plain_action":"paste-plain",
            "delete_text_action":"delete-text", "duplicate_line_action":"duplicate-line",
            "delete_line_action":"delete-line", "select_all_action":"select-all",
            "search_bar_action":"search-toggle", "replace_action":"replace",
            "font_dialog_action":"font-dialog", "increase_font_size_action":"font-size-increase",
            "decrease_font_size_action":"font-size-decrease", "text_colour_action":"text-color",
            "highlight_colour_action":"highlight", "underline_action":"underline",
            "bold_action":"bold", "italic_action":"italic", "strike_action":"strikethrough",
            "subscript_action":"subscript", "superscript_action":"superscript",
            "bullet_action":"bullet-list", "indent_action":"indent", "outdent_action":"outdent",
            "paragraph_action":"paragraph", "clear_formatting_action":"clear-formatting",
            "alignment_left_action":"align-left", "alignment_center_action":"align-center",
            "alignment_right_action":"align-right", "alignment_justify_action":"justify",
            "link_action":"insert-link", "edit_link_action":"edit-link",
            "remove_link_action":"remove-link", "rule_action":"horizontal-rule",
            "image_action":"insert-image", "table_action":"insert-table",
            "table_delete_action":"delete-table", "table_column_left_action":"insert-column-left",
            "table_column_right_action":"insert-column-right", "table_delete_column_action":"delete-column",
            "table_row_above_action":"insert-row-above", "table_row_below_action":"insert-row-below",
            "table_delete_row_action":"delete-row", "date_time_action":"date-time",
            "date_action":"insert-date", "time_action":"insert-time", "symbol_action":"symbols",
            "fullscreen_action":"full-screen", "view_only_action":"view-only",
            "word_wrap_action":"word-wrap", "editor_canvas_theme_action":"editor-canvas",
            "zoom_in_action":"zoom-in", "zoom_out_action":"zoom-out", "zoom_reset_action":"zoom-reset",
            "tab_width_action":"tab-width", "default_font_action":"default-font",
            "sidebar_action":"show-sidebar", "status_bar_action":"status-bar",
            "theme_dark_action":"theme-dark", "theme_light_action":"theme-light",
            "icon_classic_action":"icons-classic", "icon_new_action":"icons-new",
            "list_action":"list-view", "grid_action":"grid-view",
            "launch_dashboard_action":"launch-dashboard", "launch_last_file_action":"launch-last-file",
            "drop_active_action":"drop-active", "drop_new_window_action":"drop-new-window",
            "docs_action":"documentation", "quick_start_action":"tutorial",
            "shortcuts_action":"shortcuts", "github_action":"github", "issue_action":"issue",
            "about_action":"about",
            "app_theme_menu_action":"app-theme", "app_icons_menu_action":"app-icons",
            "app_dashboard_menu_action":"show-dashboard",
            "app_launch_screen_menu_action":"launch-dashboard",
            "app_drag_drop_menu_action":"drop-active",
        }
        for attr,name in mapping.items():
            action=getattr(self,attr,None); path=self._toolbar_icon_path(name)
            if isinstance(action,QAction) and path.is_file(): action.setIcon(QIcon(str(path)))

        # Classic/New are selectors for two real Rico families.  Their icons
        # preview the target family rather than both adopting the currently
        # selected family, while still following the current light/dark scheme.
        scheme = effective_scheme(str(self.config.get("app_theme", "system")))
        family_previews = (
            (self.icon_classic_action, "ribbon-icons-classic", "icons-classic"),
            (self.icon_new_action, "ribbon-icons", "icons-new"),
        )
        for action, family, name in family_previews:
            path = self.package_root / "assets" / family / scheme / f"{name}.png"
            if path.is_file():
                action.setIcon(QIcon(str(path)))

    def _create_shell_ribbon(self) -> None:
        names=("print_action","export_pdf_action","page_setup_action","new_action","new_folder_action","new_window_action","manage_workspaces_action","dashboard_action","save_as_action","properties_action","delete_file_action","external_editor_action","save_action","rename_file_action","duplicate_action","open_document_folder_action","save_new_action","save_dashboard_action","save_exit_action","exit_action","select_all_action","cut_action","delete_text_action","paste_plain_action","undo_action","redo_action","copy_action","paste_action","increase_font_size_action","decrease_font_size_action","font_dialog_action","text_colour_action","underline_action","strike_action","subscript_action","superscript_action","bold_action","italic_action","highlight_colour_action","bullet_action","alignment_right_action","alignment_justify_action","indent_action","outdent_action","alignment_left_action","alignment_center_action","paragraph_action","clear_formatting_action","replace_action","duplicate_line_action","delete_line_action","date_time_action","symbol_action","date_action","time_action","remove_link_action","image_action","link_action","edit_link_action","table_delete_action","table_column_left_action","table_column_right_action","table_delete_column_action","table_action","table_row_above_action","table_row_below_action","table_delete_row_action","rule_action","fullscreen_action","view_only_action","word_wrap_action","editor_canvas_theme_action","sidebar_action","status_bar_action","search_bar_action","zoom_in_action","zoom_reset_action","zoom_out_action","tab_width_action","default_font_action","theme_system_action","theme_dark_action","theme_light_action","icon_classic_action","icon_new_action","list_action","grid_action","launch_dashboard_action","launch_last_file_action","drop_active_action","drop_new_window_action","docs_action","quick_start_action","shortcuts_action","about_action","github_action","issue_action")
        self.shell_ribbon=ShellRibbon({n:getattr(self,n) for n in names},self.ribbon_host); self.ribbon_layout.addWidget(self.shell_ribbon)
        self.shell_ribbon.font_family_selected.connect(lambda font:self._engine_call("set_selected_font",font)); self.shell_ribbon.font_size_selected.connect(lambda text:self._engine_call("set_selected_font_size",text)); self.shell_ribbon.heading_selected.connect(self._set_heading); self.shell_ribbon.line_spacing_selected.connect(self._set_line_spacing)
        self.shell_ribbon.collapsed_changed.connect(lambda v:self.config.set("rico_plus_ribbon_collapsed",bool(v),save=True))
        if bool(self.config.get("rico_plus_ribbon_collapsed",False)): self.shell_ribbon.set_collapsed(True,emit=False)
        self._sync_editor_actions()

    def _save_current(self) -> None:
        page=self._current_page()
        if page is not None: page.save_to_disk()
    def _rename_current(self) -> None:
        if self.editor_manager.current_document is not None: self.file_actions.rename_document(self.editor_manager.current_document)
    def _delete_current_file(self) -> None:
        if self.editor_manager.current_document is not None: self.file_actions.remove_document(self.editor_manager.current_document)
    def _duplicate_current(self) -> None:
        if self.editor_manager.current_document is not None: self.file_actions.duplicate_document(self.editor_manager.current_document)
    def _open_current_document_folder(self) -> None:
        if self.editor_manager.current_document is not None: self.file_actions.open_document_folder(self.editor_manager.current_document)
    def _open_current_external(self) -> None:
        if self.editor_manager.current_document is not None: self.file_actions.open_external_editor(self.editor_manager.current_document)
    def _toggle_lock_editor_current(self, checked: bool) -> None:
        # Preserve Ricopad's protective unlock warning, then make the resulting
        # lock state application-wide so it follows the user across files and
        # survives the next session.
        page = self._current_page()
        if page is None:
            self.view_only_action.blockSignals(True)
            self.view_only_action.setChecked(bool(self.config.get("lock_editor", False)))
            self.view_only_action.blockSignals(False)
            return
        desired = bool(checked)
        source = self._engine_action("view_only_action")
        if source is not None and bool(page.view_only) != desired:
            source.trigger()
        resulting = bool(page.view_only)
        self.editor_manager.set_lock_editor(resulting)
        self._sync_editor_actions()
    def _set_alignment(self,value) -> None: self._engine_call("set_alignment",value)
    def _set_heading(self,value: int) -> None: self._engine_call("apply_heading",int(value))
    def _set_line_spacing(self,value: int) -> None: self._engine_call("set_line_spacing",int(value))

    def _sync_proxy_action(self,shell_name: str,engine_name: str) -> None:
        shell=getattr(self,shell_name); source=self._engine_action(engine_name); shell.setEnabled(source is not None and source.isEnabled())
        if shell.isCheckable() and source is not None:
            shell.blockSignals(True); shell.setChecked(source.isChecked()); shell.blockSignals(False)

    def _sync_editor_actions(self,*_args) -> None:
        page=self._current_page(); enabled=page is not None
        for name in ("save_action","save_as_action","save_new_action","save_dashboard_action","save_exit_action","properties_action","external_editor_action","rename_file_action","delete_file_action","duplicate_action","open_document_folder_action","print_action","export_pdf_action","page_setup_action"): getattr(self,name).setEnabled(enabled)
        pairs={"undo_action":"undo_action","redo_action":"redo_action","cut_action":"cut_action","copy_action":"copy_action","paste_action":"paste_action","paste_plain_action":"paste_plain_action","delete_text_action":"delete_text_action","duplicate_line_action":"duplicate_line_action","delete_line_action":"delete_line_action","select_all_action":"select_all_action","search_bar_action":"search_bar_action","replace_action":"replace_action","font_dialog_action":"font_dialog_action","increase_font_size_action":"increase_font_size_action","decrease_font_size_action":"decrease_font_size_action","text_colour_action":"text_colour_action","highlight_colour_action":"highlight_colour_action","clear_highlight_action":"clear_highlight_action","bold_action":"bold_action","italic_action":"italic_action","underline_action":"underline_action","strike_action":"strike_action","superscript_action":"superscript_action","subscript_action":"subscript_action","bullet_action":"bulleted_list_action","indent_action":"increase_indent_action","outdent_action":"decrease_indent_action","paragraph_action":"paragraph_action","clear_formatting_action":"clear_formatting_action","link_action":"link_action","edit_link_action":"edit_link_action","remove_link_action":"remove_link_action","rule_action":"horizontal_rule_action","image_action":"image_action","table_action":"table_action","table_row_above_action":"table_row_above_action","table_row_below_action":"table_row_below_action","table_delete_row_action":"table_delete_row_action","table_column_left_action":"table_column_left_action","table_column_right_action":"table_column_right_action","table_delete_column_action":"table_delete_column_action","table_delete_action":"table_delete_action","date_time_action":"insert_date_time_action","date_action":"date_action","time_action":"time_action","symbol_action":"symbol_action","word_wrap_action":"wrap_action","zoom_in_action":"zoom_in_action","zoom_out_action":"zoom_out_action","zoom_reset_action":"zoom_reset_action","tab_width_action":"tab_width_action","default_font_action":"default_font_action"}
        for a,b in pairs.items(): self._sync_proxy_action(a,b)
        self.view_only_action.setEnabled(enabled); self.view_only_action.blockSignals(True); self.view_only_action.setChecked(bool(page.view_only) if page else bool(self.config.get("lock_editor", False))); self.view_only_action.blockSignals(False)
        self.editor_canvas_theme_action.blockSignals(True)
        self.editor_canvas_theme_action.setChecked(not self._canvas_is_light())
        self.editor_canvas_theme_action.blockSignals(False)
        for action in [*self.heading_actions.values(),*self.line_spacing_actions.values(),self.alignment_left_action,self.alignment_center_action,self.alignment_right_action,self.alignment_justify_action]: action.setEnabled(enabled)
        if enabled:
            engine=page.engine
            for level,shell in self.heading_actions.items():
                source=getattr(engine,"heading_actions",{}).get(level)
                if isinstance(source,QAction):
                    shell.blockSignals(True); shell.setChecked(source.isChecked()); shell.blockSignals(False)
            for value,shell in self.line_spacing_actions.items():
                source=getattr(engine,"line_spacing_actions",{}).get(value)
                if isinstance(source,QAction):
                    shell.blockSignals(True); shell.setChecked(source.isChecked()); shell.blockSignals(False)
            for shell_name,engine_name in (("alignment_left_action","alignment_left_action"),("alignment_center_action","alignment_center_action"),("alignment_right_action","alignment_right_action"),("alignment_justify_action","alignment_justify_action")):
                shell=getattr(self,shell_name); source=getattr(engine,engine_name,None)
                if isinstance(source,QAction):
                    shell.blockSignals(True); shell.setChecked(source.isChecked()); shell.blockSignals(False)
        if hasattr(self,"shell_ribbon"):
            self.shell_ribbon.set_editor_enabled(enabled)
            if page is not None: self.shell_ribbon.sync_from_engine(page.engine)

    def _connect_signals(self) -> None:
        self.navigation.dashboard_requested.connect(
            self.editor_manager.show_dashboard
        )
        self.navigation.folder_requested.connect(self.editor_manager.open_folder)
        self.navigation.document_requested.connect(
            lambda path: self.editor_manager.open_document(path)
        )
        self.navigation.document_move_requested.connect(
            self.file_actions.move_document
        )
        self.navigation.external_files_import_requested.connect(
            self.file_actions.import_files
        )

        manager = self.editor_manager
        manager.dashboard_shown.connect(self.navigation.select_dashboard)
        manager.dashboard_shown.connect(self._sync_editor_actions)
        manager.dashboard_shown.connect(self._update_action_states)
        manager.current_folder_changed.connect(self.navigation.select_folder)
        manager.current_folder_changed.connect(self._sync_editor_actions)
        manager.current_folder_changed.connect(self._update_action_states)
        manager.current_document_changed.connect(
            lambda document: (
                self.navigation.select_document(document.path)
                if not document.external else False
            )
        )
        manager.current_document_changed.connect(
            self._remember_last_opened_document
        )
        manager.current_document_changed.connect(self._sync_editor_actions)
        manager.current_document_changed.connect(self._update_action_states)
        manager.external_editor_requested.connect(
            self.file_actions.open_external_editor
        )
        manager.containing_folder_requested.connect(
            self.file_actions.open_document_folder
        )
        manager.rename_requested.connect(self.file_actions.rename_document)
        manager.remove_requested.connect(self.file_actions.remove_document)
        manager.duplicate_requested.connect(
            self.file_actions.duplicate_document
        )
        manager.folder_open_external_requested.connect(
            self.file_actions.open_folder_external
        )
        manager.folder_rename_requested.connect(
            self.file_actions.rename_folder
        )
        manager.folder_remove_requested.connect(
            self.file_actions.remove_folder
        )
        manager.create_file_requested.connect(self.file_actions.create_file)
        manager.create_folder_requested.connect(self._create_folder)
        manager.external_files_import_requested.connect(
            self.file_actions.import_files
        )
        manager.editor_files_dropped.connect(self._handle_app_drop)
        manager.refresh_requested.connect(self._refresh_workspace)
        manager.sort_mode_changed.connect(self._remember_sort_mode)
        manager.view_mode_changed.connect(self._remember_view_mode)
        manager.view_mode_changed.connect(self._sync_view_actions)
        manager.editor_history_changed.connect(self._sync_editor_actions)
        manager.editor_formatting_changed.connect(self._sync_editor_actions)
        manager.editor_preferences_changed.connect(self._sync_editor_actions)
        manager.workspace_requested.connect(self._show_projects)
        manager.exit_requested.connect(self.close)
        manager.save_and_new_requested.connect(self._save_and_new)
        manager.save_and_dashboard_requested.connect(self._save_and_dashboard)
        manager.save_and_exit_requested.connect(self._save_and_exit)
        manager.document_path_rebound.connect(
            lambda _old, _new: self.watcher.request_rescan()
        )

        self.file_actions.folder_renamed.connect(self._on_folder_renamed)
        self.file_actions.folder_removed.connect(
            lambda _path: self.editor_manager.show_dashboard()
        )
        self.file_actions.document_created.connect(self._queue_created_open)
        self.file_actions.document_imported.connect(
            self._capture_imported_path
        )
        self.repository.document_added.connect(self._open_pending_if_ready)
        self.repository.document_path_changed.connect(
            self._remember_renamed_document_path
        )
        self.repository.dirty_count_changed.connect(self._update_dirty_status)

        for source in (manager, self.file_actions):
            source.status_message.connect(self.show_status)
        self.desktop_launcher.status_message.connect(self.show_status)
        self.desktop_launcher.launch_error.connect(
            lambda message: QMessageBox.warning(
                self, "Could Not Open", message
            )
        )
        self._connect_watcher(self.watcher)

    def _connect_watcher(self, watcher: FilesystemWatcher) -> None:
        watcher.scan_started.connect(self._on_scan_started)
        watcher.folders_discovered.connect(self.navigation.set_disk_folders)
        watcher.scan_details.connect(self._on_scan_details)
        watcher.scan_finished.connect(self._on_scan_finished)
        watcher.scan_failed.connect(self._on_scan_failed)

    def _current_page(self) -> EditorPage | None:
        page = self.stack.currentWidget()
        return page if isinstance(page, EditorPage) else None

    def _creation_folder(self) -> Path:
        if self.editor_manager.current_folder is not None:
            return self.editor_manager.current_folder
        document = self.editor_manager.current_document
        if document is not None and not document.external:
            return document.path.parent
        return self.library_root

    def _new_rtf_file(self, _checked=False) -> None:
        self.file_actions.create_file(self._creation_folder())

    def _new_folder(self, _checked=False) -> None:
        self._create_folder(self._creation_folder())

    def _new_window(self, _checked=False) -> None:
        """Open one independent Rico Plus window without changing this one."""
        if self.runtime_paths.running_as_appimage:
            executable = os.environ.get("APPIMAGE", "").strip()
            command = [executable] if executable else []
        elif self.runtime_paths.running_frozen:
            command = [sys.executable]
        else:
            command = [sys.executable, str(self.runtime_paths.launcher_root / "main.py")]
        if not command:
            QMessageBox.warning(self, "New Window Failed", "Rico Plus could not locate its launcher.")
            return
        try:
            subprocess.Popen(
                command,
                cwd=str(self.runtime_paths.launcher_root),
                start_new_session=True,
            )
        except OSError as error:
            QMessageBox.warning(
                self,
                "New Window Failed",
                f"Rico Plus could not open a new window:\n\n{error}",
            )

    def _create_folder(self, parent: str | Path) -> None:
        if self.file_actions.create_folder(parent) is not None:
            QTimer.singleShot(100, self.navigation.rebuild_from_repository)

    def _save_and_new(self, page: EditorPage) -> None:
        if page.save_to_disk():
            self.file_actions.create_file(
                page.document.path.parent
                if not page.document.external else self.library_root
            )

    def _save_and_dashboard(self, page: EditorPage) -> None:
        if page.save_to_disk():
            self.editor_manager.show_dashboard()

    def _save_and_exit(self, page: EditorPage) -> None:
        if page.save_to_disk():
            self.close()

    def _show_projects(self, _checked=False) -> None:
        dialog = ProjectsDialog(self.project_registry, self)
        if (
            dialog.exec() == QDialog.DialogCode.Accepted
            and dialog.selected_project_id
        ):
            self._switch_project(dialog.selected_project_id)
        self._rebuild_workspace_menu()

    def _rebuild_workspace_menu(self) -> None:
        self.workspace_menu.clear()
        self.workspace_menu.addAction(self.refresh_action)
        self.workspace_menu.addSeparator()
        self.workspace_action_group = QActionGroup(self.workspace_menu)
        self.workspace_action_group.setExclusive(True)
        active_id = self.project_registry.active_project_id
        for workspace in self.project_registry.projects:
            action = QAction(workspace.name, self.workspace_menu)
            action.setCheckable(True)
            action.setChecked(workspace.project_id == active_id)
            action.setData(workspace.project_id)
            action.setToolTip(str(workspace.folder))
            action.setStatusTip(str(workspace.folder))
            action.triggered.connect(
                lambda _checked=False, selected=workspace.project_id:
                    self._switch_project(selected)
            )
            self.workspace_action_group.addAction(action)
            self.workspace_menu.addAction(action)
        self.workspace_menu.addSeparator()
        self.workspace_menu.addAction(self.manage_workspaces_action)

    def _switch_project(self, project_id: str) -> bool:
        project = self.project_registry.get(project_id)
        if project is None:
            return False
        if project.project_id == self.project_registry.active_project_id:
            self.editor_manager.show_dashboard()
            return True
        if not project.folder.is_dir():
            QMessageBox.warning(
                self,
                "Workspace Folder Unavailable",
                "Relink this Workspace to an available folder before opening it.",
            )
            return False
        if not self.editor_manager.can_close_application():
            return False
        try:
            root = self.runtime_paths.ensure_writable_workspace(project.folder)
        except OSError as error:
            QMessageBox.warning(
                self, "Workspace Cannot Be Opened",
                f"Rico Plus could not use this Workspace folder:\n\n{error}",
            )
            return False
        self._save_active_project_state(save=True)
        if not self.watcher.stop(
            timeout_ms=2500, pump_events=QApplication.processEvents
        ):
            QMessageBox.warning(
                self,
                "Workspace Switch Cancelled",
                "The current Workspace scanner did not stop safely.",
            )
            return False

        previous = self.watcher
        self.library_root = root
        self._pending_open_path = None
        self._repair_navigation_after_scan = False
        self.editor_manager.switch_workspace_root(root)
        self.navigation.switch_workspace_root(root)
        self.repository.clear()
        self.project_registry.set_active(project.project_id)
        self.file_actions.switch_workspace_root(
            root,
            FilesystemWatcher(root, self.repository, parent=self),
        )
        self.watcher = self.file_actions.watcher
        self._connect_watcher(self.watcher)
        self._apply_active_project_state()
        self.watcher.start(initial_scan=True)
        previous.deleteLater()
        self.editor_manager.show_dashboard()
        self._update_window_title()
        return True

    def queue_open_path(self, path: str | Path) -> None:
        """Open a path without importing external OS-open documents."""
        target = Path(path).expanduser().resolve(strict=False)
        if not target.is_file() or target.suffix.casefold() not in RTF_EXTENSIONS:
            return
        try:
            target.relative_to(self.library_root)
        except ValueError:
            self._open_external_path(target)
            return
        self._startup_open_requested = True
        self._pending_open_path = target
        document = self.repository.get(target)
        if document is not None:
            self._open_pending_if_ready(document)
        elif not self._startup_scan_pending:
            self.watcher.request_rescan()

    def _open_external_path(self, path: Path) -> None:
        try:
            info = path.stat()
        except OSError:
            return
        document = self.repository.get(path)
        if document is None:
            document = self.repository.add(
                DocumentEntry(
                    path=path,
                    filename=path.name,
                    display_name=path.stem.replace("-", " ").replace("_", " ").title(),
                    folder=str(path.parent),
                    created=info.st_ctime,
                    modified=info.st_mtime,
                    size=info.st_size,
                    external=True,
                )
            )
        page = self.editor_manager.open_document(document)
        if page is None:
            self.repository.remove(path)

    def _queue_created_open(self, path: Path) -> None:
        self._startup_open_requested = True
        self._pending_open_path = Path(path).resolve(strict=False)
        document = self.repository.get(self._pending_open_path)
        if document is not None:
            self._open_pending_if_ready(document)

    def _open_pending_if_ready(self, document: DocumentEntry) -> None:
        if (
            self._pending_open_path is None
            or document.path != self._pending_open_path
        ):
            return
        self._pending_open_path = None
        self.editor_manager.open_document(document)

    def _handle_app_drop(
        self,
        supplied_paths,
        destination_folder=None,
    ) -> None:
        internal: list[Path] = []
        external: list[Path] = []
        for supplied in supplied_paths:
            path = Path(supplied).expanduser().resolve(strict=False)
            if (
                not path.is_file()
                or path.suffix.casefold() not in RTF_EXTENSIONS
            ):
                continue
            try:
                path.relative_to(self.library_root)
            except ValueError:
                external.append(path)
            else:
                internal.append(path)
        if external:
            self._drop_import_capture = []
            try:
                self.file_actions.import_files(
                    external, destination_folder or self._creation_folder()
                )
                internal.extend(self._drop_import_capture)
            finally:
                self._drop_import_capture = None
        if not internal:
            return
        mode = str(self.config.get("drop_open_mode", "active_window"))
        if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier:
            mode = "new_window" if mode == "active_window" else "active_window"
        if mode == "new_window":
            for path in internal:
                self._open_path_in_new_window(path)
            return
        self.queue_open_path(internal[0])
        for path in internal[1:]:
            self._open_path_in_new_window(path)

    def _capture_imported_path(self, path: Path) -> None:
        if self._drop_import_capture is not None:
            self._drop_import_capture.append(Path(path).resolve(strict=False))

    def _open_path_in_new_window(self, path: Path) -> bool:
        if self.runtime_paths.running_as_appimage:
            executable = os.environ.get("APPIMAGE", "").strip()
            command = [executable, "--open-file", str(path)] if executable else []
        elif self.runtime_paths.running_frozen:
            command = [sys.executable, "--open-file", str(path)]
        else:
            command = [
                sys.executable,
                str(self.runtime_paths.launcher_root / "main.py"),
                "--open-file",
                str(path),
            ]
        if not command:
            return False
        try:
            subprocess.Popen(
                command,
                cwd=str(self.runtime_paths.launcher_root),
                start_new_session=True,
            )
            return True
        except OSError as error:
            QMessageBox.warning(
                self,
                "Open in New Window Failed",
                f"Rico Plus could not open {path.name}:\n\n{error}",
            )
            return False

    def _canvas_is_light(self) -> bool:
        stored = self.config.get("editor_canvas_light")
        follows_app = bool(
            self.config.get("editor_canvas_follows_app_theme", True)
        )
        if not follows_app and isinstance(stored, bool):
            return stored
        base = QApplication.instance().palette().color(QPalette.ColorRole.Base)
        return base.lightness() >= 140

    def _toggle_editor_canvas_light(self, checked: bool) -> None:
        # Plus-family contract: checked means a dark editor. The editor follows
        # the application theme until this explicit toggle is used, then the
        # chosen canvas light/dark state persists independently.
        self.config.update({
            "editor_canvas_follows_app_theme": False,
            "editor_canvas_light": not bool(checked),
        }, save=True)
        self.editor_manager.apply_editor_preferences()

    def _set_theme(self, theme: str) -> None:
        if theme not in {"system", "dark", "light"}:
            return
        # The sibling Plus shell is authoritative here: the Plus shell changes the one
        # QApplication palette, then editor pages follow that effective palette
        # unless Dark Editor has been explicitly overridden.  Embedded Ricopad
        # engines must not re-theme QApplication themselves.
        self.config.set("app_theme", theme, save=True)
        apply_theme(QApplication.instance(), theme)
        for value, action in self.theme_actions.items():
            action.setChecked(value == theme)
        self._refresh_action_icons()
        if hasattr(self, "shell_ribbon"):
            self.shell_ribbon.refresh_theme()
        self.editor_manager.dashboard.refresh_theme()
        for folder_page in self.editor_manager._folder_pages.values():
            folder_page.refresh_theme()
        for _path, state in self.states:
            if isinstance(state.editor_page, EditorPage):
                state.editor_page.engine.appimage_theme = theme
                state.editor_page.engine.refresh_portable_icons()
                state.editor_page.apply_theme()

    def _set_icon_set(self, icon_set: str) -> None:
        if icon_set not in {"classic", "new"}:
            return
        self.config.set("editor_icon_set", icon_set, save=True)
        QApplication.instance().setProperty("rico_plus_icon_set", icon_set)
        for value, action in self.icon_actions.items():
            action.setChecked(value == icon_set)
        self._refresh_action_icons()
        self.editor_manager.dashboard.refresh_theme()
        for page in self.editor_manager._folder_pages.values():
            page.refresh_theme()
        for _path, state in self.states:
            if isinstance(state.editor_page, EditorPage):
                state.editor_page.engine.set_appimage_icon_set(icon_set)

    def _set_launch_screen(self, screen: str) -> None:
        if screen not in {"dashboard", "last_file"}:
            return
        self.config.set("app_launch_screen", screen, save=True)
        for value, action in self.launch_actions.items():
            action.setChecked(value == screen)

    def _set_drop_mode(self, mode: str) -> None:
        if mode not in {"active_window", "new_window"}:
            return
        self.config.set("drop_open_mode", mode, save=True)
        for value, action in self.drop_actions.items():
            action.setChecked(value == mode)

    def _toggle_sidebar(self, checked: bool) -> None:
        self.navigation.setVisible(bool(checked))

    def _toggle_status_bar(self, checked: bool) -> None:
        self.statusBar().setVisible(bool(checked))
        self.config.set("show_status_bar", bool(checked), save=True)

    def _toggle_fullscreen(self, checked: bool) -> None:
        self.showFullScreen() if checked else self.showNormal()

    def _sync_view_actions(self, mode: str) -> None:
        self.list_action.setChecked(mode == "list")
        self.grid_action.setChecked(mode == "grid")

    def _shortcut_catalog(self):
        """Group shortcut reference entries by the top-level AppMenu menu."""
        return {
            "File": [
                ("New RTF File", self.new_action),
                ("New Window", self.new_window_action),
                ("New Folder", self.new_folder_action),
                ("Show Dashboard", self.dashboard_action),
                ("Previous File", self.previous_file_action),
                ("Next File", self.next_file_action),
                ("Manage Workspaces", self.manage_workspaces_action),
                ("Save", self.save_action),
                ("Save As", self.save_as_action),
                ("Save and New", self.save_new_action),
                ("Save and Dashboard", self.save_dashboard_action),
                ("Save and Exit", self.save_exit_action),
                ("Properties", self.properties_action),
                ("Open in External Editor", self.external_editor_action),
                ("Rename", self.rename_file_action),
                ("Duplicate File", self.duplicate_action),
                ("Open Containing Folder", self.open_document_folder_action),
                ("Print", self.print_action),
                ("Export PDF", self.export_pdf_action),
                ("Exit", self.exit_action),
            ],
            "Edit": [
                ("Undo", self.undo_action),
                ("Redo", self.redo_action),
                ("Cut", self.cut_action),
                ("Copy", self.copy_action),
                ("Paste", self.paste_action),
                ("Paste Plain Text", self.paste_plain_action),
                ("Delete", self.delete_text_action),
                ("Duplicate Line / Selection", self.duplicate_line_action),
                ("Delete Line", self.delete_line_action),
                ("Select All", self.select_all_action),
                ("Find Bar", self.search_bar_action),
                ("Find and Replace", self.replace_action),
            ],
            "Format": [
                ("Font", self.font_dialog_action),
                ("Text Colour", self.text_colour_action),
                ("Highlight Colour", self.highlight_colour_action),
                ("Bold", self.bold_action),
                ("Italic", self.italic_action),
                ("Underline", self.underline_action),
                ("Strikethrough", self.strike_action),
                ("Superscript", self.superscript_action),
                ("Subscript", self.subscript_action),
                ("Bullet List", self.bullet_action),
                ("Indent", self.indent_action),
                ("Outdent", self.outdent_action),
                ("Paragraph", self.paragraph_action),
                ("Clear Formatting", self.clear_formatting_action),
            ],
            "Insert": [
                ("Insert Link", self.link_action),
                ("Horizontal Rule", self.rule_action),
                ("Image", self.image_action),
                ("Table", self.table_action),
                ("Date and Time", self.date_time_action),
                ("Date Only", self.date_action),
                ("Time Only", self.time_action),
                ("Symbol", self.symbol_action),
            ],
            "View": [
                ("Full Screen", self.fullscreen_action),
                ("Show Sidebar", self.sidebar_action),
                ("Show Status", self.status_bar_action),
                ("Word Wrap", self.word_wrap_action),
                ("Dark Editor", self.editor_canvas_theme_action),
                ("Lock Editor", self.view_only_action),
                ("Zoom In", self.zoom_in_action),
                ("Zoom Out", self.zoom_out_action),
                ("Zoom Reset", self.zoom_reset_action),
                ("Tab Width", self.tab_width_action),
                ("Next Ribbon Tab", self.next_ribbon_tab_action),
                ("Previous Ribbon Tab", self.previous_ribbon_tab_action),
            ],
            "Settings": [
                ("Toggle List/Grid View", self.toggle_dashboard_view_action),
            ],
            "Help": [
                ("Documentation", self.docs_action),
                ("Quick Tour", self.quick_start_action),
                ("Keyboard Shortcuts", self.shortcuts_action),
            ],
        }

    def _show_shortcuts(self, _checked=False) -> None:
        if self.shortcuts_dialog is not None:
            self.shortcuts_dialog.show()
            self.shortcuts_dialog.raise_()
            self.shortcuts_dialog.activateWindow()
            return
        dialog = ShortcutsDialog(self._shortcut_catalog(), self)
        dialog.finished.connect(
            lambda _result: setattr(self, "shortcuts_dialog", None)
        )
        self.shortcuts_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        dialog.search.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def _show_quick_tour(self) -> None:
        """Show the first-time Rico Plus tour in the established wizard UI."""
        if self.quick_tour_dialog is not None:
            self.quick_tour_dialog.show()
            self.quick_tour_dialog.raise_()
            self.quick_tour_dialog.activateWindow()
            return

        wizard = QWizard(self)
        wizard.setWindowTitle("Quick Tour — Rico Plus")
        wizard.setWindowIcon(self.windowIcon())
        wizard.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        wizard.setModal(False)
        wizard.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        wizard.setMinimumSize(700, 470)

        def add_page(title: str, subtitle: str, body: str, button=None) -> None:
            page = QWizardPage(wizard)
            page.setTitle(title)
            page.setSubTitle(subtitle)
            layout = QVBoxLayout(page)
            label = QLabel(body, page)
            label.setWordWrap(True)
            label.setTextFormat(Qt.TextFormat.RichText)
            layout.addWidget(label)
            if button is not None:
                layout.addWidget(button, 0, Qt.AlignmentFlag.AlignLeft)
            layout.addStretch(1)
            wizard.addPage(page)

        add_page(
            "Welcome to Rico Plus",
            "A workspace-scale Ricopad for ordinary Rich Text Format files.",
            "<p>The Ribbon has five tabs: <b>File, Home, Insert, Configure "
            "and Help</b>, with Home open by default.</p>"
            "<p>Hover a command for its name and shortcut. Use <b>Ctrl+Tab</b> "
            "and <b>Ctrl+Shift+Tab</b> to move between tabs. Double-click a "
            "tab title to collapse Ribbon controls; click a tab title to reveal "
            "them again.</p>",
        )
        add_page(
            "Workspaces and Dashboard",
            "Keep separate RTF collections without moving the application.",
            "<p><b>File → Workspace(s)</b> lists registered Workspaces and marks "
            "the active one. <b>Manage Workspaces…</b> adds an existing folder, "
            "renames its display label, relinks it, or removes only its "
            "registration.</p>"
            "<p>Only the active Workspace is scanned and watched. The Dashboard "
            "and sidebar are the navigation layer around Ricopad's RTF editor.</p>",
        )
        add_page(
            "Create, open and save",
            "Rico Plus edits standards-based RTF files directly.",
            "<p><b>File</b> contains New RTF File, New Folder, New Window, "
            "Save, Save As, Print, Export PDF and file-management commands. "
            "Save and New, Save and Dashboard and Save and Exit save first, "
            "then perform the named action.</p>"
            "<p>Use <b>Ctrl+Up</b> and <b>Ctrl+Down</b> for adjacent RTF files in "
            "the folder tree. Dragged RTF files follow the configured active-"
            "window/new-window behavior.</p>",
        )
        add_page(
            "Format rich text",
            "Ricopad remains the document-formatting engine.",
            "<p><b>Home</b> provides font face, size, paragraph style, emphasis, "
            "colours/highlights, bullets, indentation, alignment, paragraph "
            "settings and line spacing.</p>"
            "<p><b>Insert</b> contains tables, links, symbols, images, horizontal "
            "rules, dates and times. Character formatting operates on the "
            "selection, or on the current word when there is no selection.</p>",
        )
        add_page(
            "Find, protect and read",
            "Search quickly and prevent accidental edits when needed.",
            "<p><b>Ctrl+F</b> toggles Find. Use <b>F3</b> for the next result and "
            "<b>Shift+F3</b> for the previous result. Home also provides Find "
            "and Replace.</p>"
            "<p><b>Lock Editor</b> protects documents from accidental changes "
            "while navigation, copying and search remain available. The lock is "
            "a Rico Plus preference and persists as you move between files and "
            "sessions.</p>",
        )
        add_page(
            "Configure appearance",
            "Application and editor appearance stay related without being locked together.",
            "<p>The editor canvas follows the application <b>System, Dark or "
            "Light</b> theme by default. Using <b>Dark Editor</b> creates a "
            "persistent editor-only light/dark override, matching the sibling Plus "
            "behavior.</p>"
            "<p>Configure also contains Rico Icons Classic/New, zoom, sidebar and "
            "status controls, Word Wrap, Tab Width, New Document Defaults, "
            "Dashboard view, launch-screen and drag-and-drop choices.</p>",
        )
        shortcuts_button = QPushButton("Open Keyboard Shortcuts…", wizard)
        shortcuts_button.setAutoDefault(False)
        shortcuts_button.clicked.connect(self._show_shortcuts)
        add_page(
            "RTF interoperability and help",
            "Use Ricopad's established RTF workflow with Plus workspace management.",
            "<p>Rico Plus writes standards-based RTF intended to interoperate "
            "with other RTF applications. Lists use standard RTF list tables and "
            "overrides rather than private markers.</p>"
            "<p>Help contains the bundled documentation, this Tutorial Wizard, "
            "the live keyboard-shortcut inventory, GitHub, issue reporting and "
            "About.</p>",
            shortcuts_button,
        )

        def tour_finished(_result: int) -> None:
            self.quick_tour_dialog = None
            page = self._current_page()
            if page is not None:
                QTimer.singleShot(0, page.editor.setFocus)

        wizard.finished.connect(tour_finished)
        self.quick_tour_dialog = wizard
        wizard.show()
        wizard.raise_()
        wizard.activateWindow()

    def _open_documentation(self, _checked=False) -> None:
        page = self._current_page()
        if page is not None:
            page.engine.open_documentation()
            return
        path = self.package_root / "docs" / "README.md"
        if not self.desktop_launcher.open_path(path):
            QMessageBox.information(
                self, "Documentation", f"Documentation is available at:\n{path}"
            )

    def _show_about_dialog(self, _checked=False) -> None:
        if self.about_dialog is not None:
            self.about_dialog.show()
            self.about_dialog.raise_()
            self.about_dialog.activateWindow()
            return
        path = self.package_root / "assets" / "icons" / "ricopad-about.png"
        dialog = AboutDialog(
            path if path.is_file() else self.icon_path,
            self.runtime_paths.config_path,
            self,
            desktop_launcher=self.desktop_launcher,
        )
        dialog.finished.connect(
            lambda _result: setattr(self, "about_dialog", None)
        )
        self.about_dialog = dialog
        dialog.show()

    def _update_action_states(self, *_args) -> None:
        # Managed-workspace commands have one permanent owner. They must stay
        # available from the Dashboard, sidebar, folders, and active editor;
        # embedded Ribbon duplicates carry no shortcuts.
        self.new_action.setEnabled(True)
        self.manage_workspaces_action.setEnabled(True)
        self.dashboard_action.setEnabled(True)
        self.shortcuts_action.setEnabled(True)
        self._sync_editor_actions()
        self._update_window_title()

    def _update_window_title(self) -> None:
        workspace = self.project_registry.active_project.name.strip()
        document = self.editor_manager.current_document
        if document is not None:
            scope = "External" if document.external else workspace
            self.setWindowTitle(
                f"{document.filename} — {scope} — {APP_NAME}"
            )
        else:
            self.setWindowTitle(f"{workspace} — {APP_NAME}")

    def _remember_last_opened_document(
        self, document: DocumentEntry
    ) -> None:
        if document.external:
            return
        self.project_registry.update_state(
            self.project_registry.active_project_id,
            {"last_opened_file": str(document.path)},
        )

    def _remember_renamed_document_path(
        self, document: DocumentEntry, old_path: Path
    ) -> None:
        if document.external:
            return
        last = self.project_registry.active_project.state.get(
            "last_opened_file"
        )
        if last and Path(str(last)).resolve(strict=False) == old_path:
            self.project_registry.update_state(
                self.project_registry.active_project_id,
                {"last_opened_file": str(document.path)},
            )

    def _remember_sort_mode(self, mode: str) -> None:
        self.project_registry.update_state(
            self.project_registry.active_project_id,
            {"dashboard_sort": mode},
        )

    def _remember_view_mode(self, mode: str) -> None:
        self.project_registry.update_state(
            self.project_registry.active_project_id,
            {"dashboard_view": mode},
        )

    def _apply_active_project_state(self) -> None:
        state = self.project_registry.active_project.state
        self.navigation.restore_collapsed_folders(
            state.get("collapsed_folders", [])
            if isinstance(state.get("collapsed_folders", []), list)
            else []
        )
        self.editor_manager.set_sort_mode(
            str(state.get("dashboard_sort", "modified"))
        )
        self.editor_manager.set_search_text(
            str(state.get("dashboard_search", ""))
        )
        mode = str(state.get("dashboard_view", "list"))
        self.editor_manager.set_view_mode(mode)
        self._sync_view_actions(mode)

    def _save_active_project_state(self, *, save: bool) -> None:
        values = {
            "collapsed_folders": sorted(self.navigation.collapsed_folders()),
            "dashboard_sort": self.editor_manager.dashboard._sort_mode,
            "dashboard_search": self.editor_manager.dashboard.search_input.text(),
            "dashboard_view": self.editor_manager.dashboard.view_mode(),
            "last_opened_folder": (
                str(self.editor_manager.current_folder)
                if self.editor_manager.current_folder else None
            ),
        }
        document = self.editor_manager.current_document
        if document is not None and not document.external:
            values["last_opened_file"] = str(document.path)
        self.project_registry.update_state(
            self.project_registry.active_project_id, values, save=save
        )

    def _restore_window_state(self) -> None:
        self.resize(
            self.config.get_int("window_width", 1350, minimum=900),
            self.config.get_int("window_height", 850, minimum=600),
        )
        sizes = self.config.get_int_list(
            "splitter_sizes", [260, 1090], length=2
        )
        self._restored_sidebar_width = sizes[0] or 260
        QTimer.singleShot(0, self._restore_splitter_geometry)
        if bool(self.config.get("window_maximized", False)):
            self.showMaximized()

    def _restore_splitter_geometry(self) -> None:
        total = max(1, self.splitter.width() - self.splitter.handleWidth())
        maximum = max(SIDEBAR_MINIMUM_WIDTH, total - 420)
        sidebar = max(
            SIDEBAR_MINIMUM_WIDTH,
            min(int(self._restored_sidebar_width), maximum),
        )
        self.splitter.setSizes([sidebar, max(1, total - sidebar)])

    def _refresh_workspace(self, _checked=False) -> None:
        self._repair_navigation_after_scan = True
        self.watcher.request_rescan()

    def _on_scan_started(self) -> None:
        self.editor_manager.dashboard.set_loading(
            True, "Preparing your workspace…"
        )
        self.navigation.set_loading(True, "Building folder tree…")
        self.show_status("Scanning workspace in background…")

    def _on_scan_details(self, entries: int, seconds: float) -> None:
        detail = f"Scanned {entries:,} filesystem entries in {seconds:.1f}s."
        self.editor_manager.dashboard.set_loading_detail(detail)
        self.navigation.set_loading_detail(
            f"{sum(1 for document in self.repository if not document.external):,} RTF files found"
        )
        self.show_status(detail)

    def _on_scan_finished(self, count: int) -> None:
        self.editor_manager.dashboard.set_loading(False)
        self.navigation.set_loading(False)
        if self._repair_navigation_after_scan:
            self._repair_navigation_after_scan = False
            self.navigation.rebuild_from_repository()
        self.show_status(
            f"Loaded {count} RTF file(s) in "
            f"{self.project_registry.active_project.name}."
        )
        if self._pending_open_path is not None:
            document = self.repository.get(self._pending_open_path)
            if document is not None:
                self._open_pending_if_ready(document)
        if not self._startup_scan_pending:
            return
        self._startup_scan_pending = False
        if self._startup_open_requested:
            return
        if str(self.config.get("app_launch_screen", "dashboard")) == "last_file":
            last = self.project_registry.active_project.state.get(
                "last_opened_file"
            )
            document = self.repository.get(last) if last else None
            if document is not None:
                self.editor_manager.open_document(document)
                return
        self.editor_manager.show_dashboard()

    def _on_scan_failed(self, message: str) -> None:
        self.editor_manager.dashboard.set_loading(False)
        self.navigation.set_loading(False)
        self.show_status(f"Workspace scan failed: {message}")
        QMessageBox.warning(self, "Workspace Scan Failed", message)

    def _on_folder_renamed(
        self, _old_path: Path, new_path: Path
    ) -> None:
        QTimer.singleShot(
            400, lambda: self.editor_manager.open_folder(new_path)
        )

    def _update_dirty_status(self, count: int) -> None:
        if count:
            self.show_status(
                f"{count} RTF file{'s' if count != 1 else ''} "
                "have unsaved changes."
            )

    def show_status(self, message: str) -> None:
        self._status_label.setText(message)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        if any(
            url.isLocalFile()
            and Path(url.toLocalFile()).suffix.casefold() in RTF_EXTENSIONS
            for url in urls
        ):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [
            url.toLocalFile()
            for url in event.mimeData().urls()
            if url.isLocalFile()
            and Path(url.toLocalFile()).suffix.casefold() in RTF_EXTENSIONS
        ]
        if paths:
            self._handle_app_drop(paths, self._creation_folder())
            event.acceptProposedAction()
        else:
            event.ignore()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._closing:
            event.accept()
            return
        if not self.editor_manager.can_close_application():
            event.ignore()
            return
        self._closing = True
        self._save_active_project_state(save=True)
        self.config.update(
            {
                "window_width": self.width(),
                "window_height": self.height(),
                "window_maximized": self.isMaximized(),
                "splitter_sizes": self.splitter.sizes(),
            },
            save=True,
        )
        if not self.watcher.stop(
            timeout_ms=2500, pump_events=QApplication.processEvents
        ):
            self._closing = False
            QMessageBox.warning(
                self,
                "Close Delayed",
                "The workspace scanner is still stopping. Please try again.",
            )
            event.ignore()
            return
        event.accept()
