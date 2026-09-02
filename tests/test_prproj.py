"""Tests for .prproj reader."""

from pathlib import Path

from swpost.prproj import iter_sequences, load_prproj, ticks_to_frames

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "STEM-ep02-v01-cg.prproj"


def test_load_ep02_fixture():
    root = load_prproj(FIXTURE)
    assert root.tag == "PremiereData"


def test_multi_sequence_project_lists_all_with_proxy_counts():
    root = load_prproj(FIXTURE)
    sequences = iter_sequences(root)
    assert len(sequences) == 14

    by_name = {s.name: s for s in sequences}
    main = by_name["STEM-ep2-edit-v01-cl"]
    assert main.uid == "3ff4a6cc-10c8-4a29-bb48-c046859ffb75"
    assert main.proxy_clip_count == 12

    nested = [s for s in sequences if s.name.startswith("270p_")]
    assert len(nested) == 13
    assert all(s.proxy_clip_count == 2 for s in nested)


def test_ticks_to_frames():
    assert ticks_to_frames(10594584000) == 1
