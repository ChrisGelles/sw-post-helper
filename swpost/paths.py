"""Canonical paths and constants — confirmed 2026-09-01 recon."""

from __future__ import annotations

import os
import urllib.parse

VOLUME_ROOT = "/Volumes/SW_SERIES"

# Proxy registry: basename -> metadata. Match basename case-sensitively.
PROXY_REGISTRY: dict[str, dict] = {
    "270p.mp4": {
        "path": f"{VOLUME_ROOT}/04_Renders/04_Premiere/footage/proxy/270p.mp4",
        "shoot": "june",
        "width": 480,
        "height": 270,
        "scale_1080": 400,
    },
    "SW-06.2026__stringout_01.mp4": {
        "path": f"{VOLUME_ROOT}/04_Renders/04_Premiere/SW-06.2026__stringout_01.mp4",
        "shoot": "june",
        "width": 960,
        "height": 540,
        "scale_1080": 200,
    },
    "081026-stringout.mp4": {
        "path": f"{VOLUME_ROOT}/04_Renders/04_Premiere/footage/1080p/081026-stringout.mp4",
        "shoot": "aug10",
        "width": 1920,
        "height": 1080,
        "scale_1080": None,
    },
    "CMNH-081026-stringout_02.mp4": {
        "path": f"{VOLUME_ROOT}/04_Renders/04_Premiere/CMNH-081026-stringout_02.mp4",
        "shoot": "aug10",
        "width": 1920,
        "height": 1080,
        "scale_1080": None,
    },
}

PROXY_CAMERA_DATES = ("2026-05-27", "2026-06-09", "2026-06-10", "2026-08-10")
RAW_AUDIO_DATES = ("2026.05.27", "2026.06.09", "2026.08.10", "2026.09.10")

ASSET_VO = f"{VOLUME_ROOT}/02_Assets/02_Audio/04_VO/temp VO"
ASSET_CONCEPT = f"{VOLUME_ROOT}/02_Assets/03_Images/_ConceptArt"
ASSET_ANIMATION = f"{VOLUME_ROOT}/02_Assets/04_Graphics/03_Animation"
ASSET_GRAPHICS = f"{VOLUME_ROOT}/02_Assets/04_Graphics"

CONFORM_OUTPUT_DIR = (
    f"{VOLUME_ROOT}/01_ProjectFiles/05_XMLs/_conform"
)

FORBIDDEN_PATHURL_FRAGMENTS = ("CloudStorage", "Macintosh", "Dropbox", "..")

TICKS_PER_FRAME = 10_594_584_000


def canon(path: str) -> str:
    """Rewrite any SW_SERIES path to /Volumes/SW_SERIES/… without resolving symlinks."""
    path = urllib.parse.unquote(path).replace("file://localhost", "")
    path = os.path.normpath(path)
    marker = "SW_SERIES/"
    i = path.find(marker)
    if i < 0:
        raise ValueError(f"path is not under SW_SERIES: {path}")
    return VOLUME_ROOT + "/" + path[i + len(marker) :]


def proxy_basename(path: str | None) -> str | None:
    if not path:
        return None
    base = os.path.basename(path.replace("\\", "/"))
    return base if base in PROXY_REGISTRY else None


def require_volume() -> None:
    if not os.path.lexists(VOLUME_ROOT):
        raise SystemExit(
            f"{VOLUME_ROOT} is not present. Create the SW_SERIES symlink before running sw-conform."
        )
    if not (os.path.islink(VOLUME_ROOT) or os.path.ismount(VOLUME_ROOT)):
        raise SystemExit(
            f"{VOLUME_ROOT} exists but is neither a symlink nor a mount. "
            "Fix the workstation setup before running sw-conform."
        )
