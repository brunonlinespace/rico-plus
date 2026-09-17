#!/usr/bin/env python3
"""Bounded, non-executable Rich Text Format compatibility codec for Rico Plus."""
from __future__ import annotations
from dataclasses import dataclass
import base64, html, re
from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QUrl, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QImageReader, QPixmap, QTextBlockFormat, QTextCharFormat, QTextCursor, QTextDocument, QTextFormat, QTextImageFormat, QTextLength, QTextListFormat, QTextTableCellFormat, QTextTableFormat
from rico_plus.rich_text_support import is_safe_link_target

MAX_RTF_GROUP_DEPTH = 4096
MAX_RTF_PARAGRAPHS = 250_000
MAX_RTF_RUNS = 500_000
MAX_RTF_CAPTURE_CHARS = 16 * 1024
MAX_RTF_TABLE_CHARS = 2 * 1024 * 1024
MAX_RTF_TABLE_ENTRIES = 4096
MAX_RTF_TABLE_ROWS = 1000
MAX_RTF_TABLE_COLUMNS = 64
MAX_RTF_TABLE_CELLS = 20_000
MAX_RTF_CONTROL_NUMBER = 1_000_000_000
MAX_EMBEDDED_IMAGE_SIZE = 12 * 1024 * 1024
RTF_SYNTHETIC_STRUCTURE_BLOCK = QTextFormat.Property.UserProperty.value + 607
RTF_TABLE_CELLX_PROPERTY = QTextFormat.Property.UserProperty.value + 608
RTF_TABLE_LEFT_PROPERTY = QTextFormat.Property.UserProperty.value + 609
RTF_TABLE_GAP_PROPERTY = QTextFormat.Property.UserProperty.value + 610
RTF_TABLE_IMPORTED_PROPERTY = QTextFormat.Property.UserProperty.value + 611
RTF_TABLE_CELL_META_PROPERTY = QTextFormat.Property.UserProperty.value + 612
RTF_LIST_LEFT_PROPERTY = QTextFormat.Property.UserProperty.value + 613
RTF_LIST_FIRST_PROPERTY = QTextFormat.Property.UserProperty.value + 614
RTF_TABLE_AUTOFIT_PROPERTY = QTextFormat.Property.UserProperty.value + 615
RTF_AUTOMATIC_CONTRAST_PROPERTY = QTextFormat.Property.UserProperty.value + 616

QT_RICH_TEXT_DPI = 96.0
POINTS_PER_INCH = 72.0
TWIPS_PER_POINT = 20.0
TWIPS_PER_QT_PIXEL = TWIPS_PER_POINT * POINTS_PER_INCH / QT_RICH_TEXT_DPI  # 15

def _rtf_twips_to_qt_px(value):
    return float(value) / TWIPS_PER_QT_PIXEL

def _qt_px_to_rtf_twips(value):
    return int(round(float(value) * TWIPS_PER_QT_PIXEL))

# ---------- Native RTF compatibility codec ----------
# The uploaded PyWordpad snapshot has no explicit licence file. Ricopad therefore
# reimplements the useful document behaviour independently instead of copying its
# Win32/ctypes source. The codec deliberately handles the interoperable RTF subset
# used by classic WordPad-style documents and never executes embedded objects.


def _balanced_rtf_group(text, marker):
    start = text.find(marker)
    if start < 0:
        return ""
    depth = 0
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    return ""


def _rtf_bounded_decimal(value, maximum):
    """Parse an unsigned RTF decimal without constructing pathological integers."""
    digits = str(value).lstrip("0") or "0"
    maximum = max(0, int(maximum))
    maximum_digits = str(maximum)
    if len(digits) > len(maximum_digits):
        return maximum
    parsed = int(digits)
    return min(maximum, parsed)


def _rtf_top_level_child_groups(group):
    """Return bounded direct child RTF groups from one balanced parent group."""
    if not group:
        return []
    children = []
    depth = 0
    start = None
    escaped = False
    for index, char in enumerate(group):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "{":
            depth += 1
            if depth == 2:
                start = index
        elif char == "}":
            if depth == 2 and start is not None:
                children.append(group[start:index + 1])
                if len(children) >= MAX_RTF_TABLE_ENTRIES:
                    break
                start = None
            depth = max(0, depth - 1)
    return children


def _rtf_font_table(text):
    group = _balanced_rtf_group(text, "{\\fonttbl")
    fonts = {0: "Sans Serif"}
    if not group:
        return fonts
    group = group[:MAX_RTF_TABLE_CHARS]
    # Parse one direct font child at a time.  Producers such as LibreOffice put
    # an ignorable nested {\*\falt ...} group inside a font definition; a
    # flat regex stops at that nested brace and previously lost the primary
    # font name entirely.
    for count, child in enumerate(_rtf_top_level_child_groups(group)):
        if count >= MAX_RTF_TABLE_ENTRIES:
            break
        match = re.match(
            r"\{\\f(\d+)(?:\\[A-Za-z]+-?\d*\s?)*\s*([^;{}]+)",
            child,
        )
        if not match:
            continue
        index = _rtf_bounded_decimal(match.group(1), MAX_RTF_CONTROL_NUMBER)
        name = match.group(2).strip()
        if name:
            fonts[index] = name
    return fonts


def _rtf_colour_table(text):
    group = _balanced_rtf_group(text, "{\\colortbl")
    colours = [None]
    if not group:
        return colours
    body = group[len("{\\colortbl"): -1][:MAX_RTF_TABLE_CHARS]
    entries = body.split(";", MAX_RTF_TABLE_ENTRIES + 1)
    for entry in entries[1:MAX_RTF_TABLE_ENTRIES + 1]:
        red = re.search(r"\\red(\d+)", entry)
        green = re.search(r"\\green(\d+)", entry)
        blue = re.search(r"\\blue(\d+)", entry)
        if red and green and blue:
            colours.append(
                "#{:02x}{:02x}{:02x}".format(
                    _rtf_bounded_decimal(red.group(1), 255),
                    _rtf_bounded_decimal(green.group(1), 255),
                    _rtf_bounded_decimal(blue.group(1), 255),
                )
            )
        else:
            colours.append(None)
    return colours


def _rtf_list_definitions(text):
    """Return ``ls`` -> list metadata from the standard RTF list tables.

    Modern RTF stores list definitions in ``listtable`` and connects body
    paragraphs through ``listoverridetable``/the ``ls`` paragraph control. Parsing those tables
    keeps list semantics interoperable even when a producer omits the optional
    flat ``listtext`` marker used as a legacy display fallback.
    """
    list_group = (
        _balanced_rtf_group(text, "{\\*\\listtable")
        or _balanced_rtf_group(text, "{\\listtable")
    )
    override_group = (
        _balanced_rtf_group(text, "{\\*\\listoverridetable")
        or _balanced_rtf_group(text, "{\\listoverridetable")
    )
    list_types = {}
    if list_group:
        for child in _rtf_top_level_child_groups(list_group[:MAX_RTF_TABLE_CHARS]):
            ident = re.search(r"\\listid(-?\d+)", child)
            level = re.search(r"\\levelnfc(?:n)?(-?\d+)", child)
            if not ident:
                continue
            list_id = max(-MAX_RTF_CONTROL_NUMBER, min(MAX_RTF_CONTROL_NUMBER, int(ident.group(1))))
            nfc = int(level.group(1)) if level else 0
            # RTF 1.9.1 numbering format 23 is bullet.  Other formats are
            # represented as ordered in Ricopad's current two-style UI.
            list_types[list_id] = "unordered" if nfc == 23 else "ordered"
    by_ls = {}
    if override_group:
        for child in _rtf_top_level_child_groups(override_group[:MAX_RTF_TABLE_CHARS]):
            ident = re.search(r"\\listid(-?\d+)", child)
            ls = re.search(r"\\ls(\d+)", child)
            if not ident or not ls:
                continue
            list_id = max(-MAX_RTF_CONTROL_NUMBER, min(MAX_RTF_CONTROL_NUMBER, int(ident.group(1))))
            override_id = _rtf_bounded_decimal(ls.group(1), 2000)
            if override_id:
                by_ls[override_id] = {
                    "list_id": list_id,
                    "list_type": list_types.get(list_id, "ordered"),
                }
    return by_ls



def _rtf_style_delta(group):
    """Parse the portable formatting delta contained in one RTF style group.

    RTF styles are inheritance-based.  Ricopad only needs the subset that maps
    to QTextDocument formatting, but it must resolve that subset before body
    text is materialised; otherwise producers such as LibreOffice can appear to
    lose their Normal/Body Text font, size and paragraph geometry after a dirty
    save.
    """
    char = {}
    paragraph = {}
    based_on = None
    style_kind = None
    style_id = None
    for match in re.finditer(r"\\([A-Za-z]+)(-?\d+)?(?:\s)?", group):
        word = match.group(1)
        number = int(match.group(2)) if match.group(2) is not None else None
        if word in {"s", "cs"} and number is not None and style_id is None:
            style_kind = "character" if word == "cs" else "paragraph"
            style_id = max(0, min(MAX_RTF_CONTROL_NUMBER, number))
            continue
        if word == "sbasedon" and number is not None:
            based_on = max(0, min(MAX_RTF_CONTROL_NUMBER, number)); continue
        if word == "b": char["bold"] = number != 0
        elif word == "i": char["italic"] = number != 0
        elif word == "ul": char["underline"] = number != 0
        elif word == "ulnone": char["underline"] = False
        elif word == "strike": char["strike"] = number != 0
        elif word == "f" and number is not None: char["font"] = max(0, number)
        elif word == "fs" and number is not None: char["size"] = max(2, min(1024, number))
        elif word == "cf" and number is not None: char["foreground"] = max(0, number)
        elif word in {"highlight", "cb"} and number is not None: char["background"] = max(0, number)
        elif word == "super": char["superscript"] = 1
        elif word == "sub": char["superscript"] = -1
        elif word == "nosupersub": char["superscript"] = 0
        elif word == "ql": paragraph["alignment"] = "left"
        elif word == "qc": paragraph["alignment"] = "center"
        elif word == "qr": paragraph["alignment"] = "right"
        elif word == "qj": paragraph["alignment"] = "justify"
        elif word in {"li", "lin"} and number is not None: paragraph["left_indent"] = max(-1_000_000, min(1_000_000, number))
        elif word in {"ri", "rin"} and number is not None: paragraph["right_indent"] = max(-1_000_000, min(1_000_000, number))
        elif word == "fi" and number is not None: paragraph["first_indent"] = max(-1_000_000, min(1_000_000, number))
        elif word == "sb" and number is not None: paragraph["space_before"] = max(0, min(1_000_000, number))
        elif word == "sa" and number is not None: paragraph["space_after"] = max(0, min(1_000_000, number))
        elif word == "sl" and number is not None: paragraph["line_spacing"] = max(-1_000_000, min(1_000_000, number))
        elif word == "slmult" and number is not None: paragraph["line_mult"] = number
    if style_kind is None or style_id is None:
        return None
    return style_kind, style_id, based_on, char, paragraph


def _rtf_style_table(text):
    """Return resolved paragraph/character style formatting from ``stylesheet``."""
    group = _balanced_rtf_group(text, "{\\stylesheet")
    raw = {"paragraph": {}, "character": {}}
    if not group:
        return raw
    group = group[:MAX_RTF_TABLE_CHARS]
    for child in _rtf_top_level_child_groups(group):
        parsed = _rtf_style_delta(child)
        if parsed is None:
            continue
        kind, style_id, based_on, char, paragraph = parsed
        raw[kind][style_id] = {
            "based_on": based_on,
            "char": char,
            "paragraph": paragraph,
        }

    resolved = {"paragraph": {}, "character": {}}
    resolving = set()

    def resolve(kind, style_id):
        key = (kind, style_id)
        if style_id in resolved[kind]:
            return resolved[kind][style_id]
        if key in resolving:
            # Broken/cyclic foreign styles are ignored rather than recursing.
            return {"char": {}, "paragraph": {}}
        entry = raw[kind].get(style_id)
        if entry is None:
            return {"char": {}, "paragraph": {}}
        resolving.add(key)
        char = {}
        paragraph = {}
        based_on = entry.get("based_on")
        if based_on is not None and based_on != style_id:
            base = resolve(kind, based_on)
            char.update(base["char"])
            paragraph.update(base["paragraph"])
        char.update(entry["char"])
        paragraph.update(entry["paragraph"])
        resolving.discard(key)
        result = {"char": char, "paragraph": paragraph}
        resolved[kind][style_id] = result
        return result

    for kind in ("paragraph", "character"):
        for style_id in raw[kind]:
            resolve(kind, style_id)
    return resolved


def _rtf_choose_automatic_foreground_sentinel(colours):
    """Choose an internal RGB marker that cannot collide with an RTF colour.

    Qt's HTML importer materialises an implicit black foreground when HTML text
    has no explicit colour.  That is wrong for RTF colour index 0, which means
    "automatic/default foreground" and should continue to follow the editor
    palette.  Ricopad therefore marks automatic runs with a temporary RGB value
    that is guaranteed not to appear in the source colour table, then removes
    that foreground property immediately after QTextDocument import.
    """
    used = {str(value).lower() for value in colours if value}
    # A 25 MiB input cannot practically contain all 16,777,215 RGB values, so
    # the first unused value is bounded by the source size in real documents.
    for number in range(1, 0x1000000):
        candidate = f"#{number:06x}"
        if candidate not in used:
            return candidate
    raise ValueError("RTF colour table exhausted the RGB colour space.")


def _rtf_clear_automatic_foreground(document, sentinel):
    """Restore RTF automatic foreground runs to a palette-driven NoBrush.

    Explicit RTF colours, including an explicitly requested black, are left
    untouched.  Only Ricopad's collision-free temporary import marker is
    removed.
    """
    marker = QColor(sentinel)
    if not marker.isValid():
        return
    block = document.begin()
    cursor = QTextCursor(document)
    while block.isValid():
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment.isValid():
                char_format = fragment.charFormat()
                colour = _qt_brush_colour(char_format.foreground())
                if colour is not None and colour.rgb() == marker.rgb():
                    replacement = QTextCharFormat(char_format)
                    background = _qt_brush_colour(replacement.background())
                    if background is None:
                        replacement.clearProperty(QTextFormat.Property.ForegroundBrush)
                    else:
                        replacement.setForeground(_rtf_automatic_contrast_colour(background))
                        replacement.setProperty(RTF_AUTOMATIC_CONTRAST_PROPERTY, True)
                    cursor.setPosition(fragment.position())
                    cursor.setPosition(
                        fragment.position() + fragment.length(),
                        QTextCursor.MoveMode.KeepAnchor,
                    )
                    cursor.setCharFormat(replacement)
            iterator += 1
        block = block.next()


def _rtf_signed_unicode(value):
    value = int(value)
    if value < 0:
        value += 65536
    try:
        return chr(value)
    except ValueError:
        return "\ufffd"


def _new_rtf_state(parent=None, default_font=0, default_size=22):
    if parent is None:
        return {
            "bold": False,
            "italic": False,
            "underline": False,
            "strike": False,
            "font": int(default_font),
            "size": int(default_size),
            "foreground": 0,
            "background": 0,
            "alignment": "left",
            "left_indent": 0,
            "right_indent": 0,
            "first_indent": 0,
            "space_before": 0,
            "space_after": 0,
            "line_spacing": 0,
            "line_mult": 0,
            "list_id": None,
            "list_level": 0,
            "list_type": None,
            "superscript": 0,
            "hidden": False,
            "uc": 1,
            "codepage": 1252,
            "destination": None,
            "skip": False,
            "ignorable": False,
            "link": None,
            "pending_link": None,
            "capture": None,
            "pict": None,
            "in_table": False,
            "horizontal_rule": False,
            "after_list_marker": False,
        }
    clone = dict(parent)
    # Destination accumulators intentionally remain shared by nested groups.
    # Copying a growing RTF image/capture list at every brace can turn a small
    # malformed file into quadratic memory use. Formatting state itself remains
    # an independent shallow copy.
    return clone


def _safe_css_font_family(value):
    """Return a bounded CSS-safe font-family value from untrusted RTF data."""
    cleaned = "".join(
        character for character in str(value)
        if character.isalnum() or character in " .,_-'()"
    ).strip()
    return cleaned[:128] or "Sans Serif"


def _safe_qt_font_family(value):
    """Return a bounded literal family name safe for QFont/QTextCharFormat."""
    cleaned = "".join(
        character for character in str(value)
        if ord(character) >= 32 and character not in "{}\\"
    ).strip()
    return cleaned[:128] or "Sans Serif"


def _rtf_run_signature(state):
    return (
        state["bold"], state["italic"], state["underline"], state["strike"],
        state["font"], state["size"], state["foreground"], state["background"],
        state["superscript"], state.get("link"),
    )


def _rtf_paragraph_signature(state):
    return {
        "alignment": state["alignment"],
        "left_indent": state["left_indent"],
        "right_indent": state["right_indent"],
        "first_indent": state["first_indent"],
        "space_before": state["space_before"],
        "space_after": state["space_after"],
        "line_spacing": state["line_spacing"],
        "line_mult": state["line_mult"],
        "list_type": state.get("list_type"),
        "list_id": state.get("list_id"),
        "list_level": state.get("list_level", 0),
        "horizontal_rule": bool(state.get("horizontal_rule")),
    }


def rtf_to_html(payload, *, return_auto_foreground=False, return_model=False):
    """Convert a bounded, non-executable RTF subset to safe HTML.

    ``return_auto_foreground`` is an internal loader hook.  When true, the
    result is ``(html, sentinel_colour)`` so the QTextDocument importer can
    restore RTF colour index 0 to an automatic palette-driven foreground.
    """
    if isinstance(payload, bytes):
        text = payload.decode("latin-1", errors="replace")
    else:
        text = str(payload)
    if not text.lstrip().startswith("{\\rtf"):
        raise ValueError("The file does not begin with an RTF header.")

    fonts = _rtf_font_table(text)
    colours = _rtf_colour_table(text)
    list_definitions = _rtf_list_definitions(text)
    styles = _rtf_style_table(text)
    automatic_foreground = _rtf_choose_automatic_foreground_sentinel(colours)
    default_font_match = re.search(r"\\deff(\d+)", text)
    default_font_id = (
        _rtf_bounded_decimal(default_font_match.group(1), MAX_RTF_CONTROL_NUMBER)
        if default_font_match else 0
    )
    # Prefer the first body font-size declaration rather than imposing an
    # arbitrary 11 pt style on imported documents. Header destinations are
    # skipped before looking for a reasonable half-point value.
    body_probe = text
    for marker in ("{\\fonttbl", "{\\colortbl", "{\\stylesheet"):
        group = _balanced_rtf_group(body_probe, marker)
        if group:
            body_probe = body_probe.replace(group, "", 1)
    normal_style = styles.get("paragraph", {}).get(0, {})
    normal_char = normal_style.get("char", {})
    # Ricopad 0.7.1 writes its document character baseline in the root RTF
    # state before the first paragraph (for example ``\f0\fs28``).  Prefer
    # that explicit root state over guessing from the first body run: a
    # heading-first document must never turn Heading 1's 24 pt size into the
    # document default after save/reopen.  Foreign stylesheets still take
    # precedence because their Normal style is the producer's real baseline.
    first_par = body_probe.find("\\pard")
    preamble_probe = body_probe if first_par < 0 else body_probe[:first_par]
    root_size_match = re.search(r"\\fs(\d+)", preamble_probe)
    body_sizes = [
        max(2, _rtf_bounded_decimal(value, 288))
        for value in re.findall(r"\\fs(\d+)", body_probe)
    ]
    if normal_char.get("size"):
        default_half_points = int(normal_char["size"])
    elif root_size_match:
        default_half_points = max(2, _rtf_bounded_decimal(root_size_match.group(1), 288))
    elif body_sizes:
        # Legacy Ricopad files before 0.7.1 did not write a root character
        # baseline. Using the first body size made a heading-first document
        # adopt 24 pt as its default on reopen. The modal body size is a much
        # safer fallback and correctly recovers ordinary 14 pt text from those
        # files while remaining bounded for foreign RTF without styles.
        counts = {}
        first_seen = {}
        for position, value in enumerate(body_sizes):
            counts[value] = counts.get(value, 0) + 1
            first_seen.setdefault(value, position)
        default_half_points = max(counts, key=lambda value: (counts[value], -first_seen[value]))
    else:
        default_half_points = 22

    def fresh_state(parent=None):
        return _new_rtf_state(
            parent, default_font=default_font_id, default_size=default_half_points
        )

    def apply_style(style_kind, style_id):
        style = styles.get(style_kind, {}).get(int(style_id))
        if not style:
            return
        for key, value in style.get("char", {}).items():
            state[key] = value
        if style_kind == "paragraph":
            for key, value in style.get("paragraph", {}).items():
                state[key] = value
            ensure_paragraph_style()

    paragraphs = []
    current = {"style": _rtf_paragraph_signature(fresh_state()), "runs": []}
    state = fresh_state()
    stack = []
    fallback_to_skip = 0
    pending_high_surrogate = None
    index = 0
    paragraph_count = 0
    run_count = 0
    table_row_cells = None
    table_row_cellx = None
    table_row_cell_formats = None
    table_current_cell_format = None
    table_row_left = 0
    table_row_gap = None
    table_row_autofit = None
    table_row_count = 0
    table_cell_count = 0

    def ensure_paragraph_style():
        if not current["runs"]:
            current["style"] = _rtf_paragraph_signature(state)

    def append_text(value):
        nonlocal fallback_to_skip, pending_high_surrogate, run_count
        if not value or state.get("hidden") or state.get("skip"):
            return
        if state.get("destination") == "pict":
            pict = state.get("pict")
            if pict is not None and not pict.get("truncated"):
                chunk = "".join(
                    ch for ch in value if ch in "0123456789abcdefABCDEF"
                )
                remaining = MAX_EMBEDDED_IMAGE_SIZE * 2 - pict["hex_chars"]
                if len(chunk) > remaining:
                    pict["truncated"] = True
                    chunk = chunk[:max(0, remaining)]
                if chunk:
                    pict["hex"].append(chunk)
                    pict["hex_chars"] += len(chunk)
            return
        if state.get("after_list_marker") and state.get("destination") not in ("listtext",):
            # A marker destination is frequently followed by one source-level
            # separator space before the real character-format group.  That
            # byte is presentation glue, not list-item text. Older Ricopad
            # output emitted it and reopened it as a visible leading space.
            if value.startswith(" "):
                value = value[1:]
            state["after_list_marker"] = False
            if not value:
                return
        if fallback_to_skip:
            skip = min(fallback_to_skip, len(value))
            value = value[skip:]
            fallback_to_skip -= skip
            if not value:
                return
        if state.get("destination") in ("fldinst", "listtext"):
            capture = state.get("capture")
            if capture is not None:
                current_size = int(capture.get("chars", 0))
                remaining = MAX_RTF_CAPTURE_CHARS - current_size
                if remaining > 0:
                    piece = value[:remaining]
                    capture["parts"].append(piece)
                    capture["chars"] = current_size + len(piece)
            return
        normalised = []
        for value_char in value:
            codepoint = ord(value_char)
            if pending_high_surrogate is not None:
                if 0xDC00 <= codepoint <= 0xDFFF:
                    combined = 0x10000 + ((pending_high_surrogate - 0xD800) << 10) + (codepoint - 0xDC00)
                    normalised.append(chr(combined))
                    pending_high_surrogate = None
                    continue
                normalised.append("\ufffd")
                pending_high_surrogate = None
            if 0xD800 <= codepoint <= 0xDBFF:
                pending_high_surrogate = codepoint
            elif 0xDC00 <= codepoint <= 0xDFFF:
                normalised.append("\ufffd")
            else:
                normalised.append(value_char)
        value = "".join(normalised)
        if not value:
            return
        ensure_paragraph_style()
        signature = _rtf_run_signature(state)
        if current["runs"] and current["runs"][-1].get("signature") == signature:
            current["runs"][-1]["text"].append(value)
        else:
            run_count += 1
            if run_count > MAX_RTF_RUNS:
                raise ValueError("The RTF contains too many formatting runs.")
            current["runs"].append({
                "signature": signature,
                "text": [value],
                "image": None,
            })

    def append_image(pict):
        nonlocal run_count
        if pict.get("truncated"):
            return
        hex_data = "".join(pict.get("hex", []))
        if not hex_data or len(hex_data) // 2 > MAX_EMBEDDED_IMAGE_SIZE:
            return
        if len(hex_data) % 2:
            hex_data = hex_data[:-1]
        try:
            data = bytes.fromhex(hex_data)
        except ValueError:
            return
        mime = "image/png" if pict.get("kind") == "png" else "image/jpeg"
        encoded = base64.b64encode(data).decode("ascii")
        ensure_paragraph_style()
        run_count += 1
        if run_count > MAX_RTF_RUNS:
            raise ValueError("The RTF contains too many formatting runs.")
        current["runs"].append({
            "signature": None,
            "text": "",
            "image": {
                "src": f"data:{mime};base64,{encoded}",
                "kind": pict.get("kind", "png"),
                "intrinsic_width": max(0, int(pict.get("width", 0) or 0)),
                "intrinsic_height": max(0, int(pict.get("height", 0) or 0)),
                "width_goal": max(0, int(pict.get("width_goal", 0) or 0)),
                "height_goal": max(0, int(pict.get("height_goal", 0) or 0)),
                "width": min(16384.0, max(0.0, pict.get("width_goal", 0) / TWIPS_PER_QT_PIXEL)),
                "height": min(16384.0, max(0.0, pict.get("height_goal", 0) / TWIPS_PER_QT_PIXEL)),
            },
        })

    def end_paragraph(force=False):
        nonlocal current, paragraph_count
        if current["runs"] or force or not paragraphs:
            paragraph_count += 1
            if paragraph_count > MAX_RTF_PARAGRAPHS:
                raise ValueError("The RTF contains too many paragraphs.")
            paragraphs.append(current)
        current = {"style": _rtf_paragraph_signature(state), "runs": []}

    def end_table_cell(force=False):
        nonlocal current, table_row_cells, table_cell_count
        if table_row_cells is None:
            table_row_cells = []
        if current["runs"] or force:
            table_cell_count += 1
            if table_cell_count > MAX_RTF_TABLE_CELLS:
                raise ValueError("The RTF contains too many table cells.")
            if len(table_row_cells) >= MAX_RTF_TABLE_COLUMNS:
                raise ValueError("An RTF table row exceeds Ricopad's column safety limit.")
            table_row_cells.append(current)
        current = {"style": _rtf_paragraph_signature(state), "runs": []}

    def end_table_row(force=False):
        nonlocal table_row_cells, table_row_cellx, table_row_cell_formats, table_current_cell_format, table_row_left, table_row_gap, table_row_autofit, table_row_count, current
        if table_row_cells is None:
            if not force:
                return
            table_row_cells = []
        if current["runs"]:
            end_table_cell(True)
        if table_row_cells or force:
            table_row_count += 1
            if table_row_count > MAX_RTF_TABLE_ROWS:
                raise ValueError("The RTF contains too many table rows.")
            row = {"table_row": table_row_cells}
            if table_row_cellx:
                row["cellx"] = list(table_row_cellx[:MAX_RTF_TABLE_COLUMNS])
            row["trleft"] = int(table_row_left)
            if table_row_gap is not None:
                row["trgaph"] = int(table_row_gap)
            if table_row_autofit is not None:
                row["autofit"] = bool(table_row_autofit)
            if table_row_cell_formats:
                formats = list(table_row_cell_formats[:MAX_RTF_TABLE_COLUMNS])
                while len(formats) < len(table_row_cells):
                    formats.append({})
                row["cell_formats"] = formats
            paragraphs.append(row)
        table_row_cells = None
        table_row_cellx = None
        table_row_cell_formats = None
        table_current_cell_format = None
        table_row_left = 0
        table_row_gap = None
        table_row_autofit = None
        current = {"style": _rtf_paragraph_signature(state), "runs": []}

    destinations_to_skip = {
        "fonttbl", "colortbl", "stylesheet", "info", "header", "footer",
        "headerl", "headerr", "footerl", "footerr", "object", "objdata",
        "listtable", "listoverridetable", "xmlnstbl", "themedata", "datastore",
        "generator", "filetbl", "revtbl", "rsidtbl",
    }

    special_words = {
        "emdash": "—", "endash": "–", "emspace": "\u2003", "enspace": "\u2002",
        "qmspace": "\u2005", "bullet": "•", "lquote": "‘", "rquote": "’",
        "ldblquote": "“", "rdblquote": "”",
    }

    while index < len(text):
        char = text[index]
        if char == "{":
            if len(stack) >= MAX_RTF_GROUP_DEPTH:
                raise ValueError("The RTF nesting depth exceeds the safety limit.")
            if state.get("after_list_marker") and state.get("destination") not in ("listtext",):
                # No source-level separator preceded this child group.  The
                # child therefore starts real document content, and any
                # leading space inside it belongs to that formatting run.
                # Clear the parent before cloning so the marker state cannot
                # leak into this or every later sibling character group.
                state["after_list_marker"] = False
            stack.append(state)
            state = fresh_state(state)
            index += 1
            continue
        if char == "}":
            closing = state
            parent = stack.pop() if stack else fresh_state()
            destination = closing.get("destination")
            if destination == "pict" and parent.get("destination") != "pict":
                append_image(closing.get("pict") or {})
            elif destination == "fldinst" and closing.get("capture") is not None:
                instruction = "".join(closing["capture"]["parts"])
                match = re.search(r'HYPERLINK\s+"([^"]+)"', instruction, re.I)
                if match:
                    parent["pending_link"] = match.group(1)
            elif destination == "listtext" and closing.get("capture") is not None:
                marker = "".join(closing["capture"]["parts"]).strip()
                list_type = (
                    "ordered" if re.match(r"\d+[.)]?", marker) else "unordered"
                )
                # The list marker lives in its own destination group. Carry the
                # resulting paragraph property back to the parent state so the
                # first real text run cannot overwrite it.
                parent["list_type"] = list_type
                parent["after_list_marker"] = True
                current["style"]["list_type"] = list_type
            state = parent
            index += 1
            continue
        if char != "\\":
            next_control = index + 1
            while next_control < len(text) and text[next_control] not in "{}\\":
                next_control += 1
            # Physical CR/LF characters merely format the RTF source and do
            # not represent document line breaks. Real breaks use \par or
            # \line. Ignoring them prevents producer pretty-printing from
            # leaking unexplained whitespace into the opened document.
            literal = text[index:next_control].replace("\r", "").replace("\n", "").replace("\x00", "")
            append_text(literal)
            index = next_control
            continue

        index += 1
        if index >= len(text):
            break
        symbol = text[index]
        if symbol in "\\{}":
            append_text(symbol)
            index += 1
            continue
        if symbol == "~":
            append_text("\u00a0")
            index += 1
            continue
        if symbol == "_":
            append_text("\u2011")
            index += 1
            continue
        if symbol == "-":
            append_text("\u00ad")
            index += 1
            continue
        if symbol == "*":
            state["ignorable"] = True
            index += 1
            continue
        if symbol == "'" and index + 2 < len(text):
            raw = text[index + 1:index + 3]
            try:
                codepage = f"cp{state.get('codepage', 1252)}"
                decoded = bytes([int(raw, 16)]).decode(codepage, errors="replace")
            except (ValueError, LookupError):
                decoded = "\ufffd"
            append_text(decoded)
            index += 3
            continue
        if not symbol.isalpha():
            index += 1
            continue

        start = index
        while index < len(text) and text[index].isalpha():
            index += 1
        word = text[start:index]
        sign = 1
        if index < len(text) and text[index] == "-":
            sign = -1
            index += 1
        number_start = index
        while index < len(text) and text[index].isdigit():
            index += 1
        number = None
        if index > number_start:
            digits = text[number_start:index]
            if len(digits) > 10:
                number = sign * MAX_RTF_CONTROL_NUMBER
            else:
                number = sign * min(int(digits), MAX_RTF_CONTROL_NUMBER)
        if index < len(text) and text[index] == " ":
            index += 1

        if word in destinations_to_skip:
            state["destination"] = word
            state["skip"] = True
            continue
        if word == "pict":
            state["destination"] = "pict"
            state["skip"] = False
            state["pict"] = {
                "kind": "png", "hex": [], "hex_chars": 0, "truncated": False,
                "width": 0, "height": 0, "width_goal": 0, "height_goal": 0,
            }
            continue
        if word == "fldinst":
            state["destination"] = "fldinst"
            state["skip"] = False
            state["capture"] = {"parts": [], "chars": 0}
            continue
        if word == "fldrslt":
            state["destination"] = "fldrslt"
            state["skip"] = False
            state["link"] = state.get("pending_link")
            continue
        if word in ("listtext", "pntext"):
            state["destination"] = "listtext"
            state["skip"] = False
            state["capture"] = {"parts": [], "chars": 0}
            continue
        if state.get("ignorable") and word not in ("fldrslt",):
            state["skip"] = True
            continue
        if state.get("skip"):
            continue

        if word in special_words:
            append_text(special_words[word])
        elif word == "trowd":
            if table_row_cells is not None:
                end_table_row(False)
            table_row_cells = []
            table_row_cellx = []
            table_row_cell_formats = []
            table_current_cell_format = {
                "pad_left": None, "pad_right": None,
                "pad_top": None, "pad_bottom": None,
                "valign": None,
            }
            table_row_left = 0
            table_row_gap = None
            table_row_autofit = None
            state["in_table"] = True
        elif word == "intbl":
            state["in_table"] = True
        elif word == "cell":
            state["after_list_marker"] = False
            if state.get("in_table") or table_row_cells is not None:
                end_table_cell(True)
            else:
                append_text("\t")
        elif word == "row":
            state["after_list_marker"] = False
            if table_row_cells is not None:
                end_table_row(True)
            state["in_table"] = False
        elif word == "par":
            # An empty marker destination must not make the next paragraph's
            # first literal space look like marker-separator glue.
            state["after_list_marker"] = False
            if state.get("in_table") or table_row_cells is not None:
                append_text("\n")
            else:
                end_paragraph(True)
        elif word == "line":
            append_text("\n")
        elif word == "tab":
            append_text("\t")
        elif word == "u" and number is not None:
            append_text(_rtf_signed_unicode(number))
            fallback_to_skip = max(0, int(state.get("uc", 1)))
        elif word == "uc" and number is not None:
            state["uc"] = max(0, min(16, number))
        elif word == "ansicpg" and number is not None:
            state["codepage"] = max(1, number)
        elif word == "b":
            state["bold"] = number != 0
        elif word == "i":
            state["italic"] = number != 0
        elif word == "ul":
            state["underline"] = number != 0
        elif word == "ulnone":
            state["underline"] = False
        elif word == "strike":
            state["strike"] = number != 0
        elif word == "f" and number is not None:
            state["font"] = number
        elif word == "fs" and number is not None:
            state["size"] = max(2, min(1024, number))
        elif word == "cf" and number is not None:
            state["foreground"] = max(0, number)
        elif word in ("highlight", "cb") and number is not None:
            state["background"] = max(0, number)
        elif word == "super":
            state["superscript"] = 1
        elif word == "sub":
            state["superscript"] = -1
        elif word == "nosupersub":
            state["superscript"] = 0
        elif word == "v":
            state["hidden"] = number != 0
        elif word == "plain":
            for key, value in fresh_state().items():
                if key in {
                    "bold", "italic", "underline", "strike", "font", "size",
                    "foreground", "background", "superscript", "hidden", "link",
                }:
                    state[key] = value
        elif word == "pard":
            defaults = fresh_state()
            for key in {
                "alignment", "left_indent", "right_indent", "first_indent",
                "space_before", "space_after", "line_spacing", "line_mult",
                "list_id", "list_level", "list_type", "horizontal_rule",
            }:
                state[key] = defaults[key]
            ensure_paragraph_style()
        elif word == "brdrb":
            state["horizontal_rule"] = True
            current["style"]["horizontal_rule"] = True
        elif word == "s" and number is not None:
            apply_style("paragraph", number)
        elif word == "cs" and number is not None:
            apply_style("character", number)
        elif word == "cellx" and number is not None and table_row_cellx is not None:
            if len(table_row_cellx) < MAX_RTF_TABLE_COLUMNS:
                table_row_cellx.append(max(-1_000_000, min(1_000_000, number)))
                if table_row_cell_formats is not None:
                    table_row_cell_formats.append(dict(table_current_cell_format or {}))
                table_current_cell_format = {
                    "pad_left": None, "pad_right": None,
                    "pad_top": None, "pad_bottom": None,
                    "valign": None,
                }
        elif word in ("clpadl", "clpadr", "clpadt", "clpadb") and number is not None and table_current_cell_format is not None:
            key = {"clpadl":"pad_left", "clpadr":"pad_right", "clpadt":"pad_top", "clpadb":"pad_bottom"}[word]
            table_current_cell_format[key] = max(0, min(1_000_000, number))
        elif word in ("clvertalt", "clvertalc", "clvertalb") and table_current_cell_format is not None:
            table_current_cell_format["valign"] = {
                "clvertalt":"top", "clvertalc":"center", "clvertalb":"bottom"
            }[word]
        elif word == "trleft" and number is not None and table_row_cells is not None:
            table_row_left = max(-1_000_000, min(1_000_000, number))
        elif word == "trgaph" and number is not None and table_row_cells is not None:
            table_row_gap = max(0, min(1_000_000, number))
        elif word == "trautofit" and number is not None and table_row_cells is not None:
            table_row_autofit = bool(number)
        elif word in ("brdrs", "brdrw", "brsp"):
            pass
        elif word == "ql":
            state["alignment"] = "left"
        elif word == "qc":
            state["alignment"] = "center"
        elif word == "qr":
            state["alignment"] = "right"
        elif word == "qj":
            state["alignment"] = "justify"
        elif word in ("li", "lin") and number is not None:
            state["left_indent"] = max(-1_000_000, min(1_000_000, number))
        elif word in ("ri", "rin") and number is not None:
            state["right_indent"] = max(-1_000_000, min(1_000_000, number))
        elif word == "fi" and number is not None:
            state["first_indent"] = max(-1_000_000, min(1_000_000, number))
        elif word == "sb" and number is not None:
            state["space_before"] = max(0, min(1_000_000, number))
        elif word == "sa" and number is not None:
            state["space_after"] = max(0, min(1_000_000, number))
        elif word == "sl" and number is not None:
            state["line_spacing"] = max(-1_000_000, min(1_000_000, number))
        elif word == "slmult" and number is not None:
            state["line_mult"] = number
        elif word == "ls" and number is not None:
            state["list_id"] = number
            definition = list_definitions.get(number)
            if definition is not None:
                state["list_type"] = definition.get("list_type")
        elif word == "ilvl" and number is not None:
            state["list_level"] = max(0, number)
        elif word == "pnlvlblt":
            state["list_type"] = "unordered"
        elif word in ("pndec", "pnlvlbody"):
            state["list_type"] = "ordered"
        elif word == "pngblip" and state.get("pict") is not None:
            state["pict"]["kind"] = "png"
        elif word in ("jpegblip", "jpgblip") and state.get("pict") is not None:
            state["pict"]["kind"] = "jpeg"
        elif word == "picw" and number is not None and state.get("pict") is not None:
            state["pict"]["width"] = number
        elif word == "pich" and number is not None and state.get("pict") is not None:
            state["pict"]["height"] = number
        elif word == "picwgoal" and number is not None and state.get("pict") is not None:
            state["pict"]["width_goal"] = number
        elif word == "pichgoal" and number is not None and state.get("pict") is not None:
            state["pict"]["height_goal"] = number
        elif word == "bin" and number is not None:
            index = min(len(text), index + max(0, number))

    if pending_high_surrogate is not None:
        pending_high_surrogate = None
        append_text("\ufffd")
    if table_row_cells is not None:
        end_table_row(bool(table_row_cells or current["runs"]))
    if current["runs"] or not paragraphs:
        end_paragraph(False)

    def colour_at(index_value):
        return colours[index_value] if 0 <= index_value < len(colours) else None

    def render_runs(paragraph):
        rendered = []
        for run in paragraph["runs"]:
            image = run.get("image")
            if image:
                dimensions = []
                if image.get("width"):
                    dimensions.append(f'width="{max(1, round(image["width"]))}"')
                if image.get("height"):
                    dimensions.append(f'height="{max(1, round(image["height"]))}"')
                rendered.append(
                    f'<img src="{html.escape(image["src"], quote=True)}" '
                    + " ".join(dimensions) + ">"
                )
                continue
            signature = run["signature"]
            bold, italic, underline, strike, font_id, half_points, fg_id, bg_id, superscript, link = signature
            styles = []
            family = fonts.get(font_id)
            if family:
                styles.append(f"font-family:{html.escape(_safe_css_font_family(family), quote=True)}")
            styles.append(f"font-size:{max(1.0, half_points / 2.0):g}pt")
            if bold:
                styles.append("font-weight:700")
            if italic:
                styles.append("font-style:italic")
            decorations = []
            if underline:
                decorations.append("underline")
            if strike:
                decorations.append("line-through")
            if decorations:
                styles.append("text-decoration:" + " ".join(decorations))
            foreground = colour_at(fg_id)
            background = colour_at(bg_id)
            if foreground:
                styles.append(f"color:{foreground}")
            else:
                # RTF colour index 0 is automatic, not black.  Qt's HTML
                # importer otherwise turns the missing colour into explicit
                # black, which becomes unreadable on Ricopad's dark canvas.
                styles.append(f"color:{automatic_foreground}")
            if background:
                styles.append(f"background-color:{background}")
            if superscript > 0:
                styles.append("vertical-align:super")
            elif superscript < 0:
                styles.append("vertical-align:sub")
            value = html.escape("".join(run["text"])).replace("\n", "<br>").replace("\t", "&emsp;")
            span = f'<span style="{";".join(styles)}">{value}</span>'
            if link and is_safe_link_target(link):
                span = f'<a href="{html.escape(link, quote=True)}">{span}</a>'
            rendered.append(span)
        return "".join(rendered) or "<br>"

    default_family = html.escape(
        _safe_css_font_family(fonts.get(default_font_id, "Sans Serif")), quote=True
    )
    default_points = max(1.0, default_half_points / 2.0)
    output = [
        "<!doctype html><html><head><meta charset=\"utf-8\"></head>"
        f"<body style=\"font-family:{default_family};font-size:{default_points:g}pt;\">"
    ]
    active_list = None
    table_open = False
    previous_was_rule = False
    for paragraph in paragraphs:
        if "table_row" in paragraph:
            previous_was_rule = False
            if active_list:
                output.append(f"</{active_list}>")
                active_list = None
            if not table_open:
                output.append('<table border="1" cellspacing="0" cellpadding="4">')
                table_open = True
            output.append("<tr>")
            for cell in paragraph["table_row"]:
                output.append("<td>" + render_runs(cell) + "</td>")
            output.append("</tr>")
            continue
        if table_open:
            output.append("</table>")
            table_open = False
        style = paragraph["style"]
        if style.get("horizontal_rule"):
            if previous_was_rule:
                # Ricopad <=0.6.0 could accidentally inherit the ruler block
                # format onto the following empty block.  Canonicalize that
                # historical two-rule sequence back to one rule on import.
                continue
            if active_list:
                output.append(f"</{active_list}>")
                active_list = None
            output.append("<hr>")
            previous_was_rule = True
            continue
        previous_was_rule = False
        list_type = style.get("list_type")
        tag = "ol" if list_type == "ordered" else "ul" if list_type else None
        if tag != active_list:
            if active_list:
                output.append(f"</{active_list}>")
            if tag:
                output.append(f"<{tag}>")
            active_list = tag
        css = [f"text-align:{style['alignment']}"]
        css.append(f"margin-left:{_rtf_twips_to_qt_px(style['left_indent']):g}px")
        css.append(f"margin-right:{_rtf_twips_to_qt_px(style['right_indent']):g}px")
        css.append(f"text-indent:{_rtf_twips_to_qt_px(style['first_indent']):g}px")
        css.append(f"margin-top:{_rtf_twips_to_qt_px(style['space_before']):g}px")
        css.append(f"margin-bottom:{_rtf_twips_to_qt_px(style['space_after']):g}px")
        if style["line_spacing"]:
            if style["line_mult"]:
                css.append(f"line-height:{max(0.5, style['line_spacing'] / 240.0) * 100:g}%")
            else:
                css.append(f"line-height:{_rtf_twips_to_qt_px(abs(style['line_spacing'])):g}px")
        body = render_runs(paragraph)
        if tag:
            output.append(f'<li style="{";".join(css)}">{body}</li>')
        else:
            output.append(f'<p style="{";".join(css)}">{body}</p>')
    if active_list:
        output.append(f"</{active_list}>")
    if table_open:
        output.append("</table>")
    output.append("</body></html>")
    rendered_html = "".join(output)
    model = {
        "fonts": dict(fonts),
        "colours": list(colours),
        "default_font_id": int(default_font_id),
        "default_half_points": int(default_half_points),
        "styles": styles,
        "paragraphs": paragraphs,
    }
    if return_auto_foreground and return_model:
        return rendered_html, automatic_foreground, model
    if return_auto_foreground:
        return rendered_html, automatic_foreground
    if return_model:
        return rendered_html, model
    return rendered_html



def _rtf_model_has_tables(model):
    return any("table_row" in item for item in model.get("paragraphs", ()))


def _rtf_automatic_contrast_colour(background):
    """Return a readable display colour for automatic text on a highlight.

    This colour is a Qt-only presentation aid.  Runs tagged with
    ``RTF_AUTOMATIC_CONTRAST_PROPERTY`` are still serialized with RTF colour
    index 0 (automatic), so interoperability and user intent are preserved.
    """
    colour = background if isinstance(background, QColor) else QColor(background)
    if not colour.isValid():
        return QColor(Qt.GlobalColor.black)
    # Perceived luminance; the threshold keeps common yellow/green/cyan
    # highlights dark-text readable while dark blue/black use white.
    luminance = (299 * colour.red() + 587 * colour.green() + 114 * colour.blue()) / 1000.0
    return QColor(Qt.GlobalColor.black if luminance >= 145 else Qt.GlobalColor.white)


def _rtf_model_char_format(signature, fonts, colours):
    """Build one QTextCharFormat directly from parsed RTF state.

    Importing through HTML is intentionally avoided for normal RTF documents:
    HTML is a presentation bridge, not Ricopad's persistence model, and repeated
    RTF -> HTML -> QTextDocument -> RTF cycles can normalize away empty blocks,
    paragraph geometry and image provenance.
    """
    fmt = QTextCharFormat()
    if signature is None:
        return fmt
    bold, italic, underline, strike, font_id, half_points, fg_id, bg_id, superscript, link = signature
    family = fonts.get(font_id)
    if family:
        fmt.setFontFamily(_safe_qt_font_family(family))
    fmt.setFontPointSize(max(1.0, float(half_points) / 2.0))
    fmt.setFontWeight(QFont.Weight.Bold if bold else QFont.Weight.Normal)
    fmt.setFontItalic(bool(italic))
    fmt.setFontUnderline(bool(underline))
    fmt.setFontStrikeOut(bool(strike))
    explicit_foreground = 0 < int(fg_id) < len(colours) and colours[int(fg_id)]
    background_colour = QColor(colours[int(bg_id)]) if 0 < int(bg_id) < len(colours) and colours[int(bg_id)] else None
    if explicit_foreground:
        fmt.setForeground(QColor(colours[int(fg_id)]))
    if background_colour is not None and background_colour.isValid():
        fmt.setBackground(background_colour)
        if not explicit_foreground:
            fmt.setForeground(_rtf_automatic_contrast_colour(background_colour))
            fmt.setProperty(RTF_AUTOMATIC_CONTRAST_PROPERTY, True)
    if superscript > 0:
        fmt.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignSuperScript)
    elif superscript < 0:
        fmt.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignSubScript)
    if link and is_safe_link_target(link):
        fmt.setAnchor(True)
        fmt.setAnchorHref(link)
    return fmt


def _rtf_model_block_format(style):
    fmt = QTextBlockFormat()
    alignment = style.get("alignment", "left")
    if alignment == "center":
        fmt.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    elif alignment == "right":
        fmt.setAlignment(Qt.AlignmentFlag.AlignRight)
    elif alignment == "justify":
        fmt.setAlignment(Qt.AlignmentFlag.AlignJustify)
    else:
        fmt.setAlignment(Qt.AlignmentFlag.AlignLeft)
    fmt.setLeftMargin(_rtf_twips_to_qt_px(style.get("left_indent", 0)))
    fmt.setRightMargin(_rtf_twips_to_qt_px(style.get("right_indent", 0)))
    fmt.setTextIndent(_rtf_twips_to_qt_px(style.get("first_indent", 0)))
    fmt.setTopMargin(_rtf_twips_to_qt_px(style.get("space_before", 0)))
    fmt.setBottomMargin(_rtf_twips_to_qt_px(style.get("space_after", 0)))
    spacing = int(style.get("line_spacing", 0) or 0)
    multiple = int(style.get("line_mult", 0) or 0)
    if spacing:
        if multiple:
            # RTF proportional spacing uses 240 == single line; Qt expects a
            # percentage where 100 == single line.
            fmt.setLineHeight(
                max(1.0, float(spacing) / 2.4),
                QTextBlockFormat.LineHeightTypes.ProportionalHeight.value,
            )
        elif spacing < 0:
            fmt.setLineHeight(
                _rtf_twips_to_qt_px(abs(spacing)),
                QTextBlockFormat.LineHeightTypes.FixedHeight.value,
            )
        else:
            fmt.setLineHeight(
                _rtf_twips_to_qt_px(spacing),
                QTextBlockFormat.LineHeightTypes.MinimumHeight.value,
            )
    if style.get("horizontal_rule"):
        fmt.setProperty(QTextFormat.Property.BlockTrailingHorizontalRulerWidth, 100)
    return fmt


def _rtf_data_image_parts(source):
    match = re.fullmatch(
        r"data:image/(png|jpeg|jpg);base64,([A-Za-z0-9+/=\s]+)",
        str(source or "").strip(), re.I,
    )
    if match is None:
        return None
    encoded = re.sub(r"\s+", "", match.group(2))
    if len(encoded) > ((MAX_EMBEDDED_IMAGE_SIZE + 2) // 3) * 4 + 4:
        return None
    try:
        payload = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError):
        return None
    if not payload or len(payload) > MAX_EMBEDDED_IMAGE_SIZE:
        return None
    kind = "jpeg" if match.group(1).lower() in {"jpeg", "jpg"} else "png"
    # Decode only for display/resource registration.  Keep ``payload`` itself
    # untouched for later RTF serialization.  QImageReader auto-transform also
    # honours common JPEG orientation metadata without forcing a re-encode.
    encoded = QByteArray(payload)
    buffer = QBuffer(encoded)
    if not buffer.open(QIODevice.OpenModeFlag.ReadOnly):
        return None
    try:
        reader = QImageReader(buffer)
        reader.setAutoTransform(True)
        image = reader.read()
    finally:
        buffer.close()
    if image.isNull():
        return None
    return kind, payload, image


def _rtf_mark_synthetic_block(block, synthetic=True):
    if not block.isValid():
        return
    cursor = QTextCursor(block)
    fmt = QTextBlockFormat(block.blockFormat())
    if synthetic:
        fmt.setProperty(RTF_SYNTHETIC_STRUCTURE_BLOCK, True)
    else:
        fmt.clearProperty(RTF_SYNTHETIC_STRUCTURE_BLOCK)
    cursor.setBlockFormat(fmt)


def _rtf_insert_model_runs(cursor, paragraph, document, fonts, colours):
    for run in paragraph.get("runs", ()):
        image_info = run.get("image")
        if image_info:
            parts = _rtf_data_image_parts(image_info.get("src"))
            if parts is None:
                continue
            _kind, _payload, image = parts
            source = image_info.get("src")
            resource_url = QUrl(source)
            document.addResource(QTextDocument.ResourceType.ImageResource, resource_url, image)
            image_format = QTextImageFormat()
            image_format.setName(source)
            if image_info.get("width"):
                image_format.setWidth(max(1.0, float(image_info["width"])))
            if image_info.get("height"):
                image_format.setHeight(max(1.0, float(image_info["height"])))
            cursor.insertImage(image_format)
            continue
        fmt = _rtf_model_char_format(run.get("signature"), fonts, colours)
        value = "".join(run.get("text", ())).replace("\n", "\u2028")
        if value:
            cursor.insertText(value, fmt)


def _rtf_encode_cell_meta(meta):
    if not meta:
        return ""
    values = []
    for key in ("pad_left", "pad_right", "pad_top", "pad_bottom"):
        value = meta.get(key)
        values.append("" if value is None else str(int(value)))
    values.append(str(meta.get("valign") or ""))
    return ",".join(values)


def _rtf_decode_cell_meta(value):
    parts = str(value or "").split(",")
    while len(parts) < 5:
        parts.append("")
    result = {}
    for key, raw in zip(("pad_left", "pad_right", "pad_top", "pad_bottom"), parts[:4]):
        if raw.strip():
            try:
                result[key] = max(0, min(1_000_000, int(raw)))
            except ValueError:
                pass
    if parts[4] in {"top", "center", "bottom"}:
        result["valign"] = parts[4]
    return result


def populate_qtextdocument_from_rtf_model(document, model):
    """Populate a QTextDocument directly from Ricopad's parsed RTF model.

    The direct path is deliberately structural: paragraphs are QTextBlocks,
    blank paragraphs remain real empty blocks, tables remain QTextTables, and
    embedded PNG/JPEG data URLs retain their original bytes.  This avoids the
    repeated normalization inherent in an RTF -> HTML -> QTextDocument bridge.
    """
    fonts = dict(model.get("fonts", {}))
    colours = list(model.get("colours", [None]))
    default_font_id = int(model.get("default_font_id", 0))
    default_half_points = int(model.get("default_half_points", 22))
    default_font = QFont(_safe_qt_font_family(fonts.get(default_font_id, "Sans Serif")))
    default_font.setPointSizeF(max(1.0, default_half_points / 2.0))

    document.clear()
    document.setDefaultFont(default_font)
    cursor = QTextCursor(document)
    cursor.movePosition(QTextCursor.MoveOperation.Start)
    block_available = True
    active_list = None
    active_lists = {}
    items = list(model.get("paragraphs", ()))
    index = 0

    while index < len(items):
        paragraph = items[index]
        if "table_row" in paragraph:
            row_items = []
            rows = []
            while index < len(items) and "table_row" in items[index]:
                row_items.append(items[index])
                rows.append(items[index]["table_row"])
                index += 1
            columns = max((len(row) for row in rows), default=0)
            if not rows or columns <= 0:
                continue
            if len(rows) > MAX_RTF_TABLE_ROWS or columns > MAX_RTF_TABLE_COLUMNS or len(rows) * columns > MAX_RTF_TABLE_CELLS:
                raise ValueError("The RTF table exceeds Ricopad's safety limits.")

            # The root QTextDocument requires separator blocks around frames.
            # Mark only those implementation blocks so the RTF serializer can
            # omit them; explicit empty paragraphs from the source remain plain
            # unmarked QTextBlocks and therefore survive save cycles.
            if block_available and not cursor.block().text():
                _rtf_mark_synthetic_block(cursor.block(), True)
            else:
                cursor.movePosition(QTextCursor.MoveOperation.End)

            table_format = QTextTableFormat()
            table_format.setBorder(1.0)
            table_format.setCellSpacing(0.0)
            first_row = row_items[0] if row_items else {}
            imported_gap = first_row.get("trgaph")
            gap_twips = None if imported_gap is None else max(0, int(imported_gap or 0))
            # QTextTableFormat exposes one common cell-padding value. If the
            # producer used one uniform RTF padding value (LibreOffice's common
            # case), reproduce it visually; exact per-cell values remain in
            # cell metadata for canonical serialization.
            all_cell_formats = [
                meta for row_item in row_items
                for meta in row_item.get("cell_formats", ())
                if meta
            ]
            pad_values = []
            for meta in all_cell_formats:
                values = [meta.get(k) for k in ("pad_left","pad_right","pad_top","pad_bottom")]
                if all(value is not None for value in values) and len(set(values)) == 1:
                    pad_values.append(values[0])
                else:
                    pad_values = []; break
            if pad_values and len(set(pad_values)) == 1:
                table_format.setCellPadding(max(0.0, _rtf_twips_to_qt_px(pad_values[0])))
            elif gap_twips is not None:
                table_format.setCellPadding(max(0.0, _rtf_twips_to_qt_px(gap_twips) / 2.0))
            cellx = [int(value) for value in first_row.get("cellx", ())[:columns]]
            trleft = int(first_row.get("trleft", 0) or 0)
            autofit = bool(first_row.get("autofit", False))
            if len(cellx) == columns and all(cellx[pos] > (trleft if pos == 0 else cellx[pos - 1]) for pos in range(columns)):
                widths = []
                previous = trleft
                for boundary in cellx:
                    widths.append(boundary - previous)
                    previous = boundary
                total = float(sum(widths))
                # An auto-fit table deliberately leaves Qt's column constraints
                # empty so the same content-driven layout seen before Save is
                # restored after reopen. Explicit foreign geometry remains
                # percentage-constrained and round-trips through cellx.
                if total > 0 and not autofit:
                    table_format.setColumnWidthConstraints([
                        QTextLength(QTextLength.Type.PercentageLength, width * 100.0 / total)
                        for width in widths
                    ])
                table_format.setProperty(RTF_TABLE_CELLX_PROPERTY, ",".join(str(value) for value in cellx))
                table_format.setProperty(RTF_TABLE_LEFT_PROPERTY, trleft)
            table_format.setProperty(RTF_TABLE_IMPORTED_PROPERTY, True)
            if autofit:
                table_format.setProperty(RTF_TABLE_AUTOFIT_PROPERTY, True)
            if gap_twips is not None:
                table_format.setProperty(RTF_TABLE_GAP_PROPERTY, gap_twips)
            table = cursor.insertTable(len(rows), columns, table_format)
            for row_index, row in enumerate(rows):
                row_meta = row_items[row_index].get("cell_formats", ()) if row_index < len(row_items) else ()
                for column_index in range(columns):
                    cell = table.cellAt(row_index, column_index)
                    if column_index < len(row_meta):
                        meta = row_meta[column_index]
                        encoded_meta = _rtf_encode_cell_meta(meta)
                        if encoded_meta:
                            try:
                                cell_format = cell.format().toTableCellFormat()
                                if meta.get("pad_left") is not None:
                                    cell_format.setLeftPadding(_rtf_twips_to_qt_px(meta["pad_left"]))
                                if meta.get("pad_right") is not None:
                                    cell_format.setRightPadding(_rtf_twips_to_qt_px(meta["pad_right"]))
                                if meta.get("pad_top") is not None:
                                    cell_format.setTopPadding(_rtf_twips_to_qt_px(meta["pad_top"]))
                                if meta.get("pad_bottom") is not None:
                                    cell_format.setBottomPadding(_rtf_twips_to_qt_px(meta["pad_bottom"]))
                                cell_format.setProperty(RTF_TABLE_CELL_META_PROPERTY, encoded_meta)
                                cell.setFormat(cell_format)
                            except Exception:
                                # Exact RTF metadata is still preserved on the
                                # table-cell format when Qt's visual cell-format
                                # conversion is unavailable on an older binding.
                                fallback_format = cell.format()
                                fallback_format.setProperty(RTF_TABLE_CELL_META_PROPERTY, encoded_meta)
                                cell.setFormat(fallback_format)
                    cell_cursor = cell.firstCursorPosition()
                    cell_paragraph = row[column_index] if column_index < len(row) else {"style": _rtf_paragraph_signature(_new_rtf_state()), "runs": []}
                    cell_cursor.setBlockFormat(_rtf_model_block_format(cell_paragraph.get("style", {})))
                    _rtf_insert_model_runs(cell_cursor, cell_paragraph, document, fonts, colours)

            post_block = table.lastCursorPosition().block().next()
            while post_block.isValid():
                try:
                    if QTextCursor(post_block).currentTable() is None:
                        break
                except Exception:
                    break
                post_block = post_block.next()
            if post_block.isValid():
                cursor = QTextCursor(post_block)
            else:
                cursor = QTextCursor(document); cursor.movePosition(QTextCursor.MoveOperation.End); cursor.insertBlock()
            if cursor.block().isValid() and not cursor.block().text():
                _rtf_mark_synthetic_block(cursor.block(), True)
            block_available = True
            active_list = None
            active_lists.clear()
            continue

        if not block_available:
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertBlock()
        _rtf_mark_synthetic_block(cursor.block(), False)
        block_available = False
        paragraph_style = dict(paragraph.get("style", {}))
        list_type = paragraph_style.get("list_type")
        list_left = int(paragraph_style.get("left_indent", 0) or 0)
        list_first = int(paragraph_style.get("first_indent", 0) or 0)
        list_level = max(0, min(8, int(paragraph_style.get("list_level", 0) or 0)))
        if list_type:
            # QTextList already supplies the visual list indentation. Feeding
            # the RTF list's li/fi into QTextBlockFormat as well double-indents
            # every reopened Ricopad list. Retain the original RTF geometry as
            # metadata for serialization, but do not apply it twice on screen.
            paragraph_style["left_indent"] = 0
            paragraph_style["first_indent"] = 0
        block_format = _rtf_model_block_format(paragraph_style)
        if list_type:
            # Store the level-0 base rather than this paragraph's already
            # level-adjusted left edge.  The serializer adds 360 twips per
            # semantic list level; retaining the effective value here made a
            # nested item drift another 360 twips on every save/reopen cycle.
            block_format.setProperty(RTF_LIST_LEFT_PROPERTY, list_left - list_level * 360)
            block_format.setProperty(RTF_LIST_FIRST_PROPERTY, list_first)
        cursor.setBlockFormat(block_format)

        if list_type:
            list_key = (paragraph_style.get("list_id"), list_type, list_level)
            active_list = active_lists.get(list_key)
            if active_list is None:
                list_format = QTextListFormat()
                list_format.setStyle(
                    QTextListFormat.Style.ListDecimal
                    if list_type == "ordered"
                    else QTextListFormat.Style.ListDisc
                )
                list_format.setIndent(max(1, list_level + 1))
                active_list = cursor.createList(list_format)
                active_lists[list_key] = active_list
            else:
                active_list.add(cursor.block())
        else:
            active_list = None
            active_lists.clear()

        _rtf_insert_model_runs(cursor, paragraph, document, fonts, colours)
        if list_type:
            # Qt paints a list marker from the block character baseline. Keep
            # it aligned with the paragraph's first real text run instead of
            # stale heading/default state.
            block = cursor.block()
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment(); iterator += 1
                if fragment.isValid() and fragment.text():
                    marker_cursor = QTextCursor(block)
                    marker_cursor.setBlockCharFormat(fragment.charFormat())
                    break
        index += 1

    if not items:
        document.clear()
        document.setDefaultFont(default_font)
    document.setModified(False)
    return True


def _rtf_escape_text(value):
    output = []
    for char in value:
        code = ord(char)
        if char in "\\{}":
            output.append("\\" + char)
        elif char in ("\n", "\u2028"):
            output.append("\\line ")
        elif char == "\t":
            output.append("\\tab ")
        elif 32 <= code < 127:
            output.append(char)
        else:
            encoded = char.encode("utf-16-le", errors="replace")
            for offset in range(0, len(encoded), 2):
                unit = int.from_bytes(encoded[offset:offset + 2], "little")
                signed = unit if unit < 32768 else unit - 65536
                output.append(f"\\u{signed}?")
    return "".join(output)


def _qt_brush_colour(brush):
    """Return a real brush colour, never Qt's nominal black for NoBrush.

    This distinction is release-critical: an unset foreground/background must
    remain absent when saving RTF rather than turning into black text/highlight.
    """
    try:
        if brush.style() == Qt.BrushStyle.NoBrush:
            return None
        colour = brush.color()
        return colour if colour.isValid() and colour.alpha() else None
    except Exception:
        return None


def _qt_font_family(char_format, default="Sans Serif"):
    try:
        families = char_format.fontFamilies()
        if families:
            family = str(families[0]).strip()
            if family:
                return family
    except Exception:
        pass
    try:
        font = char_format.font()
        try:
            families = font.families()
            if families:
                family = str(families[0]).strip()
                if family:
                    return family
        except Exception:
            pass
        family = font.family()
        return family or default
    except Exception:
        return default


def _qt_image_payload(document, image_format):
    """Return (kind, bytes, intrinsic_width, intrinsic_height) for an image.

    If the QTextImageFormat still carries an embedded PNG/JPEG data URL,
    preserve those exact encoded bytes.  This prevents repeated RTF save/open
    cycles from decoding and re-encoding photographs, which can discard JPEG
    metadata/colour profiles and needlessly alter the embedded payload.
    """
    name = image_format.name()
    parts = _rtf_data_image_parts(name)
    if parts is not None:
        kind, payload, image = parts
        return kind, payload, image.width(), image.height()

    resource = None
    try:
        resource = document.resource(
            QTextDocument.ResourceType.ImageResource,
            QUrl(name),
        )
    except Exception:
        resource = None

    image = QImage()
    if isinstance(resource, QImage):
        image = resource
    elif isinstance(resource, QPixmap):
        image = resource.toImage()
    elif isinstance(resource, QByteArray):
        image.loadFromData(bytes(resource))
    elif isinstance(resource, (bytes, bytearray)):
        image.loadFromData(bytes(resource))

    if image.isNull():
        return None
    array = QByteArray()
    buffer = QBuffer(array)
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
        return None
    try:
        if not image.save(buffer, "PNG"):
            return None
    finally:
        buffer.close()
    data = bytes(array)
    if len(data) > MAX_EMBEDDED_IMAGE_SIZE:
        return None
    return "png", data, image.width(), image.height()


def document_to_rtf(document):
    """Serialise a QTextDocument into a bounded WordPad-compatible RTF subset.

    Ricopad 0.7.2 supports conservative non-nested table rows/cells and paragraph
    horizontal rules while retaining the existing inline formatting/image/link
    subset. Unsupported nested table structure is flattened to the outer cell.
    """
    fonts = []
    colours = []

    def add_font(name):
        name = name or "Sans Serif"
        if name not in fonts:
            fonts.append(name)
        return fonts.index(name)

    def add_colour(colour):
        if colour is None:
            return 0
        key = (colour.red(), colour.green(), colour.blue())
        if key not in colours:
            colours.append(key)
        return colours.index(key) + 1

    try:
        default_families = document.defaultFont().families()
        default_family = str(default_families[0]).strip() if default_families else document.defaultFont().family()
    except Exception:
        default_family = document.defaultFont().family()
    add_font(default_family or "Sans Serif")
    list_definitions = {}
    ordered_styles = {
        QTextListFormat.Style.ListDecimal,
        QTextListFormat.Style.ListLowerAlpha,
        QTextListFormat.Style.ListUpperAlpha,
        QTextListFormat.Style.ListLowerRoman,
        QTextListFormat.Style.ListUpperRoman,
    }
    block = document.begin()
    while block.isValid():
        text_list = block.textList()
        if text_list is not None and QTextCursor(block).currentTable() is None:
            key = text_list.objectIndex()
            if key not in list_definitions:
                style = text_list.format().style()
                block_format = block.blockFormat()
                ordinal = len(list_definitions) + 1
                if block_format.hasProperty(RTF_LIST_LEFT_PROPERTY):
                    list_left = int(block_format.property(RTF_LIST_LEFT_PROPERTY))
                else:
                    list_left = 720
                if block_format.hasProperty(RTF_LIST_FIRST_PROPERTY):
                    list_first = int(block_format.property(RTF_LIST_FIRST_PROPERTY))
                else:
                    list_first = -360
                list_definitions[key] = {
                    "ls": ordinal,
                    "listid": 1000 + ordinal,
                    "templateid": 2000 + ordinal,
                    "type": "ordered" if style in ordered_styles else "unordered",
                    "left": list_left,
                    "first": list_first,
                }
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment.isValid():
                fmt = fragment.charFormat()
                add_font(_qt_font_family(fmt, fonts[0]))
                if not bool(fmt.property(RTF_AUTOMATIC_CONTRAST_PROPERTY)):
                    add_colour(_qt_brush_colour(fmt.foreground()))
                add_colour(_qt_brush_colour(fmt.background()))
            iterator += 1
        block = block.next()

    font_table = ["{\\fonttbl"]
    for idx, family in enumerate(fonts):
        safe_family = _rtf_escape_text(family).replace(";", "")
        font_table.append(f"{{\\f{idx}\\fnil {safe_family};}}")
    font_table.append("}")

    colour_table = ["{\\colortbl ;"]
    for red, green, blue in colours:
        colour_table.append(f"\\red{red}\\green{green}\\blue{blue};")
    colour_table.append("}")

    list_table = []
    override_table = []
    if list_definitions:
        list_table.append("{\\*\\listtable")
        override_table.append("{\\*\\listoverridetable")
        for definition in list_definitions.values():
            base_left = int(definition["left"])
            first = int(definition["first"])
            levels=[]
            for level_index in range(9):
                left=base_left + level_index * 360
                if definition["type"] == "unordered":
                    levels.append(
                        "{\\listlevel\\levelnfc23\\leveljc0\\levelstartat1\\levelfollow0"
                        r"{\leveltext \'01\u8226 ?;}{\levelnumbers;}"
                        f"\\f0\\fi{first}\\li{left}"
                        "}"
                    )
                else:
                    levels.append(
                        "{\\listlevel\\levelnfc0\\leveljc0\\levelstartat1\\levelfollow0"
                        r"{\leveltext \'02\'00.;}{\levelnumbers \'01;}"
                        f"\\fi{first}\\li{left}"
                        "}"
                    )
            list_table.append(
                "{\\list"
                f"\\listtemplateid{definition['templateid']}"
                + "".join(levels)
                + f"\\listid{definition['listid']}"
                + "}"
            )
            override_table.append(
                "{\\listoverride"
                f"\\listid{definition['listid']}"
                "\\listoverridecount0"
                f"\\ls{definition['ls']}"
                "}"
            )
        list_table.append("}")
        override_table.append("}")

    list_counters = {}

    def paragraph_controls(block, *, in_table=False):
        block_format = block.blockFormat()
        text_list = block.textList()
        block_indent = max(0, int(block_format.indent()))
        try:
            indent_width = float(document.indentWidth() or 40.0)
        except Exception:
            indent_width = 40.0
        effective_left_margin = float(block_format.leftMargin())
        if text_list is None or in_table:
            # QTextBlockFormat.indent() is a Qt layout abstraction with no
            # automatic RTF encoding.  Materialise it as an RTF left margin so
            # programmatic/legacy indents survive save and reopen.
            effective_left_margin += block_indent * indent_width
        controls = ["\\pard"]
        if in_table:
            controls.append("\\intbl")
        alignment = block_format.alignment()
        if alignment & Qt.AlignmentFlag.AlignHCenter:
            controls.append("\\qc")
        elif alignment & Qt.AlignmentFlag.AlignRight:
            controls.append("\\qr")
        elif alignment & Qt.AlignmentFlag.AlignJustify:
            controls.append("\\qj")
        else:
            controls.append("\\ql")
        controls.extend([
            f"\\li{_qt_px_to_rtf_twips(effective_left_margin)}",
            f"\\ri{_qt_px_to_rtf_twips(block_format.rightMargin())}",
            f"\\fi{_qt_px_to_rtf_twips(block_format.textIndent())}",
            f"\\sb{_qt_px_to_rtf_twips(block_format.topMargin())}",
            f"\\sa{_qt_px_to_rtf_twips(block_format.bottomMargin())}",
        ])
        try:
            line_height = float(block_format.lineHeight() or 0.0)
            line_type = int(block_format.lineHeightType())
            if line_type == int(QTextBlockFormat.LineHeightTypes.ProportionalHeight.value) and line_height:
                controls.extend([f"\\sl{round(line_height * 2.4)}", "\\slmult1"])
            elif line_type == int(QTextBlockFormat.LineHeightTypes.FixedHeight.value) and line_height:
                controls.extend([f"\\sl{-_qt_px_to_rtf_twips(line_height)}", "\\slmult0"])
            elif line_type == int(QTextBlockFormat.LineHeightTypes.MinimumHeight.value) and line_height:
                controls.extend([f"\\sl{_qt_px_to_rtf_twips(line_height)}", "\\slmult0"])
            # SingleHeight is represented by omitting \sl.  LineDistanceHeight
            # has no exact RTF equivalent and is not generated by Ricopad's UI.
        except Exception:
            pass
        try:
            if block_format.property(QTextFormat.Property.BlockTrailingHorizontalRulerWidth):
                controls.extend(["\\brdrb", "\\brdrs", "\\brdrw20", "\\brsp20"])
        except Exception:
            pass

        if text_list is not None and not in_table:
            definition = list_definitions.get(text_list.objectIndex())
            if definition is not None:
                list_key = text_list.objectIndex()
                list_counters[list_key] = list_counters.get(list_key, 0) + 1
                level = max(0, min(8, int(text_list.format().indent() or 1) + block_indent - 1))
                # Keep body geometry aligned with the declared list level.  An
                # explicit level-0 \li on a nested paragraph can override the
                # list table in external readers, so derive it from \ilvl.
                level_left = int(definition["left"]) + level * 360
                controls.append(f"\\li{level_left}\\fi{definition['first']}")
                if definition["type"] == "ordered":
                    marker = f"{list_counters[list_key]}."
                    controls.append("{\\listtext\\pard\\plain " + _rtf_escape_text(marker) + "\\tab}")
                else:
                    controls.append("{\\listtext\\pard\\plain\\f0 \\u8226?\\tab}")
                controls.extend([f"\\ilvl{level}", f"\\ls{definition['ls']}"])
        return controls

    def serialise_runs(block):
        output = []
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if not fragment.isValid():
                iterator += 1
                continue
            fmt = fragment.charFormat()
            if fmt.isImageFormat():
                image_info = _qt_image_payload(document, fmt.toImageFormat())
                if image_info is not None:
                    kind, data, width, height = image_info
                    image_format = fmt.toImageFormat()
                    display_width = image_format.width() or width
                    display_height = image_format.height() or height
                    hex_data = data.hex()
                    blip = "\\jpegblip" if kind == "jpeg" else "\\pngblip"
                    output.append(
                        "{\\pict" + blip
                        + f"\\picw{width}\\pich{height}"
                        f"\\picwgoal{_qt_px_to_rtf_twips(display_width)}"
                        f"\\pichgoal{_qt_px_to_rtf_twips(display_height)}\n"
                        + "\n".join(hex_data[i:i + 128] for i in range(0, len(hex_data), 128))
                        + "}"
                    )
                iterator += 1
                continue

            family = _qt_font_family(fmt, fonts[0])
            font_index = add_font(family)
            point_size = fmt.fontPointSize() or document.defaultFont().pointSizeF() or 11.0
            char_controls = ["\\plain", f"\\f{font_index}", f"\\fs{max(2, round(point_size * 2))}"]
            try:
                if int(fmt.fontWeight()) >= int(QFont.Weight.Bold):
                    char_controls.append("\\b")
            except Exception:
                pass
            if fmt.fontItalic():
                char_controls.append("\\i")
            if fmt.fontUnderline():
                char_controls.append("\\ul")
            if fmt.fontStrikeOut():
                char_controls.append("\\strike")
            foreground = 0 if bool(fmt.property(RTF_AUTOMATIC_CONTRAST_PROPERTY)) else add_colour(_qt_brush_colour(fmt.foreground()))
            background = add_colour(_qt_brush_colour(fmt.background()))
            if foreground:
                char_controls.append(f"\\cf{foreground}")
            if background:
                char_controls.append(f"\\highlight{background}")
            try:
                vertical = fmt.verticalAlignment()
                if vertical == QTextCharFormat.VerticalAlignment.AlignSuperScript:
                    char_controls.append("\\super")
                elif vertical == QTextCharFormat.VerticalAlignment.AlignSubScript:
                    char_controls.append("\\sub")
            except Exception:
                pass

            content = _rtf_escape_text(fragment.text().replace("\u2029", ""))
            if fmt.isAnchor() and fmt.anchorHref() and is_safe_link_target(fmt.anchorHref()):
                href = _rtf_escape_text(fmt.anchorHref()).replace('"', '\\"')
                content = (
                    "{\\field{\\*\\fldinst HYPERLINK \"" + href +
                    "\"}{\\fldrslt " + content + "}}"
                )
            output.append("{" + "".join(char_controls) + " " + content + "}")
            iterator += 1
        return "".join(output)

    def serialise_table(table):
        rows = int(table.rows())
        columns = int(table.columns())
        if rows <= 0 or columns <= 0:
            return ""
        if rows > MAX_RTF_TABLE_ROWS or columns > MAX_RTF_TABLE_COLUMNS or rows * columns > MAX_RTF_TABLE_CELLS:
            raise ValueError("The table exceeds Ricopad's RTF safety limits.")
        pieces = []
        table_format = table.format()
        trleft = int(table_format.property(RTF_TABLE_LEFT_PROPERTY) or 0)
        imported_table = bool(table_format.property(RTF_TABLE_IMPORTED_PROPERTY))
        autofit = bool(table_format.property(RTF_TABLE_AUTOFIT_PROPERTY))
        if table_format.hasProperty(RTF_TABLE_GAP_PROPERTY):
            trgaph = max(0, int(table_format.property(RTF_TABLE_GAP_PROPERTY) or 0))
        else:
            # Content-fit Ricopad tables must not gain synthetic cell padding on
            # their first reopen. Older output invented trgaph108 here, and the
            # importer faithfully turned half of it into Qt cell padding.
            trgaph = None if (imported_table or autofit) else 108
        original_cellx = []
        raw_cellx = str(table_format.property(RTF_TABLE_CELLX_PROPERTY) or "")
        if raw_cellx:
            try:
                original_cellx = [int(value) for value in raw_cellx.split(",") if value.strip()]
            except ValueError:
                original_cellx = []
        if len(original_cellx) == columns and all(original_cellx[pos] > (trleft if pos == 0 else original_cellx[pos - 1]) for pos in range(columns)):
            boundary_values = original_cellx
        else:
            constraints = list(table_format.columnWidthConstraints())
            percentages = []
            if len(constraints) == columns:
                for constraint in constraints:
                    try:
                        if constraint.type() == QTextLength.Type.PercentageLength and constraint.rawValue() > 0:
                            percentages.append(float(constraint.rawValue()))
                        else:
                            percentages = []; break
                    except Exception:
                        percentages = []; break
            if percentages and sum(percentages) > 0:
                total_twips = 9000
                running = trleft
                boundary_values = []
                pct_total = sum(percentages)
                for pct in percentages:
                    running += max(1, round(total_twips * pct / pct_total))
                    boundary_values.append(running)
            else:
                if autofit and not imported_table:
                    # A new Ricopad table is content-fit, not page-width by default.
                    # Keep a moderate initial grid for external RTF consumers;
                    # \trautofit1 remains free to expand cells for wider content.
                    cell_width = max(1, 5400 // max(1, columns))
                else:
                    cell_width = max(720, min(3600, 9000 // max(1, columns)))
                boundary_values = [trleft + cell_width * (column + 1) for column in range(columns)]
        for row in range(rows):
            row_prefix = f"{{\\trowd"
            if autofit:
                row_prefix += "\\trautofit1"
            if trgaph is not None:
                row_prefix += f"\\trgaph{max(0, trgaph)}"
            row_prefix += f"\\trleft{trleft}"
            cell_prefixes = []
            for column in range(columns):
                cell = table.cellAt(row, column)
                meta = _rtf_decode_cell_meta(cell.format().property(RTF_TABLE_CELL_META_PROPERTY))
                cell_prefix = ""
                for rtf_word, key in (("clpadl","pad_left"),("clpadt","pad_top"),("clpadb","pad_bottom"),("clpadr","pad_right")):
                    if meta.get(key) is not None:
                        suffix = {"clpadl":"l","clpadt":"t","clpadb":"b","clpadr":"r"}[rtf_word]
                        cell_prefix += f"\\clpadf{suffix}3\\{rtf_word}{int(meta[key])}"
                valign = meta.get("valign")
                if valign == "center": cell_prefix += "\\clvertalc"
                elif valign == "bottom": cell_prefix += "\\clvertalb"
                elif valign == "top": cell_prefix += "\\clvertalt"
                cell_prefix += f"\\cellx{boundary_values[column]}"
                cell_prefixes.append(cell_prefix)
            pieces.append(row_prefix + "".join(cell_prefixes) + "\n")
            for column in range(columns):
                cell = table.cellAt(row, column)
                pieces.append("{")
                first = cell.firstCursorPosition()
                last = cell.lastCursorPosition()
                cell_end = last.position()
                cell_block = first.block()
                wrote_block = False
                while cell_block.isValid() and cell_block.position() < cell_end:
                    if wrote_block:
                        pieces.append("\\line ")
                    pieces.append("".join(paragraph_controls(cell_block, in_table=True)))
                    pieces.append(serialise_runs(cell_block))
                    wrote_block = True
                    cell_block = cell_block.next()
                if not wrote_block:
                    pieces.append("\\pard\\intbl ")
                pieces.append("\\cell}")
            pieces.append("\\row}\n")
        return "".join(pieces)

    body = []
    seen_tables = set()
    previous_was_rule = False
    block = document.begin()
    while block.isValid():
        if (
            not block.text()
            and bool(block.blockFormat().property(RTF_SYNTHETIC_STRUCTURE_BLOCK))
        ):
            block = block.next()
            continue
        table = None
        try:
            table = QTextCursor(block).currentTable()
        except Exception:
            table = None
        if table is not None:
            key = table.firstCursorPosition().position()
            if key not in seen_tables:
                seen_tables.add(key)
                body.append(serialise_table(table))
            previous_was_rule = False
            block = block.next()
            continue
        is_rule = bool(block.blockFormat().property(QTextFormat.Property.BlockTrailingHorizontalRulerWidth))
        if is_rule and previous_was_rule and not block.text().strip():
            block = block.next()
            continue
        body.append("".join(paragraph_controls(block)))
        body.append(serialise_runs(block))
        body.append("\\par\n")
        previous_was_rule = is_rule
        block = block.next()

    # add_font/add_colour only encounter formats already traversed in the first
    # pass, so the tables assembled above remain complete at this point.
    default_half_points = max(2, round((document.defaultFont().pointSizeF() or 11.0) * 2))
    header = [
        "{\\rtf1\\ansi\\ansicpg1252\\deff0\\uc1",
        "".join(font_table),
        "".join(colour_table),
        "".join(list_table),
        "".join(override_table),
        f"\\f0\\fs{default_half_points}\\viewkind4\\widowctrl\n",
    ]
    return ("".join(header) + "".join(body) + "}").encode("ascii", errors="strict")



@dataclass(frozen=True)
class RtfImportResult:
    html: str
    automatic_foreground: str | None
    warnings: tuple[str, ...]
    document_properties: dict[str, int | bool]
    model: dict


def _rtf_document_properties(payload: bytes) -> dict[str, int | bool]:
    text = payload.decode("latin-1", errors="ignore")
    properties: dict[str, int | bool] = {}
    for key in ("paperw", "paperh", "margl", "margr", "margt", "margb"):
        match = re.search(rf"\\{key}(-?\d+)", text[:256_000])
        if match:
            value = max(0, min(int(match.group(1)), MAX_RTF_CONTROL_NUMBER))
            properties[key] = value
    if re.search(r"\\landscape(?:\D|$)", text[:256_000]):
        properties["landscape"] = True
    return properties


def _rtf_compatibility_warnings(payload: bytes) -> tuple[str, ...]:
    text = payload.decode("latin-1", errors="ignore").lower()
    checks = (
        (r"\\(?:object|objdata)\b", "Embedded OLE/object data"),
        (r"\\(?:header|headerl|headerr|headerf|footer|footerl|footerr|footerf)\b", "Headers or footers"),
        (r"\\footnote\b", "Footnotes/endnotes"),
        (r"\\annotation\b", "Comments/annotations"),
        (r"\\(?:shp|shpinst|do)\b", "Shapes/drawing objects"),
        (r"\\nesttableprops\b|\\nestcell\b|\\nestrow\b", "Nested tables"),
        (r"\\(?:revised|deleted|revauth|revdttm)\b", "Tracked revisions"),
        (r"\\(?:keep|keepn|widctlpar|nowidctlpar)\b", "Paragraph pagination/widow controls"),
        (r"\\(?:tx-?\d+|tb-?\d+|tqc|tqr|tqdec|tldot|tleq|tlhyph|tlth|tlul)\b", "Custom paragraph tab stops/leaders"),
        (r"\\(?:rtlpar|ltrpar)\b", "Explicit paragraph text direction"),
        (r"\\piccrop(?:l|r|t|b)-?\d+\b", "Cropped image geometry"),
    )
    return tuple(label for pattern, label in checks if re.search(pattern, text))


def decode_rtf(payload: bytes) -> RtfImportResult:
    html_value, automatic, model = rtf_to_html(
        payload, return_auto_foreground=True, return_model=True
    )
    return RtfImportResult(
        html=html_value,
        automatic_foreground=automatic,
        warnings=_rtf_compatibility_warnings(payload),
        document_properties=_rtf_document_properties(payload),
        model=model,
    )


def document_to_rtf_with_properties(document, properties=None) -> bytes:
    """Serialize canonical RTF and retain safe page geometry from imported RTF."""
    payload = document_to_rtf(document)
    props = dict(properties or {})
    controls = []
    for key in ("paperw", "paperh", "margl", "margr", "margt", "margb"):
        value = props.get(key)
        if isinstance(value, int) and 0 <= value <= MAX_RTF_CONTROL_NUMBER:
            controls.append(f"\\{key}{value}")
    if props.get("landscape") is True:
        controls.append("\\landscape")
    if not controls:
        return payload
    text = payload.decode("ascii", errors="strict")
    marker = "\\viewkind4\\widowctrl\n"
    if marker in text:
        text = text.replace(marker, "".join(controls) + marker, 1)
    return text.encode("ascii", errors="strict")
