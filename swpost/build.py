"""High-level conform build orchestration."""

from __future__ import annotations

import re
from pathlib import Path

from swpost.cards import CardBuildReport, load_cards_from_export, match_card_to_offline
from swpost.conform_report import ConformBuildReport
from swpost.fcpxml import (
    analyze_xmeml,
    build_xmeml,
    distinct_source_basenames,
    offline_placeholder_basenames,
    write_xmeml,
)
from swpost.offline import assign_synthetic_offline_names, extract_offline_clips
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


def build_conform(
    project_path: Path,
    sequence_name: str,
    out: Path | None = None,
    *,
    cards_from: Path | None = None,
) -> tuple[Path, Path, Path, dict]:
    verify_references()
    relink_map = build_basename_relink_map()
    build_report = ConformBuildReport()
    root = load_prproj(project_path)
    matches = [s for s in iter_sequences(root) if s.name == sequence_name]
    if len(matches) != 1:
        names = ", ".join(s.name for s in iter_sequences(root))
        raise ValueError(f"expected one sequence match; got {len(matches)}. Available: {names}")

    seq = matches[0]
    pieces, report = project_sequence(root, seq)
    build_report.nested_resolutions = list(report.nested_resolutions)
    offline = assign_synthetic_offline_names(
        extract_offline_clips(
            seq,
            relink_map=relink_map,
            relink_report=build_report.relink,
        ),
        pieces,
    )

    card_report = CardBuildReport()
    lifted_cards = []
    skip_offline: set[int] = set()
    if cards_from is not None:
        lifted_cards = load_cards_from_export(cards_from, sequence_name)
        used: set[int] = set()
        for clip in offline:
            if clip.output_role != "CARDS":
                continue
            matched = match_card_to_offline(lifted_cards, clip.label, used)
            if matched is not None:
                card_report.cards.append(matched)
                skip_offline.add(id(clip))
    else:
        card_report.placeholders = any(o.output_role == "CARDS" for o in offline)
    build_report.cards = card_report
    offline_for_xml = [o for o in offline if id(o) not in skip_offline]

    xml_path, prefix = conform_output_paths(sequence_name, out)
    expected = distinct_source_basenames(pieces, offline_for_xml)
    xmeml = build_xmeml(
        sequence_name=xml_path.stem,
        seq_prefix=prefix,
        pieces=pieces,
        offline=offline_for_xml,
        report=report,
        build_report=build_report,
        cards=card_report.cards,
    )
    inventory = analyze_xmeml(
        xmeml,
        expected,
        offline_basenames=offline_placeholder_basenames(offline_for_xml),
        card_masterclip_ids={
            mc.text
            for c in card_report.cards
            for mc in [c.clipitem.find("masterclipid")]
            if mc is not None and mc.text
        },
    )
    write_xmeml(
        xml_path,
        xmeml,
        expected_basenames=expected,
        card_masterclip_ids={
            mc.text
            for c in card_report.cards
            for mc in [c.clipitem.find("masterclipid")]
            if mc is not None and mc.text
        },
    )

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
    report_base = xml_path.with_suffix("")
    md_path, json_path = write_report(report_base, payload, report, offline, build_report)
    return xml_path, md_path, json_path, payload
