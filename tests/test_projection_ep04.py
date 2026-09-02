"""ep04 projection gate — hand-verified Morgan segment (brief v04 Milestone 3)."""

from __future__ import annotations

import json
from pathlib import Path

from swpost.labels import label_timecode_frame, parse_select_label
from swpost.prproj import iter_sequences, load_prproj
from swpost.project import _project_interval_pieces, extract_proxy_cuts, project_prproj

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "STEM-ep04-v03-cc.prproj"
DATA = REPO / "tests" / "fixtures" / "projection_ep04.json"


def _load_data() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


def _first_video_cut(cuts):
    video = [c for c in cuts if c.track_kind == "video"]
    return sorted(video, key=lambda c: c.timeline_start)[0]


def test_ep04_first_v1_cut_morgan_source_frames():
    """Brief v04 M3: first V1 clip → A007 53237–53357, B003 53336–53456."""
    data = _load_data()
    expected = data["first_v1_cut"]
    root = load_prproj(FIXTURE)
    seq = next(s for s in iter_sequences(root) if s.name == data["sequence"]["name"])
    cuts = extract_proxy_cuts(root, seq)
    cut = _first_video_cut(cuts)

    assert cut.stringout_in == expected["stringout_in"]
    assert cut.stringout_out == expected["stringout_out"]
    assert cut.proxy_basename == expected["proxy_basename"]

    from swpost.assemblies import load_reference_assemblies

    june = load_reference_assemblies().june
    by_role: dict[str, list] = {}
    for role in ("CAM_A", "CAM_B"):
        pieces, _ = _project_interval_pieces(cut, role, june.intervals[role])
        by_role[role] = pieces

    for exp in expected["camera_pieces"]:
        role = exp["role"]
        matches = [
            p
            for p in by_role[role]
            if p.file_basename == exp["file_basename"]
            and p.source_in == exp["source_in"]
            and p.source_out == exp["source_out"]
        ]
        assert len(matches) == 1


def test_ep04_label_morgan_05200512_lands_in_camera_piece():
    """MORGAN 05:20:05:12 → frame 460932 must fall inside projected camera source range."""
    data = _load_data()
    lc = data["label_check"]
    assert label_timecode_frame(5, 20, 5, 12) == lc["stringout_frame"]

    root = load_prproj(FIXTURE)
    seq = next(s for s in iter_sequences(root) if s.name == data["sequence"]["name"])
    cuts = extract_proxy_cuts(root, seq)
    cut = next(c for c in cuts if c.stringout_in == lc["stringout_in"])
    parsed = parse_select_label(cut.label)
    assert parsed is not None
    person, frame = parsed
    assert person == "Morgan Sibbald"
    assert frame == lc["stringout_frame"]

    from swpost.assemblies import load_reference_assemblies

    june = load_reference_assemblies().june
    landed = False
    for role in ("CAM_A", "CAM_B"):
        pieces, _ = _project_interval_pieces(cut, role, june.intervals[role])
        for p in pieces:
            src_at = p.source_in + (frame - cut.stringout_in)
            if p.source_in <= src_at < p.source_out:
                landed = True
    assert landed


def test_projection_ep04_end_to_end():
    """Full sequence projection — hand-verified piece counts."""
    data = _load_data()
    pieces, report = project_prproj(FIXTURE, sequence_name=data["sequence"]["name"])

    assert report.cuts_processed == 34
    assert report.piece_counts == {
        "CAM_B": 34,
        "CAM_A": 34,
        "BOOM": 34,
        "LAV": 34,
        "LAV_INT": 9,
    }

    aug10_a = [
        p
        for p in pieces
        if p.role == "CAM_A" and p.file_basename.endswith("_R5DJ.mov")
    ]
    assert len(aug10_a) == 21
    assert all(not p.enabled for p in aug10_a)

    june_a = [p for p in pieces if p.role == "CAM_A" and p not in aug10_a]
    assert len(june_a) == 13
    assert all(p.enabled for p in june_a)

    assert report.boom_track_not_boom
    assert any(
        e["file_on_boom_track"] == "Destiny Take 02 Lav.wav"
        for e in report.boom_track_not_boom
    )
