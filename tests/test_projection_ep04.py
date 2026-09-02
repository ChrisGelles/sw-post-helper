"""ep04 projection gate — pending review. Do not enable until fixture is approved."""

from __future__ import annotations

import pytest

# Expected values from brief / lineage (Morgan segment, ep04 first V1 cut):
#   CAM_A  A007C001_260610_R0DH.mov  source 53237–53357
#   CAM_B  B003C001_260610_R51N.mov   source 53336–53456
# Label check: MORGAN 05:20:05:12 → frame 466524 must fall inside projected camera piece.

EP04_FIXTURE = "tests/STEM-ep04-v03-cc.prproj"  # not pinned yet
EP04_SEQUENCE = "STEM-ep4-rough-main-v01-cl"


@pytest.mark.skip(reason="ep04 fixture under review — enable when Chris approves")
def test_ep04_first_cut_morgan_segment():
    """Gate from brief v03 Milestone 3 check."""
    pytest.fail("Implement when ep04 fixture is added to tests/")


@pytest.mark.skip(reason="ep04 fixture under review")
def test_ep04_label_morgan_05200512_lands_in_camera_piece():
    """466524 = 5*86400 + 20*1440 + 5*24 + 12"""
    expected_frame = 5 * 86400 + 20 * 1440 + 5 * 24 + 12
    assert expected_frame == 466524
    pytest.fail("Implement when ep04 fixture is added to tests/")
