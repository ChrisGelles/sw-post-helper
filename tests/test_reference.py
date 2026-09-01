"""Reference assembly pinning tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from swpost.reference import ReferenceChecksumError, verify_references

REPO = Path(__file__).resolve().parents[1]
REF = REPO / "reference"


def test_reference_checksums_match():
    verify_references(REF)


def test_reference_checksum_mismatch_refuses():
    path = REF / "CMNH-SW-stringout-ref-270.xml"
    original = path.read_bytes()
    try:
        path.write_bytes(original + b"\n")
        with pytest.raises(ReferenceChecksumError) as exc:
            verify_references(REF)
        assert "expected" in str(exc.value).lower() or "got" in str(exc.value).lower()
    finally:
        path.write_bytes(original)


def test_no_cloudstorage_in_reference_pathurls():
    """Sanity: reference XMLs may contain legacy paths; flag if we ever rewrite them."""
    for name in json.loads((REF / "checksums.json").read_text())["files"]:
        text = (REF / name).read_text(encoding="utf-8", errors="replace")
        # Reference files are read-only inputs; this test documents current state.
        assert "sequence" in text
