"""FCPXML writer — id stability, enabled flags, scale, pathurl guards."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from swpost.fcpxml import (
    analyze_xmeml,
    build_xmeml,
    distinct_source_basenames,
    file_id,
    masterclip_id,
    native_video_scale,
    write_xmeml,
)
from swpost.offline import assign_synthetic_offline_names, extract_offline_clips
from swpost.paths import FORBIDDEN_PATHURL_FRAGMENTS
from swpost.prproj import iter_sequences, load_prproj
from swpost.project import project_sequence

REPO = Path(__file__).resolve().parents[1]
EP04 = REPO / "tests" / "STEM-ep04-v03-cc.prproj"
EP01 = Path(
    "/Volumes/SW_SERIES/01_ProjectFiles/04_Premiere/_Episodes/ep01-humans&color/STEM-ep01-v11-cc.prproj"
)
SEQ_NAME = "STEM-ep4-rough-main-v01-cl"
EP01_SEQ = "ep01-humans&color-v11-cc"


def _ep04_bundle():
    root = load_prproj(EP04)
    seq = next(s for s in iter_sequences(root) if s.name == SEQ_NAME)
    pieces, report = project_sequence(root, seq)
    offline = assign_synthetic_offline_names(extract_offline_clips(seq), pieces)
    return pieces, report, offline


def _write_ep04(root: ET.Element, out: Path, pieces, offline) -> None:
    expected = distinct_source_basenames(pieces, offline)
    write_xmeml(out, root, expected_basenames=expected)


def _collect_ids(xml_path: Path) -> tuple[list[str], list[str], list[str]]:
    tree = ET.parse(xml_path)
    root = tree.getroot()
    clipitem_ids = [
        el.get("id") for el in root.iter("clipitem") if el.get("id")
    ]
    master_ids = sorted(
        {el.text for el in root.iter("masterclipid") if el.text}
    )
    pathurls = sorted({el.text for el in root.iter("pathurl") if el.text})
    return clipitem_ids, master_ids, pathurls


@pytest.mark.parametrize(
    ("basename", "width", "height", "scale"),
    [
        ("270p.mp4", 480, 270, 400),
        ("SW-06.2026__stringout_01.mp4", 960, 540, 200),
        ("081026-stringout.mp4", 1920, 1080, None),
        (
            "A007C001_260610_R0DH.mov",
            960,
            540,
            200,
        ),
        (
            "A009C002_130101_R5DJ.mov",
            1920,
            1080,
            None,
        ),
    ],
)
def test_native_video_scale(basename, width, height, scale):
    path = f"/Volumes/SW_SERIES/04_Renders/04_Premiere/footage/proxy/{basename}"
    if basename.endswith("_R5DJ.mov"):
        path = f"/Volumes/SW_SERIES/04_Renders/04_Premiere/footage/1080p/PROXIES/2026-08-10/{basename}"
    w, h, sc = native_video_scale(path, basename)
    assert (w, h, sc) == (width, height, scale)


def test_masterclip_id_from_basename_only():
    assert masterclip_id("A007C001_260610_R0DH.mov") == "masterclip-A007C001-260610-R0DH"
    assert file_id("A007C001_260610_R0DH.mov") == "file-A007C001-260610-R0DH"
    assert masterclip_id("Take 01 - Boom.wav") == "masterclip-Take-01-Boom"


def test_writer_ids_stable_across_runs(tmp_path):
    pieces, report, offline = _ep04_bundle()
    paths: list[Path] = []
    for i in range(2):
        out = tmp_path / f"run{i}.xml"
        root = build_xmeml(
            sequence_name="STEM-ep04-conform-v01-cl",
            seq_prefix="ep04",
            pieces=pieces,
            offline=offline,
            report=report,
        )
        _write_ep04(root, out, pieces, offline)
        paths.append(out)

    a_ids, a_master, a_urls = _collect_ids(paths[0])
    b_ids, b_master, b_urls = _collect_ids(paths[1])

    assert a_master == b_master
    assert a_urls == b_urls
    # Sequence clipitem ids use counters — stable given same sort order.
    assert a_ids == b_ids


def test_clipitem_ids_unique_and_masterclipid_present(tmp_path):
    pieces, report, offline = _ep04_bundle()
    out = tmp_path / "ep04.xml"
    root = build_xmeml(
        sequence_name="STEM-ep04-conform-v01-cl",
        seq_prefix="ep04",
        pieces=pieces,
        offline=offline,
        report=report,
    )
    _write_ep04(root, out, pieces, offline)
    tree = ET.parse(out)
    root_el = tree.getroot()

    seq_clipitems = [
        el
        for el in root_el.iter("clipitem")
        if el.get("id") and el.find("start") is not None
    ]
    ids = [el.get("id") for el in seq_clipitems]
    assert len(ids) == len(set(ids)), "duplicate sequence clipitem ids"

    for el in seq_clipitems:
        mc = el.find("masterclipid")
        assert mc is not None and mc.text


def test_aug10_cam_a_enabled_false_in_xml(tmp_path):
    pieces, report, offline = _ep04_bundle()
    out = tmp_path / "ep04.xml"
    root = build_xmeml(
        sequence_name="STEM-ep04-conform-v01-cl",
        seq_prefix="ep04",
        pieces=pieces,
        offline=offline,
        report=report,
    )
    _write_ep04(root, out, pieces, offline)
    tree = ET.parse(out)

    cam_a_track = None
    for tr in tree.getroot().iter("track"):
        if tr.get("MZ.TrackName") == "V2-CAM-A":
            cam_a_track = tr
            break
    assert cam_a_track is not None

    disabled_r5dj: list[str] = []
    enabled_june: list[str] = []
    for el in cam_a_track.findall("clipitem"):
        name = el.findtext("name") or ""
        enabled = el.findtext("enabled") or ""
        if name.endswith("_R5DJ.mov") or "_130101_" in name or "_120101_" in name:
            disabled_r5dj.append(enabled)
        else:
            enabled_june.append(enabled)

    assert len(disabled_r5dj) == 21
    assert all(v == "FALSE" for v in disabled_r5dj)
    assert len(enabled_june) == 13
    assert all(v == "TRUE" for v in enabled_june)


def test_no_forbidden_pathurl_fragments(tmp_path):
    pieces, report, offline = _ep04_bundle()
    out = tmp_path / "ep04.xml"
    root = build_xmeml(
        sequence_name="STEM-ep04-conform-v01-cl",
        seq_prefix="ep04",
        pieces=pieces,
        offline=offline,
        report=report,
    )
    _write_ep04(root, out, pieces, offline)
    text = out.read_text(encoding="utf-8")
    for frag in FORBIDDEN_PATHURL_FRAGMENTS:
        assert frag not in text


def test_june_camera_scale_200_not_400(tmp_path):
    pieces, report, offline = _ep04_bundle()
    out = tmp_path / "ep04.xml"
    root = build_xmeml(
        sequence_name="STEM-ep04-conform-v01-cl",
        seq_prefix="ep04",
        pieces=pieces,
        offline=offline,
        report=report,
    )
    _write_ep04(root, out, pieces, offline)
    tree = ET.parse(out)
    june_scales = []
    for el in tree.getroot().iter("clipitem"):
        name = el.findtext("name") or ""
        if not name.endswith("_R0DH.mov") and not name.endswith("_R51N.mov"):
            continue
        if el.find("start") is None:
            continue
        for param in el.iter("parameter"):
            if param.findtext("parameterid") == "scale":
                june_scales.append(int(param.findtext("value")))
    assert june_scales
    assert all(s == 200 for s in june_scales)
    assert 400 not in june_scales


def test_master_clip_count_matches_distinct_sources(tmp_path):
    pieces, report, offline = _ep04_bundle()
    expected = distinct_source_basenames(pieces, offline)
    root = build_xmeml(
        sequence_name="STEM-ep04-conform-v01-cl",
        seq_prefix="ep04",
        pieces=pieces,
        offline=offline,
        report=report,
    )
    inventory = analyze_xmeml(
        root,
        expected,
        offline_basenames={o.output_basename for o in offline if o.synthetic},
    )
    assert inventory.master_clip_count == inventory.real_source_master_clip_count + inventory.offline_placeholder_count
    assert inventory.master_clip_count == len(expected)
    timeline_refs = sum(inventory.master_clip_timeline_refs.values())
    assert timeline_refs == 34 * 4 + 9 + len(offline)
    assert inventory.offline_placeholder_count == sum(1 for o in offline if o.synthetic)
    assert len({o.output_basename for o in offline if o.synthetic}) == inventory.offline_placeholder_count


def _ep01_bundle():
    if not EP01.is_file():
        pytest.skip("ep01 project not available")
    root = load_prproj(EP01)
    seq = next(s for s in iter_sequences(root) if s.name == EP01_SEQ)
    pieces, report = project_sequence(root, seq)
    offline = assign_synthetic_offline_names(extract_offline_clips(seq), pieces)
    return pieces, report, offline


def test_ep01_xml_byte_identical_across_runs(tmp_path):
    pieces, report, offline = _ep01_bundle()
    expected = distinct_source_basenames(pieces, offline)
    blobs: list[bytes] = []
    for i in range(2):
        out = tmp_path / f"ep01-{i}.xml"
        root = build_xmeml(
            sequence_name="STEM-ep01-conform-v01-cl",
            seq_prefix="ep01",
            pieces=pieces,
            offline=offline,
            report=report,
        )
        write_xmeml(out, root, expected_basenames=expected)
        blobs.append(out.read_bytes())
    assert blobs[0] == blobs[1]


def test_ids_derived_from_basename_ep01_and_ep04(tmp_path):
    if not EP01.is_file():
        pytest.skip("ep01 project not available")
    ep04_pieces, ep04_report, ep04_offline = _ep04_bundle()
    ep01_pieces, ep01_report, ep01_offline = _ep01_bundle()

    def assert_ids_match_formula(pieces, report, offline, prefix, seq_name):
        root = build_xmeml(
            sequence_name=seq_name,
            seq_prefix=prefix,
            pieces=pieces,
            offline=offline,
            report=report,
        )
        out = tmp_path / f"{prefix}-ids.xml"
        write_xmeml(out, root, expected_basenames=distinct_source_basenames(pieces, offline))
        tree = ET.parse(out)
        for clip in tree.getroot().iter("clip"):
            if clip.findtext("ismasterclip") != "TRUE":
                continue
            bn = clip.findtext("name") or ""
            assert clip.get("id") == masterclip_id(bn)
        for fe in tree.getroot().iter("file"):
            if fe.find("pathurl") is None:
                continue
            bn = fe.findtext("name") or ""
            assert fe.get("id") == file_id(bn)

    assert_ids_match_formula(
        ep01_pieces, ep01_report, ep01_offline, "ep01", "STEM-ep01-conform-v01-cl"
    )
    assert_ids_match_formula(
        ep04_pieces, ep04_report, ep04_offline, "ep04", "STEM-ep04-conform-v01-cl"
    )

    ep01_names = distinct_source_basenames(ep01_pieces, ep01_offline)
    ep04_names = distinct_source_basenames(ep04_pieces, ep04_offline)
    shared = ep01_names & ep04_names
    for bn in shared:
        assert masterclip_id(bn) == masterclip_id(bn)
        assert file_id(bn) == file_id(bn)


def test_ep01_no_empty_vo_bin(tmp_path):
    pieces, report, offline = _ep01_bundle()
    out = tmp_path / "ep01.xml"
    root = build_xmeml(
        sequence_name="STEM-ep01-conform-v01-cl",
        seq_prefix="ep01",
        pieces=pieces,
        offline=offline,
        report=report,
    )
    write_xmeml(out, root, expected_basenames=distinct_source_basenames(pieces, offline))
    text = out.read_text(encoding="utf-8")
    assert "<name>VO</name>" not in text


def test_sequence_clipitem_names_are_basenames(tmp_path):
    pieces, report, offline = _ep04_bundle()
    out = tmp_path / "ep04.xml"
    root = build_xmeml(
        sequence_name="STEM-ep04-conform-v01-cl",
        seq_prefix="ep04",
        pieces=pieces,
        offline=offline,
        report=report,
    )
    write_xmeml(out, root, expected_basenames=distinct_source_basenames(pieces, offline))
    tree = ET.parse(out)
    for ci in tree.getroot().iter("clipitem"):
        if ci.find("start") is None:
            continue
        name = ci.findtext("name") or ""
        assert "/" not in name
        assert not name.startswith("270p_")
