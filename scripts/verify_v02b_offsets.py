#!/usr/bin/env python3
"""Throwaway Milestone 1 gate: recompute B→A offset table from pinned v02b."""

from __future__ import annotations

import sys
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
V02B = REPO / "reference" / "081026-Stringout-Source-v02b-cg.xml"

PUBLISHED = [
    ("B009C001_130101_R1IB.mov", 0, 36875, "A009C002_130101_R5DJ.mov", -1),
    ("B010C001_130101_R1IB.mov", 0, 25531, "A009C003_130101_R5DJ.mov", -1),
    ("B011C001_130101_R1IB.mov", 0, 18252, "A010C001_130101_R5DJ.mov", 0),
    ("B012C001_130101_R1IB.mov", 0, 14588, "A010C002_130101_R5DJ.mov", 6),
    ("B013C001_130101_R1IB.mov", 748, 21659, "A011C001_130101_R5DJ.mov", 1),
    ("B013C001_130101_R1IB.mov", 21329, 36417, "A011C001_130101_R5DJ.mov", 1),
    ("B014C001_130101_R1IB.mov", 0, 7155, "A012C001_130101_R5DJ.mov", 1),
    ("B014C002_130101_R1IB.mov", 0, 12855, "A012C002_130101_R5DJ.mov", -1),
    ("B014C002_130101_R1IB.mov", 12960, 47486, "A012C002_130101_R5DJ.mov", -1),
    ("B015C001_130101_R1IB.mov", 1348, 8521, "A013C001_120101_R5DJ.mov", -3),
    ("B015C001_130101_R1IB.mov", 8625, 32515, "A013C001_120101_R5DJ.mov", 1),
    ("B015C002_130101_R1IB.mov", 220, 33732, "A014C001_120101_R5DJ.mov", 0),
    ("B016C001_130101_R1IB.mov", 244, 25278, "A015C001_130101_R5DJ.mov", 1),
    ("B016C001_130101_R1IB.mov", 25388, 29021, "A015C001_130101_R5DJ.mov", 1),
]


@dataclass(frozen=True)
class ClipItem:
    name: str
    file_basename: str
    tl_start: int
    tl_end: int
    src_in: int
    src_out: int
    name_matches_file: bool


def _basename_from_pathurl(pathurl: str) -> str:
    path = urllib.parse.unquote(pathurl.replace("file://localhost", ""))
    return path.rsplit("/", 1)[-1]


def _file_basename(clipitem: ET.Element, files: dict[str, str]) -> str:
    file_el = clipitem.find("file")
    if file_el is None:
        return ""
    if file_el.find("pathurl") is not None:
        return _basename_from_pathurl(file_el.findtext("pathurl", default=""))
    file_id = file_el.get("id")
    return files.get(file_id, "")


def _build_file_map(root: ET.Element) -> dict[str, str]:
    files: dict[str, str] = {}
    for file_el in root.iter("file"):
        fid = file_el.get("id")
        pathurl = file_el.findtext("pathurl")
        if fid and pathurl:
            files[fid] = _basename_from_pathurl(pathurl)
    return files


def _parse_video_clips(track: ET.Element, files: dict[str, str]) -> list[ClipItem]:
    clips: list[ClipItem] = []
    for clipitem in track.findall("clipitem"):
        name = clipitem.findtext("name", default="")
        file_base = _file_basename(clipitem, files)
        clips.append(
            ClipItem(
                name=name,
                file_basename=file_base,
                tl_start=int(clipitem.findtext("start", "0")),
                tl_end=int(clipitem.findtext("end", "0")),
                src_in=int(clipitem.findtext("in", "0")),
                src_out=int(clipitem.findtext("out", "0")),
                name_matches_file=(name == file_base),
            )
        )
    return clips


def _overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> tuple[int, int] | None:
    start = max(a_start, b_start)
    end = min(a_end, b_end)
    if start >= end:
        return None
    return start, end


def _best_a_partner(b: ClipItem, a_clips: list[ClipItem]) -> ClipItem | None:
    best: ClipItem | None = None
    best_len = -1
    for a in a_clips:
        ov = _overlap(a.tl_start, a.tl_end, b.tl_start, b.tl_end)
        if ov is None:
            continue
        length = ov[1] - ov[0]
        if length > best_len:
            best_len = length
            best = a
    return best


def compute_offsets(v02b_path: Path) -> tuple[list[tuple], list[ClipItem], list[ClipItem]]:
    root = ET.parse(v02b_path).getroot()
    files = _build_file_map(root)
    seq = root.find(".//sequence")
    if seq is None:
        raise SystemExit("no sequence found")

    video = seq.find("media/video")
    if video is None:
        raise SystemExit("no video media found")

    tracks = video.findall("track")
    if len(tracks) < 2:
        raise SystemExit("expected at least two video tracks")

    a_clips = _parse_video_clips(tracks[0], files)
    b_clips = _parse_video_clips(tracks[1], files)

    rows: list[tuple] = []
    for b in b_clips:
        if not b.file_basename.startswith("B"):
            continue
        a = _best_a_partner(b, a_clips)
        if a is None:
            continue
        ov = _overlap(a.tl_start, a.tl_end, b.tl_start, b.tl_end)
        assert ov is not None
        tl_ov_start = ov[0]
        b_src_at = b.src_in + (tl_ov_start - b.tl_start)
        a_src_at = a.src_in + (tl_ov_start - a.tl_start)
        offset = a_src_at - b_src_at
        rows.append(
            (
                b.file_basename,
                b.src_in,
                b.src_out,
                a.name,
                offset,
                a.name_matches_file,
            )
        )
    return rows, a_clips, b_clips


def check_a009_defect(a_clips: list[ClipItem]) -> bool:
    for clip in a_clips:
        if clip.name == "A009C002_130101_R5DJ.mov":
            return clip.file_basename != "A009C002_130101_R5DJ.mov"
    return False


def main() -> int:
    computed, a_clips, _b_clips = compute_offsets(V02B)
    defect = check_a009_defect(a_clips)

    print("Computed B→A offset table from pinned v02b:\n")
    print(f"{'CAM B':<32} {'B source range':<20} {'CAM A':<32} {'offset':>6}  note")
    print("-" * 100)
    for b_file, b_in, b_out, a_file, offset, name_ok in computed:
        note = "" if name_ok else "NAME≠FILE"
        print(f"{b_file:<32} {b_in}–{b_out:<14} {a_file:<32} {offset:+4d}  {note}")

    print("\nPublished table comparison:\n")
    print(f"{'CAM B':<32} {'B range':<20} {'CAM A':<32} {'pub':>4} {'calc':>4} {'match'}")
    print("-" * 100)

    calc_by_key = {(b, b_in, b_out): (a, off, ok) for b, b_in, b_out, a, off, ok in computed}

    all_match = True
    for b_file, b_in, b_out, a_file, pub_off in PUBLISHED:
        key = (b_file, b_in, b_out)
        if key not in calc_by_key:
            print(f"{b_file:<32} {b_in}–{b_out:<14} {a_file:<32} {pub_off:+4d}  ----  MISSING")
            all_match = False
            continue
        calc_a, calc_off, name_ok = calc_by_key[key]
        match = calc_off == pub_off and calc_a == a_file
        if not match:
            all_match = False
        flag = "yes" if match else "NO"
        extra = "" if name_ok else " (A name≠file)"
        print(
            f"{b_file:<32} {b_in}–{b_out:<14} {a_file:<32} {pub_off:+4d} {calc_off:+4d}  {flag}{extra}"
        )

    print("\nA009C002 link defect present:", "yes" if defect else "no")
    if defect:
        for clip in a_clips:
            if clip.name == "A009C002_130101_R5DJ.mov":
                print(
                    f"  clipitem name={clip.name!r} resolves to file={clip.file_basename!r}"
                )

    if all_match and defect:
        print("\nVERDICT: Tables match and the defect is present — proceed with defect branch.")
    elif all_match and not defect:
        print("\nVERDICT: Tables match and the defect is gone — Chi Lee take 01 offset is trustworthy.")
    else:
        print("\nVERDICT: Tables differ — stop before projection code.")

    return 0 if all_match else 1


if __name__ == "__main__":
    sys.exit(main())
