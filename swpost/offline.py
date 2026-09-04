"""Offline / synthetic clip passthrough for conform output."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, replace
from pathlib import Path

from swpost.paths import (
    ASSET_ANIMATION,
    ASSET_CONCEPT,
    ASSET_GRAPHICS,
    ASSET_VO,
    canon,
)
from swpost.relink import RelinkReport, resolve_media_path
from swpost.project import ProjectedPiece


@dataclass(frozen=True)
class OfflineClip:
    clip_id: str
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
    empty_graphic: bool
    output_role: str  # CARDS | VO | PASSTHROUGH
    destination_dir: str
    output_basename: str
    output_path: str
    media_key: str = ""


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
    """Sequential VO- names for synthetic VO clips; real paths unchanged."""
    cam_b = [p for p in pieces if p.role == "CAM_B"]
    ordered = sorted(offline, key=lambda c: (c.timeline_start, c.output_role))
    out: list[OfflineClip] = []
    vo_seq = 0
    for clip in ordered:
        if clip.empty_graphic or not clip.synthetic:
            out.append(clip)
            continue
        if clip.output_role != "VO":
            out.append(clip)
            continue
        vo_seq += 1
        _, _, ext = classify_offline(clip.label, clip.filepath)
        person = _cam_b_person_under(clip.timeline_start, clip.timeline_end, cam_b)
        suffix = _person_card_suffix(person)
        stem = f"VO-{vo_seq:02d}-{suffix}" if suffix else f"VO-{vo_seq:02d}"
        basename = ascii_safe_basename(stem + ext)
        path = f"{clip.destination_dir.rstrip('/')}/{basename}"
        out.append(
            replace(
                clip,
                output_basename=basename,
                output_path=path,
                media_key=path,
            )
        )
    return out


def classify_offline(label: str, filepath: str | None) -> tuple[str, str, str]:
    """Return (output_role, destination_dir, extension). Unknown labels are UNCLASSIFIED."""
    upper = label.upper()
    if "VO PICKUP" in upper:
        return "VO", ASSET_VO, ".wav"
    if "ANIM" in upper:
        return "CARDS", ASSET_ANIMATION, ".mov"
    if any(
        token in upper
        for token in ("NARRATOR", "NARRATION", "ON-SCREEN", "CARD")
    ):
        return "CARDS", ASSET_GRAPHICS, ".png"
    if upper == "GRAPHIC":
        return "PASSTHROUGH", ASSET_GRAPHICS, ".png"
    if "bg for gfx" in label.lower():
        return "PASSTHROUGH", ASSET_GRAPHICS, ".png"
    if filepath and not filepath.isdigit():
        ext = Path(filepath).suffix if Path(filepath).suffix else ""
        return "PASSTHROUGH", "", ext
    return "UNCLASSIFIED", "", ""


def card_text_from_label(label: str) -> str | None:
    """Marker text usable for Essential Graphics synthesis."""
    upper = label.upper()
    if any(
        token in upper
        for token in ("NARRATOR", "NARRATION", "ON-SCREEN", "CARD", "ANIM")
    ):
        return label.strip()
    return None


def _unresolved_output_path(normalized: str, dest_dir: str, basename: str) -> str:
    if "SW_SERIES/" in normalized:
        try:
            return canon(normalized)
        except ValueError:
            pass
    if dest_dir:
        return f"{dest_dir.rstrip('/')}/{basename}"
    return normalized


def build_offline_clip(
    clip,
    *,
    clip_id: str = "",
    relink_map: dict[str, str] | None = None,
    relink_report: RelinkReport | None = None,
) -> OfflineClip:
    """Build OfflineClip from a prproj TimelineClip."""
    role, dest_dir, ext = classify_offline(clip.label, clip.filepath)
    if role == "UNCLASSIFIED":
        raise ValueError(
            f"offline clip {clip.label!r} is UNCLASSIFIED; ledger should have stopped earlier"
        )
    if role == "PASSTHROUGH" and not dest_dir:
        dest_dir = ASSET_GRAPHICS
    synthetic = not clip.filepath or clip.filepath.isdigit()
    empty_graphic = (
        synthetic
        and clip.track_kind == "video"
        and role == "PASSTHROUGH"
    )
    src_in, src_out = _normalize_source_range(
        clip.timeline_start,
        clip.timeline_end,
        clip.source_in,
        clip.source_out,
    )
    if empty_graphic:
        out_name = ""
        out_path = ""
        media_key = ""
    elif synthetic:
        placeholder = f"placeholder{ext}"
        out_name = placeholder
        out_path = f"{dest_dir.rstrip('/')}/{placeholder}"
        media_key = "" if empty_graphic else out_path
    else:
        normalized = clip.filepath.replace("\\", "/")
        out_name = os.path.basename(normalized)
        resolved = resolve_media_path(clip.filepath, relink_map or {}, relink_report)
        if resolved:
            out_path = resolved
            media_key = resolved
        else:
            out_path = _unresolved_output_path(normalized, dest_dir, out_name)
            media_key = normalized
    return OfflineClip(
        clip_id=clip_id or getattr(clip, "clip_id", "") or "",
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
        empty_graphic=empty_graphic,
        output_role=role,
        destination_dir=dest_dir,
        output_basename=out_name,
        output_path=out_path,
        media_key=media_key,
    )


def extract_offline_clips(
    entries,
    *,
    relink_map: dict[str, str] | None = None,
    relink_report: RelinkReport | None = None,
) -> list[OfflineClip]:
    """Passthrough and card-placeholder clips from ledger entries (never projected)."""
    from swpost.ledger import LedgerEntry

    out: list[OfflineClip] = []
    for entry in entries:
        if not isinstance(entry, LedgerEntry):
            raise TypeError("extract_offline_clips expects LedgerEntry items")
        out.append(
            build_offline_clip(
                entry.clip,
                clip_id=entry.clip_id,
                relink_map=relink_map,
                relink_report=relink_report,
            )
        )
    return sorted(out, key=lambda c: (c.timeline_start, c.output_role))


def is_camera_mov(basename: str) -> bool:
    if not basename.lower().endswith(".mov"):
        return False
    stem = basename.split("_")[0]
    return len(stem) >= 2 and stem[0] in "AB" and stem[1].isdigit()


def _timeline_overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end


def drop_embedded_camera_audio(
    offline: list[OfflineClip],
    *,
    dropped: list[dict[str, str | int]] | None = None,
    dropped_clip_ids: set[str] | None = None,
) -> list[OfflineClip]:
    """Drop passthrough camera .mov audio when field recordings cover the same range."""
    picture_cameras = {
        clip.output_basename.lower()
        for clip in offline
        if clip.track_kind == "video"
        and clip.output_basename
        and is_camera_mov(clip.output_basename)
    }
    if not picture_cameras:
        return offline

    field_clips = [
        clip
        for clip in offline
        if clip.track_kind == "audio"
        and clip.output_basename
        and not is_camera_mov(clip.output_basename)
    ]

    def field_covers(tl_start: int, tl_end: int) -> bool:
        return any(
            _timeline_overlaps(tl_start, tl_end, field.timeline_start, field.timeline_end)
            for field in field_clips
        )

    kept: list[OfflineClip] = []
    for clip in offline:
        if (
            clip.track_kind == "audio"
            and clip.output_basename
            and is_camera_mov(clip.output_basename)
            and clip.output_basename.lower() in picture_cameras
            and field_covers(clip.timeline_start, clip.timeline_end)
        ):
            if dropped_clip_ids is not None and clip.clip_id:
                dropped_clip_ids.add(clip.clip_id)
            if dropped is not None:
                dropped.append(
                    {
                        "basename": clip.output_basename,
                        "timeline_start": clip.timeline_start,
                        "timeline_end": clip.timeline_end,
                        "source_in": clip.source_in,
                        "source_out": clip.source_out,
                        "track_index": clip.track_index,
                        "clip_id": clip.clip_id,
                    }
                )
            continue
        kept.append(clip)
    return kept


def assert_offline_file_ids_distinct_sources(offline: list[OfflineClip]) -> None:
    """No file id may aggregate clipitems from different source paths."""
    from swpost.fcpxml import file_id_for_media_key

    by_fid: dict[str, set[str]] = {}
    for clip in offline:
        if clip.empty_graphic or not clip.media_key:
            continue
        fid = file_id_for_media_key(clip.media_key)
        source = (clip.filepath or clip.media_key).replace("\\", "/")
        by_fid.setdefault(fid, set()).add(source)
    conflicts = {fid: sources for fid, sources in by_fid.items() if len(sources) > 1}
    if conflicts:
        detail = "; ".join(
            f"{fid} ← {sorted(sources)!r}" for fid, sources in sorted(conflicts.items())
        )
        raise ValueError(
            "offline file id shared by clipitems from different source paths: " + detail
        )
