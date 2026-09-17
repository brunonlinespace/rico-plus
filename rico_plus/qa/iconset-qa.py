#!/usr/bin/env python3
"""Audit Rico Plus's complete Classic/New Ribbon icon families."""

from __future__ import annotations

import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FAMILIES = {
    "new": ROOT / "assets" / "ribbon-icons",
    "classic": ROOT / "assets" / "ribbon-icons-classic",
}
VARIANTS = ("light", "dark")
REQUIRED_CORE = {
    "about",
    "bold",
    "bullet-list",
    "copy",
    "cut",
    "documentation",
    "exit",
    "find",
    "new",
    "open-folder",
    "save",
    "save-as",
    "save-exit",
    "shortcuts",
    "view-only",
}


def png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError(f"Not a PNG: {path}")
    return struct.unpack(">II", data[16:24])


inventories: dict[tuple[str, str], set[str]] = {}
for family, base in FAMILIES.items():
    for variant in VARIANTS:
        pngs = {path.stem for path in (base / variant).glob("*.png")}
        svgs = {path.stem for path in (base / "svg" / variant).glob("*.svg")}
        assert pngs == svgs, (
            family,
            variant,
            "PNG/SVG mismatch",
            sorted(pngs - svgs),
            sorted(svgs - pngs),
        )
        assert REQUIRED_CORE <= pngs, (
            family,
            variant,
            "missing core icons",
            sorted(REQUIRED_CORE - pngs),
        )
        assert "layout-retro" not in pngs, "Retired Retro icon remains"
        assert len(pngs) >= 80, (family, variant, len(pngs))
        for name in pngs:
            assert png_dimensions(base / variant / f"{name}.png") == (64, 64), (
                family,
                variant,
                name,
            )
        inventories[(family, variant)] = pngs

reference = inventories[("new", "light")]
assert all(names == reference for names in inventories.values()), (
    "The four icon variants do not expose identical commands",
    {key: sorted(reference ^ names) for key, names in inventories.items()},
)

for variant in VARIANTS:
    changed = sum(
        (FAMILIES["new"] / variant / f"{name}.png").read_bytes()
        != (FAMILIES["classic"] / variant / f"{name}.png").read_bytes()
        for name in reference
    )
    assert changed >= 80, (variant, "families are not visually distinct", changed)

print(
    "PASS: Rico Plus dual icon families "
    f"({len(reference)} commands x light/dark x Classic/New)"
)
