"""High-level conform build orchestration."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

from swpost.cards import (
    CardBuildReport,
    CardClip,
    StyleExport,
    conform_export_warning,
    is_title_card_entry,
    load_cards_export,
    load_style_from_export,
    match_card_to_entry,
    synthesize_card,
    _is_graphic_card,
    _source_text_blob,
)
from swpost.graphic import extract_source_text
from swpost.conform_report import ConformBuildReport
from swpost.fcpxml import (
    analyze_xmeml,
    build_xmeml,
    collect_card_masterclip_ids,
    distinct_source_basenames,
    offline_placeholder_basenames,
    write_xmeml,
)
from swpost.ledger import (
    LedgerError,
    assert_output_accounting,
    build_timeline_ledger,
)
from swpost.markers import load_dva_markers, marker_text_for_clip
from swpost.offline import (
    assign_synthetic_offline_names,
    assert_offline_file_ids_distinct_sources,
    card_text_from_label,
    drop_embedded_camera_audio,
    extract_offline_clips,
)
from swpost.paths import CONFORM_OUTPUT_DIR
from swpost.prproj import iter_sequences, load_prproj
from swpost.project import project_sequence
from swpost.reference import verify_references
from swpost.relink import build_basename_relink_map
from swpost.report import build_report_payload, load_checksums_for_report, write_report


def _sanitize_sequence_name(name: str) -> str:
    out = re.sub(r"[^A-Za-z0-9._-]", "-", name)
    out = re.sub(r"-+", "-", out)
    return out.strip("-") or "conform"


def conform_output_paths(
    sequence_name: str,
    out: Path | None = None,
) -> tuple[Path, str]:
    safe = _sanitize_sequence_name(sequence_name)
    prefix = safe[:24] if len(safe) > 24 else safe
    if out is not None:
        return out, prefix
    version = 1
    while True:
        candidate = Path(CONFORM_OUTPUT_DIR) / f"{safe}-conform-v{version:02d}-cl.xml"
        if not candidate.exists():
            return candidate, prefix
        version += 1


def audit_pathurl_prefixes(xml_path: Path) -> dict[str, int]:
    """Return distinct decoded pathurl prefix counts for diagnostics."""
    import xml.etree.ElementTree as ET

    root = ET.parse(xml_path).getroot()
    counts: dict[str, int] = {}
    for el in root.iter("pathurl"):
        raw = unquote((el.text or "").replace("file://localhost", ""))
        if raw.startswith("/Volumes/SW_SERIES/"):
            key = "/Volumes/SW_SERIES/"
        elif raw.startswith("/Volumes/SW_"):
            key = "/Volumes/SW_ (truncated — missing SERIES/)"
        elif raw.startswith("SERIES/"):
            key = "SERIES/ (truncated — missing /Volumes/SW_)"
        elif raw.startswith("2_Assets/"):
            key = "2_Assets/ (truncated — missing /Volumes/SW_SERIES/0)"
        elif raw.startswith("Assets/"):
            key = "Assets/ (malformed prefix)"
        else:
            key = raw[:48] + ("…" if len(raw) > 48 else "")
        counts[key] = counts.get(key, 0) + 1
    return counts


def _text_by_timeline_from_file(export_path: Path, sequence_name: str) -> dict[tuple[int, int], str]:
    import xml.etree.ElementTree as ET

    root = ET.parse(export_path).getroot()
    texts: dict[tuple[int, int], str] = {}
    for seq in root.iter("sequence"):
        if seq.find("media") is None:
            continue
        video = seq.find("media/video")
        if video is None:
            continue
        for track in video.findall("track"):
            for ci in track.findall("clipitem"):
                if not _is_graphic_card(ci):
                    continue
                blob = _source_text_blob(ci)
                if blob is None:
                    continue
                tl = (int(ci.findtext("start", "0")), int(ci.findtext("end", "0")))
                texts[tl] = extract_source_text(blob)
    return texts


def _export_text_for_clip(
    style_bundle: StyleExport,
    timeline_start: int,
    timeline_end: int,
) -> str | None:
    text = style_bundle.text_by_timeline.get((timeline_start, timeline_end))
    if text is not None:
        return text
    for (start, end), candidate in style_bundle.text_by_timeline.items():
        if start == timeline_start:
            return candidate
    return None


def _resolve_card_text(
    entry,
    markers,
    style_bundle: StyleExport | None,
) -> str | None:
    clip = entry.clip
    export_text = (
        _export_text_for_clip(style_bundle, clip.timeline_start, clip.timeline_end)
        if style_bundle is not None
        else None
    )
    marker_text = marker_text_for_clip(clip, markers)
    if export_text and marker_text:
        return export_text if len(export_text) >= len(marker_text) else marker_text
    return export_text or marker_text or card_text_from_label(clip.label)


def _resolve_style_bundle(
    *,
    cards_from: Path | None,
    style_from: Path | None,
    sequence_name: str,
) -> StyleExport | None:
    card_export = load_cards_export(cards_from, sequence_name) if cards_from else None
    style_export = load_style_from_export(style_from, sequence_name) if style_from else None

    header_source = card_export if card_export and card_export.style_header else style_export
    if header_source is None or header_source.style_header is None or header_source.template_clipitem is None:
        return None

    text_by_timeline: dict[tuple[int, int], str] = {}
    if style_export is not None:
        text_by_timeline.update(style_export.text_by_timeline)
    if card_export is not None:
        for card in card_export.cards:
            key = (card.timeline_start, card.timeline_end)
            blob = _source_text_blob(card.clipitem)
            if blob is not None:
                text_by_timeline.setdefault(key, extract_source_text(blob))
        if cards_from is not None:
            text_by_timeline.update(_text_by_timeline_from_file(cards_from, sequence_name))

    return StyleExport(
        style_header=header_source.style_header,
        template_clipitem=header_source.template_clipitem,
        sequence_name=header_source.sequence_name,
        is_conform_output=header_source.is_conform_output,
        text_by_timeline=text_by_timeline,
    )


def _style_sequence_differs(style_sequence: str, build_sequence: str) -> bool:
    if not style_sequence or not build_sequence:
        return False
    if style_sequence == build_sequence:
        return False
    if style_sequence.startswith(build_sequence) or build_sequence.startswith(style_sequence):
        return False
    return True


def _style_layout_warning(
    style_from: Path,
    style_sequence: str,
    build_sequence: str,
) -> str | None:
    if not _style_sequence_differs(style_sequence, build_sequence):
        return None
    return (
        f"Style header from `--style-from` export {style_from.name!r} "
        f"(sequence {style_sequence!r}) applied to build of {build_sequence!r}. "
        "Card layout is borrowed and will need correcting in Premiere."
    )


def _card_display_name(entry, markers, text: str) -> str:
    marker_text = marker_text_for_clip(entry.clip, markers)
    if marker_text == text:
        for marker in markers:
            if marker.comment == text and marker.name.startswith("CARD"):
                return marker.name
    label = entry.clip.label.strip()
    if label.upper().startswith("CARD ") and len(label) <= 10:
        return label
    return text[:57].strip()


def _process_card_entries(
    card_entries,
    *,
    cards_from: Path | None,
    style_from: Path | None,
    sequence_name: str,
    markers,
) -> tuple[CardBuildReport, list, list[str]]:
    """Resolve title-card ledger entries; generic Graphic clips stay offline."""
    card_report = CardBuildReport()
    placeholder_entries: list = []
    warnings: list[str] = []

    title_entries = [e for e in card_entries if is_title_card_entry(e)]

    if cards_from is not None:
        warn = conform_export_warning(cards_from, sequence_name)
        if warn:
            warnings.append(warn)
            print(f"WARNING: {warn}", file=sys.stderr)

    if style_from is not None:
        style_export = load_style_from_export(style_from, sequence_name)
        if cards_from is None and style_export.is_conform_output:
            msg = (
                f"--style-from points at conform output {style_from.name!r}. "
                "Style header is borrowed deliberately; card clipitems are not lifted."
            )
            warnings.append(msg)
            print(f"WARNING: {msg}", file=sys.stderr)
        layout_warn = _style_layout_warning(
            style_from, style_export.sequence_name, sequence_name
        )
        if layout_warn:
            warnings.insert(0, layout_warn)
            print(f"WARNING: {layout_warn}", file=sys.stderr)

    if cards_from is None and style_from is None:
        card_report.placeholders = bool(title_entries)
        return card_report, title_entries, warnings

    card_export = load_cards_export(cards_from, sequence_name) if cards_from else None
    style_bundle = _resolve_style_bundle(
        cards_from=cards_from,
        style_from=style_from,
        sequence_name=sequence_name,
    )

    used: set[int] = set()
    for entry in title_entries:
        if card_export is not None:
            matched = match_card_to_entry(card_export.cards, entry, used)
            if matched is not None:
                card_report.cards.append(matched)
                continue

        text = _resolve_card_text(entry, markers, style_bundle)
        if (
            text
            and style_bundle is not None
            and style_bundle.style_header is not None
            and style_bundle.template_clipitem is not None
        ):
            display = _card_display_name(entry, markers, text)
            synth = synthesize_card(
                style_bundle.template_clipitem,
                style_bundle.style_header,
                entry=entry,
                text=text,
                track_index=entry.clip.track_index,
                display_name=display,
            )
            card_report.cards.append(synth)
            card_report.synthesized.append(synth)
            continue

        placeholder_entries.append(entry)

    if placeholder_entries:
        card_report.placeholders = True
    return card_report, placeholder_entries, warnings


def build_conform(
    project_path: Path,
    sequence_name: str,
    out: Path | None = None,
    *,
    cards_from: Path | None = None,
    style_from: Path | None = None,
) -> tuple[Path, Path, Path, dict]:
    verify_references()
    relink_map = build_basename_relink_map()
    build_report = ConformBuildReport()
    root = load_prproj(project_path)
    markers = load_dva_markers(root)
    matches = [s for s in iter_sequences(root) if s.name == sequence_name]
    if len(matches) != 1:
        names = ", ".join(s.name for s in iter_sequences(root))
        raise ValueError(f"expected one sequence match; got {len(matches)}. Available: {names}")

    seq = matches[0]
    ledger = build_timeline_ledger(root, seq)
    ledger.raise_if_unclassified()

    pieces, report = project_sequence(root, seq, ledger=ledger)
    build_report.nested_resolutions = list(ledger.projection_report.nested_resolutions)

    card_report, card_placeholder_entries, card_warnings = _process_card_entries(
        ledger.card_entries(),
        cards_from=cards_from,
        style_from=style_from,
        sequence_name=sequence_name,
        markers=markers,
    )
    build_report.cards = card_report
    build_report.card_warnings = card_warnings
    for warn in card_warnings:
        if "Card layout is borrowed" in warn:
            build_report.style_layout_warning = warn
            break

    offline_entries = ledger.passthrough_entries() + card_placeholder_entries
    offline = assign_synthetic_offline_names(
        extract_offline_clips(
            offline_entries,
            relink_map=relink_map,
            relink_report=build_report.relink,
        ),
        pieces,
    )
    dropped_clip_ids: set[str] = set()
    offline = drop_embedded_camera_audio(
        offline,
        dropped=build_report.dropped_embedded_camera_audio,
        dropped_clip_ids=dropped_clip_ids,
    )
    assert_offline_file_ids_distinct_sources(offline)

    card_clip_ids = {c.source_clip_id for c in card_report.cards if c.source_clip_id}
    offline_clip_ids = {o.clip_id for o in offline}
    assert_output_accounting(
        ledger,
        offline_clip_ids=offline_clip_ids,
        card_clip_ids=card_clip_ids,
        dropped_clip_ids=dropped_clip_ids,
    )

    xml_path, prefix = conform_output_paths(sequence_name, out)
    expected = distinct_source_basenames(pieces, offline)
    xmeml = build_xmeml(
        sequence_name=xml_path.stem,
        seq_prefix=prefix,
        pieces=pieces,
        offline=offline,
        report=report,
        build_report=build_report,
        cards=card_report.cards,
    )
    card_masterclip_ids = collect_card_masterclip_ids(xmeml)
    inventory = analyze_xmeml(
        xmeml,
        expected,
        offline_basenames=offline_placeholder_basenames(offline),
        card_masterclip_ids=card_masterclip_ids,
    )
    write_xmeml(
        xml_path,
        xmeml,
        expected_basenames=expected,
        card_masterclip_ids=card_masterclip_ids,
    )

    pathurl_audit = audit_pathurl_prefixes(xml_path)
    build_report.pathurl_prefixes = pathurl_audit

    checksums = load_checksums_for_report()
    payload = build_report_payload(
        project_path=project_path,
        sequence_name=seq.name,
        sequence_uid=seq.uid,
        xml_path=xml_path,
        pieces=pieces,
        offline=offline,
        report=report,
        checksums=checksums,
        inventory=inventory,
        build_report=build_report,
    )
    payload["pathurl_prefix_audit"] = pathurl_audit
    payload["card_warnings"] = card_warnings
    payload["cards_lifted"] = sum(1 for c in card_report.cards if c.status == "lifted")
    payload["cards_synthesized"] = len(card_report.synthesized)
    report_base = xml_path.with_suffix("")
    md_path, json_path = write_report(report_base, payload, report, offline, build_report)
    return xml_path, md_path, json_path, payload
