"""Basename relink map from pinned stringout assemblies."""

from __future__ import annotations

import os
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from swpost.paths import canon
from swpost.reference import REFERENCE_DIR


@dataclass
class RelinkReport:
    applied: list[dict[str, str]] = field(default_factory=list)
    unresolved: list[dict[str, str]] = field(default_factory=list)


def _basename_from_pathurl(pathurl: str) -> str:
    path = urllib.parse.unquote(pathurl.replace("file://localhost", ""))
    return path.rsplit("/", 1)[-1]


def build_basename_relink_map(reference_dir: Path | None = None) -> dict[str, str]:
    """Case-insensitive basename → canonical /Volumes/SW_SERIES/… path."""
    ref = reference_dir or REFERENCE_DIR
    paths = (
        ref / "CMNH-SW-stringout-ref-270.xml",
        ref / "081026-Stringout-Source-v02-cg.xml",
        ref / "081026-Stringout-Source-v03-cg.xml",
    )
    out: dict[str, str] = {}
    for xml_path in paths:
        root = ET.parse(xml_path).getroot()
        for file_el in root.iter("file"):
            pathurl = file_el.findtext("pathurl")
            if not pathurl:
                continue
            raw = urllib.parse.unquote(pathurl.replace("file://localhost", ""))
            try:
                canonical = canon(raw)
            except ValueError:
                continue
            basename = _basename_from_pathurl(pathurl)
            out[basename.lower()] = canonical
    return out


def resolve_media_path(
    filepath: str | None,
    relink_map: dict[str, str],
    report: RelinkReport | None = None,
) -> str | None:
    """Resolve a media path via canon() or basename relink; None if unresolved."""
    if not filepath or filepath.isdigit():
        return None
    normalized = filepath.replace("\\", "/")
    try:
        return canon(normalized)
    except ValueError:
        pass
    basename = os.path.basename(normalized)
    key = basename.lower()
    canonical = relink_map.get(key)
    if canonical:
        if report is not None:
            report.applied.append(
                {"basename": basename, "from_path": filepath, "to_path": canonical}
            )
        return canonical
    if report is not None:
        report.unresolved.append({"basename": basename, "from_path": filepath})
    return None
