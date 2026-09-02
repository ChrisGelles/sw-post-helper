"""Tests for .prproj reader."""

import re
import subprocess
import sys
from pathlib import Path

from swpost.prproj import iter_sequences, load_prproj, ticks_to_frames

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "STEM-ep02-v01-cg.prproj"
EP01 = Path("/Volumes/SW_SERIES/01_ProjectFiles/04_Premiere/_Episodes/ep01-humans&color/STEM-ep01-v11-cc.prproj")
SW_CONFORM = REPO / "sw-conform"


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


def test_list_hides_zero_proxy_sequences(capsys):
    if not EP01.is_file():
        return
    proc = subprocess.run(
        [sys.executable, "-m", "swpost.cli", "list", str(EP01)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    lines = [ln for ln in proc.stdout.strip().splitlines() if ln]
    assert all("\t" in ln for ln in lines)
    assert not any(re.match(r"270p_\d+\t", ln) for ln in lines)
    assert "ep01-humans&color-v11-cc" in proc.stdout
    assert "nested sequences hidden" in proc.stderr


def test_list_all_includes_nested_270p():
    if not EP01.is_file():
        return
    proc = subprocess.run(
        [sys.executable, "-m", "swpost.cli", "list", str(EP01), "--all"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "270p_001" in proc.stdout
    assert "nested sequences hidden" not in proc.stderr
