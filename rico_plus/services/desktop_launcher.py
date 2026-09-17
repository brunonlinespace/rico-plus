# Rico Plus
# Copyright (C) 2026 Bruno Machado
# SPDX-License-Identifier: GPL-3.0-or-later
"""Open host files, folders, editors, and web links safely."""

from __future__ import annotations

import os
import shlex
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

from PyQt6.QtCore import QObject, QProcess, QProcessEnvironment, pyqtSignal

from rico_plus.services.runtime_paths import RuntimePaths


EDITOR_OVERRIDE_VARIABLE = "RICO_PLUS_EDITOR"

# AppImage/PyInstaller variables that must not leak into host applications.
# Bundled Qt and library paths can otherwise prevent the desktop opener or a
# host editor from starting.
_SANITIZED_VARIABLES = frozenset(
    {
        "APPDIR",
        "APPIMAGE",
        "ARGV0",
        "OWD",
        "LD_LIBRARY_PATH",
        "PYTHONHOME",
        "PYTHONPATH",
        "PYTHONEXECUTABLE",
        "QT_PLUGIN_PATH",
        "QT_QPA_PLATFORM_PLUGIN_PATH",
        "QML2_IMPORT_PATH",
        "QML_IMPORT_PATH",
    }
)


def _absolute_user_path(value: str | os.PathLike[str]) -> Path:
    """Return an absolute path without resolving the user's final symlink."""
    expanded = Path(value).expanduser()
    return Path(os.path.abspath(os.fspath(expanded)))


@dataclass(frozen=True, slots=True)
class _LaunchCommand:
    program: str
    arguments: tuple[str, ...] = ()
    working_directory: Path | None = None


class DesktopLauncher(QObject):
    """Launch host-side desktop applications from every packaging mode."""

    status_message = pyqtSignal(str)
    launch_error = pyqtSignal(str)

    def __init__(
        self,
        runtime_paths: RuntimePaths,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.runtime_paths = runtime_paths

    def _configure_process(
        self,
        process: QProcess,
        command: _LaunchCommand,
    ) -> None:
        process.setProgram(command.program)
        process.setArguments(list(command.arguments))
        if command.working_directory is not None:
            process.setWorkingDirectory(str(command.working_directory))
        process.setProcessEnvironment(self._process_environment())

    def _start_detached(self, command: _LaunchCommand) -> bool:
        process = QProcess(self)
        self._configure_process(process, command)
        try:
            try:
                result = process.startDetached()
            except TypeError:
                # Compatibility fallback for bindings exposing only the static
                # overload. The ordinary instance path remains authoritative.
                result = QProcess.startDetached(
                    command.program,
                    list(command.arguments),
                    (
                        str(command.working_directory)
                        if command.working_directory is not None
                        else ""
                    ),
                )
        finally:
            process.deleteLater()

        if isinstance(result, tuple):
            return bool(result[0])
        return bool(result)

    def _process_environment(self) -> QProcessEnvironment:
        environment = QProcessEnvironment.systemEnvironment()
        if (
            not self.runtime_paths.running_as_appimage
            and not self.runtime_paths.running_frozen
        ):
            return environment

        for name in _SANITIZED_VARIABLES:
            environment.remove(name)

        host_path = self._host_path()
        if host_path:
            environment.insert("PATH", host_path)

        for name in ("LD_LIBRARY_PATH", "PYTHONHOME", "PYTHONPATH"):
            original_name = f"APPIMAGE_ORIGINAL_{name}"
            original_value = os.environ.get(original_name)
            if original_value is not None:
                environment.insert(name, original_value)
            environment.remove(original_name)

        return environment

    def open_path(self, path: str | Path) -> bool:
        """Open a file or folder with the host desktop's default application."""
        target = _absolute_user_path(path)
        command = self._desktop_open_command(str(target))
        if command is None:
            return self._fail(
                "No host desktop opener was found (xdg-open or gio)."
            )
        if not self._start_detached(command):
            return self._fail(f"Could not open '{target}'.")
        return True

    def open_url(self, url: str) -> bool:
        """Open an HTTP(S) URL with the host browser."""
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return self._fail(f"Unsupported URL: {url}")
        command = self._desktop_open_command(url)
        if command is None:
            return self._fail(
                "No host desktop opener was found (xdg-open or gio)."
            )
        if not self._start_detached(command):
            return self._fail(f"Could not open '{url}'.")
        return True

    def open_in_external_editor(self, path: str | Path) -> bool:
        """Open a RTF document in a visible host graphical editor."""
        target = _absolute_user_path(path)
        if not target.is_file():
            return self._fail(f"The document does not exist: {target}")

        explicit_override = os.environ.get(
            EDITOR_OVERRIDE_VARIABLE,
            "",
        ).strip()
        if explicit_override:
            try:
                parts = shlex.split(explicit_override)
            except ValueError as error:
                return self._fail(
                    f"Invalid {EDITOR_OVERRIDE_VARIABLE} value: {error}"
                )
            if parts:
                resolved = self._resolve_executable(parts[0])
                if resolved:
                    command = _LaunchCommand(
                        resolved,
                        tuple(parts[1:] + [str(target)]),
                        target.parent,
                    )
                    if self._start_detached(command):
                        return True

        desktop_command = self._desktop_open_command(str(target))
        if desktop_command is not None and self._start_detached(desktop_command):
            return True

        candidates: tuple[tuple[str, tuple[str, ...]], ...] = (
            ("gnome-text-editor", (str(target),)),
            ("kate", (str(target),)),
            ("code", (str(target),)),
            ("codium", (str(target),)),
            ("gedit", (str(target),)),
            ("geany", (str(target),)),
            ("mousepad", (str(target),)),
            ("xed", (str(target),)),
            ("pluma", (str(target),)),
        )
        command = self._first_available_command(candidates, target.parent)
        if command is not None and self._start_detached(command):
            return True

        return self._fail(
            "No graphical editor or desktop file association could be started."
        )

    def _desktop_open_command(self, target: str) -> _LaunchCommand | None:
        xdg_open = self._resolve_executable("xdg-open")
        if xdg_open:
            return _LaunchCommand(xdg_open, (target,))

        gio = self._resolve_executable("gio")
        if gio:
            return _LaunchCommand(gio, ("open", target))

        return None

    def _first_available_command(
        self,
        candidates: Iterable[tuple[str, tuple[str, ...]]],
        working_directory: Path,
    ) -> _LaunchCommand | None:
        for executable, arguments in candidates:
            resolved = self._resolve_executable(executable)
            if resolved:
                return _LaunchCommand(
                    program=resolved,
                    arguments=arguments,
                    working_directory=working_directory,
                )
        return None

    def _resolve_executable(self, executable: str) -> str | None:
        path = Path(executable).expanduser()
        if path.is_absolute():
            return str(path) if path.is_file() and os.access(path, os.X_OK) else None
        return shutil.which(executable, path=self._host_path())

    def _host_path(self) -> str | None:
        """Return PATH without entries private to the bundled application."""
        original = os.environ.get("APPIMAGE_ORIGINAL_PATH")
        if original:
            return original

        current = os.environ.get("PATH")
        if not current or (
            not self.runtime_paths.running_as_appimage
            and not self.runtime_paths.running_frozen
        ):
            return current

        blocked_roots = {
            str(self.runtime_paths.launcher_root),
            str(self.runtime_paths.package_root),
        }
        appdir = os.environ.get("APPDIR")
        if appdir:
            blocked_roots.add(str(Path(appdir).resolve(strict=False)))
        frozen_root = getattr(sys, "_MEIPASS", None)
        if frozen_root:
            blocked_roots.add(str(Path(frozen_root).resolve(strict=False)))

        clean_entries: list[str] = []
        for entry in current.split(os.pathsep):
            if not entry:
                continue
            resolved = str(Path(entry).expanduser().resolve(strict=False))
            if any(
                resolved == base or resolved.startswith(base + os.sep)
                for base in blocked_roots
            ):
                continue
            clean_entries.append(entry)
        return os.pathsep.join(clean_entries)

    def _fail(self, message: str) -> bool:
        self.launch_error.emit(message)
        self.status_message.emit(message)
        return False
