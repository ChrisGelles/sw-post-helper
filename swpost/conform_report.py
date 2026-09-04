"""Conform build metadata beyond projection."""

from __future__ import annotations

from dataclasses import dataclass, field

from swpost.cards import CardBuildReport
from swpost.overlap import OverlapTrim
from swpost.relink import RelinkReport


@dataclass
class ConformBuildReport:
    relink: RelinkReport = field(default_factory=RelinkReport)
    overlap_trims: list[OverlapTrim] = field(default_factory=list)
    nested_resolutions: list[dict] = field(default_factory=list)
    cards: CardBuildReport = field(default_factory=CardBuildReport)
    scratch_vo_relocate: list[dict[str, str]] = field(default_factory=list)
    pathurl_prefixes: dict[str, int] = field(default_factory=dict)
    card_warnings: list[str] = field(default_factory=list)
    style_layout_warning: str | None = None
    dropped_embedded_camera_audio: list[dict[str, str | int]] = field(
        default_factory=list
    )
    color_mattes_emitted: int = 0
