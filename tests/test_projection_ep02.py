"""Data-driven projection tests — ep02 fixture."""

from __future__ import annotations

import json
from pathlib import Path

from swpost.assemblies import load_reference_assemblies
from swpost.prproj import iter_sequences, load_prproj
from swpost.project import extract_proxy_cuts, project_prproj

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "STEM-ep02-v01-cg.prproj"
DATA = REPO / "tests" / "fixtures" / "projection_ep02.json"


def _load_data() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


def _piece_key(p) -> dict:
    return {
        "role": p.role,
        "timeline_start": p.timeline_start,
        "timeline_end": p.timeline_end,
        "source_in": p.source_in,
        "source_out": p.source_out,
        "file_basename": p.file_basename,
        "person": p.person,
    }


def test_projection_ep02_from_fixture_data():
    data = _load_data()
    seq_info = data["sequence"]
    pieces, report = project_prproj(FIXTURE, sequence_name=seq_info["name"])

    assert report.cuts_processed == data["cuts_expected"]
    assert report.piece_counts == data["piece_counts_total"]

    sample = data["sample_cut"]
    cut_pieces = [p for p in pieces if p.cut_label == sample["label"]]
    got = [_piece_key(p) for p in sorted(cut_pieces, key=lambda x: (x.role, x.timeline_start))]
    assert got == sample["pieces"]


def test_v02b_usable_offset_rows_exclude_defect():
    refs = load_reference_assemblies()
    assert len(refs.b_to_a) == 13
    assert not any(o.b_file == "B009C001_130101_R1IB.mov" for o in refs.b_to_a)


def test_v02b_boom_offset_table_sixteen_rows():
    refs = load_reference_assemblies()
    assert len(refs.b_to_boom) == 16
    destiny_lav = [o for o in refs.b_to_boom if o.media_file == "Destiny Take 02 Lav.wav"]
    assert len(destiny_lav) == 1
    assert destiny_lav[0].is_lav_on_boom_track


def test_extract_proxy_cuts_finds_twelve_video_nested_cuts():
    data = _load_data()
    root = load_prproj(FIXTURE)
    seq = next(s for s in iter_sequences(root) if s.name == data["sequence"]["name"])
    cuts = extract_proxy_cuts(root, seq)
    assert len(cuts) == 12
    assert all(c.proxy_basename == "270p.mp4" for c in cuts)
