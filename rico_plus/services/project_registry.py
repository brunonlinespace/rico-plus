# Rico Plus
# Copyright (C) 2026 Bruno Machado
# SPDX-License-Identifier: GPL-3.0-or-later
"""Registered project folders and their small per-project UI state."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from rico_plus.services.config_service import ConfigService


PROJECT_STATE_KEYS = frozenset(
    {
        "collapsed_folders",
        "dashboard_search",
        "dashboard_sort",
        "dashboard_view",
        "last_opened_folder",
        "last_opened_file",
    }
)


@dataclass(frozen=True, slots=True)
class ProjectRecord:
    project_id: str
    name: str
    folder: Path
    state: dict[str, object]


class ProjectRegistry:
    """Keep a lightweight folder registry without scanning inactive projects."""

    SCHEMA_VERSION = 1

    def __init__(self, config: ConfigService, initial_folder: str | Path) -> None:
        self.config = config
        self.initial_folder = self._normalise_folder(initial_folder)
        self._projects: list[ProjectRecord] = []
        self._active_project_id = ""
        self._load_and_migrate()

    @staticmethod
    def _normalise_folder(folder: str | Path) -> Path:
        return Path(folder).expanduser().resolve(strict=False)

    @staticmethod
    def _default_name(folder: Path) -> str:
        return folder.name.strip() or "Rico Plus Workspace"

    @staticmethod
    def _clean_state(value: object) -> dict[str, object]:
        if not isinstance(value, dict):
            return {}
        cleaned = {
            key: value[key] for key in PROJECT_STATE_KEYS if key in value
        }
        if "last_opened_file" not in cleaned and value.get("last_opened_script"):
            cleaned["last_opened_file"] = value["last_opened_script"]
        return cleaned

    def _load_and_migrate(self) -> None:
        seen_ids: set[str] = set()
        seen_folders: set[Path] = set()
        raw_projects = self.config.get("projects", [])
        if isinstance(raw_projects, list):
            for raw in raw_projects:
                if not isinstance(raw, dict):
                    continue
                raw_id = str(raw.get("id", "")).strip()
                raw_name = str(raw.get("name", "")).strip()
                raw_folder = str(raw.get("folder", "")).strip()
                if not raw_id or not raw_folder or raw_id in seen_ids:
                    continue
                folder = self._normalise_folder(raw_folder)
                if folder in seen_folders:
                    continue
                self._projects.append(
                    ProjectRecord(
                        raw_id,
                        raw_name or self._default_name(folder),
                        folder,
                        self._clean_state(raw.get("state")),
                    )
                )
                seen_ids.add(raw_id)
                seen_folders.add(folder)

        if not self._projects:
            legacy_state = {
                key: self.config.get(key)
                for key in PROJECT_STATE_KEYS
                if self.config.get(key) is not None
            }
            if (
                "last_opened_file" not in legacy_state
                and self.config.get("last_opened_script") is not None
            ):
                legacy_state["last_opened_file"] = self.config.get(
                    "last_opened_script"
                )
            first = ProjectRecord(
                uuid4().hex,
                self._default_name(self.initial_folder),
                self.initial_folder,
                self._clean_state(legacy_state),
            )
            self._projects.append(first)

        requested_active = str(self.config.get("active_project_id", "")).strip()
        self._active_project_id = (
            requested_active
            if any(project.project_id == requested_active for project in self._projects)
            else self._projects[0].project_id
        )
        self._save()

    def _serialise(self) -> list[dict[str, object]]:
        return [
            {
                "id": project.project_id,
                "name": project.name,
                "folder": str(project.folder),
                "state": dict(project.state),
            }
            for project in self._projects
        ]

    def _save(self) -> bool:
        active = self.active_project
        self.config.update(
            {
                "project_registry_version": self.SCHEMA_VERSION,
                "projects": self._serialise(),
                "active_project_id": self._active_project_id,
                # Keep the established setting mirrored for compatibility with
                # older source revisions and the first-run assistant.
                "workspace_path": str(active.folder),
            },
            save=True,
        )
        return True

    @property
    def projects(self) -> tuple[ProjectRecord, ...]:
        return tuple(self._projects)

    @property
    def active_project_id(self) -> str:
        return self._active_project_id

    @property
    def active_project(self) -> ProjectRecord:
        project = self.get(self._active_project_id)
        return project if project is not None else self._projects[0]

    def get(self, project_id: str) -> ProjectRecord | None:
        return next(
            (project for project in self._projects if project.project_id == project_id),
            None,
        )

    def find_folder(self, folder: str | Path) -> ProjectRecord | None:
        normalised = self._normalise_folder(folder)
        return next(
            (project for project in self._projects if project.folder == normalised),
            None,
        )

    def add_folder(self, folder: str | Path, name: str = "") -> ProjectRecord:
        normalised = self._normalise_folder(folder)
        existing = self.find_folder(normalised)
        if existing is not None:
            return existing
        project = ProjectRecord(
            uuid4().hex,
            name.strip() or self._default_name(normalised),
            normalised,
            {},
        )
        self._projects.append(project)
        self._save()
        return project

    def rename(self, project_id: str, name: str) -> bool:
        cleaned = name.strip()
        if not cleaned:
            return False
        for index, project in enumerate(self._projects):
            if project.project_id != project_id:
                continue
            self._projects[index] = ProjectRecord(
                project.project_id,
                cleaned,
                project.folder,
                dict(project.state),
            )
            self._save()
            return True
        return False

    def relink(self, project_id: str, folder: str | Path) -> bool:
        normalised = self._normalise_folder(folder)
        duplicate = self.find_folder(normalised)
        if duplicate is not None and duplicate.project_id != project_id:
            return False
        for index, project in enumerate(self._projects):
            if project.project_id != project_id:
                continue
            state = dict(project.state)
            for key in (
                "collapsed_folders",
                "last_opened_folder",
                "last_opened_file",
            ):
                state.pop(key, None)
            self._projects[index] = ProjectRecord(
                project.project_id,
                project.name,
                normalised,
                state,
            )
            self._save()
            return True
        return False

    def remove(self, project_id: str) -> bool:
        if len(self._projects) <= 1 or project_id == self._active_project_id:
            return False
        original = len(self._projects)
        self._projects = [
            project for project in self._projects
            if project.project_id != project_id
        ]
        if len(self._projects) == original:
            return False
        self._save()
        return True

    def set_active(self, project_id: str) -> bool:
        if self.get(project_id) is None:
            return False
        self._active_project_id = project_id
        self._save()
        return True

    def update_state(
        self,
        project_id: str,
        values: dict[str, object],
        *,
        save: bool = False,
    ) -> bool:
        updates = {key: value for key, value in values.items() if key in PROJECT_STATE_KEYS}
        for index, project in enumerate(self._projects):
            if project.project_id != project_id:
                continue
            state = dict(project.state)
            state.update(updates)
            self._projects[index] = ProjectRecord(
                project.project_id,
                project.name,
                project.folder,
                state,
            )
            if save:
                self._save()
            return True
        return False
        return False
