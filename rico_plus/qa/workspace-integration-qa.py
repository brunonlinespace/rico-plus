#!/usr/bin/env python3
"""Offscreen integration checks for Rico Plus workspace/file behavior."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.dont_write_bytecode = True

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from PyQt6.QtCore import QEventLoop, QTimer, Qt
from PyQt6.QtGui import QFont, QTextCharFormat, QTextCursor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMainWindow

from rico_plus.app import requested_open_paths
from rico_plus.rtf_codec import decode_rtf
from rico_plus.services.config_service import ConfigService
from rico_plus.services.project_registry import ProjectRegistry
from rico_plus.services.runtime_paths import RuntimePaths
from rico_plus.services.rtf_new_document import build_new_document_rtf_from_config
from rico_plus.widgets.main_window import MainWindow
from rico_plus.widgets.shortcuts_dialog import (
    _shortcut_query_matches,
    _shortcut_tokens,
)


def require(value, message: str) -> None:
    if not value:
        raise AssertionError(message)


def wait(milliseconds: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


app = QApplication.instance() or QApplication(["rico-plus-workspace-qa"])

with tempfile.TemporaryDirectory(prefix="rico-plus-workspace-qa-") as raw_base:
    base = Path(raw_base).resolve()
    workspace = base / "workspace"
    outside = base / "outside"
    workspace.mkdir()
    outside.mkdir()
    config = ConfigService(base / "config.json")
    config.update(
        {
            "workspace_path": str(workspace),
            "setup_completed": True,
            "quick_tour_seen": True,
        },
        save=True,
    )
    registry = ProjectRegistry(config, workspace)
    runtime = RuntimePaths.detect(PROJECT / "main.py")
    window = MainWindow(
        workspace,
        config,
        registry,
        runtime,
        icon_path=runtime.icon_path,
    )
    window.show()
    wait(600)

    expected_app_menus = [
        "File", "Edit", "Format", "Insert", "View", "Settings", "Help"
    ]

    def app_menu_titles():
        return [
            action.text().replace("&", "")
            for action in window.menuBar().actions()
        ]

    require(
        app_menu_titles() == expected_app_menus,
        "Dashboard did not publish the complete stable application menu",
    )
    require(
        "Search" not in app_menu_titles(),
        "A stray top-level Search menu leaked into the application menu",
    )

    require(type(window.stack.currentWidget()).__name__ == "DashboardWidget", "startup did not show Dashboard")
    require(len(window.repository) == 0, "empty startup invented a document")
    require(not tuple(workspace.glob("*.rtf")), "empty startup wrote an RTF file")
    require(not window.repository.dirty, "empty startup is dirty")
    require(
        window.shell_ribbon.isVisible(),
        "Dashboard did not receive the shell-owned top Ribbon",
    )
    require(
        window.ribbon_host.y() == 0
        and window.splitter.y() >= window.ribbon_host.height(),
        "Workspace/sidebar is not underneath the Ribbon",
    )

    with patch(
        "rico_plus.controllers.file_actions.QInputDialog.getText",
        return_value=("Virgin.rtf", True),
    ):
        created = window.file_actions.create_file(workspace)
    require(created is not None and created.is_file(), "New RTF did not create a file")
    payload = created.read_bytes()
    require(len(payload) > 0 and payload.startswith(b"{\\rtf") and payload.rstrip().endswith(b"}"), "New RTF is not a complete RTF payload")
    decoded = decode_rtf(payload)
    require(not decoded.model["paragraphs"][0]["runs"], "Virgin template is not empty")
    wait(900)

    page = window._current_page()
    require(page is not None and page.document.path == created, "New RTF did not open")
    require(not page.is_modified and not window.repository.dirty, "Virgin RTF opened dirty")
    require(page.isVisible(), "Editor page is not visible")
    require(type(page._surface).__name__ == "RicopadEditorWidget", "Managed page did not use the extracted Ricopad editor widget")
    require(not isinstance(page._surface, QMainWindow), "Managed editor regressed to a nested QMainWindow")
    require(not page._surface.isWindow(), "Managed RTF editor surface became a top-level window")
    require(page._surface.minimumWidth() == 0, "Managed editor surface imposes a standalone minimum width")
    require(page.editor.minimumWidth() == 0, "Rich-text editor imposes a standalone minimum width")
    require(page._surface.isVisible(), "Managed RTF editor is not visible")
    require(page.editor.isVisible(), "RTF editor canvas is not visible")
    require(
        not hasattr(page._surface, "centralWidget")
        and not hasattr(page._surface, "menuWidget")
        and not hasattr(page._surface, "statusBar"),
        "Managed editor regressed to a QMainWindow compatibility API",
    )
    require(
        app_menu_titles() == expected_app_menus,
        "Opening a document swapped the application menu inventory",
    )
    require(
        window.save_action in window.file_menu.actions()
        and window.save_action is not page._surface.save_action,
        "Shell File menu does not own its stable Save command",
    )
    page.editor.setFocus()
    app.processEvents()
    require(
        app_menu_titles() == expected_app_menus,
        "Editor focus replaced the shell-owned application menu",
    )
    window.navigation.setFocus()
    app.processEvents()
    require(
        app_menu_titles() == expected_app_menus,
        "Sidebar focus replaced the shell-owned application menu",
    )
    # The managed editor must reflow to the actual Plus viewport rather than
    # retaining standalone Ricopad's 720 px minimum-window geometry.
    window.resize(560, 720)
    wait(100)
    require(
        page.editor.viewport().width() <= page.width(),
        "Word-wrap viewport is wider than the visible EditorPage",
    )
    require(window.shell_ribbon.isVisible(), "Shell Ribbon is not visible")
    require(
        not hasattr(page._surface, "ribbon_tabs"),
        "Managed editor constructed a hidden Ricopad Ribbon",
    )
    require(
        window.shell_ribbon.parent() is window.ribbon_host
        and window.shell_ribbon.x() == 0
        and window.shell_ribbon.width() == window.ribbon_host.width(),
        "Shell Ribbon does not span the complete workspace above the sidebar",
    )
    require(page._surface.visual_editor.isVisible(), "Document canvas is not visible")
    require(
        window.shell_ribbon.tabs.width() > 0
        and window.shell_ribbon.tabs.height() > window.shell_ribbon.tabs.tabBar().height(),
        "Shell Ribbon has no rendered command-page geometry",
    )
    require(
        page._surface.visual_editor.width() > 0
        and page._surface.visual_editor.height() > 0,
        "Document canvas has no visible rendered area",
    )
    rendered_editor = window.centralWidget().grab()
    require(
        not rendered_editor.isNull()
        and rendered_editor.width() == window.centralWidget().width()
        and rendered_editor.height() == window.centralWidget().height(),
        "Composed Ribbon/workspace/editor surface could not be rendered",
    )
    require(
        [window.shell_ribbon.tabs.tabText(index) for index in range(window.shell_ribbon.tabs.count())]
        == ["File", "Home", "Insert", "Configure", "Help"],
        "Shell Ribbon tab inventory changed",
    )
    require(
        not hasattr(page._surface, "toolbar_stack"),
        "Managed editor constructed a hidden legacy command bar",
    )
    require(window.manage_workspaces_action.shortcut().toString() == "Ctrl+O", "Ctrl+O is not workspace management")
    require(page._surface.workspace_action.shortcut().isEmpty(), "Embedded editor still owns Ctrl+O")
    require(window.manage_workspaces_action.isEnabled(), "Ctrl+O is disabled while editing")
    require(window.shortcuts_action.isEnabled(), "Fuzzy shortcut search is disabled while editing")
    require(window.duplicate_action.shortcut().toString() == "Ctrl+Shift+D", "Duplicate File does not use the Plus-family shortcut")
    require(window.duplicate_line_action.shortcut().toString() == "Ctrl+D", "Duplicate Line does not use the Plus-family shortcut")
    require(window.editor_canvas_theme_action.shortcut().toString() == "Ctrl+Alt+Shift+E", "Dark Editor conflicts with List/Grid")
    require(page._surface.duplicate_file_action.shortcut().isEmpty(), "Embedded editor still owns Duplicate File shortcut")
    require(page._surface.duplicate_line_action.shortcut().isEmpty(), "Embedded editor still owns Duplicate Line shortcut")
    require(window.toggle_dashboard_view_action.shortcut().toString() == "Ctrl+Alt+Shift+D", "List/Grid shortcut changed")
    require(window.refresh_action.shortcut().isEmpty(), "Refresh still conflicts with Ricopad F5")
    # Exercise the real event route, not QAction.trigger(): these bindings were
    # previously disabled while an editor was active.
    workspace_hits = []
    window.manage_workspaces_action.triggered.disconnect()
    window.manage_workspaces_action.triggered.connect(
        lambda: workspace_hits.append("workspace")
    )
    page.editor.setFocus()
    QTest.keyClick(
        page.editor,
        Qt.Key.Key_O,
        Qt.KeyboardModifier.ControlModifier,
    )
    app.processEvents()
    require(workspace_hits == ["workspace"], "Ctrl+O did not fire once while editing")

    shortcut_hits = []
    window.shortcuts_action.triggered.disconnect()
    window.shortcuts_action.triggered.connect(
        lambda: shortcut_hits.append("shortcuts")
    )
    QTest.keyClick(
        page.editor,
        Qt.Key.Key_Slash,
        Qt.KeyboardModifier.ControlModifier
        | Qt.KeyboardModifier.ShiftModifier,
    )
    app.processEvents()
    require(shortcut_hits == ["shortcuts"], "Fuzzy shortcut search key did not fire once while editing")

    dashboard_mode = window.editor_manager.dashboard.view_mode()
    QTest.keyClick(
        page.editor,
        Qt.Key.Key_D,
        Qt.KeyboardModifier.ControlModifier
        | Qt.KeyboardModifier.AltModifier
        | Qt.KeyboardModifier.ShiftModifier,
    )
    app.processEvents()
    require(
        window.editor_manager.dashboard.view_mode() != dashboard_mode,
        "Ctrl+Alt+Shift+D did not toggle List/Grid while editing",
    )
    original_canvas = page._surface.editor_canvas_theme
    QTest.keyClick(
        page.editor,
        Qt.Key.Key_E,
        Qt.KeyboardModifier.ControlModifier
        | Qt.KeyboardModifier.AltModifier
        | Qt.KeyboardModifier.ShiftModifier,
    )
    app.processEvents()
    require(
        page._surface.editor_canvas_theme != original_canvas,
        "Ctrl+Alt+Shift+E did not toggle Dark Editor",
    )
    require(
        [page._surface.save_action.text(), page._surface.save_new_action.text(), page._surface.save_dashboard_action.text(), page._surface.save_exit_action.text()]
        == ["Save", "Save and New", "Save and Dashboard", "Save and Exit"],
        "Save workflow inventory changed",
    )

    page.editor.setPlainText("alpha bold omega")
    cursor = page.editor.textCursor()
    cursor.setPosition(6)
    cursor.setPosition(10, QTextCursor.MoveMode.KeepAnchor)
    char_format = QTextCharFormat()
    char_format.setFontWeight(QFont.Weight.Bold)
    cursor.mergeCharFormat(char_format)
    require(page.save_to_disk(), "Formatted RTF did not save")
    app.processEvents()
    require(not page.document.dirty, "Saved document stayed edited in the sidebar repository")
    require("edited" not in window.navigation._document_label(page.document), "Saved sidebar label stayed edited")
    require(page.load_from_disk(), "Formatted RTF did not reopen")
    require(page.editor.toPlainText() == "alpha bold omega", "Formatting boundary spaces changed")
    require(
        page.editor.document().find("bold").charFormat().fontWeight()
        >= int(QFont.Weight.Bold),
        "Bold formatting did not survive reopen",
    )
    cursor = page.editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.insertText("!")
    app.processEvents()
    require(page.document.dirty, "A real edit did not mark the sidebar edited")
    window.save_action.trigger()
    app.processEvents()
    wait(20)
    require(not page.document.dirty, "Ribbon Save left the sidebar stuck on edited")
    require("edited" not in window.navigation._document_label(page.document), "Ribbon Save did not refresh the sidebar label")

    # exp8: external disk changes must reach the live page, and the warning
    # must not depend on the optional file header.  Emit the same repository
    # notification the watcher produces after updating scanner metadata.
    page.set_header_visible(False)
    original_disk = page.document.path.read_bytes()
    changed_disk = original_disk + b"\n"
    page.document.path.write_bytes(changed_disk)
    info = page.document.path.stat()
    page.document.modified = info.st_mtime
    page.document.size = info.st_size
    window.repository.document_changed.emit(page.document)
    app.processEvents()
    require(page.external_banner.isVisible(), "External-change warning did not appear")
    require(not page.title_label.isVisible(), "External-change test unexpectedly restored File Header")
    external_original = page.document.path
    preserved_version = workspace / "Externally Changed - Rico Version.rtf"

    # exp8-r1: the preservation branch must never be able to overwrite the
    # externally changed source path.  Cancelling/choosing that source leaves
    # the warning active and the external bytes untouched.
    with patch(
        "rico_plus.widgets.rtf_editor.QFileDialog.getSaveFileName",
        return_value=(str(external_original), "Rich Text Format (*.rtf)"),
    ), patch("rico_plus.widgets.rtf_editor.QMessageBox.warning"):
        require(
            not page._save_editor_version_as(),
            "Save Version As accepted the externally changed source path",
        )
    require(page.external_banner.isVisible(), "Rejected Save Version As dismissed warning")
    require(external_original.read_bytes() == changed_disk, "Rejected Save Version As changed external work")

    with patch(
        "rico_plus.widgets.rtf_editor.QFileDialog.getSaveFileName",
        return_value=(str(preserved_version), "Rich Text Format (*.rtf)"),
    ):
        require(page._save_editor_version_as(), "Save Version As failed")
    app.processEvents()
    require(not page.external_banner.isVisible(), "Save Version As did not dismiss external warning")
    require(external_original.read_bytes() == changed_disk, "Save Version As overwrote external work")
    require(preserved_version.is_file(), "Save Version As did not create the preserved Rico version")
    require(page.document.path == preserved_version, "Editor did not rebind to preserved Rico version")
    created = preserved_version
    page.set_header_visible(bool(config.get("show_file_header", True)))

    end_cursor = page.editor.textCursor()
    end_cursor.movePosition(QTextCursor.MoveOperation.End)
    page.editor.setTextCursor(end_cursor)
    window.editor_manager.show_dashboard()
    require(
        window.shell_ribbon.isVisible(),
        "Dashboard did not retain the shell-owned top Ribbon",
    )
    require(
        not hasattr(window, "_dashboard_ribbon_engine"),
        "A hidden Dashboard Ricopad command provider still exists",
    )
    require(
        app_menu_titles() == expected_app_menus,
        "Returning to Dashboard swapped the application menu inventory",
    )
    card = window.editor_manager.dashboard._list_cards[created]
    require(card.edit_button.text() == "Open" and card.view_only_button.text() == "View Only", "Dashboard actions changed")
    view_page = window.editor_manager.open_document(created, view_only=True)
    require(view_page is page and page.view_only and page.editor.isReadOnly(), "Locked Mode did not protect the editor")
    require(page.editor.textCursor().position() == 0, "Locked Mode did not open the document at the top")
    require(page.editor.verticalScrollBar().value() == page.editor.verticalScrollBar().minimum(), "Locked Mode viewport did not reset to the top")
    window._update_window_title()
    require(window.windowTitle().endswith(" — Locked Mode"), "Locked Mode warning is missing from the Plus window title")
    require(bool(config.get("lock_editor", False)), "Locked Mode state was not persisted")
    window.editor_manager.set_lock_editor(False)
    window._update_window_title()
    require(not window.windowTitle().endswith(" — Locked Mode"), "Locked Mode warning remained after unlocking")
    require(not page.view_only and not bool(config.get("lock_editor", False)), "Locked Mode did not clear application-wide")

    managed_copy = workspace / "Managed Copy.rtf"
    with patch(
        "rico_plus.widgets.rtf_editor.QFileDialog.getSaveFileName",
        return_value=(str(managed_copy), "Rich Text Format (*.rtf)"),
    ):
        require(page._surface.save_as_file(), "Managed Save As failed")
    require(page.document.path == managed_copy and not page.document.external, "Managed Save As did not rebind")
    require(created.exists(), "Managed Save As removed the source file")

    external = outside / "Outside.rtf"
    external.write_bytes(build_new_document_rtf_from_config(config.path.parent))
    window.queue_open_path(external)
    wait(300)
    external_document = window.repository.get(external)
    external_page = window._current_page()
    require(external_document is not None and external_document.external, "OS-open file is not transient external")
    require(external_page is not None and external_page.document is external_document, "External file did not open")
    require(external not in window.editor_manager.dashboard._list_cards, "External file leaked into Dashboard")
    require(not (workspace / external.name).exists(), "External OS-open file was copied")
    window.watcher.request_rescan()
    wait(600)
    require(window.repository.get(external) is external_document, "Workspace rescan discarded external session")

    imported = workspace / "Saved Into Workspace.rtf"
    with patch(
        "rico_plus.widgets.rtf_editor.QFileDialog.getSaveFileName",
        return_value=(str(imported), "Rich Text Format (*.rtf)"),
    ):
        require(external_page._surface.save_as_file(), "External-to-workspace Save As failed")
    require(window.repository.get(external) is None and external.exists(), "External source/session lifecycle is wrong")
    require(external_page.document.path == imported and not external_page.document.external, "External Save As did not become managed")

    parsed = requested_open_paths(
        ["--open-file", str(external), str(imported), str(external), "--setup"]
    )
    require(parsed == [external, imported], "Desktop positional/--open-file parsing changed")
    require(_shortcut_query_matches("shift ctrl s", _shortcut_tokens("Ctrl+Shift+S")), "Reordered shortcut search failed")
    require(_shortcut_query_matches("ctl s", _shortcut_tokens("Ctrl+S")), "Shortcut alias search failed")

    # Marko Plus r3's registered-Workspace menu is the quick selector. It
    # inventories every registered folder without scanning inactive roots.
    second_workspace = base / "second-workspace"
    second_workspace.mkdir()
    second = registry.add_folder(second_workspace, "Second Workspace")
    window._rebuild_workspace_menu()
    quick_actions = window.workspace_action_group.actions()
    require(
        [action.data() for action in quick_actions]
        == [project.project_id for project in registry.projects],
        "Workspace quick selector is not registry-backed",
    )
    require(
        sum(action.isChecked() for action in quick_actions) == 1
        and any(action.data() == second.project_id for action in quick_actions),
        "Workspace quick selector active/inactive state is wrong",
    )

    window.watcher.stop(
        timeout_ms=2500,
        pump_events=QApplication.processEvents,
    )
    window.close()
    app.processEvents()

print("PASS: Rico Plus workspace/create/open/view/save integration QA")
