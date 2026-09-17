# Contributing to Rico Plus

Read `ARCHITECTURE.md`, `PROJECT_MEMORY.md`, and `QA.md` before changing code.

1. Keep changes focused and describe the user-visible outcome.
2. Preserve ordinary RTF files as the storage contract.
3. Keep workspace commands in the shell and document commands in the Ribbon.
4. Preserve canonical `DocumentEntry` and `DocumentState` objects across path
   changes where possible.
5. Treat unsaved content, external changes, symlinks, and replacement races
   conservatively.
6. Run `python -m rico_plus.tools.release_check` and the relevant manual QA.

Generated environments, caches, workspaces, build outputs, and local settings
do not belong in source releases. Contributions are GPL-3.0-or-later.
