#!/usr/bin/env python3
"""Gate: recompute Aug 10 B→boom offsets from pinned v02b."""

from __future__ import annotations

import sys
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
V02B = REPO / "reference" / "081026-Stringout-Source-v02b-cg.xml"

PUBLISHED = [
    ("B009C001_130101_R1IB.mov", 132, 36831, "Dr. Lee Take 01 Boom.wav", -132),
    ("B009C001_130101_R1IB.mov", 36834, 36875, "Dr. Lee Take 02 Boom.wav", -36834),
    ("B010C001_130101_R1IB.mov", 0, 25420, "Dr. Lee Take 02 Boom.wav", 42),
    ("B011C001_130101_R1IB.mov", 81, 1812, "Destiny Take 01 Boom.wav", 335),
    ("B011C001_130101_R1IB.mov", 2031, 18249, "Destiny Take 01 Boom.wav", 226),
    ("B012C001_130101_R1IB.mov", 73, 14585, "Destiny Take 02 Lav.wav", 137),
    ("B013C001_130101_R1IB.mov", 748, 21793, "Caitlin Take 01 Boom.wav", -485),
    ("B013C001_130101_R1IB.mov", 21920, 36416, "Caitlin Take 01 Boom.wav", -593),
    ("B014C001_130101_R1IB.mov", 3, 7155, "Caitlin Take 02 Boom.wav", 70),
    ("B014C002_130101_R1IB.mov", 0, 12855, "Nicole Take 01 Boom.wav", 12),
    ("B014C002_130101_R1IB.mov", 12960, 47486, "Nicole Take 01 Boom.wav", -95),
    ("B015C001_130101_R1IB.mov", 1348, 8521, "Miranda Take 01 Boom.wav", -503),
    ("B015C001_130101_R1IB.mov", 8625, 32515, "Miranda Take 01 Boom.wav", -607),
    ("B015C002_130101_R1IB.mov", 220, 33732, "Miranda Take 02 Boom.wav", 519),
    ("B016C001_130101_R1IB.mov", 244, 25278, "Emma Boom.wav", -244),
    ("B016C001_130101_R1IB.mov", 25388, 29021, "Emma Boom.wav", -353),
]


@dataclass(frozen=True)
class ClipItem:
    name: str
    file_basename: str
    tl_start: int
    tl_end: int
    src_in: int
    src_out: int


def _basename_from_pathurl(pathurl: str) -> str:
    return urllib.parse.unquote(pathurl.replace("file://localhost", "")).rsplit("/", 1)[-1]


def _build_file_map(root: ET.Element) -> dict[str, str]:
    files: dict[str, str] = {}
    for file_el in root.iter("file"):
        fid = file_el.get("id")
        pathurl = file_el.findtext("pathurl")
        if fid and pathurl:
            files[fid] = _basename_from_pathurl(pathurl)
    return files


def _resolve_basename(ci: ET.Element, files: dict[str, str]) -> str:
    fe = ci.find("file")
    if fe is None:
        return ""
    if fe.find("pathurl") is not None:
        return _basename_from_pathurl(fe.findtext("pathurl", ""))
    return files.get(fe.get("id", ""), "")


def _parse_clips(track: ET.Element, files: dict[str, str]) -> list[ClipItem]:
    out: list[ClipItem] = []
    for ci in track.findall("clipitem"):
        out.append(
            ClipItem(
                name=ci.findtext("name", ""),
                file_basename=_resolve_basename(ci, files),
                tl_start=int(ci.findtext("start", "0")),
                tl_end=int(ci.findtext("end", "0")),
                src_in=int(ci.findtext("in", "0")),
                src_out=int(ci.findtext("out", "0")),
            )
        )
    return out


def _overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> tuple[int, int] | None:
    start = max(a_start, b_start)
    end = min(a_end, b_end)
    if start >= end:
        return None
    return start, end


def _track_by_name(seq: ET.Element, media: str, name: str) -> ET.Element | None:
    container = seq.find(f"media/{media}")
    if container is None:
        return None
    for tr in container.findall("track"):
        if tr.get("MZ.TrackName") == name:
            return tr
    return None


def compute_boom_offsets(v02b_path: Path) -> list[tuple]:
    root = ET.parse(v02b_path).getroot()
    files = _build_file_map(root)
    seq = root.find(".//sequence")
    video = seq.find("media/video")
    b_track = video.findall("track")[1]
    boom_track = _track_by_name(seq, "audio", "BOOM")
    if boom_track is None:
        raise SystemExit("BOOM track not found")

    b_clips = _parse_clips(b_track, files)
    boom_clips = _parse_clips(boom_track, files)
    rows: list[tuple] = []

    for b in b_clips:
        if not b.file_basename.startswith("B"):
            continue
        for boom in boom_clips:
            ov = _overlap(b.tl_start, b.tl_end, boom.tl_start, boom.tl_end)
            if ov is None:
                continue
            tl_a, tl_b = ov
            b_src_a = b.src_in + (tl_a - b.tl_start)
            b_src_b = b.src_in + (tl_b - b.tl_start)
            boom_src_a = boom.src_in + (tl_a - boom.tl_start)
            offset = boom_src_a - b_src_a
            is_lav = "lav" in boom.file_basename.lower() and "boom" not in boom.file_basename.lower()
            rows.append((b.file_basename, b_src_a, b_src_b, boom.file_basename, offset, is_lav))

    return _merge_b_keyed_rows(rows)


def _merge_b_keyed_rows(rows: list[tuple]) -> list[tuple]:
    """Merge adjacent B-source ranges sharing the same B file, media file, and offset."""
    if not rows:
        return rows
    sorted_rows = sorted(rows, key=lambda r: (r[0], r[3], r[4], r[1]))
    merged: list[tuple] = [sorted_rows[0]]
    for row in sorted_rows[1:]:
        b, b_in, b_out, media, off, is_lav = row
        pb, p_in, p_out, pm, po, pl = merged[-1]
        if b == pb and media == pm and off == po and is_lav == pl and b_in <= p_out + 1:
            merged[-1] = (pb, p_in, max(p_out, b_out), pm, po, pl)
        else:
            merged.append(row)
    return merged


def main() -> int:
    computed = compute_boom_offsets(V02B)
    print("Computed B→boom offset table from pinned v02b:\n")
    print(f"{'CAM B':<32} {'B source range':<20} {'Boom file':<36} {'offset':>6}  note")
    print("-" * 110)
    for b_file, b_in, b_out, boom_file, offset, is_lav in computed:
        note = "NOT BOOM (lav on boom track)" if is_lav else ""
        print(f"{b_file:<32} {b_in}–{b_out:<14} {boom_file:<36} {offset:+4d}  {note}")

    print("\nPublished table comparison:\n")
    calc_by_key = {(b, bi, bo): (f, off) for b, bi, bo, f, off, _ in computed}
    all_match = True
    for b_file, b_in, b_out, boom_file, pub_off in PUBLISHED:
        key = (b_file, b_in, b_out)
        if key not in calc_by_key:
            print(f"{b_file} {b_in}-{b_out} {boom_file} pub={pub_off:+d}  MISSING")
            all_match = False
            continue
        calc_file, calc_off = calc_by_key[key]
        match = calc_off == pub_off and calc_file == boom_file
        if not match:
            all_match = False
            print(f"MISMATCH {b_file} {b_in}-{b_out}: pub {boom_file} {pub_off:+d} vs calc {calc_file} {calc_off:+d}")
        else:
            print(f"OK {b_file} {b_in}-{b_out} {boom_file} {pub_off:+d}")

    print("\nVERDICT:", "Tables match" if all_match else "Tables differ — stop")
    return 0 if all_match else 1


if __name__ == "__main__":
    sys.exit(main())
