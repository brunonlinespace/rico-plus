#!/usr/bin/env python3
# Rico Plus
# SPDX-License-Identifier: GPL-3.0-or-later
"""Static verification of cancellable, responsive clean shutdown."""

from pathlib import Path


def main() -> int:
    package = Path(__file__).resolve().parents[1]
    scanner = (package / "services/document_scanner.py").read_text(encoding="utf-8")
    watcher = (package / "services/filesystem_watcher.py").read_text(encoding="utf-8")
    window = (package / "widgets/main_window.py").read_text(encoding="utf-8")

    required = (
        (scanner, "class ScanCancelled"),
        (scanner, "should_cancel"),
        (watcher, "thread.cancel()"),
        (watcher, "thread.wait(40)"),
        (watcher, "self._watcher.blockSignals(True)"),
        (window, "ClosingDialog"),
        (window, "RICO_PLUS_PROFILE_SHUTDOWN"),
        (window, "self.watcher.stop("),
        (window, "os._exit(0)"),
    )
    forbidden = (
        (watcher, "self._watcher.removePaths(watched)"),
    )

    missing = [fragment for source, fragment in required if fragment not in source]
    bad = [fragment for source, fragment in forbidden if fragment in source]
    if missing:
        raise SystemExit(f"Missing shutdown wiring: {missing}")
    if bad:
        raise SystemExit(f"Legacy shutdown wiring remains: {bad}")

    close_event = window[window.index("    def closeEvent("):]
    config_pos = close_event.index("self.config.update(")
    watcher_pos = close_event.index("self.watcher.stop(")
    exit_pos = close_event.index("os._exit(0)")
    if not (config_pos < watcher_pos < exit_pos):
        raise SystemExit("Fast exit occurs before clean-shutdown prerequisites.")

    print("Clean shutdown checks: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
