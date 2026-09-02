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
