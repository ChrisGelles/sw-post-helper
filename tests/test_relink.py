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
