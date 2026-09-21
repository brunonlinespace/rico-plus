#!/usr/bin/env python3
"""Static exp8-r1 contract for proactive external-change safety."""
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
source = (PACKAGE / "widgets/editor_page.py").read_text(encoding="utf-8")

required = (
    "self.repository.document_changed.connect(",
    "self._on_repository_document_changed",
    "def _on_repository_document_changed(self, changed: DocumentEntry) -> None:",
    "loaded_signature = self._surface.file_disk_signature",
    "disk_signature = self._current_disk_signature()",
    "if disk_signature == loaded_signature:",
    "self.external_banner.show()",
    '"Discard Editor Changes"',
    "if self.is_modified:",
    'QPushButton("Save Version As…", self.external_banner)',
    "def _save_editor_version_as(self) -> bool:",
    'f"{source_path.stem} - Rico Version{suffix}"',
    "initial_path=str(suggested)",
    "forbidden_paths=(source_path,)",
    'dialog_title="Save Version As — Rico Plus"',
    "external disk copy preserved",
)
missing = [fragment for fragment in required if fragment not in source]
if missing:
    raise SystemExit("External-change contract missing: " + repr(missing))

# The warning is structurally independent of the optional file header.
build_start = source.index("    def _build_ui(self) -> None:")
build_end = source.index("    def _connect_signals(self) -> None:", build_start)
build = source[build_start:build_end]
if "root.addWidget(self.title_label)" not in build or "root.addWidget(self.external_banner)" not in build:
    raise SystemExit("External-change banner is not a separate EditorPage layout surface")
header_start = source.index("    def set_header_visible(self, visible: bool) -> None:")
header_end = source.index("    def set_status_visible", header_start)
header = source[header_start:header_end]
if "external_banner" in header:
    raise SystemExit("File-header visibility is incorrectly coupled to external-change warning")

# exp8-r1 must not retain the unsafe acknowledgement path that allowed a later
# ordinary Save to overwrite externally changed work without another warning.
for forbidden in ("Keep My Version", "def _keep_editor_version", "self._surface.file_disk_signature = disk_signature"):
    if forbidden in source:
        raise SystemExit(f"Unsafe external-change preservation path remains: {forbidden}")

rtf_source = (PACKAGE / "widgets/rtf_editor.py").read_text(encoding="utf-8")
for fragment in (
    "forbidden_paths=()",
    "if candidate in forbidden:",
    "forbidden_message or",
):
    if fragment not in rtf_source:
        raise SystemExit(f"Save Version As target protection missing: {fragment}")

print("PASS: Rico Plus proactive external-change contract")
