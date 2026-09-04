"""Conform run report — markdown and JSON sidecars."""

from __future__ import annotations

import json
from pathlib import Path

from swpost.conform_report import ConformBuildReport
from swpost.fcpxml import XmemlInventory
from swpost.offline import OfflineClip
from swpost.project import ProjectedPiece, ProjectionReport
from swpost.reference import verify_references


def _tc(frame: int) -> str:
    h = frame // 86400
    m = (frame % 86400) // 1440
    s = (frame % 1440) // 24
    fr = frame % 24
    return f"{h:02d}:{m:02d}:{s:02d}:{fr:02d}"


def build_report_payload(
    *,
    project_path: Path,
    sequence_name: str,
    sequence_uid: str,
    xml_path: Path,
    pieces: list[ProjectedPiece],
    offline: list[OfflineClip],
    report: ProjectionReport,
    checksums: dict[str, str],
    inventory: XmemlInventory | None = None,
    build_report: ConformBuildReport | None = None,
) -> dict:
    payload = {
        "project_path": str(project_path),
        "sequence_name": sequence_name,
        "sequence_uid": sequence_uid,
        "xml_path": str(xml_path),
        "reference_checksums": checksums,
        "piece_counts": report.piece_counts,
        "cuts_processed": report.cuts_processed,
        "offline_clips": [
            {
                "label": o.label,
                "timeline": [o.timeline_start, o.timeline_end],
                "output_path": o.output_path,
                "role": o.output_role,
                "synthetic": o.synthetic,
            }
            for o in offline
        ],
        "audio_substitutions": report.audio_substitutions,
        "boom_track_not_boom": report.boom_track_not_boom,
        "empty_role_ranges": report.empty_role_ranges,
        "collisions": report.collisions,
        "label_mismatches": report.label_mismatches,
        "clip_map": [
            {
                "role": p.role,
                "timeline_in": p.timeline_start,
                "timeline_out": p.timeline_end,
                "timeline_in_tc": _tc(p.timeline_start),
                "timeline_out_tc": _tc(p.timeline_end),
                "file": p.file_basename,
                "source_in": p.source_in,
                "source_out": p.source_out,
                "person": p.person,
                "enabled": p.enabled,
                "cut_label": p.cut_label,
            }
            for p in sorted(pieces, key=lambda x: (x.timeline_start, x.role))
        ],
    }
    if inventory is not None:
        payload["master_clip_count"] = inventory.master_clip_count
        payload["real_source_master_clip_count"] = inventory.real_source_master_clip_count
        payload["offline_placeholder_count"] = inventory.offline_placeholder_count
        payload["bin_tree"] = inventory.bin_tree_lines
        payload["master_clip_timeline_refs"] = inventory.master_clip_timeline_refs
        payload["master_clip_bins"] = inventory.master_clip_bins
    if build_report is not None:
        payload["relink_map"] = build_report.relink.applied
        payload["unresolved_media"] = build_report.relink.unresolved
        payload["overlap_trims"] = [
            {
                "track": t.track,
                "clip": t.clip_name,
                "old_end": t.old_end,
                "new_end": t.new_end,
            }
            for t in build_report.overlap_trims
        ]
        payload["nested_resolutions"] = build_report.nested_resolutions
        payload["cards"] = [
            {
                "name": c.name,
                "track": c.track_name,
                "timeline": [c.timeline_start, c.timeline_end],
                "status": c.status,
            }
            for c in build_report.cards.cards
        ]
        payload["card_placeholders"] = build_report.cards.placeholders
        payload["scale_warnings"] = build_report.cards.scale_warnings
        payload["scratch_vo_relocate"] = build_report.scratch_vo_relocate
        payload["style_layout_warning"] = build_report.style_layout_warning
        payload["dropped_embedded_camera_audio"] = (
            build_report.dropped_embedded_camera_audio
        )
        payload["color_mattes_emitted"] = build_report.color_mattes_emitted
    return payload


def write_report(
    base_path: Path,
    payload: dict,
    report: ProjectionReport,
    offline: list[OfflineClip],
    build_report: ConformBuildReport | None = None,
) -> tuple[Path, Path]:
    json_path = base_path.with_suffix(".json")
    md_path = base_path.with_suffix(".md")
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Stringout conform report",
        "",
        f"- **Input project:** `{payload['project_path']}`",
        f"- **Sequence:** `{payload['sequence_name']}` (`{payload['sequence_uid']}`)",
        f"- **Output XML:** `{payload['xml_path']}`",
        "",
    ]
    if build_report is not None and build_report.style_layout_warning:
        lines.extend(
            [
                "## Style source",
                "",
                f"**{build_report.style_layout_warning}**",
                "",
            ]
        )
    if "master_clip_count" in payload:
        lines.extend(
            [
                "## Master clips",
                "",
                f"- **Master clip count:** {payload['master_clip_count']}",
                f"- **Real source master clips:** {payload['real_source_master_clip_count']}",
                f"- **Offline placeholders:** {payload['offline_placeholder_count']}",
                "",
                "### Bin tree (project panel)",
                "",
                "```",
                *payload["bin_tree"],
                "```",
                "",
                "### Timeline references per master clip",
                "",
                "| Master clip | Bin | Timeline clipitems |",
                "|---|---|---:|",
            ]
        )
        for basename, refs in payload["master_clip_timeline_refs"].items():
            bin_path = payload["master_clip_bins"].get(basename, "")
            lines.append(f"| `{basename}` | `{bin_path}` | {refs} |")
        lines.append("")

    lines.extend(
        [
            "## Reference checksums",
            "",
        ]
    )
    for name, digest in payload["reference_checksums"].items():
        lines.append(f"- `{name}`: `{digest}`")
    lines.extend(["", "## Piece counts", ""])
    for role, count in payload["piece_counts"].items():
        lines.append(f"- {role}: {count}")

    lines.extend(["", "## Offline clipitems", ""])
    if offline:
        for o in offline:
            if o.empty_graphic:
                dest = "color matte generator (STEM-physics-v07 reference shape)"
            else:
                dest = o.output_path or "(no path)"
            lines.append(
                f"- `{o.label[:60]}` → `{dest}` ({o.output_role}, "
                f"synthetic={o.synthetic}, empty_graphic={o.empty_graphic})"
            )
    else:
        lines.append("- none")

    if build_report is not None and build_report.relink.applied:
        lines.extend(["", "## Relink map", ""])
        for row in build_report.relink.applied:
            lines.append(
                f"- `{row['basename']}`: `{row['from_path']}` → `{row['to_path']}`"
            )
    if build_report is not None and build_report.relink.unresolved:
        lines.extend(
            [
                "",
                "## Unresolved media (will import offline — relink by hand)",
                "",
            ]
        )
        seen: set[str] = set()
        for row in build_report.relink.unresolved:
            basename = row["basename"]
            if basename in seen:
                continue
            seen.add(basename)
            lines.append(f"- `{basename}` from `{row['from_path']}`")
    if build_report is not None and build_report.overlap_trims:
        lines.extend(["", "## Overlap trims", ""])
        for t in build_report.overlap_trims:
            lines.append(
                f"- {t.track}: `{t.clip_name}` end {t.old_end} → {t.new_end}"
            )
    if build_report is not None and build_report.nested_resolutions:
        lines.extend(["", "## Nested sequence resolutions", ""])
        for row in build_report.nested_resolutions:
            lines.append(
                f"- `{row['outer_label']}` → `{row['nested_sequence']}` "
                f"frames {row['composed_in']}–{row['composed_out']} on "
                f"`{row['proxy_basename']}`"
            )
    if build_report is not None and build_report.scratch_vo_relocate:
        lines.extend(
            [
                "",
                "## Scratch VO to be relocated to 02_Audio/04_VO/temp VO",
                "",
            ]
        )
        for row in build_report.scratch_vo_relocate:
            lines.append(f"- `{row['basename']}` — `{row['path']}`")
    if build_report is not None and build_report.dropped_embedded_camera_audio:
        lines.extend(
            [
                "",
                "## Dropped embedded camera audio",
                "",
                "Passthrough camera .mov audio removed where field recordings cover the same timeline range.",
                "",
            ]
        )
        seen: set[str] = set()
        for row in build_report.dropped_embedded_camera_audio:
            basename = str(row["basename"])
            if basename in seen:
                continue
            seen.add(basename)
            lines.append(
                f"- `{basename}` — {row['timeline_start']}–{row['timeline_end']} "
                f"(track index {row['track_index']})"
            )
    if build_report is not None and build_report.color_mattes_emitted:
        lines.extend(
            [
                "",
                "## Color mattes (unresolved animation/background)",
                "",
                f"- **{build_report.color_mattes_emitted}** disabled clip(s) emitted as Premiere "
                "`Color` generator mattes (black fill, `enabled=FALSE`) — structure only, "
                "no render.",
                "- Reference shape: `STEM-physics-v07-cl.xml` generatoritem `clipitem-2062`.",
                "",
            ]
        )
    if build_report is not None:
        lines.extend(["", "## Title cards", ""])
        if build_report.card_warnings:
            for warn in build_report.card_warnings:
                lines.append(f"- **Warning:** {warn}")
        lifted = sum(1 for c in build_report.cards.cards if c.status == "lifted")
        synthesized = len(build_report.cards.synthesized)
        if lifted:
            lines.append(f"- **{lifted}** card(s) lifted verbatim from `--cards-from`.")
        if synthesized:
            lines.append(
                f"- **{synthesized}** card(s) synthesized via `build_source_text()` "
                f"using style header from export."
            )
        if build_report.cards.placeholders and not build_report.cards.cards:
            lines.append(
                "- Cards emitted as **offline placeholders** "
                "(no `--cards-from` / `--style-from`)."
            )
        elif build_report.cards.placeholders:
            lines.append(
                "- Some cards remain **offline placeholders** "
                "(no export match / no marker text)."
            )
        for card in build_report.cards.cards:
            lines.append(
                f"- `{card.name[:60]}` on `{card.track_name}` "
                f"({card.timeline_start}–{card.timeline_end}) — **{card.status}**"
            )
        for warn in build_report.cards.scale_warnings:
            lines.append(f"- Scale warning: {warn}")
    if build_report is not None and build_report.pathurl_prefixes:
        lines.extend(["", "## Pathurl prefix audit", ""])
        for prefix, count in sorted(
            build_report.pathurl_prefixes.items(), key=lambda x: (-x[1], x[0])
        ):
            lines.append(f"- `{prefix}` × {count}")

    lines.extend(
        [
            "",
            "Narration cards are expected to remain offline permanently when no export is "
            "provided — timeline position, duration, and names are preserved for editor relink.",
            "",
            "## v03 audio substitutions (informational)",
            "",
        ]
    )
    for sub in report.audio_substitutions:
        lines.append(
            f"- track {sub.get('track')}: {sub.get('clipitem_name')!r} → "
            f"{sub.get('resolved_file')!r}"
        )

    lines.extend(["", "## Boom track inventory (v03 A3)", ""])
    for row in report.boom_track_not_boom:
        lines.append(f"- {row.get('file_on_boom_track')} on {row.get('b_file')} "
                     f"B-source {row.get('b_source_range')}: {row.get('note')}")

    lines.extend(
        [
            "",
            "## Premiere verification (manual, before baseline)",
            "",
            "Aug 10 **BOOM** (A1-BOOM) is the only audio track with no stringout render "
            "behind it. June boom and Aug 10 lav both appear in a playable stringout; "
            "Aug 10 boom comes from v03, which was never rendered.",
            "",
            "On a Miranda Aug 10 cut: solo A1-BOOM against A2-LAV and confirm they "
            "phase rather than slap. If off, report as a v03 assembly problem — do not "
            "adjust tool offsets to compensate.",
            "",
        ]
    )

    if report.empty_role_ranges:
        lines.extend(["## Empty role ranges", ""])
        for row in report.empty_role_ranges[:20]:
            lines.append(f"- {row}")
        if len(report.empty_role_ranges) > 20:
            lines.append(f"- … and {len(report.empty_role_ranges) - 20} more")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path, json_path


def load_checksums_for_report() -> dict[str, str]:
    return verify_references()
