"""Basename relink map from pinned stringout assemblies."""

from __future__ import annotations

import glob
import os
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from swpost.paths import ASSET_VO, VOLUME_ROOT, canon
from swpost.reference import REFERENCE_DIR

# Team Elevate shared-post volume (see premiere-vendor-relink-mapping-v01-cu.md).
VENDOR_ROOTS = (
    "/Volumes/projects/POST PRODUCTION PROJECTS/CMNH/",
)

# Vendor tree variants → canonical SW_SERIES layout.
_VENDOR_SUFFIX_REWRITES = (
    ("02_Assets/01_Video/02_Acquired/PROXIES/", "02_Assets/01_Video/01_Footage/PROXIES/"),
    ("02_Assets/01_Video/02_Acquired/RENDERS/", "04_Renders/04_Premiere/"),
)


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


def _rewrite_vendor_suffix(suffix: str) -> str:
    out = suffix
    for old, new in _VENDOR_SUFFIX_REWRITES:
        if old in out:
            out = out.replace(old, new, 1)
    return out


def _resolve_vendor_path(normalized: str) -> str | None:
    for root in VENDOR_ROOTS:
        if not normalized.startswith(root):
            continue
        suffix = _rewrite_vendor_suffix(normalized[len(root) :].lstrip("/"))
        candidate = f"{VOLUME_ROOT}/{suffix}"
        if os.path.isfile(candidate):
            return candidate
    return None


def _resolve_by_basename_search(basename: str) -> str | None:
    """Find a unique file under SW_SERIES by basename (case-insensitive)."""
    if not basename:
        return None
    patterns = (
        f"{VOLUME_ROOT}/02_Assets/**/{basename}",
        f"{VOLUME_ROOT}/04_Renders/**/{basename}",
    )
    matches: list[str] = []
    for pattern in patterns:
        matches.extend(p for p in glob.glob(pattern, recursive=True) if os.path.isfile(p))
    if not matches:
        lower = basename.lower()
        for pattern in patterns:
            for path in glob.glob(pattern, recursive=True):
                if os.path.isfile(path) and os.path.basename(path).lower() == lower:
                    matches.append(path)
    unique = sorted(set(matches))
    if len(unique) == 1:
        return unique[0]
    if len(unique) > 1:
        exact = [p for p in unique if os.path.basename(p) == basename]
        if len(exact) == 1:
            return exact[0]
    return None


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
    vendor = _resolve_vendor_path(normalized)
    if vendor:
        if report is not None:
            report.applied.append(
                {"basename": basename, "from_path": filepath, "to_path": vendor}
            )
        return vendor
    key = basename.lower()
    canonical = relink_map.get(key)
    if canonical:
        if report is not None:
            report.applied.append(
                {"basename": basename, "from_path": filepath, "to_path": canonical}
            )
        return canonical
    if "02_Audio/04_VO/" in normalized:
        temp_vo = f"{ASSET_VO.rstrip('/')}/{basename}"
        if report is not None:
            report.applied.append(
                {
                    "basename": basename,
                    "from_path": filepath,
                    "to_path": temp_vo,
                }
            )
        return temp_vo
    searched = _resolve_by_basename_search(basename)
    if searched:
        if report is not None:
            report.applied.append(
                {"basename": basename, "from_path": filepath, "to_path": searched}
            )
        return searched
    if report is not None:
        report.unresolved.append({"basename": basename, "from_path": filepath})
    return None
