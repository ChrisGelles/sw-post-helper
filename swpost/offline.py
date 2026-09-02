"""Offline / synthetic clip passthrough for conform output."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from swpost.paths import (
    ASSET_ANIMATION,
    ASSET_CONCEPT,
    ASSET_GRAPHICS,
    ASSET_VO,
)
from swpost.relink import RelinkReport, resolve_media_path
from swpost.project import ProjectedPiece


@dataclass(frozen=True)
class OfflineClip:
    label: str
    track_name: str
    track_kind: str
    track_index: int
    timeline_start: int
    timeline_end: int
    source_in: int
    source_out: int
    filepath: str | None
    synthetic: bool
    output_role: str  # CARDS | VO
    destination_dir: str
    output_basename: str
    output_path: str


def _normalize_source_range(
    timeline_start: int,
    timeline_end: int,
    source_in: int,
    source_out: int,
) -> tuple[int, int]:
    """Premiere out is exclusive; timeline and source spans must match."""
    tl_len = timeline_end - timeline_start
    if source_out - source_in != tl_len:
        source_out = source_in + tl_len
    return source_in, source_out


def ascii_safe_basename(name: str) -> str:
    """Replace non [A-Za-z0-9._-] with hyphen; collapse runs."""
    out = re.sub(r"[^A-Za-z0-9._-]", "-", name)
    out = re.sub(r"-+", "-", out)
    return out.strip("-") or "offline-clip"


def _person_card_suffix(person: str | None) -> str:
    if not person or person == "Unknown":
        return ""
    return person.split()[0]


def person_under_cam_b(
    timeline_start: int,
    timeline_end: int,
    pieces: list[ProjectedPiece],
) -> str | None:
    return _cam_b_person_under(
        timeline_start,
        timeline_end,
        [p for p in pieces if p.role == "CAM_B"],
    )


def _cam_b_person_under(
    timeline_start: int,
    timeline_end: int,
    cam_b_pieces: list[ProjectedPiece],
) -> str | None:
    for piece in cam_b_pieces:
        if piece.timeline_start < timeline_end and piece.timeline_end > timeline_start:
            return piece.person
    return None


def assign_synthetic_offline_names(
    offline: list[OfflineClip],
    pieces: list[ProjectedPiece],
) -> list[OfflineClip]:
    """Sequential Card-/VO- names for synthetic offline; real paths unchanged."""
    cam_b = [p for p in pieces if p.role == "CAM_B"]
    ordered = sorted(offline, key=lambda c: (c.timeline_start, c.output_role))
    out: list[OfflineClip] = []
    card_seq = 0
    vo_seq = 0
    for clip in ordered:
        if not clip.synthetic:
            out.append(clip)
            continue
        role_prefix = "VO" if clip.output_role == "VO" else "Card"
        if clip.output_role == "VO":
            vo_seq += 1
            seq = vo_seq
        else:
            card_seq += 1
            seq = card_seq
        _, _, ext = classify_offline(clip.label, clip.filepath)
        person = _cam_b_person_under(clip.timeline_start, clip.timeline_end, cam_b)
        suffix = _person_card_suffix(person)
        stem = f"{role_prefix}-{seq:02d}-{suffix}" if suffix else f"{role_prefix}-{seq:02d}"
        basename = ascii_safe_basename(stem + ext)
        path = f"{clip.destination_dir.rstrip('/')}/{basename}"
        out.append(
            replace(
                clip,
                output_basename=basename,
                output_path=path,
            )
        )
    return out


def classify_offline(label: str, filepath: str | None) -> tuple[str, str, str]:
    """Return (output_role, destination_dir, extension)."""
    upper = label.upper()
    if "VO PICKUP" in upper:
        return "VO", ASSET_VO, ".wav"
    if "ANIM" in upper:
        return "CARDS", ASSET_ANIMATION, ".mov"
    if "NARRATOR" in upper or "CARD" in upper:
        return "CARDS", ASSET_GRAPHICS, ".png"
    return "CARDS", ASSET_CONCEPT, ".png"


def build_offline_clip(
    clip,
    *,
    relink_map: dict[str, str] | None = None,
    relink_report: RelinkReport | None = None,
) -> OfflineClip:
    """Build OfflineClip from a prproj TimelineClip."""
    role, dest_dir, ext = classify_offline(clip.label, clip.filepath)
    synthetic = not clip.filepath or clip.filepath.isdigit()
    src_in, src_out = _normalize_source_range(
        clip.timeline_start,
        clip.timeline_end,
        clip.source_in,
        clip.source_out,
    )
    if synthetic:
        placeholder = f"placeholder{ext}"
        out_name = placeholder
        out_path = f"{dest_dir.rstrip('/')}/{placeholder}"
    else:
        resolved = resolve_media_path(clip.filepath, relink_map or {}, relink_report)
        if resolved:
            out_path = resolved
            out_name = out_path.rsplit("/", 1)[-1]
        else:
            out_name = f"offline{ext}"
            out_path = f"{dest_dir.rstrip('/')}/{out_name}"
            synthetic = True
    return OfflineClip(
        label=clip.label,
        track_name=clip.track_name,
        track_kind=clip.track_kind,
        track_index=clip.track_index,
        timeline_start=clip.timeline_start,
        timeline_end=clip.timeline_end,
        source_in=src_in,
        source_out=src_out,
        filepath=clip.filepath,
        synthetic=synthetic,
        output_role=role,
        destination_dir=dest_dir,
        output_basename=out_name,
        output_path=out_path,
    )


def extract_offline_clips(
    sequence,
    *,
    relink_map: dict[str, str] | None = None,
    relink_report: RelinkReport | None = None,
) -> list[OfflineClip]:
    """Non-proxy timeline clips preserved as offline passthrough."""
    out: list[OfflineClip] = []
    for clip in sequence.clips:
        if clip.proxy_basename:
            continue
        out.append(
            build_offline_clip(
                clip,
                relink_map=relink_map,
                relink_report=relink_report,
            )
        )
    return sorted(out, key=lambda c: (c.timeline_start, c.output_role))
