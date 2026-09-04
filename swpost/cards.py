"""Title card lift and synthesis from exported Premiere XML."""

from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from swpost.graphic import (
    b64_encode_source_text,
    build_source_text,
    extract_source_text,
    style_header_from_blob,
)
from swpost.ledger import LedgerEntry
from swpost.offline import card_text_from_label
from swpost.prproj import TimelineClip


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
    source_clip_id: str = ""


@dataclass
class CardBuildReport:
    cards: list[CardClip] = field(default_factory=list)
    synthesized: list[CardClip] = field(default_factory=list)
    scale_warnings: list[dict] = field(default_factory=list)
    placeholders: bool = False


@dataclass
class CardsExport:
    cards: list[CardClip]
    style_header: bytes | None
    template_clipitem: ET.Element | None
    sequence_name: str = ""
    is_conform_output: bool = False


@dataclass
class StyleExport:
    style_header: bytes
    template_clipitem: ET.Element
    sequence_name: str = ""
    is_conform_output: bool = False
    text_by_timeline: dict[tuple[int, int], str] = field(default_factory=dict)


def is_conform_output_export(root: ET.Element, export_path: Path) -> bool:
    path_hint = "_conform" in export_path.as_posix() or "-conform-v" in export_path.name
    for seq in root.iter("sequence"):
        if seq.find("media") is None:
            continue
        name = seq.findtext("name") or ""
        if "-conform-v" in name and name.endswith("-cl"):
            return True
    return path_hint


def conform_export_warning(export_path: Path, sequence_name: str) -> str | None:
    root = ET.parse(export_path).getroot()
    if not is_conform_output_export(root, export_path):
        return None
    seq = _sequence_by_name(root, sequence_name)
    found = seq.findtext("name") if seq is not None else export_path.name
    return (
        f"--cards-from points at conform output {export_path.name!r} "
        f"(sequence {found!r}). Prefer a Premiere edit export when one exists."
    )


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


def _source_text_blob(ci: ET.Element) -> bytes | None:
    for eff in ci.iter("effect"):
        if eff.findtext("effectid") != "GraphicAndType":
            continue
        for param in eff.findall("parameter"):
            if param.findtext("name") != "Source Text":
                continue
            val = param.findtext("value") or ""
            if not val.strip():
                return None
            from swpost.graphic import b64_decode_source_text

            try:
                return b64_decode_source_text(val)
            except Exception:
                return None
    return None


def _set_source_text(ci: ET.Element, blob: bytes) -> None:
    encoded = b64_encode_source_text(blob)
    for eff in ci.iter("effect"):
        if eff.findtext("effectid") != "GraphicAndType":
            continue
        for param in eff.findall("parameter"):
            if param.findtext("name") == "Source Text":
                val_el = param.find("value")
                if val_el is None:
                    val_el = ET.SubElement(param, "value")
                val_el.text = encoded
                return
    raise ValueError("GraphicAndType clipitem missing Source Text parameter")


def graphic_and_type_effect(root: ET.Element) -> ET.Element | None:
    for eff in root.iter("effect"):
        if eff.findtext("effectid") == "GraphicAndType":
            return eff
    return None


def graphic_and_type_parameter_ids(root: ET.Element) -> set[str]:
    eff = graphic_and_type_effect(root)
    if eff is None:
        return set()
    return {el.text for el in eff.findall("parameter/parameterid") if el.text}


def sync_graphic_and_type_from_template(dest: ET.Element, template: ET.Element) -> None:
    """Ensure dest carries the full GraphicAndType parameter list from template."""
    src_eff = graphic_and_type_effect(template)
    if src_eff is None:
        return
    dest_filters = dest.findall("filter")
    dest_filter: ET.Element | None = None
    for filt in dest_filters:
        if any(eff.findtext("effectid") == "GraphicAndType" for eff in filt.findall("effect")):
            dest_filter = filt
            break
    if dest_filter is None:
        dest_filter = dest_filters[-1] if dest_filters else ET.SubElement(dest, "filter")
    for eff in list(dest_filter.findall("effect")):
        if eff.findtext("effectid") == "GraphicAndType":
            dest_filter.remove(eff)
    dest_filter.append(copy.deepcopy(src_eff))


def populate_graphic_and_type_file(
    file_el: ET.Element,
    name: str,
    *,
    width: int,
    height: int,
    rate: tuple[int, bool] = (24, True),
) -> None:
    """Inline GraphicAndType file block (no pathurl, no duration)."""
    tb, ntsc = rate
    name_el = file_el.find("name")
    if name_el is None:
        name_el = ET.SubElement(file_el, "name")
    name_el.text = name.strip()[:57] or "Graphic"

    ms = file_el.find("mediaSource")
    if ms is None:
        ms = ET.SubElement(file_el, "mediaSource")
    ms.text = "GraphicAndType"

    rate_el = file_el.find("rate")
    if rate_el is None:
        rate_el = ET.SubElement(file_el, "rate")
    tb_el = rate_el.find("timebase")
    if tb_el is None:
        tb_el = ET.SubElement(rate_el, "timebase")
    tb_el.text = str(tb)
    ntsc_el = rate_el.find("ntsc")
    if ntsc_el is None:
        ntsc_el = ET.SubElement(rate_el, "ntsc")
    ntsc_el.text = "TRUE" if ntsc else "FALSE"

    tc = file_el.find("timecode")
    if tc is None:
        tc = ET.SubElement(file_el, "timecode")
    tc_rate = tc.find("rate")
    if tc_rate is None:
        tc_rate = ET.SubElement(tc, "rate")
    tc_tb = tc_rate.find("timebase")
    if tc_tb is None:
        tc_tb = ET.SubElement(tc_rate, "timebase")
    tc_tb.text = str(tb)
    tc_ntsc = tc_rate.find("ntsc")
    if tc_ntsc is None:
        tc_ntsc = ET.SubElement(tc_rate, "ntsc")
    tc_ntsc.text = "TRUE" if ntsc else "FALSE"
    tc_string = tc.find("string")
    if tc_string is None:
        tc_string = ET.SubElement(tc, "string")
    tc_string.text = "00;00;00;00" if tb == 30 and ntsc else "00:00:00:00"
    tc_frame = tc.find("frame")
    if tc_frame is None:
        tc_frame = ET.SubElement(tc, "frame")
    tc_frame.text = "0"
    tc_fmt = tc.find("displayformat")
    if tc_fmt is None:
        tc_fmt = ET.SubElement(tc, "displayformat")
    tc_fmt.text = "DF" if tb == 30 and ntsc else "NDF"

    media = file_el.find("media")
    if media is None:
        media = ET.SubElement(file_el, "media")
    video = media.find("video")
    if video is None:
        video = ET.SubElement(media, "video")
    sc = video.find("samplecharacteristics")
    if sc is None:
        sc = ET.SubElement(video, "samplecharacteristics")
    sc_rate = sc.find("rate")
    if sc_rate is None:
        sc_rate = ET.SubElement(sc, "rate")
    sc_tb = sc_rate.find("timebase")
    if sc_tb is None:
        sc_tb = ET.SubElement(sc_rate, "timebase")
    sc_tb.text = str(tb)
    sc_ntsc = sc_rate.find("ntsc")
    if sc_ntsc is None:
        sc_ntsc = ET.SubElement(sc_rate, "ntsc")
    sc_ntsc.text = "TRUE" if ntsc else "FALSE"
    for tag, val in (
        ("width", width),
        ("height", height),
        ("anamorphic", "FALSE"),
        ("pixelaspectratio", "square"),
        ("fielddominance", "none"),
    ):
        el = sc.find(tag)
        if el is None:
            el = ET.SubElement(sc, tag)
        el.text = str(val)


def renamespace_card_clipitem(
    ci: ET.Element,
    *,
    clip_id: str,
    masterclip_id: str,
    file_id: str,
    file_name: str,
    width: int,
    height: int,
    rate: tuple[int, bool] = (24, True),
) -> None:
    ci.set("id", clip_id)
    mc_el = ci.find("masterclipid")
    if mc_el is None:
        mc_el = ET.SubElement(ci, "masterclipid")
    mc_el.text = masterclip_id
    file_el = ci.find("file")
    if file_el is None:
        file_el = ET.SubElement(ci, "file", id=file_id)
    else:
        file_el.set("id", file_id)
    populate_graphic_and_type_file(
        file_el, file_name, width=width, height=height, rate=rate
    )


def has_graphic_and_type_source_text(root: ET.Element) -> bool:
    """True when a GraphicAndType effect includes a Source Text parameter."""
    for eff in root.iter("effect"):
        if eff.findtext("effectid") != "GraphicAndType":
            continue
        for param in eff.findall("parameter"):
            if param.findtext("parameterid") == "Source Text":
                return True
            if param.findtext("name") == "Source Text":
                return True
    return False


def _append_color_matte_effect(parent: ET.Element) -> None:
    """Color matte generator effect from STEM-physics-v07-cl.xml clipitem-2062."""
    effect = ET.SubElement(parent, "effect")
    ET.SubElement(effect, "name").text = "Color"
    ET.SubElement(effect, "effectid").text = "Color"
    ET.SubElement(effect, "effectcategory").text = "Matte"
    ET.SubElement(effect, "effecttype").text = "generator"
    ET.SubElement(effect, "mediatype").text = "video"
    param = ET.SubElement(effect, "parameter", authoringApp="PremierePro")
    ET.SubElement(param, "parameterid").text = "fillcolor"
    ET.SubElement(param, "name").text = "Color"
    value = ET.SubElement(param, "value")
    ET.SubElement(value, "alpha").text = "0"
    ET.SubElement(value, "red").text = "0"
    ET.SubElement(value, "green").text = "0"
    ET.SubElement(value, "blue").text = "0"


def build_color_matte_generatoritem(
    *,
    label: str,
    timeline_start: int,
    timeline_end: int,
    source_in: int,
    source_out: int,
    clip_id: str,
    rate: tuple[int, bool] = (24, True),
) -> ET.Element:
    """Sequence generatoritem: disabled Premiere Color matte (physics v07 shape)."""
    name = label.strip() or "Graphic"
    duration = max(timeline_end, source_out, 1)
    tb, ntsc = rate
    gi = ET.Element("generatoritem", id=clip_id)
    ET.SubElement(gi, "name").text = name
    ET.SubElement(gi, "enabled").text = "FALSE"
    ET.SubElement(gi, "duration").text = str(duration)
    ET.SubElement(gi, "start").text = str(timeline_start)
    ET.SubElement(gi, "end").text = str(timeline_end)
    ET.SubElement(gi, "in").text = str(source_in)
    ET.SubElement(gi, "out").text = str(source_out)
    clip_rate = ET.SubElement(gi, "rate")
    ET.SubElement(clip_rate, "timebase").text = str(tb)
    ET.SubElement(clip_rate, "ntsc").text = "TRUE" if ntsc else "FALSE"
    _append_color_matte_effect(gi)
    info = ET.SubElement(gi, "logginginfo")
    ET.SubElement(info, "description").text = label
    ET.SubElement(info, "scene").text = ""
    ET.SubElement(info, "shottake").text = ""
    ET.SubElement(info, "lognote").text = ""
    ET.SubElement(info, "good").text = ""
    return gi


def _sequence_by_name(root: ET.Element, sequence_name: str) -> ET.Element | None:
    candidates: list[ET.Element] = []
    for seq in root.iter("sequence"):
        if seq.find("media") is None:
            continue
        name = seq.findtext("name") or ""
        if name == sequence_name:
            return seq
        if name.startswith(sequence_name):
            candidates.append(seq)
    if len(candidates) == 1:
        return candidates[0]
    if candidates:
        # Prefer the conform export whose name embeds the edit sequence.
        ranked = sorted(
            candidates,
            key=lambda s: (0 if "conform" in (s.findtext("name") or "") else 1, s.findtext("name") or ""),
        )
        return ranked[0]
    # Last resort: sole timeline sequence in the export.
    with_media = [s for s in root.iter("sequence") if s.find("media") is not None]
    if len(with_media) == 1:
        return with_media[0]
    return None


def load_style_from_export(
    export_path: Path,
    sequence_name: str,
) -> StyleExport:
    root = ET.parse(export_path).getroot()
    seq = _sequence_by_name(root, sequence_name)
    if seq is None:
        raise ValueError(f"sequence {sequence_name!r} not found in {export_path}")
    is_conform = is_conform_output_export(root, export_path)
    video = seq.find("media/video")
    if video is None:
        raise ValueError(f"no video tracks in export {export_path}")
    style_header: bytes | None = None
    template_clipitem: ET.Element | None = None
    text_by_timeline: dict[tuple[int, int], str] = {}
    for track in video.findall("track"):
        for ci in track.findall("clipitem"):
            if not _is_graphic_card(ci):
                continue
            blob = _source_text_blob(ci)
            if style_header is None and blob is not None:
                style_header = style_header_from_blob(blob)
                template_clipitem = copy.deepcopy(ci)
            tl = (int(ci.findtext("start", "0")), int(ci.findtext("end", "0")))
            if blob is not None:
                text_by_timeline[tl] = extract_source_text(blob)
    if style_header is None or template_clipitem is None:
        raise ValueError(f"no GraphicAndType style header found in {export_path}")
    return StyleExport(
        style_header=style_header,
        template_clipitem=template_clipitem,
        sequence_name=seq.findtext("name") or sequence_name,
        is_conform_output=is_conform,
        text_by_timeline=text_by_timeline,
    )


def is_title_card_entry(entry: LedgerEntry) -> bool:
    """True for narration/on-screen cards, not generic Graphic placeholders."""
    label = entry.clip.label.strip()
    if label.lower() == "graphic":
        return False
    return card_text_from_label(label) is not None


def load_cards_from_export(
    export_path: Path,
    sequence_name: str,
) -> list[CardClip]:
    return load_cards_export(export_path, sequence_name).cards


def load_cards_export(export_path: Path, sequence_name: str) -> CardsExport:
    root = ET.parse(export_path).getroot()
    seq = _sequence_by_name(root, sequence_name)
    if seq is None:
        raise ValueError(f"sequence {sequence_name!r} not found in {export_path}")
    is_conform = is_conform_output_export(root, export_path)

    cards: list[CardClip] = []
    style_header: bytes | None = None
    template_clipitem: ET.Element | None = None
    video = seq.find("media/video")
    if video is None:
        return CardsExport(
            cards=cards,
            style_header=None,
            template_clipitem=None,
            sequence_name=sequence_name,
            is_conform_output=is_conform,
        )

    for track_index, track in enumerate(video.findall("track")):
        track_name = track.get("MZ.TrackName") or f"V{track_index + 1}"
        for ci in track.findall("clipitem"):
            if ci.find("start") is None:
                continue
            if not _is_graphic_card(ci):
                continue
            name = ci.findtext("name") or ""
            blob = _source_text_blob(ci)
            if style_header is None and blob is not None:
                style_header = style_header_from_blob(blob)
                template_clipitem = copy.deepcopy(ci)
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
    return CardsExport(
        cards=sorted(cards, key=lambda c: c.timeline_start),
        style_header=style_header,
        template_clipitem=template_clipitem,
        sequence_name=seq.findtext("name") or sequence_name,
        is_conform_output=is_conform,
    )


def synthesize_card(
    template: ET.Element,
    style_header: bytes,
    *,
    entry: LedgerEntry,
    text: str,
    track_index: int,
    display_name: str | None = None,
) -> CardClip:
    """Build a graphic clipitem from export style header and marker text."""
    clip = entry.clip
    ci = copy.deepcopy(template)
    sync_graphic_and_type_from_template(ci, template)
    name = (display_name or text).strip()
    name_el = ci.find("name")
    if name_el is None:
        name_el = ET.SubElement(ci, "name")
    name_el.text = name
    for tag, val in (
        ("start", clip.timeline_start),
        ("end", clip.timeline_end),
        ("in", clip.source_in),
        ("out", clip.source_out),
    ):
        el = ci.find(tag)
        if el is not None:
            el.text = str(val)
    template_blob = _source_text_blob(template) or b""
    template_text = extract_source_text(template_blob)
    pad = max(1200, len(template_blob) - 380 - len(template_text) - 4)
    blob = build_source_text(style_header, text, pad=pad)
    _set_source_text(ci, blob)
    return CardClip(
        name=name,
        text_prefix=_card_text_prefix(name),
        track_name=clip.track_name or f"V{track_index + 1}",
        track_index=track_index,
        timeline_start=clip.timeline_start,
        timeline_end=clip.timeline_end,
        source_in=clip.source_in,
        source_out=clip.source_out,
        clipitem=ci,
        scale_value=_graphic_scale(template),
        status="synthesized",
        source_clip_id=entry.clip_id,
    )


def _prefix_match(label_prefix: str, card: CardClip) -> bool:
    if card.name == label_prefix or card.text_prefix == label_prefix:
        return True
    if len(card.text_prefix) < 15:
        return False
    return (
        card.text_prefix.startswith(label_prefix)
        or label_prefix.startswith(card.text_prefix)
        or card.name.startswith(label_prefix)
        or label_prefix.startswith(card.name[:57])
    )


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
        if _prefix_match(label_prefix, card):
            used.add(idx)
            return card
    return None


def _apply_entry_timing(ci: ET.Element, entry: LedgerEntry) -> None:
    clip = entry.clip
    for tag, val in (
        ("start", clip.timeline_start),
        ("end", clip.timeline_end),
        ("in", clip.source_in),
        ("out", clip.source_out),
    ):
        el = ci.find(tag)
        if el is not None:
            el.text = str(val)


def match_card_to_entry(
    cards: list[CardClip],
    entry: LedgerEntry,
    used: set[int],
) -> CardClip | None:
    matched = match_card_to_offline(cards, entry.clip.label, used)
    if matched is None:
        return None
    ci = copy.deepcopy(matched.clipitem)
    _apply_entry_timing(ci, entry)
    out = CardClip(
        name=matched.name,
        text_prefix=matched.text_prefix,
        track_name=entry.clip.track_name or matched.track_name,
        track_index=entry.clip.track_index,
        timeline_start=entry.clip.timeline_start,
        timeline_end=entry.clip.timeline_end,
        source_in=entry.clip.source_in,
        source_out=entry.clip.source_out,
        clipitem=ci,
        scale_value=matched.scale_value,
        status="lifted",
        source_clip_id=entry.clip_id,
    )
    return out
