#!/usr/bin/env python3
"""Regression checks for Ricopad-style programmatic new-document creation."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from rico_plus.services.rtf_new_document import build_new_document_rtf_from_config


def require(value, message: str) -> None:
    if not value:
        raise AssertionError(message)


def valid_rtf(payload: bytes) -> bool:
    return payload.startswith(b"{\\rtf") and payload.rstrip().endswith(b"}")


with tempfile.TemporaryDirectory(prefix="rico-plus-new-document-qa-") as raw:
    config_dir = Path(raw)

    # No editor.json and no factory .rtf: creation must still work.
    default_payload = build_new_document_rtf_from_config(config_dir)
    require(valid_rtf(default_payload), "Missing preferences did not produce a valid blank RTF")
    require(b"\\fs24" in default_payload, "Default 12 pt font was not materialised")
    require(b"\\ql" in default_payload, "Default left alignment was not materialised")

    # Saved Ricopad New Document Defaults must define the generated workspace file.
    (config_dir / "editor.json").write_text(
        json.dumps(
            {
                "font_family": "Liberation Serif",
                "font_size": 18,
                "font_weight": "bold",
                "font_slant": "italic",
                "new_document_line_spacing": 150,
                "new_document_alignment": "centre",
            }
        ),
        encoding="utf-8",
    )
    custom_payload = build_new_document_rtf_from_config(config_dir)
    require(valid_rtf(custom_payload), "Saved defaults did not produce a valid blank RTF")
    require(b"Liberation Serif" in custom_payload, "Saved font family was not materialised")
    require(b"\\fs36" in custom_payload, "Saved 18 pt font size was not materialised")
    require(b"\\b" in custom_payload and b"\\i" in custom_payload, "Saved character defaults were not materialised")
    require(b"\\qc" in custom_payload, "Saved centre alignment was not materialised")
    require(b"\\sl360\\slmult1" in custom_payload, "Saved 150% line spacing was not materialised")

    # Corrupt settings must fall back to built-in Ricopad defaults, not an asset.
    (config_dir / "editor.json").write_bytes(b"{not-json")
    fallback_payload = build_new_document_rtf_from_config(config_dir)
    require(valid_rtf(fallback_payload), "Corrupt preferences prevented blank RTF creation")
    require(fallback_payload == default_payload, "Corrupt preferences did not use built-in defaults")

print("PASS: programmatic new-document factory")
