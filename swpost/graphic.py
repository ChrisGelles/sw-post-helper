"""Essential Graphics Source Text blob encode/decode."""

from __future__ import annotations

import base64
import struct

HEADER_LEN = 376
TEXT_START = 380


def build_source_text(style_header: bytes, text: str, pad: int = 1200) -> bytes:
    t = text.encode("utf-8")
    h = bytearray(style_header[:HEADER_LEN])
    struct.pack_into("<I", h, 0, TEXT_START + ((len(t) - 11 + 3) // 4) * 4)
    return bytes(h) + struct.pack("<I", len(t)) + t + b"\0" * pad


def extract_source_text(blob: bytes) -> str:
    if len(blob) < TEXT_START + 4:
        return ""
    tlen = struct.unpack_from("<I", blob, HEADER_LEN)[0]
    raw = blob[TEXT_START : TEXT_START + tlen]
    return raw.split(b"\0", 1)[0].decode("utf-8")


def style_header_from_blob(blob: bytes) -> bytes:
    return blob[:HEADER_LEN]


def b64_decode_source_text(value: str) -> bytes:
    padded = value.strip()
    pad = (-len(padded)) % 4
    if pad:
        padded += "=" * pad
    return base64.b64decode(padded, validate=False)


def b64_encode_source_text(blob: bytes) -> str:
    return base64.b64encode(blob).decode("ascii")
