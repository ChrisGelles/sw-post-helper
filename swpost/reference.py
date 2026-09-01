"""Pinned reference assembly verification."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DIR = REPO_ROOT / "reference"
CHECKSUMS_PATH = REFERENCE_DIR / "checksums.json"


class ReferenceChecksumError(RuntimeError):
    """Raised when a pinned reference file does not match its recorded digest."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_checksums() -> dict[str, str]:
    data = json.loads(CHECKSUMS_PATH.read_text(encoding="utf-8"))
    return dict(data["files"])


def verify_references(reference_dir: Path | None = None) -> dict[str, str]:
    """Verify pinned assemblies; return filename → digest map."""
    ref_dir = reference_dir or REFERENCE_DIR
    expected = load_checksums()
    actual: dict[str, str] = {}
    errors: list[str] = []

    for name, want in expected.items():
        path = ref_dir / name
        if not path.is_file():
            errors.append(f"missing reference file: {path}")
            continue
        got = sha256_file(path)
        actual[name] = got
        if got != want:
            errors.append(f"{name}: expected {want}, got {got}")

    if errors:
        msg = "Reference checksum mismatch:\n" + "\n".join(f"  - {e}" for e in errors)
        raise ReferenceChecksumError(msg)

    return actual
