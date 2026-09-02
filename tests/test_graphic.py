"""Tests for graphic Source Text blob round-trip."""

from __future__ import annotations

import struct
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from swpost.graphic import (
    HEADER_LEN,
    TEXT_START,
    b64_decode_source_text,
    build_source_text,
    extract_source_text,
    style_header_from_blob,
)

EP02_REF = Path(
    "/Volumes/SW_SERIES/01_ProjectFiles/04_Premiere/_Episodes/ep02-physics/XMLs/STEM-ep02-conform-v06-cl.xml"
)


def _reference_blobs() -> list[bytes]:
    if not EP02_REF.is_file():
        pytest.skip("ep02 reference conform XML not available")
    root = ET.parse(EP02_REF).getroot()
    blobs: list[bytes] = []
    for eff in root.iter("effect"):
        if eff.findtext("effectid") != "GraphicAndType":
            continue
        for param in eff.findall("parameter"):
            if param.findtext("name") != "Source Text":
                continue
            val = param.findtext("value") or ""
            if not val.strip():
                continue
            try:
                blobs.append(b64_decode_source_text(val))
            except Exception:
                continue
    return blobs


def test_build_source_text_round_trip_ep02_reference():
    blobs = _reference_blobs()
    assert len(blobs) == 24
    header = style_header_from_blob(blobs[0])
    for orig in blobs:
        text = extract_source_text(orig)
        tlen = struct.unpack_from("<I", orig, HEADER_LEN)[0]
        tail = orig[TEXT_START + tlen :]
        pad = len(tail)
        rebuilt = build_source_text(header, text, pad=pad)
        assert extract_source_text(rebuilt) == text
        assert struct.unpack_from("<I", rebuilt, 0)[0] == struct.unpack_from("<I", orig, 0)[0]


def test_extract_short_card_text():
    blobs = _reference_blobs()
    assert extract_source_text(blobs[0]) == "ON-SCREEN: "
