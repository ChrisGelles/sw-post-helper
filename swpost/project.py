"""Stringout projection engine."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from swpost.assemblies import (
    ROLES,
    AssemblyMaps,
    B013_A_CAMERA_GAP,
    BKeyedOffset,
    CAITLIN_INTERNAL_LAV_PACK,
    Interval,
    OffsetEntry,
    ReferenceBundle,
    detect_link_defects,
    load_reference_assemblies,
    lookup_b_keyed,
    lookup_offset,
    person_for_stringout_frame,
)
from swpost.labels import parse_select_label
from swpost.paths import PROXY_REGISTRY, proxy_basename
from swpost.prproj import (
    ObjectIndex,
    SequenceInfo,
    iter_sequences,
    load_prproj,
    ticks_to_frames,
    _resolve_media_from_clip_ref,
    _track_items_from_track,
    _tracks_from_group,
)

SEQUENCE_CLASS = "6a15d903-8739-11d5-af2d-9b7855ad8974"
VIDEO_TRACK_GROUP = "228cda18-3625-4d2d-951e-348879e4ed93"


class ProjectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProxyCut:
    label: str
    track_name: str
    track_kind: str
    timeline_start: int
    timeline_end: int
    stringout_in: int
    stringout_out: int
    proxy_basename: str
    shoot: str


@dataclass
class ProjectedPiece:
    role: str
    timeline_start: int
    timeline_end: int
    source_in: int
    source_out: int
    file_basename: str
    file_path: str
    person: str
    sourcetrack_index: int
    cut_label: str
    enabled: bool = True


@dataclass
class ProjectionReport:
    sequence_name: str
    sequence_uid: str
    cuts_processed: int = 0
    piece_counts: dict[str, int] = field(default_factory=dict)
    empty_role_ranges: list[dict] = field(default_factory=list)
    offset_boundary_splits: list[dict] = field(default_factory=list)
    absent_roles: list[dict] = field(default_factory=list)
    label_mismatches: list[dict] = field(default_factory=list)
    collisions: list[dict] = field(default_factory=list)
    link_defects: list[dict] = field(default_factory=list)
    boom_track_not_boom: list[dict] = field(default_factory=list)
    internal_lav_pack: list[dict] = field(default_factory=list)
    name_file_mismatches: list[dict] = field(default_factory=list)
    b_keyed_accuracy_notes: list[dict] = field(default_factory=list)


def _overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> tuple[int, int] | None:
    start = max(a_start, b_start)
    end = min(a_end, b_end)
    if start >= end:
        return None
    return start, end


def _nested_proxy_clip(
    nested: SequenceInfo,
) -> tuple[int, int, str] | None:
    """Return (source_in, source_out, filepath) for the proxy inside a nested sequence."""
    for clip in nested.clips:
        if clip.proxy_basename and clip.track_kind == "video":
            return clip.source_in, clip.source_out, clip.filepath or ""
    for clip in nested.clips:
        if clip.proxy_basename:
            return clip.source_in, clip.source_out, clip.filepath or ""
    return None


def extract_proxy_cuts(root: ET.Element, sequence: SequenceInfo) -> list[ProxyCut]:
    index = ObjectIndex(root)
    by_name = {s.name: s for s in iter_sequences(root)}
    cuts: dict[tuple, ProxyCut] = {}

    seq_el = None
    for el in root.iter("Sequence"):
        if el.get("ObjectUID") == sequence.uid:
            seq_el = el
            break
    if seq_el is None:
        return []

    # Video tracks: nested sequence clips (e.g. 270p_1554).
    tgs = seq_el.find("TrackGroups")
    if tgs is not None:
        for tg_entry in tgs.findall("TrackGroup"):
            if tg_entry.findtext("First") != VIDEO_TRACK_GROUP:
                continue
            group_el = index.ref_oid(tg_entry.find("Second").get("ObjectRef"))
            if group_el is None:
                continue
            for track_name, track_el in _tracks_from_group(group_el, index, "video"):
                for ti in _track_items_from_track(track_el):
                    ref = ti.get("ObjectRef")
                    wrapper = index.ref_oid(ref)
                    if wrapper is None:
                        continue
                    cti = wrapper.find("ClipTrackItem")
                    if cti is None:
                        continue
                    ti_el = cti.find("TrackItem")
                    if ti_el is None:
                        continue
                    tl_start = ticks_to_frames(ti_el.findtext("Start"))
                    tl_end = ticks_to_frames(ti_el.findtext("End"))
                    sub = cti.find("SubClip")
                    if sub is None:
                        continue
                    subclip = index.ref_oid(sub.get("ObjectRef"), "SubClip")
                    if subclip is None:
                        continue
                    label = subclip.findtext("Name", default="")
                    clip_ref = subclip.find("Clip")
                    if clip_ref is None:
                        continue
                    holder = index.ref_oid(clip_ref.get("ObjectRef"))
                    if holder is None:
                        continue
                    inline = holder.find("Clip")
                    if inline is None:
                        continue
                    src_el = inline.find("Source")
                    if src_el is None:
                        continue
                    source = index.ref_oid(src_el.get("ObjectRef"))
                    if source is None or source.tag != "VideoSequenceSource":
                        # Direct file on video track.
                        fp, src_in, src_out = _resolve_media_from_clip_ref(clip_ref, index)
                        base = proxy_basename(fp)
                        if not base:
                            continue
                        key = (tl_start, tl_end, src_in, src_out, base)
                        cuts[key] = ProxyCut(
                            label=label,
                            track_name=track_name,
                            track_kind="video",
                            timeline_start=tl_start,
                            timeline_end=tl_end,
                            stringout_in=src_in,
                            stringout_out=src_out,
                            proxy_basename=base,
                            shoot=PROXY_REGISTRY[base]["shoot"],
                        )
                        continue

                    seq_src = source.find("SequenceSource")
                    if seq_src is None:
                        continue
                    seq_ref = seq_src.find("Sequence")
                    if seq_ref is None:
                        continue
                    nested_uid = seq_ref.get("ObjectURef")
                    nested = next((s for s in iter_sequences(root) if s.uid == nested_uid), None)
                    if nested is None:
                        nested = by_name.get(label)
                    if nested is None:
                        continue
                    inner = _nested_proxy_clip(nested)
                    if inner is None:
                        continue
                    inner_in, inner_out, _fp = inner
                    trim_in = ticks_to_frames(inline.findtext("InPoint"))
                    trim_out = ticks_to_frames(inline.findtext("OutPoint"))
                    so_in = inner_in + trim_in
                    so_out = inner_in + trim_out
                    base = "270p.mp4" if label.startswith("270p") else proxy_basename(_fp)
                    if not base or base not in PROXY_REGISTRY:
                        continue
                    key = (tl_start, tl_end, so_in, so_out, base)
                    cuts[key] = ProxyCut(
                        label=label,
                        track_name=track_name,
                        track_kind="video",
                        timeline_start=tl_start,
                        timeline_end=tl_end,
                        stringout_in=so_in,
                        stringout_out=so_out,
                        proxy_basename=base,
                        shoot=PROXY_REGISTRY[base]["shoot"],
                    )

    # Direct proxy file refs on any track (e.g. audio) — dedupe if video already captured.
    for clip in sequence.clips:
        if not clip.proxy_basename:
            continue
        key = (
            clip.timeline_start,
            clip.timeline_end,
            clip.source_in,
            clip.source_out,
            clip.proxy_basename,
        )
        if key in cuts:
            continue
        cuts[key] = ProxyCut(
            label=clip.label,
            track_name=clip.track_name,
            track_kind=clip.track_kind,
            timeline_start=clip.timeline_start,
            timeline_end=clip.timeline_end,
            stringout_in=clip.source_in,
            stringout_out=clip.source_out,
            proxy_basename=clip.proxy_basename,
            shoot=PROXY_REGISTRY[clip.proxy_basename]["shoot"],
        )

    return sorted(cuts.values(), key=lambda c: (c.timeline_start, c.stringout_in))


def _project_interval_pieces(
    cut: ProxyCut,
    role: str,
    intervals: list[Interval],
) -> tuple[list[ProjectedPiece], list[tuple[int, int]]]:
    pieces: list[ProjectedPiece] = []
    empty_ranges: list[tuple[int, int]] = []
    so_in, so_out = cut.stringout_in, cut.stringout_out
    cursor = so_in
    hits = False

    for interval in intervals:
        ov = _overlap(interval.tl_in, interval.tl_out, so_in, so_out)
        if ov is None:
            continue
        hits = True
        ov_start, ov_end = ov
        if ov_start > cursor:
            empty_ranges.append((cursor, ov_start))
        cursor = max(cursor, ov_end)
        piece_tl_start = cut.timeline_start + (ov_start - so_in)
        piece_tl_end = cut.timeline_start + (ov_end - so_in)
        piece_src_in = interval.source_in + (ov_start - interval.tl_in)
        piece_src_out = interval.source_in + (ov_end - interval.tl_in)
        pieces.append(
            ProjectedPiece(
                role=role,
                timeline_start=piece_tl_start,
                timeline_end=piece_tl_end,
                source_in=piece_src_in,
                source_out=piece_src_out,
                file_basename=interval.file_basename,
                file_path=interval.file_path,
                person=interval.person,
                sourcetrack_index=interval.sourcetrack_index,
                cut_label=cut.label,
                enabled=True,
            )
        )

    if cursor < so_out:
        empty_ranges.append((cursor, so_out))
    if not hits:
        empty_ranges.append((so_in, so_out))

    return pieces, empty_ranges


def _subtract_b_source_gap(
    r_in: int, r_out: int, gap_start: int, gap_end: int
) -> list[tuple[int, int]]:
    if r_out <= gap_start or r_in >= gap_end:
        return [(r_in, r_out)]
    parts: list[tuple[int, int]] = []
    if r_in < gap_start:
        parts.append((r_in, min(r_out, gap_start)))
    if r_out > gap_end:
        parts.append((max(r_in, gap_end), r_out))
    return parts


def _project_aug10_a_camera(
    cut: ProxyCut,
    b_pieces: list[ProjectedPiece],
    offsets: list[OffsetEntry],
    report: ProjectionReport,
) -> list[ProjectedPiece]:
    a_pieces: list[ProjectedPiece] = []
    gap_lo, gap_hi = B013_A_CAMERA_GAP
    for bp in b_pieces:
        for r_in, r_out in _split_b_source_ranges(bp, offsets):
            entry = lookup_offset(offsets, bp.file_basename, r_in)
            if entry is None:
                report.empty_role_ranges.append(
                    {
                        "role": "CAM_A",
                        "b_source_range": [r_in, r_out],
                        "cut_label": cut.label,
                        "b_file": bp.file_basename,
                    }
                )
                continue
            if not entry.name_matches_file:
                report.name_file_mismatches.append(
                    {
                        "role": "CAM_A",
                        "clipitem_name": entry.a_file,
                        "cut_label": cut.label,
                        "note": "name≠file on sync assembly — emit anyway",
                    }
                )
            if r_in < gap_hi and r_out > gap_lo:
                report.empty_role_ranges.append(
                    {
                        "role": "CAM_A",
                        "b_source_range": [max(r_in, gap_lo), min(r_out, gap_hi)],
                        "cut_label": cut.label,
                        "b_file": bp.file_basename,
                        "note": "v03 A011 clamp — no A-camera coverage",
                    }
                )
            for s_in, s_out in _subtract_b_source_gap(r_in, r_out, gap_lo, gap_hi):
                if s_in >= s_out:
                    continue
                a_in = s_in + entry.offset
                a_out = s_out + entry.offset
                a_dur = entry.a_duration
                emit_end = s_out
                if a_dur is not None and a_out > a_dur:
                    emit_end = min(s_out, s_in + max(0, a_dur - entry.offset))
                    if emit_end < s_out:
                        report.empty_role_ranges.append(
                            {
                                "role": "CAM_A",
                                "b_source_range": [emit_end, s_out],
                                "cut_label": cut.label,
                                "b_file": bp.file_basename,
                                "note": (
                                    f"No A-camera coverage — {entry.a_file} ends at "
                                    f"source frame {a_dur}"
                                ),
                            }
                        )
                if emit_end <= s_in:
                    continue
                if a_dur is not None and (s_in + entry.offset) >= a_dur:
                    report.empty_role_ranges.append(
                        {
                            "role": "CAM_A",
                            "b_source_range": [s_in, emit_end],
                            "cut_label": cut.label,
                            "b_file": bp.file_basename,
                            "note": f"A-camera source exceeds {entry.a_file} duration",
                        }
                    )
                    continue
                tl_len = bp.timeline_end - bp.timeline_start
                src_len = bp.source_out - bp.source_in
                rel_in = (s_in - bp.source_in) / src_len if src_len else 0
                rel_out = (emit_end - bp.source_in) / src_len if src_len else 1
                a_pieces.append(
                    ProjectedPiece(
                        role="CAM_A",
                        timeline_start=bp.timeline_start + round(rel_in * tl_len),
                        timeline_end=bp.timeline_start + round(rel_out * tl_len),
                        source_in=s_in + entry.offset,
                        source_out=emit_end + entry.offset,
                        file_basename=entry.a_file,
                        file_path=(
                            f"/Volumes/SW_SERIES/02_Assets/01_Video/01_Footage/"
                            f"PROXIES/2026-08-10/{entry.a_file}"
                        ),
                        person=bp.person,
                        sourcetrack_index=1,
                        cut_label=cut.label,
                        enabled=False,
                    )
                )
    return a_pieces


def _split_b_source_ranges(
    bp: ProjectedPiece,
    entries: list[BKeyedOffset] | list[OffsetEntry],
) -> list[tuple[int, int]]:
    boundaries = sorted(
        {
            e.b_src_in
            for e in entries
            if e.b_file == bp.file_basename and bp.source_in < e.b_src_in < bp.source_out
        }
    )
    ranges: list[tuple[int, int]] = []
    start = bp.source_in
    for bnd in boundaries:
        if start < bnd:
            ranges.append((start, bnd))
        start = bnd
    ranges.append((start, bp.source_out))
    return ranges


def _project_b_keyed_role(
    cut: ProxyCut,
    b_pieces: list[ProjectedPiece],
    entries: list[BKeyedOffset],
    role: str,
    report: ProjectionReport,
) -> list[ProjectedPiece]:
    out: list[ProjectedPiece] = []
    for bp in b_pieces:
        for r_in, r_out in _split_b_source_ranges(bp, entries):
            entry = lookup_b_keyed(entries, bp.file_basename, r_in)
            if entry is None:
                continue

            if role == "LAV" and entry.media_file == CAITLIN_INTERNAL_LAV_PACK:
                report.internal_lav_pack.append(
                    {
                        "cut_label": cut.label,
                        "b_file": bp.file_basename,
                        "b_source_range": [r_in, r_out],
                        "file": entry.media_file,
                        "note": (
                            "Internal lavalier pack; subclip name reads "
                            "'Caitlin Take 01 Lav.wav'"
                        ),
                    }
                )

            if role == "BOOM":
                if entry.is_lav_on_boom_track:
                    report.boom_track_not_boom.append(
                        {
                            "cut_label": cut.label,
                            "b_file": bp.file_basename,
                            "b_source_range": [r_in, r_out],
                            "file_on_boom_track": entry.media_file,
                            "note": "Destiny take 02 — lav on boom track, not a boom file",
                        }
                    )
                if entry.media_file == "Destiny Take 01 Boom.wav":
                    report.b_keyed_accuracy_notes.append(
                        {
                            "file": entry.media_file,
                            "note": (
                                "Destiny take 01: v02 reads +332/+223, v03 reads +335/+226 "
                                "— three-frame error floor for B-keyed audio"
                            ),
                        }
                    )

            tl_len = bp.timeline_end - bp.timeline_start
            src_len = bp.source_out - bp.source_in
            rel_in = (r_in - bp.source_in) / src_len if src_len else 0
            rel_out = (r_out - bp.source_in) / src_len if src_len else 1
            piece_tl_start = bp.timeline_start + round(rel_in * tl_len)
            piece_tl_end = bp.timeline_start + round(rel_out * tl_len)
            out.append(
                ProjectedPiece(
                    role=role,
                    timeline_start=piece_tl_start,
                    timeline_end=piece_tl_end,
                    source_in=r_in + entry.offset,
                    source_out=r_out + entry.offset,
                    file_basename=entry.media_file,
                    file_path=entry.media_path,
                    person=bp.person,
                    sourcetrack_index=1,
                    cut_label=cut.label,
                )
            )
    return out


def _validate_label(cut: ProxyCut, pieces: list[ProjectedPiece], report: ProjectionReport) -> None:
    parsed = parse_select_label(cut.label)
    if parsed is None:
        return
    person, frame = parsed
    for piece in pieces:
        if piece.role not in ("CAM_B", "CAM_A"):
            continue
        if piece.source_in <= frame < piece.source_out:
            if piece.person != person:
                report.label_mismatches.append(
                    {
                        "cut_label": cut.label,
                        "label_person": person,
                        "label_frame": frame,
                        "projected_file": piece.file_basename,
                        "projected_person": piece.person,
                    }
                )
            return
    report.label_mismatches.append(
        {
            "cut_label": cut.label,
            "label_person": person,
            "label_frame": frame,
            "error": "label frame not inside any projected camera piece",
        }
    )


def _check_collisions(pieces: list[ProjectedPiece], report: ProjectionReport) -> None:
    by_role: dict[str, list[ProjectedPiece]] = {r: [] for r in ROLES}
    for p in pieces:
        by_role[p.role].append(p)
    for role, role_pieces in by_role.items():
        ordered = sorted(role_pieces, key=lambda p: p.timeline_start)
        for i in range(len(ordered) - 1):
            a, b = ordered[i], ordered[i + 1]
            if b.timeline_start < a.timeline_end:
                report.collisions.append(
                    {
                        "role": role,
                        "piece_a": {
                            "file": a.file_basename,
                            "tl": [a.timeline_start, a.timeline_end],
                            "cut": a.cut_label,
                        },
                        "piece_b": {
                            "file": b.file_basename,
                            "tl": [b.timeline_start, b.timeline_end],
                            "cut": b.cut_label,
                        },
                    }
                )


def project_sequence(
    root: ET.Element,
    sequence: SequenceInfo,
    refs: ReferenceBundle | None = None,
) -> tuple[list[ProjectedPiece], ProjectionReport]:
    if refs is None:
        refs = load_reference_assemblies()

    june, aug10, offsets = refs.june, refs.aug10, refs.b_to_a

    report = ProjectionReport(sequence_name=sequence.name, sequence_uid=sequence.uid)
    v03_path = Path(__file__).resolve().parents[1] / "reference" / "081026-Stringout-Source-v03-cg.xml"
    for name, resolved in detect_link_defects(v03_path):
        report.link_defects.append({"clipitem_name": name, "resolved_file": resolved})

    cuts = extract_proxy_cuts(root, sequence)
    report.cuts_processed = len(cuts)
    all_pieces: list[ProjectedPiece] = []

    for cut in cuts:
        assembly = june if cut.shoot == "june" else aug10
        b_pieces: list[ProjectedPiece] = []

        for role in ROLES:
            if cut.shoot == "aug10" and role in ("CAM_A", "BOOM", "LAV"):
                continue  # derived from CAM_B via v03 B-keyed tables

            intervals = assembly.intervals.get(role, [])
            pieces, empty = _project_interval_pieces(cut, role, intervals)
            for r_in, r_out in empty:
                if r_in >= r_out:
                    continue
                report.empty_role_ranges.append(
                    {
                        "role": role,
                        "stringout_range": [r_in, r_out],
                        "cut_label": cut.label,
                        "person": person_for_stringout_frame(r_in, cut.shoot),
                    }
                )
            if role == "CAM_B":
                b_pieces = pieces
            all_pieces.extend(pieces)

        if cut.shoot == "aug10":
            all_pieces.extend(_project_aug10_a_camera(cut, b_pieces, offsets, report))
            all_pieces.extend(
                _project_b_keyed_role(cut, b_pieces, refs.b_to_boom, "BOOM", report)
            )
            all_pieces.extend(
                _project_b_keyed_role(cut, b_pieces, refs.b_to_lav, "LAV", report)
            )

        _validate_label(cut, [p for p in all_pieces if p.cut_label == cut.label], report)

    for role in ROLES:
        report.piece_counts[role] = sum(1 for p in all_pieces if p.role == role)

    _check_collisions(all_pieces, report)

    if report.label_mismatches:
        lm = report.label_mismatches[0]
        raise ProjectionError(
            f"Label/person mismatch on cut {lm.get('cut_label')!r}: "
            f"label says {lm.get('label_person')}, projected {lm.get('projected_person') or lm.get('error')}"
        )
    if report.collisions:
        c = report.collisions[0]
        raise ProjectionError(
            f"Timeline collision on {c['role']}: "
            f"{c['piece_a']['file']} vs {c['piece_b']['file']}"
        )

    return all_pieces, report


def project_prproj(
    project_path: str | Path,
    sequence_name: str | None = None,
    sequence_uid: str | None = None,
) -> tuple[list[ProjectedPiece], ProjectionReport]:
    root = load_prproj(project_path)
    sequences = iter_sequences(root)
    matches = [
        s
        for s in sequences
        if (sequence_uid and s.uid == sequence_uid)
        or (sequence_name and s.name == sequence_name)
    ]
    if len(matches) != 1:
        names = ", ".join(s.name for s in sequences)
        raise ProjectionError(
            f"Expected exactly one sequence match; got {len(matches)}. Available: {names}"
        )
    return project_sequence(root, matches[0])
