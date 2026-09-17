#!/usr/bin/env python3
"""Optional external RTF interoperability gate using a host LibreOffice/soffice.

The gate validates semantics in LibreOffice's generated ODT rather than depending
on one exact XML spelling.  LibreOffice releases may serialise logical right
alignment as either ``end`` or ``right`` while preserving the same layout.
"""
from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
import tempfile
import urllib.parse
import zipfile
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
CORPUS = pathlib.Path(__file__).resolve().parent / "rtf-corpus"

NS = {
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "style": "urn:oasis:names:tc:opendocument:xmlns:style:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "fo": "urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0",
    "svg": "urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0",
}

def q(prefix: str, name: str) -> str:
    return f"{{{NS[prefix]}}}{name}"


def require(value, message):
    if not value:
        raise AssertionError(message)

soffice = shutil.which("soffice") or shutil.which("libreoffice")
if not soffice:
    print("SKIP: LibreOffice interoperability QA (soffice/libreoffice not installed)")
    raise SystemExit(0)

lists_payload = (CORPUS / "lists.rtf").read_bytes()
for token in (b"\\listtable", b"\\listoverridetable", b"\\levelnfc23", b"\\levelnfc0", b"\\ilvl0", b"\\ls1", b"\\ls2"):
    require(token in lists_payload, f"standards-based list corpus is missing {token!r}")


def convert_to_odt(source: pathlib.Path, output: pathlib.Path, profile: pathlib.Path) -> pathlib.Path:
    output.mkdir(parents=True, exist_ok=True)
    profile.mkdir(parents=True, exist_ok=True)
    profile_uri = "file://" + urllib.parse.quote(str(profile.resolve()))
    completed = subprocess.run(
        [soffice, f"-env:UserInstallation={profile_uri}", "--headless", "--convert-to", "odt", "--outdir", str(output), str(source)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=60,
        check=False,
    )
    target = output / (source.stem + ".odt")
    require(completed.returncode == 0 and target.is_file(), f"LibreOffice conversion failed for {source.name}: {completed.stdout} {completed.stderr}")
    return target


def odt_members(path: pathlib.Path) -> tuple[str, ET.Element, ET.Element | None]:
    with zipfile.ZipFile(path) as archive:
        content_bytes = archive.read("content.xml")
        styles_bytes = archive.read("styles.xml") if "styles.xml" in archive.namelist() else None
    content_xml = content_bytes.decode("utf-8", errors="strict")
    content_root = ET.fromstring(content_bytes)
    styles_root = ET.fromstring(styles_bytes) if styles_bytes is not None else None
    return content_xml, content_root, styles_root


def style_index(*roots: ET.Element | None) -> dict[str, ET.Element]:
    result: dict[str, ET.Element] = {}
    for root in roots:
        if root is None:
            continue
        for node in root.findall(".//style:style", NS):
            name = node.get(q("style", "name"))
            if name:
                result[name] = node
    return result


def resolved_properties(styles: dict[str, ET.Element], style_name: str | None, property_tag: str) -> dict[str, str]:
    """Resolve a style's inherited ODF property attributes, child overriding parent."""
    chain: list[ET.Element] = []
    seen: set[str] = set()
    name = style_name
    while name and name not in seen:
        seen.add(name)
        node = styles.get(name)
        if node is None:
            break
        chain.append(node)
        name = node.get(q("style", "parent-style-name"))
    result: dict[str, str] = {}
    for node in reversed(chain):
        props = node.find(f"style:{property_tag}", NS)
        if props is not None:
            result.update(props.attrib)
    return result


def clean_font_family(value: str | None) -> str:
    if not value:
        return ""
    return value.strip().strip("'\"").replace("&apos;", "'").strip("'")


def validate_default_document(odt_path: pathlib.Path) -> None:
    _content_xml, content_root, styles_root = odt_members(odt_path)
    styles = style_index(styles_root, content_root)

    paragraph = None
    for candidate in content_root.findall(".//text:p", NS):
        if "".join(candidate.itertext()).strip() == "Default test":
            paragraph = candidate
            break
    require(paragraph is not None, "LibreOffice default-document import lost the test paragraph")

    paragraph_style = paragraph.get(q("text", "style-name"))
    paragraph_props = resolved_properties(styles, paragraph_style, "paragraph-properties")
    alignment = paragraph_props.get(q("fo", "text-align"), "").lower()
    require(alignment in {"end", "right"}, f"LibreOffice did not preserve the default-document right alignment (reported {alignment!r})")
    require(paragraph_props.get(q("fo", "line-height")) == "200%", "LibreOffice did not preserve the default-document 2.0 line spacing")

    span = next((node for node in paragraph.findall(".//text:span", NS) if "Default test" in "".join(node.itertext())), None)
    text_style = span.get(q("text", "style-name")) if span is not None else None
    text_props = resolved_properties(styles, text_style, "text-properties")
    if not text_props:
        # Some LibreOffice versions place character properties on the paragraph style.
        text_props = resolved_properties(styles, paragraph_style, "text-properties")

    family = clean_font_family(text_props.get(q("fo", "font-family")))
    require(family == "Noto Serif", f"LibreOffice did not preserve the exact default-document font family (reported {family!r})")
    require(text_props.get(q("fo", "font-size")) == "18pt", "LibreOffice did not preserve the default-document 18 pt size")
    require(text_props.get(q("fo", "font-weight"), "").lower() == "bold", "LibreOffice did not preserve the default-document bold style")


with tempfile.TemporaryDirectory(prefix="ricopad-lo-interop-") as temp:
    temp_path = pathlib.Path(temp)
    lists_xml, _lists_root, _lists_styles = odt_members(convert_to_odt(CORPUS / "lists.rtf", temp_path / "lists", temp_path / "profile-lists"))
    require(len(re.findall(r"<text:list(?:\s|>)", lists_xml)) >= 2, "LibreOffice did not import Ricopad's standard RTF as real list objects")
    require(lists_xml.count("<text:list-item") >= 4, "LibreOffice did not import all bullet/external-decimal list items")
    for phrase in ("Bullet one", "Bullet two", "Number one", "Number two"):
        require(phrase in lists_xml, f"LibreOffice list import lost {phrase!r}")

    defaults_odt = convert_to_odt(CORPUS / "new-document-defaults.rtf", temp_path / "defaults", temp_path / "profile-defaults")
    validate_default_document(defaults_odt)

print("PASS: LibreOffice RTF interoperability QA (standard lists + exact default-document formatting)")
