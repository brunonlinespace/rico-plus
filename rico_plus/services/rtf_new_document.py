# Rico Plus
# Copyright (C) 2026 Bruno Machado
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure Ricopad-derived new-document defaults and RTF payload generation.

This module deliberately has no Qt dependency.  Rico Plus workspace file creation
asks this document-domain service for the initial RTF bytes; it never copies a
bundled template file.  The same payload builder is also used by the Ricopad
editor compatibility layer so both paths share one definition of a new document.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

MAX_CONFIG_FILE_SIZE = 1024 * 1024


@dataclass(frozen=True)
class NewDocumentDefaults:
    font_family: str = "Sans Serif"
    font_size: int = 12
    font_weight: str = "normal"
    font_slant: str = "roman"
    line_spacing: int = 115
    alignment: str = "left"


def _read_bounded_bytes(path: Path, limit: int = MAX_CONFIG_FILE_SIZE) -> bytes:
    with path.open("rb") as handle:
        payload = handle.read(int(limit) + 1)
    if len(payload) > int(limit):
        raise ValueError("The preferences file exceeds Rico Plus's safety limit.")
    return payload


def _preference_text(data: dict, key: str, default: str, *, limit: int) -> str:
    value = data.get(key, default)
    if not isinstance(value, str):
        return str(default)
    return value[:limit]


def load_new_document_defaults(config_directory: str | Path) -> NewDocumentDefaults:
    """Load only the Ricopad settings that define a brand-new document.

    Invalid/missing preferences intentionally fall back to Ricopad's built-in
    defaults.  A factory .rtf asset is never required.
    """
    defaults = NewDocumentDefaults()
    path = Path(config_directory).expanduser() / "editor.json"
    try:
        raw = _read_bounded_bytes(path)
        data = json.loads(raw.decode("utf-8", errors="strict"))
        if not isinstance(data, dict):
            raise ValueError("Preferences must contain a JSON object.")

        family = _preference_text(data, "font_family", defaults.font_family, limit=256)
        size = max(6, min(72, int(data.get("font_size", defaults.font_size))))
        weight = _preference_text(data, "font_weight", defaults.font_weight, limit=32)
        slant = _preference_text(data, "font_slant", defaults.font_slant, limit=32)
        spacing = max(
            50,
            min(400, int(data.get("new_document_line_spacing", defaults.line_spacing))),
        )
        alignment = _preference_text(
            data, "new_document_alignment", defaults.alignment, limit=16
        ).lower()
        if alignment not in ("left", "centre", "right", "justify"):
            alignment = defaults.alignment
        return NewDocumentDefaults(
            font_family=family,
            font_size=size,
            font_weight=weight,
            font_slant=slant,
            line_spacing=spacing,
            alignment=alignment,
        )
    except (OSError, UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError):
        return defaults


def build_new_document_rtf_payload(defaults: NewDocumentDefaults) -> bytes:
    """Build the interoperable blank RTF used by Ricopad new-document semantics."""
    family = (defaults.font_family or "Sans Serif").strip() or "Sans Serif"
    safe_family = (
        family.replace("\\", " ")
        .replace("{", " ")
        .replace("}", " ")
        .replace(";", " ")
        .strip()
        or "Sans Serif"
    )
    escaped: list[str] = []
    for char in safe_family:
        code = ord(char)
        if 32 <= code < 127:
            escaped.append(char)
        else:
            encoded = char.encode("utf-16-le", errors="replace")
            for offset in range(0, len(encoded), 2):
                unit = int.from_bytes(encoded[offset:offset + 2], "little")
                escaped.append(f"\\u{unit if unit < 32768 else unit - 65536}?")

    align = {
        "left": "\\ql",
        "centre": "\\qc",
        "right": "\\qr",
        "justify": "\\qj",
    }.get(defaults.alignment, "\\ql")
    spacing = max(50, min(400, int(defaults.line_spacing)))
    point_size = max(6, min(72, int(defaults.font_size)))
    char_controls = f"\\f0\\fs{point_size * 2}"
    if defaults.font_weight == "bold":
        char_controls += "\\b"
    if defaults.font_slant == "italic":
        char_controls += "\\i"

    # 240 twips is one proportional line in RTF; Ricopad stores percent.
    sl = round(spacing * 2.4)
    body = (
        "{\\rtf1\\ansi\\ansicpg1252\\deff0\\uc1"
        "{\\fonttbl{\\f0\\fnil " + "".join(escaped) + ";}}"
        "{\\colortbl ;}"
        + char_controls + "\\viewkind4\\widowctrl\n"
        "\\pard" + align + "\\li0\\ri0\\fi0\\sb0\\sa0"
        + f"\\sl{sl}\\slmult1"
        + "{\\plain" + char_controls + " }\\par\n}"
    )
    return body.encode("ascii", errors="strict")


def build_new_document_rtf_from_config(config_directory: str | Path) -> bytes:
    """Generate a blank RTF directly from current Ricopad new-document defaults."""
    return build_new_document_rtf_payload(load_new_document_defaults(config_directory))
