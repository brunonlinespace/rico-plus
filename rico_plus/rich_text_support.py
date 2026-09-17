#!/usr/bin/env python3
"""Safe rich-text helpers used by Ricopad's RTF editor."""
from __future__ import annotations
import base64
import html as html_module
import re

MAX_DATA_IMAGE_BYTES = 12 * 1024 * 1024
MAX_DATA_IMAGE_PIXELS = 40_000_000
_DANGEROUS_BLOCK_RE = re.compile(r"<\s*(script|iframe|object|embed|form|input|button|base|link)\b[^>]*>.*?<\s*/\s*\1\s*>|<\s*(script|iframe|object|embed|form|input|button|base|link)\b[^>]*/?\s*>", re.I|re.S)
_EVENT_ATTRIBUTE_RE = re.compile(r"\s+on[a-zA-Z]+\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+)", re.I)
_META_REFRESH_RE = re.compile(r"<meta\b[^>]*http-equiv\s*=\s*([\"'])?refresh\1?[^>]*>", re.I)
_RESOURCE_ATTRIBUTE_RE = re.compile(r"\s+(src|href|background)\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))", re.I|re.S)
_CSS_URL_RE = re.compile(r"url\s*\([^)]*\)", re.I|re.S)
_CSS_IMPORT_RE = re.compile(r"@import\b[^;}]*(?:;|(?=}))", re.I|re.S)
_SAFE_DATA_IMAGE_RE = re.compile(r"^data:image/(png|jpeg|jpg);base64,([A-Za-z0-9+/=\s]+)$", re.I)
_SAFE_LINK_SCHEMES = {"http","https","mailto"}

def is_safe_link_target(value: str) -> bool:
    target=html_module.unescape(str(value)).strip()
    if not target or any(ord(ch)<32 for ch in target): return False
    if target.startswith("#"): return True
    if target.startswith("//"): return False
    match=re.match(r"^([A-Za-z][A-Za-z0-9+.-]*):",target)
    return match is None or match.group(1).lower() in _SAFE_LINK_SCHEMES

def _raster_dimensions(payload: bytes, subtype: str):
    subtype=str(subtype).lower()
    if subtype=="png":
        if len(payload)>=24 and payload.startswith(b"\x89PNG\r\n\x1a\n") and payload[12:16]==b"IHDR": return int.from_bytes(payload[16:20],"big"),int.from_bytes(payload[20:24],"big")
        return None
    if subtype in {"jpeg","jpg"} and payload.startswith(b"\xff\xd8"):
        markers={0xC0,0xC1,0xC2,0xC3,0xC5,0xC6,0xC7,0xC9,0xCA,0xCB,0xCD,0xCE,0xCF}; i=2
        while i+3<len(payload):
            if payload[i]!=0xFF: i+=1; continue
            while i<len(payload) and payload[i]==0xFF: i+=1
            if i>=len(payload): break
            marker=payload[i]; i+=1
            if marker in {0x01,*range(0xD0,0xDA)}: continue
            if i+2>len(payload): break
            length=int.from_bytes(payload[i:i+2],"big")
            if length<2 or i+length>len(payload): break
            if marker in markers and length>=7: return int.from_bytes(payload[i+5:i+7],"big"),int.from_bytes(payload[i+3:i+5],"big")
            i+=length
    return None

def _safe_data_image_target(value: str) -> bool:
    match=_SAFE_DATA_IMAGE_RE.fullmatch(str(value).strip())
    if match is None: return False
    encoded=re.sub(r"\s+","",match.group(2))
    if len(encoded)>((MAX_DATA_IMAGE_BYTES+2)//3)*4+4: return False
    try: payload=base64.b64decode(encoded,validate=True)
    except (ValueError,TypeError): return False
    if not payload or len(payload)>MAX_DATA_IMAGE_BYTES: return False
    dim=_raster_dimensions(payload,match.group(1))
    if dim is None: return False
    w,h=dim
    return 0<w<=MAX_DATA_IMAGE_PIXELS and 0<h<=MAX_DATA_IMAGE_PIXELS and w*h<=MAX_DATA_IMAGE_PIXELS

def _sanitise_resource_attribute(match):
    attribute=match.group(1).lower(); value=next((item for item in match.groups()[1:] if item is not None),"").strip()
    if attribute=="background": return ""
    if attribute=="src":
        if not _safe_data_image_target(value): return ""
    elif not is_safe_link_target(value): return ""
    return f' {attribute}="{html_module.escape(value,quote=True)}"'

def sanitise_qt_html(value: str) -> str:
    value=str(value); value=_DANGEROUS_BLOCK_RE.sub("",value); value=_EVENT_ATTRIBUTE_RE.sub("",value); value=_META_REFRESH_RE.sub("",value); value=_CSS_IMPORT_RE.sub("",value); value=_CSS_URL_RE.sub("",value); return _RESOURCE_ATTRIBUTE_RE.sub(_sanitise_resource_attribute,value)
