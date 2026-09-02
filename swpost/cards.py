"""Title card lift from exported Premiere XML."""

from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CardClip:
    name: str
    text_prefix: str
    track_name: str
    track_index: int
    timeline_start: int
    timeline_end: int
    source_in: int
    source_out: int
    clipitem: ET.Element
    scale_value: float | None = None
    status: str = "lifted"  # lifted | synthesized | placeholder


@dataclass
class CardBuildReport:
    cards: list[CardClip] = field(default_factory=list)
    scale_warnings: list[dict] = field(default_factory=list)
    placeholders: bool = False


def _card_text_prefix(name: str) -> str:
    return name.strip()[:57]


def _is_graphic_card(ci: ET.Element) -> bool:
    file_el = ci.find("file")
    if file_el is None:
        return False
    if file_el.findtext("mediaSource") == "GraphicAndType":
        return True
    for eff in ci.iter("effect"):
        if eff.findtext("effectid") == "GraphicAndType":
            return True
    return False


def _graphic_scale(ci: ET.Element) -> float | None:
    for eff in ci.iter("effect"):
        if eff.findtext("effectid") != "GraphicAndType":
            continue
        for param in eff.findall("parameter"):
            if param.findtext("parameterid") == "4" and param.findtext("name") == "Scale":
                raw = param.findtext("value") or ""
                parts = raw.split(",")
                if len(parts) >= 2:
                    try:
                        return float(parts[1].rstrip("."))
                    except ValueError:
                        return None
    return None


def _sequence_by_name(root: ET.Element, sequence_name: str) -> ET.Element | None:
    for seq in root.iter("sequence"):
        if seq.findtext("name") == sequence_name and seq.find("media") is not None:
            return seq
    return None


def load_cards_from_export(
    export_path: Path,
    sequence_name: str,
) -> list[CardClip]:
    root = ET.parse(export_path).getroot()
    seq = _sequence_by_name(root, sequence_name)
    if seq is None:
        raise ValueError(f"sequence {sequence_name!r} not found in {export_path}")

    cards: list[CardClip] = []
    video = seq.find("media/video")
    if video is None:
        return cards

    for track_index, track in enumerate(video.findall("track")):
        track_name = track.get("MZ.TrackName") or f"V{track_index + 1}"
        for ci in track.findall("clipitem"):
            if ci.find("start") is None:
                continue
            if not _is_graphic_card(ci):
                continue
            name = ci.findtext("name") or ""
            cards.append(
                CardClip(
                    name=name,
                    text_prefix=_card_text_prefix(name),
                    track_name=track_name,
                    track_index=track_index,
                    timeline_start=int(ci.findtext("start", "0")),
                    timeline_end=int(ci.findtext("end", "0")),
                    source_in=int(ci.findtext("in", "0")),
                    source_out=int(ci.findtext("out", "0")),
                    clipitem=copy.deepcopy(ci),
                    scale_value=_graphic_scale(ci),
                    status="lifted",
                )
            )
    return sorted(cards, key=lambda c: c.timeline_start)


def match_card_to_offline(
    cards: list[CardClip],
    offline_label: str,
    used: set[int],
) -> CardClip | None:
    """Match exported card to offline clip by text prefix (C4)."""
    label_prefix = _card_text_prefix(offline_label)
    if not label_prefix:
        return None
    for idx, card in enumerate(cards):
        if idx in used:
            continue
        if card.text_prefix.startswith(label_prefix) or label_prefix.startswith(
            card.text_prefix
        ):
            used.add(idx)
            return card
        if card.name.startswith(label_prefix) or label_prefix.startswith(card.name[:57]):
            used.add(idx)
            return card
    return None
