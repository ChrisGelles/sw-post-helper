"""Tests for basename relink map."""

from __future__ import annotations

from swpost.relink import RelinkReport, build_basename_relink_map, resolve_media_path


def test_relink_map_is_case_insensitive():
    relink = build_basename_relink_map()
    assert "destiny take 02 lav.wav" in relink or "lav 03 caitlin take 01.wav" in relink
    key = next(iter(relink))
    assert key == key.lower()


def test_resolve_prefers_canon_for_sw_series_paths():
    relink = build_basename_relink_map()
    report = RelinkReport()
    path = resolve_media_path(
        "/Volumes/SW_SERIES/02_Assets/01_Video/01_Footage/PROXIES/2026-06-09/B004C001_260610_R51N.mov",
        relink,
        report,
    )
    assert path is not None
    assert path.startswith("/Volumes/SW_SERIES/")
    assert not report.applied


def test_resolve_external_path_via_basename():
    relink = build_basename_relink_map()
    report = RelinkReport()
    canonical = next(iter(relink.values()))
    basename = canonical.rsplit("/", 1)[-1]
    external = f"/some/editor/tree/{basename.upper()}"
    resolved = resolve_media_path(external, relink, report)
    assert resolved == canonical
    assert report.applied


def test_resolve_vo_scratch_path_to_temp_vo_folder():
    relink = build_basename_relink_map()
    report = RelinkReport()
    basename = "Ep02-Ep09-Joey-Temp-VO-esv2-30p-bg-m-music-10p.wav"
    source = f"/editor/project/02_Audio/04_VO/scratch/{basename}"
    resolved = resolve_media_path(source, relink, report)
    assert resolved is not None
    assert resolved.endswith(f"/temp VO/{basename}")
    assert report.applied
    assert not report.unresolved


def test_resolve_team_elevate_vendor_prefix():
    relink = build_basename_relink_map()
    report = RelinkReport()
    source = (
        "/Volumes/projects/POST PRODUCTION PROJECTS/CMNH/"
        "02_Assets/02_Audio/01_Raw/2026.08.10/00. Field Recorder [Boom and Lav]/"
        "03. Caitlin/Take 01/Caitlin Take 01 Lav.wav"
    )
    resolved = resolve_media_path(source, relink, report)
    assert resolved is not None
    assert resolved.startswith("/Volumes/SW_SERIES/")
    assert resolved.endswith("Caitlin Take 01 Lav.wav")
    assert "Catilin" in resolved
    assert report.applied
    assert not report.unresolved

