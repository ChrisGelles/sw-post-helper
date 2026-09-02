"""Trim overlapping timeline clipitems (Premiere transition handles)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

T = TypeVar("T")


@dataclass
class OverlapTrim:
    track: str
    clip_name: str
    old_end: int
    new_end: int


def trim_track_overlaps(
    clips: list[T],
    *,
    track_label: str,
    get_start: Callable[[T], int],
    get_end: Callable[[T], int],
    set_end: Callable[[T, int], None],
    set_out: Callable[[T, int], None],
    get_source_in: Callable[[T], int],
    get_name: Callable[[T], str],
) -> tuple[list[T], list[OverlapTrim]]:
    """Sort by start; shorten earlier clip when end exceeds next start."""
    if not clips:
        return clips, []
    ordered = sorted(clips, key=get_start)
    trims: list[OverlapTrim] = []
    for i in range(1, len(ordered)):
        prev = ordered[i - 1]
        cur = ordered[i]
        prev_end = get_end(prev)
        cur_start = get_start(cur)
        if prev_end <= cur_start:
            continue
        src_in = get_source_in(prev)
        new_end = cur_start
        set_end(prev, new_end)
        set_out(prev, src_in + (new_end - get_start(prev)))
        trims.append(
            OverlapTrim(
                track=track_label,
                clip_name=get_name(prev),
                old_end=prev_end,
                new_end=new_end,
            )
        )
    return ordered, trims
