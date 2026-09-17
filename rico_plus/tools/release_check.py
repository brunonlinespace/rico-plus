#!/usr/bin/env python3
"""Authoritative Rico Plus source-release gate."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import re
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


PACKAGE = Path(__file__).resolve().parents[1]
SOURCE = PACKAGE.parent
VERSION = "0.0.2"


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    return struct.unpack(">II", data[16:24])


def source_files() -> set[str]:
    manifest = PACKAGE / "SOURCE_MANIFEST.sha256"
    selected: set[str] = set()
    for path in SOURCE.rglob("*"):
        if not path.is_file() or path == manifest:
            continue
        relative = path.relative_to(SOURCE)
        if "__pycache__" in relative.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        selected.add(relative.as_posix())
    return selected




def shell_ribbon_action_contract_errors() -> list[str]:
    """Ensure every action name referenced by ShellRibbon is supplied by MainWindow."""
    import ast as _ast
    import re as _re

    main_window = (PACKAGE / "widgets" / "main_window.py").read_text(encoding="utf-8")
    shell_ribbon = (PACKAGE / "widgets" / "shell_ribbon.py").read_text(encoding="utf-8")
    tree = _ast.parse(main_window)
    supplied: set[str] = set()
    for node in _ast.walk(tree):
        if isinstance(node, _ast.FunctionDef) and node.name == "_create_shell_ribbon":
            for child in _ast.walk(node):
                if (
                    isinstance(child, _ast.Assign)
                    and any(isinstance(target, _ast.Name) and target.id == "names" for target in child.targets)
                    and isinstance(child.value, _ast.Tuple)
                ):
                    supplied = {
                        element.value
                        for element in child.value.elts
                        if isinstance(element, _ast.Constant) and isinstance(element.value, str)
                    }
                    break
    referenced = set(_re.findall(r'"([a-z_]+_action)"', shell_ribbon))
    missing = sorted(referenced - supplied)
    return [f"ShellRibbon references actions not supplied by MainWindow: {missing}"] if missing else []


def assigned_constants(path: Path, names: set[str]) -> dict[str, str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    values: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Constant):
            continue
        if not isinstance(node.value.value, str):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in names:
                values[target.id] = node.value.value
    return values


def run_check(path: Path, errors: list[str], *, qt: bool = False) -> None:
    environment = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    if qt:
        environment.setdefault("QT_QPA_PLATFORM", "offscreen")
    completed = subprocess.run(
        [sys.executable, str(path)],
        cwd=SOURCE,
        env=environment,
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )
    if completed.stdout.strip():
        print(completed.stdout.strip())
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        errors.append(f"{path.relative_to(PACKAGE)} failed: {detail}")


def main() -> int:
    errors: list[str] = []

    root_entries = {
        path.name for path in SOURCE.iterdir() if path.name != "__pycache__"
    }
    if root_entries != {"main.py", "rico_plus"}:
        errors.append(f"Source root inventory changed: {sorted(root_entries)}")

    required = {
        "LICENSE",
        "rico-plus.json",
        "SOURCE_MANIFEST.sha256",
        "assets/icons/ricopad.png",
        "assets/icons/ricopad.ico",
        "assets/templates/default-document.rtf",
        "assets/styles/breeze-light.qss",
        "assets/styles/breeze-dark.qss",
        "docs/README.md",
        "docs/ARCHITECTURE.md",
        "docs/QA.md",
        "docs/RELEASE_NOTES.md",
        "packaging/appimage/rico-plus.desktop",
        "packaging/appimage/io.github.brunonlinespace.rico_plus.metainfo.xml",
        "packaging/pyinstaller/rico-plus.spec",
        "qa/qt-rtf-qa.py",
        "qa/workspace-integration-qa.py",
        "qa/rtf-corpus/list-format-boundary-spaces.rtf",
        "tools/release_check.py",
    }
    for relative in sorted(required):
        if not (PACKAGE / relative).is_file():
            errors.append(f"Missing required file: {relative}")

    forbidden_paths = {
        "widgets/code_editor.py",
        "widgets/markopad_preview.py",
        "widgets/markopad_source_editor.py",
        "qa/retro-ui-qa.py",
        "assets/ribbon-icons/light/layout-retro.png",
        "assets/ribbon-icons/dark/layout-retro.png",
        "assets/ribbon-icons-classic/light/layout-retro.png",
        "assets/ribbon-icons-classic/dark/layout-retro.png",
    }
    for relative in sorted(forbidden_paths):
        if (PACKAGE / relative).exists():
            errors.append(f"Retired file remains: {relative}")

    for path in sorted(SOURCE.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError, UnicodeError) as exc:
            errors.append(f"Python syntax: {path.relative_to(SOURCE)}: {exc}")

    expected_identity = {
        "APP_NAME": "Rico Plus",
        "APP_ID": "rico-plus",
        "APP_VERSION": VERSION,
        "PUBLISHER_ID": "brunonlinespace",
        "DESKTOP_ID": "io.github.brunonlinespace.rico_plus",
    }
    actual_identity = assigned_constants(PACKAGE / "__init__.py", set(expected_identity))
    if actual_identity != expected_identity:
        errors.append(f"Package identity mismatch: {actual_identity!r}")

    try:
        project = json.loads((PACKAGE / "rico-plus.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        project = {}
        errors.append(f"Invalid rico-plus.json: {exc}")
    expected_project = {
        "name": "Rico Plus",
        "id": "rico-plus",
        "version": VERSION,
        "publisher_id": "brunonlinespace",
        "desktop_id": "io.github.brunonlinespace.rico_plus",
        "repository": "https://github.com/brunonlinespace/rico-plus",
        "tagline": "Friendly. Fast. Focused.",
    }
    for key, value in expected_project.items():
        if project.get(key) != value:
            errors.append(f"Project identity mismatch: {key}={project.get(key)!r}")

    version_probe = subprocess.run(
        [sys.executable, str(SOURCE / "main.py"), "--version"],
        cwd=SOURCE,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    if version_probe.returncode or version_probe.stdout.strip() != f"Rico Plus {VERSION}":
        errors.append(
            "Version probe failed: "
            f"exit={version_probe.returncode}, output={version_probe.stdout.strip()!r}, "
            f"error={version_probe.stderr.strip()!r}"
        )

    core_paths = [
        PACKAGE / "app.py",
        PACKAGE / "app_constants.py",
        *sorted((PACKAGE / "controllers").glob("*.py")),
        *sorted((PACKAGE / "models").glob("*.py")),
        *sorted((PACKAGE / "services").glob("*.py")),
        *sorted((PACKAGE / "widgets").glob("*.py")),
    ]
    forbidden_text = {
        "markopad": "Markopad residue",
        "marko plus": "Marko Plus residue",
        "python lair": "Python Lair residue",
        "source + preview": "retired document layout",
        "source only": "retired document layout",
        "preview only": "retired document layout",
        "build_retro_toolbar": "Retro implementation",
        "layout-retro": "Retro asset reference",
    }
    for path in core_paths:
        text = path.read_text(encoding="utf-8").casefold()
        for fragment, label in forbidden_text.items():
            if fragment in text:
                errors.append(f"{label} in {path.relative_to(PACKAGE)}")

    app_source = (PACKAGE / "app.py").read_text(encoding="utf-8")
    main_source = (PACKAGE / "widgets/main_window.py").read_text(encoding="utf-8")
    editor_source = (PACKAGE / "widgets/rtf_editor.py").read_text(encoding="utf-8")
    shortcuts_source = (PACKAGE / "widgets/shortcuts_dialog.py").read_text(encoding="utf-8")
    ribbon_source = (PACKAGE / "widgets/shell_ribbon.py").read_text(encoding="utf-8")
    card_source = (PACKAGE / "widgets/dashboard_card.py").read_text(encoding="utf-8")
    file_source = (PACKAGE / "controllers/file_actions.py").read_text(encoding="utf-8")
    config_source = (PACKAGE / "services/config_service.py").read_text(encoding="utf-8")
    structural_fragments = {
        "app.py": (
            "def requested_open_paths(",
            'argument == "--open-file"',
            "window.queue_open_path(open_paths[0])",
            "app.setDesktopFileName(APP_RUNTIME_DESKTOP_ID)",
        ),
        "widgets/main_window.py": (
            '"Manage Workspaces…"',
            "QKeySequence.StandardKey.Open",
            "def _open_external_path(",
            "external=True",
            "ShellRibbon",
            "def _build_static_menus(",
            "def _sync_editor_actions(",
            '"App Icons"',
            "bar.setNativeMenuBar(True)",
            '"New Folder…", self._new_folder, "Ctrl+Shift+N"',
            'self.properties_action = self._action("Properties", lambda: self._engine_call("show_properties_dialog"), "F4")',
            'for a in (self.new_action,self.new_window_action,self.new_folder_action)',
            'misc=self.view_menu.addMenu("Editor Miscellaneous"); misc.addAction(self.tab_width_action); misc.addAction(self.default_font_action)',
            'self.file_menu.addAction(self.dashboard_action); self.file_menu.addAction(self.previous_file_action); self.file_menu.addAction(self.next_file_action)',
            'self.workspace_menu.addAction(self.refresh_action)',
            'more.addAction(self.external_editor_action); more.addSeparator()',
            'more.addSeparator(); more.addAction(self.open_document_folder_action); more.addAction(self.properties_action)',
            'self.view_menu.addAction(self.fullscreen_action); self.view_menu.addAction(self.sidebar_action); self.view_menu.addAction(self.status_bar_action); self.view_menu.addSeparator(); self.view_menu.addAction(self.word_wrap_action); self.view_menu.addAction(self.editor_canvas_theme_action); self.view_menu.addSeparator(); self.view_menu.addAction(self.view_only_action)',
            '"Toggle List/Grid View",',
            '"Ctrl+Alt+Shift+D",',
            'self.save_new_action = self._action("Save and New", lambda: self._save_and_new(self._current_page()) if self._current_page() else None, "Ctrl+Shift+S")',
            'self.duplicate_action = self._action("Duplicate File", self._duplicate_current, "Ctrl+Shift+D")',
            'self.duplicate_line_action=self._proxy("Duplicate Line / Selection","duplicate_line_action","Ctrl+D")',
            'self.view_only_action=self._action("Lock Editor", self._toggle_lock_editor_current, "F12", checkable=True)',
            'self.editor_canvas_theme_action=self._action(',
            '"Ctrl+Alt+Shift+E", checkable=True,',
            'def _canvas_is_light(self) -> bool:',
            '"editor_canvas_follows_app_theme": False,',
            'self.editor_manager.apply_editor_preferences()',
            'wizard.setWindowTitle("Quick Tour — Rico Plus")',
            'wizard.setWizardStyle(QWizard.WizardStyle.ModernStyle)',
            '"Welcome to Rico Plus"',
            '"RTF interoperability and help"',
            '"theme_dark_action":"theme-dark"',
            '"theme_light_action":"theme-light"',
            '"icon_classic_action":"icons-classic"',
            '"icon_new_action":"icons-new"',
            'self.shell_ribbon.refresh_theme()',
            'state.editor_page.engine.refresh_portable_icons()',
            '"File": [',
            '"Settings": [',
        ),
        "widgets/shell_ribbon.py": (
            'self._page("Configure")',
            'self._group(p, "View Control")',
            'self._group(p, "Editor Settings")',
            'self._group(p, "Theme Settings")',
            'self._group(p, "App Settings")',
            'action.shortcuts()',
            'def refresh_theme(self) -> None:',
            '("new_action", 1, 0)',
            '("new_folder_action", 1, 1)',
            '("new_window_action", 1, 2)',
            '("manage_workspaces_action", 0, 0)',
            '("save_dashboard_action", 0, 1)',
            '("save_exit_action", 0, 2)',
            '("dashboard_action", 1, 0)',
            '("save_new_action", 1, 1)',
            '("exit_action", 1, 2)',
            '("fullscreen_action", 0, 0)',
            '("sidebar_action", 0, 1)',
            '("status_bar_action", 0, 2)',
            '("search_bar_action", 0, 0)',
            '("tab_width_action", 0, 1)',
            '("default_font_action", 0, 2)',
            '("word_wrap_action", 1, 0)',
            '("editor_canvas_theme_action", 1, 1)',
            '("view_only_action", 1, 2)',
            '("theme_light_action", 0, 0)',
            '("icon_classic_action", 0, 1)',
            '("theme_dark_action", 1, 0)',
            '("icon_new_action", 1, 1)',
            '("grid_action", 0, 0)',
            '("launch_last_file_action", 0, 1)',
            '("drop_new_window_action", 0, 2)',
        ),
        "widgets/rtf_editor.py": (
            'page("File")',
            'page("Home")',
            'page("Insert")',
            'page("View")',
            'page("Help")',
            '"Save and New"',
            '"Save and Dashboard"',
            '"Save and Exit"',
            '"Lock Editor"',
            "save_as_target_validator",
            "class _EmbeddedMenuRegistry:",
            "self.app_menu_bar = _EmbeddedMenuRegistry()",
            'if self.appimage_theme_available and not self.embedded:',
            'self.managed_canvas_light_provider = None',
            'if self.embedded and callable(provider):',
            'editor.setStyleSheet("")',
            'self.visual_insert_actions.extend([self.insert_date_time_action,self.date_action,self.time_action,self.symbol_action',
        ),
        "widgets/shortcuts_dialog.py": (
            'QLabel("Menu:", self)',
            'self.category.addItems(["All", *catalog.keys()])',
            'for menu_name, entries in catalog.items()',
        ),
        "widgets/dashboard_card.py": (
            'self._button("Open"',
            '"View Only"',
        ),
        "controllers/file_actions.py": (
            '"default-document.rtf"',
            'payload.startswith(b"{\\\\rtf")',
            "install_new_file_from_temp(temporary, destination)",
            "fsync_directory(folder)",
        ),
    }
    source_map = {
        "app.py": app_source,
        "widgets/main_window.py": main_source,
        "widgets/shell_ribbon.py": ribbon_source,
        "widgets/rtf_editor.py": editor_source,
        "widgets/shortcuts_dialog.py": shortcuts_source,
        "widgets/dashboard_card.py": card_source,
        "controllers/file_actions.py": file_source,
    }
    for relative, fragments in structural_fragments.items():
        for fragment in fragments:
            if fragment not in source_map[relative]:
                errors.append(f"Missing implementation in {relative}: {fragment}")
    for retired_shell_fragment in (
        "_dashboard_ribbon_engine",
        "_mounted_ribbon_engine",
        "def _mount_ribbon(",
        "def _copy_menu_actions(",
        "def _rebuild_application_menu(",
        "setNativeMenuBar(False)",
    ):
        if retired_shell_fragment in main_source:
            errors.append(
                f"Retired editor-owned shell behavior remains: {retired_shell_fragment}"
            )
    for fragment in (
        'self.save_as_action = self.add_menu_action(menu, "Save As…", self.save_as_file, QKeySequence.StandardKey.SaveAs)',
        'self.duplicate_file_action = self.add_menu_action(self.more_actions_menu, "Duplicate File", self.duplicate_requested.emit, QKeySequence("Ctrl+Shift+D"))',
        'self.duplicate_line_action=self.add_menu_action(menu,"Duplicate Line / Selection",self.duplicate_current_line,QKeySequence("Ctrl+D"))',
    ):
        if fragment not in editor_source:
            errors.append(f"Rico Plus editor shortcut contract regression: {fragment}")
    if 'self.editor_canvas_theme_action=self.add_menu_action(menu,"Dark Editor",self.toggle_editor_canvas_light,QKeySequence("Ctrl+Alt+Shift+D"),checkable=True)' in editor_source:
        errors.append("Dark Editor still steals Ctrl+Alt+Shift+D from the dashboard view toggle")
    if 'QMenuBar(self)' in editor_source or 'setNativeMenuBar(False)' in editor_source:
        errors.append("Embedded Ricopad still creates a menu bar that can steal Plasma global-menu ownership")

    editor_page_source = (PACKAGE / "widgets/editor_page.py").read_text(encoding="utf-8")
    for fragment in (
        "self.engine.ribbon_tabs.hide()",
        "self.engine.app_menu_bar.hide()",
        "action.setShortcut(QKeySequence())",
        "self.title_label = QLabel(self)",
        'f"<h2>{display_name}{dirty}</h2>"',
        "escape(str(self.document.path))",
    ):
        if fragment not in editor_page_source:
            errors.append(f"Missing managed-editor shell isolation: {fragment}")

    for fragment in (
        'self.config.get("editor_canvas_follows_app_theme", True)',
        'self.config.get("editor_canvas_light")',
        'self.engine.managed_canvas_light_provider = self._canvas_is_light',
        'self.engine.editor_canvas_theme = (',
        'class _PersistentNativeFocusFrame(QWidget):',
        'QStyle.PrimitiveElement.PE_FrameFocusRect',
    ):
        if fragment not in editor_page_source:
            errors.append(f"Missing editor theme follow/override implementation: {fragment}")

    if "state.editor_page.engine.apply_appimage_theme(theme)" in main_source:
        errors.append("Embedded Ricopad still re-themes QApplication during Plus theme changes")
    if "self.engine.apply_appimage_theme(theme)" in editor_page_source:
        errors.append("EditorPage still lets an embedded Ricopad engine own application theming")
    if 'QTextEdit#visualEditor { border: 1px solid palette(highlight); }' in editor_source:
        errors.append("Invented hard-coded editor-border QSS remains instead of the native focus primitive")
    if "def _apply_editor_canvas_preference" in main_source:
        errors.append("Rico Plus still carries the divergent r8 editor-theme helper instead of the Marko Plus apply-editor-preferences contract")

    for removed in ("open_document_action", "Open RTF Document", "drop_open_mode"):
        if removed in editor_source:
            errors.append(f"Retired editor behavior remains: {removed}")
    for removed_key in ("source_font", "preview_font", "editor_layout", "python"):
        if f'"{removed_key}"' in config_source:
            errors.append(f"Retired config key remains: {removed_key}")

    manager_source = (PACKAGE / "controllers/editor_manager.py").read_text(encoding="utf-8")
    navigation_source = (PACKAGE / "widgets/navigation.py").read_text(encoding="utf-8")
    if '"lock_editor": False' not in config_source or 'def set_lock_editor(self, enabled: bool)' not in manager_source:
        errors.append("Persistent Lock Editor application state is missing")
    if '"editor_canvas_follows_app_theme": True' not in config_source or '"editor_canvas_light": None' not in config_source:
        errors.append("Marko-style editor theme follow/override config is missing")
    if "Rico Plus keeps RTF files in ordinary workspace folders." in main_source:
        errors.append("The first-time tutorial regressed to the r6 QMessageBox")
    if "My Nest" in navigation_source or "My Workspace" not in navigation_source:
        errors.append("Workspace sidebar label was not corrected to My Workspace")
    if 'misc.addAction(self.search_bar_action)' in main_source:
        errors.append("Find Bar is duplicated in View → Editor Miscellaneous")
    view_menu_line = 'self.view_menu.addAction(self.fullscreen_action); self.view_menu.addAction(self.sidebar_action); self.view_menu.addAction(self.status_bar_action); self.view_menu.addSeparator(); self.view_menu.addAction(self.word_wrap_action); self.view_menu.addAction(self.editor_canvas_theme_action); self.view_menu.addSeparator(); self.view_menu.addAction(self.view_only_action)'
    if view_menu_line not in main_source:
        errors.append("View menu order does not match the r6 contract")

    template = (PACKAGE / "assets/templates/default-document.rtf").read_bytes()
    if not template.startswith(b"{\\rtf") or not template.rstrip().endswith(b"}"):
        errors.append("Bundled default document is not a complete RTF payload")

    icon_sizes = {
        "ricopad-master.png": (1024, 1024),
        "ricopad.png": (512, 512),
        "ricopad-about.png": (256, 256),
        **{f"ricopad-{size}.png": (size, size) for size in (16, 32, 48, 64, 128, 256, 512)},
    }
    for name, expected in icon_sizes.items():
        path = PACKAGE / "assets/icons" / name
        try:
            actual = png_size(path)
        except (OSError, ValueError) as exc:
            errors.append(f"Invalid icon {name}: {exc}")
            continue
        if actual != expected:
            errors.append(f"Wrong icon size for {name}: {actual}, expected {expected}")

    desktop = (PACKAGE / "packaging/appimage/rico-plus.desktop").read_text(encoding="utf-8")
    for fragment in (
        "Name=Rico Plus",
        "Exec=rico-plus %F",
        "MimeType=application/rtf;text/rtf;application/x-rtf;",
        "Terminal=false",
        f"X-AppImage-Version={VERSION}",
    ):
        if fragment not in desktop:
            errors.append(f"Desktop entry missing: {fragment}")
    try:
        ET.parse(PACKAGE / "packaging/appimage/io.github.brunonlinespace.rico_plus.metainfo.xml")
    except (OSError, ET.ParseError) as exc:
        errors.append(f"Invalid AppStream XML: {exc}")

    for script in sorted((PACKAGE / "packaging").rglob("*.sh")):
        result = subprocess.run(
            ["bash", "-n", str(script)],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode:
            errors.append(f"Shell syntax: {script.relative_to(PACKAGE)}: {result.stderr.strip()}")

    manifest_path = PACKAGE / "SOURCE_MANIFEST.sha256"
    manifest: dict[str, str] = {}
    try:
        lines = manifest_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        lines = []
        errors.append(f"Could not read source manifest: {exc}")
    for line in lines:
        if not line.strip():
            continue
        match = re.fullmatch(r"([0-9a-f]{64})  \./(.+)", line)
        if not match:
            errors.append(f"Invalid manifest line: {line!r}")
            continue
        relative = Path(match.group(2))
        if relative.is_absolute() or ".." in relative.parts:
            errors.append(f"Unsafe manifest path: {relative}")
            continue
        manifest[relative.as_posix()] = match.group(1)
    expected_files = source_files()
    if set(manifest) != expected_files:
        errors.append(
            "Source manifest inventory mismatch: "
            f"missing={sorted(expected_files - set(manifest))[:5]}, "
            f"stale={sorted(set(manifest) - expected_files)[:5]}"
        )
    for relative, expected in manifest.items():
        path = SOURCE / relative
        if path.is_file() and digest(path) != expected:
            errors.append(f"Source manifest checksum mismatch: {relative}")

    secret_pattern = re.compile(
        r"(?i)(api[_-]?key|access[_-]?token|client[_-]?secret|private[_-]?key)"
        r"\s*[:=]\s*['\"][^'\"]+"
    )
    for path in sorted(SOURCE.rglob("*")):
        if not path.is_file() or path.suffix.casefold() in {".png", ".ico", ".zip"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        if secret_pattern.search(text):
            errors.append(f"Possible secret in {path.relative_to(SOURCE)}")

    for name in (
        "rtf-fidelity-qa.py",
        "security-qa.py",
        "check-ribbon-runtime-methods.py",
        "iconset-qa.py",
        "libreoffice-interop-qa.py",
    ):
        run_check(PACKAGE / "qa" / name, errors)

    if importlib.util.find_spec("PyQt6") is not None:
        run_check(PACKAGE / "qa/qt-rtf-qa.py", errors, qt=True)
        run_check(PACKAGE / "qa/workspace-integration-qa.py", errors, qt=True)
    else:
        print("SKIP: PyQt6 runtime suites (PyQt6 is not installed)")

    if errors:
        print("Rico Plus release check failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"PASS: Rico Plus {VERSION} source release gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
