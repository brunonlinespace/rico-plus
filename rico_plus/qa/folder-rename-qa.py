#!/usr/bin/env python3
"""Static exp8-r2 contract for F2 file/folder rename parity."""
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
main = (PACKAGE / "widgets/main_window.py").read_text(encoding="utf-8")
files = (PACKAGE / "controllers/file_actions.py").read_text(encoding="utf-8")

required_main = (
    'self.rename_file_action = self._command("Rename…", self._rename_current, "F2")',
    'document = self.editor_manager.current_document',
    'self.file_actions.rename_document(document)',
    'folder = self.editor_manager.current_folder',
    'folder is not None and folder != self.library_root',
    'self.file_actions.rename_folder(folder)',
    'self.rename_file_action.setEnabled(',
    'self.rename_file_action: "Rename File or Folder"',
)
for fragment in required_main:
    if fragment not in main:
        raise SystemExit(f"FAIL: missing F2 folder-rename contract: {fragment}")

required_files = (
    'def rename_folder(self, folder_path: str | Path) -> bool:',
    'folder = self._validated_folder(folder_path, allow_root=False)',
    'if not self.editor_manager.close_pages_in_folder(folder):',
    'folder.rename(destination)',
    'self._request_rescan()',
    'self.folder_renamed.emit(folder, destination)',
)
for fragment in required_files:
    if fragment not in files:
        raise SystemExit(f"FAIL: safe folder rename implementation missing: {fragment}")

print("PASS: F2 file/folder rename parity contract")
