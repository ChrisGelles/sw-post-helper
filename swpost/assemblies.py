"""Parse stringout reference assemblies into interval maps."""

from __future__ import annotations

import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from swpost.paths import canon
from swpost.reference import REFERENCE_DIR

ROLES = ("CAM_B", "CAM_A", "BOOM", "LAV", "LAV_INT")

JUNE_VIDEO_ROLES: tuple[str | None, ...] = ("CAM_B", "CAM_A", None)
JUNE_AUDIO_ROLES: tuple[str | None, ...] = (None, "BOOM", "LAV", "LAV_INT", None, None)
AUG10_VIDEO_ROLES: tuple[str | None, ...] = ("CAM_B", None)
AUG10_AUDIO_ROLES: tuple[str | None, ...] = (None, "LAV")

JUNE_SEGMENTS: list[tuple[str, int, int]] = [
    ("Kiki Redhead", 0, 83295),
    ("Kiki Redhead", 83295, 109064),
    ("Jim Leonard", 109064, 208056),
    ("Stacy Conté", 208056, 282402),
    ("Stephanie Castro", 282402, 334323),
    ("Tony Rook", 334323, 411381),
    ("Morgan Sibbald", 411381, 515148),
    ("Tony Rook", 515148, 533764),
    ("Forrest Blackburn", 533764, 593423),
    ("Forrest Blackburn", 593423, 620331),
    ("Jim Leonard", 620331, 643326),
]

AUG10_SEGMENTS: list[tuple[str, int, int]] = [
    ("Chi Lee", 0, 36876),
    ("Chi Lee", 36876, 62408),
    ("Destiny Thomas", 62408, 80646),
    ("Destiny Thomas", 80646, 95254),
    ("Caitlin Colleary", 95254, 116165),
    ("Caitlin Colleary", 116165, 131253),
    ("Caitlin Colleary", 131253, 138420),
    ("Nikki Burt", 138420, 151275),
    ("Nikki Burt", 151275, 185801),
    ("Miranda Sinnott-Armstrong", 185801, 218172),
    ("Miranda Sinnott-Armstrong", 218172, 251721),
    ("Emma Finestone", 251721, 276649),
    ("Emma Finestone", 276649, 279671),
]


@dataclass(frozen=True)
class Interval:
    role: str
    file_basename: str
    file_path: str
    tl_in: int
    tl_out: int
    source_in: int
    source_out: int
    sourcetrack_index: int
    person: str


CAITLIN_INTERNAL_LAV_PACK = "Lav 03 Caitlin Take 01.wav"
A011_MAX_SOURCE_FRAME = 33986  # A011C001 clamped duration in v03 sync assembly
B013_A_CAMERA_GAP = (33986, 36417)  # B-source frames with no A-camera coverage in v03


@dataclass(frozen=True)
class BKeyedOffset:
    b_file: str
    b_src_in: int
    b_src_out: int
    media_file: str
    media_path: str
    offset: int
    is_lav_on_boom_track: bool = False


@dataclass(frozen=True)
class OffsetEntry:
    b_file: str
    b_src_in: int
    b_src_out: int
    a_file: str
    offset: int
    name_matches_file: bool
    a_duration: int | None = None


@dataclass
class ReferenceBundle:
    june: AssemblyMaps
    aug10: AssemblyMaps
    b_to_a: list[OffsetEntry]
    b_to_boom: list[BKeyedOffset]
    b_to_lav: list[BKeyedOffset]


@dataclass
class AssemblyMaps:
    shoot: str
    intervals: dict[str, list[Interval]] = field(default_factory=dict)


def _basename_from_pathurl(pathurl: str) -> str:
    path = urllib.parse.unquote(pathurl.replace("file://localhost", ""))
    return path.rsplit("/", 1)[-1]


def _build_file_map(root: ET.Element) -> dict[str, tuple[str, str]]:
    files: dict[str, tuple[str, str]] = {}
    for file_el in root.iter("file"):
        fid = file_el.get("id")
        pathurl = file_el.findtext("pathurl")
        if not fid or not pathurl or fid in files:
            continue
        raw = urllib.parse.unquote(pathurl.replace("file://localhost", ""))
        try:
            path = canon(raw)
        except ValueError:
            path = raw
        files[fid] = (_basename_from_pathurl(pathurl), path)
    return files


def _resolve_file(ci: ET.Element, files: dict[str, tuple[str, str]]) -> tuple[str, str]:
    file_el = ci.find("file")
    if file_el is None:
        return "", ""
    if file_el.find("pathurl") is not None:
        raw = urllib.parse.unquote(file_el.findtext("pathurl", "").replace("file://localhost", ""))
        try:
            path = canon(raw)
        except ValueError:
            path = raw
        return _basename_from_pathurl(file_el.findtext("pathurl", "")), path
    return files.get(file_el.get("id", ""), ("", ""))


def person_for_stringout_frame(frame: int, shoot: str) -> str:
    segments = JUNE_SEGMENTS if shoot == "june" else AUG10_SEGMENTS
    for name, start, end in segments:
        if start <= frame < end:
            return name
    return "Unknown"


def _is_render_clip(name: str) -> bool:
    if name.startswith("SW-06.") and name.endswith(".mp4"):
        return True
    if "stringout" in name.lower() and name.endswith(".mp4"):
        return True
    return False


def parse_assembly(path: Path, shoot: str) -> AssemblyMaps:
    root = ET.parse(path).getroot()
    seq = root.find(".//sequence")
    if seq is None:
        raise ValueError(f"no sequence in {path}")

    files = _build_file_map(root)
    maps = AssemblyMaps(shoot=shoot, intervals={role: [] for role in ROLES})

    v_roles = JUNE_VIDEO_ROLES if shoot == "june" else AUG10_VIDEO_ROLES
    a_roles = JUNE_AUDIO_ROLES if shoot == "june" else AUG10_AUDIO_ROLES

    video = seq.find("media/video")
    if video is not None:
        for idx, track in enumerate(video.findall("track")):
            if idx >= len(v_roles):
                break
            role = v_roles[idx]
            if role:
                _append_track_intervals(track, role, shoot, files, maps)

    audio = seq.find("media/audio")
    if audio is not None:
        for idx, track in enumerate(audio.findall("track")):
            if idx >= len(a_roles):
                break
            role = a_roles[idx]
            if role:
                _append_track_intervals(track, role, shoot, files, maps)

    return maps


def _append_track_intervals(
    track: ET.Element,
    role: str,
    shoot: str,
    files: dict[str, tuple[str, str]],
    maps: AssemblyMaps,
) -> None:
    for ci in track.findall("clipitem"):
        name = ci.findtext("name", "")
        basename, path = _resolve_file(ci, files)
        if not basename or _is_render_clip(name or basename):
            continue
        tl_in = int(ci.findtext("start", "0"))
        tl_out = int(ci.findtext("end", "0"))
        source_in = int(ci.findtext("in", "0"))
        source_out = int(ci.findtext("out", "0"))
        st = ci.find("sourcetrack/trackindex")
        sourcetrack_index = int(st.text) if st is not None and st.text else 1
        maps.intervals[role].append(
            Interval(
                role=role,
                file_basename=basename,
                file_path=path,
                tl_in=tl_in,
                tl_out=tl_out,
                source_in=source_in,
                source_out=source_out,
                sourcetrack_index=sourcetrack_index,
                person=person_for_stringout_frame(tl_in, shoot),
            )
        )


def _filter_short_b_ranges(
    b_in: int, b_out: int, min_frames: int = 2
) -> bool:
    """Return True if range should be kept (>= min_frames)."""
    return (b_out - b_in) >= min_frames


def parse_v03_offsets(path: Path) -> list[OffsetEntry]:
    """Pair v03 V1 A camera with V2 B camera; key by B source frame."""
    root = ET.parse(path).getroot()
    files = _build_file_map(root)
    video = root.find(".//sequence/media/video")
    tracks = video.findall("track")
    a_list = _parse_video_clipitems(tracks[0], files)
    b_list = _parse_video_clipitems(tracks[1], files)

    rows: list[OffsetEntry] = []
    for b in b_list:
        if not b["file_basename"].startswith("B"):
            continue
        best_a = None
        best_len = -1
        for a in a_list:
            ov = _overlap(a["tl_start"], a["tl_end"], b["tl_start"], b["tl_end"])
            if ov is None:
                continue
            length = ov[1] - ov[0]
            if length > best_len:
                best_len = length
                best_a = (a, ov[0])
        if best_a is None:
            continue
        a, tl_start = best_a
        b_src_at = b["src_in"] + (tl_start - b["tl_start"])
        a_src_at = a["src_in"] + (tl_start - a["tl_start"])
        if not _filter_short_b_ranges(b["src_in"], b["src_out"]):
            continue
        rows.append(
            OffsetEntry(
                b_file=b["file_basename"],
                b_src_in=b["src_in"],
                b_src_out=b["src_out"],
                a_file=a["name"],
                offset=a_src_at - b_src_at,
                name_matches_file=(a["name"] == a["file_basename"]),
                a_duration=a.get("duration"),
            )
        )
    return rows


def parse_v02b_offsets(path: Path) -> list[OffsetEntry]:
    """Deprecated alias."""
    return parse_v03_offsets(path)


def _parse_video_clipitems(track: ET.Element, files: dict[str, tuple[str, str]]) -> list[dict]:
    clips = []
    for ci in track.findall("clipitem"):
        basename, _ = _resolve_file(ci, files)
        dur = ci.findtext("duration")
        clips.append(
            {
                "name": ci.findtext("name", ""),
                "file_basename": basename,
                "tl_start": int(ci.findtext("start", "0")),
                "tl_end": int(ci.findtext("end", "0")),
                "src_in": int(ci.findtext("in", "0")),
                "src_out": int(ci.findtext("out", "0")),
                "duration": int(dur) if dur else None,
            }
        )
    return clips


def _overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> tuple[int, int] | None:
    start = max(a_start, b_start)
    end = min(a_end, b_end)
    if start >= end:
        return None
    return start, end


def lookup_offset(
    entries: list[OffsetEntry],
    b_file: str,
    b_src_frame: int,
) -> OffsetEntry | None:
    for entry in entries:
        if entry.b_file != b_file:
            continue
        if entry.b_src_in <= b_src_frame < entry.b_src_out:
            return entry
    return None


def lookup_b_keyed(
    entries: list[BKeyedOffset],
    b_file: str,
    b_src_frame: int,
) -> BKeyedOffset | None:
    for entry in entries:
        if entry.b_file != b_file:
            continue
        if entry.b_src_in <= b_src_frame < entry.b_src_out:
            return entry
    return None


def _merge_b_keyed_rows(rows: list[tuple]) -> list[tuple]:
    if not rows:
        return rows
    sorted_rows = sorted(rows, key=lambda r: (r[0], r[3], r[4], r[1]))
    merged: list[tuple] = [sorted_rows[0]]
    for row in sorted_rows[1:]:
        b, b_in, b_out, media, path, off, is_lav = row
        pb, p_in, p_out, pm, pp, po, pl = merged[-1]
        if b == pb and media == pm and off == po and is_lav == pl and b_in <= p_out + 1:
            merged[-1] = (pb, p_in, max(p_out, b_out), pm, pp, po, pl)
        else:
            merged.append(row)
    return merged


def _track_by_name(seq: ET.Element, media: str, name: str) -> ET.Element | None:
    container = seq.find(f"media/{media}")
    if container is None:
        return None
    for tr in container.findall("track"):
        if tr.get("MZ.TrackName") == name:
            return tr
    return None


def _parse_av_clips(track: ET.Element, files: dict[str, tuple[str, str]]) -> list[dict]:
    clips = []
    for ci in track.findall("clipitem"):
        basename, path = _resolve_file(ci, files)
        clips.append(
            {
                "file_basename": basename,
                "file_path": path,
                "tl_start": int(ci.findtext("start", "0")),
                "tl_end": int(ci.findtext("end", "0")),
                "src_in": int(ci.findtext("in", "0")),
                "src_out": int(ci.findtext("out", "0")),
            }
        )
    return clips


def parse_v03_b_keyed_offsets(path: Path, audio_track_name: str) -> list[BKeyedOffset]:
    """Pair v03 V2 B camera with named audio track; key by B source frame."""
    root = ET.parse(path).getroot()
    files = _build_file_map(root)
    seq = root.find(".//sequence")
    video = seq.find("media/video")
    b_track = video.findall("track")[1]
    audio_track = _track_by_name(seq, "audio", audio_track_name)
    if audio_track is None:
        raise ValueError(f"track {audio_track_name!r} not found in {path.name}")

    b_clips = _parse_av_clips(b_track, files)
    audio_clips = _parse_av_clips(audio_track, files)
    raw: list[tuple] = []

    for b in b_clips:
        if not b["file_basename"].startswith("B"):
            continue
        for aud in audio_clips:
            ov = _overlap(b["tl_start"], b["tl_end"], aud["tl_start"], aud["tl_end"])
            if ov is None:
                continue
            tl_a, tl_b = ov
            b_src_a = b["src_in"] + (tl_a - b["tl_start"])
            b_src_b = b["src_in"] + (tl_b - b["tl_start"])
            aud_src_a = aud["src_in"] + (tl_a - aud["tl_start"])
            offset = aud_src_a - b_src_a
            is_lav_on_boom = audio_track_name == "BOOM" and (
                "lav" in aud["file_basename"].lower() and "boom" not in aud["file_basename"].lower()
            )
            raw.append(
                (
                    b["file_basename"],
                    b_src_a,
                    b_src_b,
                    aud["file_basename"],
                    aud["file_path"],
                    offset,
                    is_lav_on_boom,
                )
            )

    rows: list[BKeyedOffset] = []
    for b, b_in, b_out, media, media_path, off, is_lav in _merge_b_keyed_rows(raw):
        if not _filter_short_b_ranges(b_in, b_out):
            continue
        rows.append(
            BKeyedOffset(
                b_file=b,
                b_src_in=b_in,
                b_src_out=b_out,
                media_file=media,
                media_path=media_path,
                offset=off,
                is_lav_on_boom_track=is_lav,
            )
        )
    return rows


def parse_v02b_b_keyed_offsets(path: Path, audio_track_name: str) -> list[BKeyedOffset]:
    """Deprecated alias."""
    return parse_v03_b_keyed_offsets(path, audio_track_name)


def load_reference_assemblies(
    reference_dir: Path | None = None,
) -> ReferenceBundle:
    ref = reference_dir or REFERENCE_DIR
    v03 = ref / "081026-Stringout-Source-v03-cg.xml"
    return ReferenceBundle(
        june=parse_assembly(ref / "CMNH-SW-stringout-ref-270.xml", "june"),
        aug10=parse_assembly(ref / "081026-Stringout-Source-v02-cg.xml", "aug10"),
        b_to_a=parse_v03_offsets(v03),
        b_to_boom=parse_v03_b_keyed_offsets(v03, "BOOM"),
        b_to_lav=parse_v03_b_keyed_offsets(v03, "LAV"),
    )


def load_reference_assemblies_legacy(
    reference_dir: Path | None = None,
) -> tuple[AssemblyMaps, AssemblyMaps, list[OffsetEntry]]:
    bundle = load_reference_assemblies(reference_dir)
    return bundle.june, bundle.aug10, bundle.b_to_a


def detect_link_defects(path: Path) -> list[tuple[str, str]]:
    root = ET.parse(path).getroot()
    files = _build_file_map(root)
    v1 = root.find(".//sequence/media/video/track")
    defects = []
    for ci in v1.findall("clipitem"):
        name = ci.findtext("name", "")
        basename, _ = _resolve_file(ci, files)
        if name and basename and name != basename:
            defects.append((name, basename))
    return defects
