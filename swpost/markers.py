"""DVAMarker comment extraction from Premiere .prproj."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from swpost.prproj import TimelineClip, ticks_to_frames


@dataclass(frozen=True)
class DvaMarker:
    name: str
    comment: str
    start_frame: int


def load_dva_markers(root: ET.Element) -> list[DvaMarker]:
    markers: list[DvaMarker] = []
    seen: set[tuple[str, int, str]] = set()
    for el in root.iter("DVAMarker"):
        txt = el.text or ""
        if not txt.strip().startswith("{"):
            continue
        try:
            payload = json.loads(txt)
        except json.JSONDecodeError:
            continue
        inner = payload.get("DVAMarker", payload)
        name = (inner.get("mName") or inner.get("Name") or "").strip()
        comment = (inner.get("mComment") or inner.get("Comment") or "").strip()
        if not comment:
            continue
        ticks = inner.get("mStartTime", {}).get("ticks", 0)
        frame = ticks_to_frames(ticks)
        key = (name, frame, comment)
        if key in seen:
            continue
        seen.add(key)
        markers.append(DvaMarker(name=name, comment=comment, start_frame=frame))
    return sorted(markers, key=lambda m: (m.start_frame, m.name))


def _is_stub_comment(comment: str) -> bool:
    stripped = comment.strip().rstrip(":")
    upper = stripped.upper()
    return upper in {"ON-SCREEN", "NARRATION", "NARRATOR", "ANIM", "CARD"}


def _comment_matches_clip(marker: DvaMarker, clip: TimelineClip) -> bool:
    label = clip.label.strip()
    comment = marker.comment.strip()
    if not label or not comment or _is_stub_comment(comment):
        return False
    probe = min(40, len(label), len(comment))
    if probe < 15:
        return False
    return comment.startswith(label[:probe]) or label.startswith(comment[:probe])


def _usable_card_marker(marker: DvaMarker) -> bool:
    if marker.name.startswith("CARD"):
        return not _is_stub_comment(marker.comment)
    upper = marker.comment.upper()
    return any(token in upper for token in ("NARRATOR", "NARRATION", "ON-SCREEN", "ANIM"))


def _marker_score(marker: DvaMarker, clip: TimelineClip) -> tuple[int, int, int]:
    """Higher is better: label/comment agreement, anchor position, length."""
    prefix = int(_comment_matches_clip(marker, clip))
    in_span = int(clip.timeline_start <= marker.start_frame < clip.timeline_end)
    at_start = int(abs(marker.start_frame - clip.timeline_start) <= 2)
    near = int(clip.timeline_start - 120 <= marker.start_frame < clip.timeline_end + 30)
    return (prefix * 10 + at_start * 4 + in_span * 2 + near, len(marker.comment), -abs(marker.start_frame - clip.timeline_start))


def marker_text_for_clip(clip: TimelineClip, markers: list[DvaMarker]) -> str | None:
    """Return the best marker comment anchoring this clip."""
    if not markers:
        return None

    candidates = [m for m in markers if _usable_card_marker(m) and not _is_stub_comment(m.comment)]
    if not candidates:
        return None

    scored: list[tuple[tuple[int, int, int], DvaMarker]] = []
    for marker in candidates:
        score = _marker_score(marker, clip)
        if score[0] > 0 or _comment_matches_clip(marker, clip):
            scored.append((score, marker))

    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1].comment
