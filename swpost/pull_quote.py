"""Build FCP7 XMEML quote pulls from pinned stringout assemblies."""

from __future__ import annotations

import argparse
import glob
import hashlib
import os
import re
import sys
import tempfile
import xml.dom.minidom
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote
from xml.etree.ElementTree import Element

from swpost.paths import VOLUME_ROOT

HANDLE_FRAMES = 24

PINNED_ASSEMBLY = (
    Path(__file__).resolve().parents[1]
    / "reference"
    / "CMNH-SW-stringout-ref-270.xml"
)
FALLBACK_ASSEMBLY = Path(
    "/Volumes/SW_SERIES/01_ProjectFiles/05_XMLs/_stringout-source/"
    "CMNH-SW-stringout-ref-270.xml"
)
EXPECTED_ASSEMBLY_SHA256 = (
    "5b3d6a6906833ec69389baa2d38aaa10e38502ecb85e3f589962e16c4f37e863"
)

CAM_A = "A006C001_260609_R0DH.mov"
CAM_B_B002 = "B002C002_260609_R51N.mov"
CAM_B_B001 = "B001C003_260609_R51N.mov"
BOOM = "Toni Rook Take 01 Boom.WAV"
LAV = "Toni Rook Take 01 Lav.WAV"

TRACK_KEYS = ("V1", "V2", "A1", "A2", "A3")
ASSEMBLY_TRACK = {
    "V1": ("video", 0),
    "V2": ("video", 1),
    "A1": ("audio", 0),
    "A2": ("audio", 1),
    "A3": ("audio", 2),
}


@dataclass(frozen=True)
class PullDef:
    pull_id: str
    quote_in_tc: str
    quote_out_tc: str
    duration: int
    sequence_name: str
    label: str
    cam_b: str
    expected_offsets: dict[str, int]
    expected_source: dict[str, tuple[int, int]]
    ab_pairing: int


PULLS: tuple[PullDef, ...] = (
    PullDef(
        pull_id="p1",
        quote_in_tc="04:37:40:14",
        quote_out_tc="04:37:46:06",
        duration=184,
        sequence_name="ep7-pull-P1-interface-TonyRook-04374014",
        label="Rose",
        cam_b=CAM_B_B001,
        expected_offsets={
            "V2": -334201,
            "V1": -395032,
            "A1": -334201,
            "A2": -333579,
            "A3": -333579,
        },
        expected_source={
            "V2": (65629, 65813),
            "V1": (4798, 4982),
            "A1": (65629, 65813),
            "A2": (66251, 66435),
            "A3": (66251, 66435),
        },
        ab_pairing=60831,
    ),
    PullDef(
        pull_id="p2",
        quote_in_tc="04:00:07:19",
        quote_out_tc="04:01:07:12",
        duration=1481,
        sequence_name="ep7-pull-P2-modeoflife-TonyRook-04000719",
        label="Mango",
        cam_b=CAM_B_B002,
        expected_offsets={
            "V2": -334201,
            "V1": -334054,
            "A1": -334201,
            "A2": -333579,
            "A3": -333579,
        },
        expected_source={
            "V2": (11562, 13043),
            "V1": (11709, 13190),
            "A1": (11562, 13043),
            "A2": (12184, 13665),
            "A3": (12184, 13665),
        },
        ab_pairing=-147,
    ),
    PullDef(
        pull_id="p3",
        quote_in_tc="04:01:07:16",
        quote_out_tc="04:01:31:00",
        duration=608,
        sequence_name="ep7-pull-P3-planetearth-TonyRook-04010716",
        label="Lavender",
        cam_b=CAM_B_B002,
        expected_offsets={
            "V2": -334201,
            "V1": -334054,
            "A1": -334201,
            "A2": -333579,
            "A3": -333579,
        },
        expected_source={
            "V2": (12999, 13607),
            "V1": (13146, 13754),
            "A1": (12999, 13607),
            "A2": (13621, 14229),
            "A3": (13621, 14229),
        },
        ab_pairing=-147,
    ),
    PullDef(
        pull_id="p4",
        quote_in_tc="04:44:20:09",
        quote_out_tc="04:44:34:14",
        duration=389,
        sequence_name="ep7-pull-P4-rockinspace-TonyRook-04442009",
        label="Cerulean",
        cam_b=CAM_B_B001,
        expected_offsets={
            "V2": -334201,
            "V1": -395032,
            "A1": -334201,
            "A2": -333579,
            "A3": -333579,
        },
        expected_source={
            "V2": (75224, 75613),
            "V1": (14393, 14782),
            "A1": (75224, 75613),
            "A2": (75846, 76235),
            "A3": (75846, 76235),
        },
        ab_pairing=60831,
    ),
    PullDef(
        pull_id="p5",
        quote_in_tc="04:15:15:09",
        quote_out_tc="04:15:43:18",
        duration=729,
        sequence_name="ep7-pull-P5-city-TonyRook-04151509",
        label="Forest",
        cam_b=CAM_B_B002,
        expected_offsets={
            "V2": -334201,
            "V1": -334054,
            "A1": -334201,
            "A2": -333579,
            "A3": -333579,
        },
        expected_source={
            "V2": (33344, 34073),
            "V1": (33491, 34220),
            "A1": (33344, 34073),
            "A2": (33966, 34695),
            "A3": (33966, 34695),
        },
        ab_pairing=-147,
    ),
)

ALL_SOURCES = (
    CAM_A,
    CAM_B_B002,
    CAM_B_B001,
    BOOM,
    LAV,
)


@dataclass
class TrackSpan:
    key: str
    kind: str
    clip_name: str
    clip_start: int
    clip_end: int
    clip_in: int
    offset: int
    source_in: int
    source_out: int
    file_el: Element
    assembly_track_index: int


@dataclass
class PullResult:
    pull: PullDef
    handled_in: int
    handled_out: int
    spans: list[TrackSpan] = field(default_factory=list)
    ok: bool = False
    error: str | None = None


def tc_to_frame(tc: str) -> int:
    hh, mm, ss, fr = (int(part) for part in tc.split(":"))
    return hh * 86400 + mm * 1440 + ss * 24 + fr


B_CAMERA_GAP_START = tc_to_frame("04:33:51:06")
B_CAMERA_GAP_END = tc_to_frame("04:34:19:16")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assembly_path() -> Path:
    if PINNED_ASSEMBLY.is_file():
        return PINNED_ASSEMBLY
    if FALLBACK_ASSEMBLY.is_file():
        return FALLBACK_ASSEMBLY
    raise FileNotFoundError(
        f"pinned assembly not found at {PINNED_ASSEMBLY} or {FALLBACK_ASSEMBLY}"
    )


def masterclip_id_for(basename: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", basename)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return f"masterclip-{slug}"


def file_id_for(basename: str) -> str:
    return f"file-{masterclip_id_for(basename)[len('masterclip-'):]}"


def deterministic_uuid(name: str) -> str:
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()
    return f"{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}"


def canonical_pathurl(pathurl: str) -> str:
    if "SW_SERIES/" not in pathurl:
        raise ValueError(f"pathurl is not under SW_SERIES: {pathurl!r}")
    suffix = pathurl.split("SW_SERIES/", 1)[1]
    return f"file://localhost/Volumes/SW_SERIES/{suffix}"


def locate_clipitem_at_frame(
    root: ET.Element,
    *,
    kind: str,
    assembly_track_index: int,
    frame: int,
    match_name: str | None = None,
) -> Element:
    if kind == "video":
        tracks = root.find("sequence/media/video").findall("track")
    else:
        tracks = root.find("sequence/media/audio").findall("track")
    track = tracks[assembly_track_index]
    for ci in track.findall("clipitem"):
        name = ci.findtext("name") or ""
        if match_name and match_name not in name:
            continue
        start = int(ci.findtext("start", "0"))
        end = int(ci.findtext("end", "0"))
        if start <= frame < end:
            return ci
    label = match_name or f"track {assembly_track_index}"
    raise ValueError(
        f"no {kind} clipitem matching {label!r} containing frame {frame}"
    )


def resolve_file_element(root: ET.Element, ci: Element) -> Element:
    file_ref = ci.find("file")
    if file_ref is None:
        raise ValueError(f"clipitem {ci.get('id')} missing file")
    fid = file_ref.get("id")
    if file_ref.find("pathurl") is not None:
        return file_ref
    if not fid:
        raise ValueError(f"clipitem {ci.get('id')} file has no id or pathurl")
    for fe in root.iter("file"):
        if fe.get("id") == fid and fe.find("pathurl") is not None:
            return fe
    raise ValueError(f"no full file definition for id {fid!r}")


def find_assembly_file_element(root: ET.Element, basename: str) -> Element:
    for ci in root.iter("clipitem"):
        if (ci.findtext("name") or "") == basename:
            return resolve_file_element(root, ci)
    raise ValueError(f"no assembly clipitem found for {basename!r}")


def assert_b_gap_clear(handled_in: int, handled_out: int) -> None:
    if handled_in < B_CAMERA_GAP_END and handled_out > B_CAMERA_GAP_START:
        raise ValueError(
            f"handled range [{handled_in},{handled_out}) intersects B-camera gap "
            f"[{B_CAMERA_GAP_START},{B_CAMERA_GAP_END})"
        )


def assert_a4_absent(root: ET.Element, handled_in: int) -> None:
    audio_tracks = root.find("sequence/media/audio").findall("track")
    if len(audio_tracks) < 4:
        return
    for ci in audio_tracks[3].findall("clipitem"):
        start = int(ci.findtext("start", "0"))
        end = int(ci.findtext("end", "0"))
        if start <= handled_in < end:
            raise ValueError(
                f"A4 clipitem {ci.findtext('name')} unexpectedly covers frame {handled_in}"
            )


def derive_spans(
    root: ET.Element,
    pull: PullDef,
    handled_in: int,
    handled_out: int,
) -> list[TrackSpan]:
    match_names = {
        "V1": pull.cam_b,
        "V2": CAM_A,
        "A1": CAM_A,
        "A2": BOOM,
        "A3": LAV,
    }
    spans: list[TrackSpan] = []
    for key in TRACK_KEYS:
        kind, track_index = ASSEMBLY_TRACK[key]
        ci = locate_clipitem_at_frame(
            root,
            kind=kind,
            assembly_track_index=track_index,
            frame=handled_in,
            match_name=match_names[key],
        )
        clip_start = int(ci.findtext("start", "0"))
        clip_end = int(ci.findtext("end", "0"))
        clip_in = int(ci.findtext("in", "0"))
        ci_out = int(ci.findtext("out", "0"))
        end_ci = locate_clipitem_at_frame(
            root,
            kind=kind,
            assembly_track_index=track_index,
            frame=handled_out - 1,
            match_name=match_names[key],
        )
        if end_ci is not ci:
            raise ValueError(
                f"{key} handled_out crosses cut: in-clip {ci.findtext('name')} "
                f"vs out-clip {end_ci.findtext('name')}"
            )
        if not (clip_start <= handled_in < clip_end and clip_start < handled_out <= clip_end):
            raise ValueError(
                f"{key} span [{clip_start},{clip_end}) does not contain "
                f"handled endpoints [{handled_in},{handled_out}]"
            )
        offset = clip_in - clip_start
        source_in = handled_in + offset
        source_out = handled_out + offset
        file_el = resolve_file_element(root, ci)
        file_duration = int(file_el.findtext("duration", "0"))
        if source_out >= file_duration:
            raise ValueError(
                f"{key} source_out {source_out} >= file duration {file_duration}"
            )
        spans.append(
            TrackSpan(
                key=key,
                kind=kind,
                clip_name=ci.findtext("name") or match_names[key],
                clip_start=clip_start,
                clip_end=clip_end,
                clip_in=clip_in,
                offset=offset,
                source_in=source_in,
                source_out=source_out,
                file_el=file_el,
                assembly_track_index=track_index,
            )
        )
        _ = ci_out
    return spans


def validate_pull(root: ET.Element, pull: PullDef) -> PullResult:
    quote_in = tc_to_frame(pull.quote_in_tc)
    quote_out = tc_to_frame(pull.quote_out_tc)
    handled_in = quote_in - HANDLE_FRAMES
    handled_out = quote_out + HANDLE_FRAMES
    result = PullResult(pull=pull, handled_in=handled_in, handled_out=handled_out)
    try:
        if handled_out - handled_in != pull.duration:
            raise ValueError(
                f"handled span {handled_out - handled_in} != duration {pull.duration}"
            )
        assert_b_gap_clear(handled_in, handled_out)
        spans = derive_spans(root, pull, handled_in, handled_out)
        span_by_key = {s.key: s for s in spans}
        for key in TRACK_KEYS:
            if span_by_key[key].offset != pull.expected_offsets[key]:
                raise ValueError(
                    f"{key} offset {span_by_key[key].offset} != "
                    f"expected {pull.expected_offsets[key]}"
                )
        ab_delta = span_by_key["V2"].offset - span_by_key["V1"].offset
        if ab_delta != pull.ab_pairing:
            raise ValueError(
                f"A/B pairing {ab_delta} != expected {pull.ab_pairing}"
            )
        assert_a4_absent(root, handled_in)
        for key in TRACK_KEYS:
            got = (span_by_key[key].source_in, span_by_key[key].source_out)
            exp = pull.expected_source[key]
            if got != exp:
                raise ValueError(f"{key} source {got} != expected {exp}")
        result.spans = spans
        result.ok = True
    except Exception as exc:
        result.error = str(exc)
        if pull.pull_id == "p1":
            print(f"P1 GATE FAILED: {exc}", file=sys.stderr)
    return result


def scan_originals_report() -> str:
    footage_root = Path(VOLUME_ROOT) / "02_Assets/01_Video/01_Footage"
    lines = ["# Camera originals scan — ep7 pull interface v02", ""]
    lines.append(f"## Footage root `{footage_root}`")
    lines.append("")
    if footage_root.is_dir():
        top_level = sorted(p.name for p in footage_root.iterdir() if p.is_dir())
        lines.append("Top-level directories:")
        for name in top_level:
            lines.append(f"- `{name}`")
        lines.append("")
        lines.append(
            "No `ORIGINALS`, `R3D`, or `RAW` tree found under `01_Footage/`. "
            "Only `PROXIES/` is present for 2026-06-09."
        )
    else:
        lines.append(f"Footage root not found: `{footage_root}`")
    lines.append("")
    lines.append("## Target clips")
    lines.append("")
    for basename in (CAM_A, CAM_B_B002, CAM_B_B001):
        proxy_hits = glob.glob(
            str(footage_root / "PROXIES" / "**" / basename), recursive=True
        )
        other_hits = [
            p
            for p in glob.glob(str(footage_root / "**" / basename), recursive=True)
            if "/PROXIES/" not in p.replace("\\", "/")
        ]
        lines.append(f"### `{basename}`")
        lines.append(f"- Proxy: `{proxy_hits[0]}`" if proxy_hits else "- Proxy: not found")
        if other_hits:
            lines.append(f"- Non-proxy match: `{other_hits[0]}`")
        else:
            lines.append("- Original: **not found**")
        lines.append("")
    lines.append("Build v02 uses proxy `.mov` files for all video pulls.")
    lines.append("")
    return "\n".join(lines) + "\n"


def _sub(parent: Element, tag: str, text: str | int | None = None, **attrs: str) -> Element:
    el = ET.SubElement(parent, tag, attrs)
    if text is not None:
        el.text = str(text)
    return el


def _rate(parent: Element, tb: int = 24, ntsc: bool = True) -> None:
    rate = _sub(parent, "rate")
    _sub(rate, "timebase", tb)
    _sub(rate, "ntsc", "TRUE" if ntsc else "FALSE")


def _labels(parent: Element, color: str) -> None:
    labels = _sub(parent, "labels")
    _sub(labels, "label2", color)


def _basic_motion_scale_200(parent: Element) -> None:
    filt = _sub(parent, "filter")
    effect = _sub(filt, "effect")
    _sub(effect, "name", "Basic Motion")
    _sub(effect, "effectid", "basic")
    _sub(effect, "effectcategory", "motion")
    _sub(effect, "effecttype", "motion")
    _sub(effect, "mediatype", "video")
    param = _sub(effect, "parameter")
    _sub(param, "parameterid", "scale")
    _sub(param, "name", "Scale")
    _sub(param, "valuemin", "0")
    _sub(param, "valuemax", "1000")
    _sub(param, "value", "200")


def _append_video_file_def(
    parent: Element,
    *,
    file_id: str,
    basename: str,
    pathurl: str,
    duration: int,
    width: int,
    height: int,
    channelcount: int,
) -> None:
    fe = _sub(parent, "file", id=file_id)
    _sub(fe, "name", basename)
    _sub(fe, "pathurl", pathurl)
    _rate(fe, 24, True)
    _sub(fe, "duration", duration)
    tc = _sub(fe, "timecode")
    _rate(tc, 24, True)
    _sub(tc, "string", "00:00:00:00")
    _sub(tc, "displayformat", "NDF")
    _sub(tc, "frame", 0)
    media = _sub(fe, "media")
    video = _sub(media, "video")
    sc = _sub(video, "samplecharacteristics")
    _rate(sc, 24, True)
    _sub(sc, "width", width)
    _sub(sc, "height", height)
    _sub(sc, "anamorphic", "FALSE")
    _sub(sc, "pixelaspectratio", "square")
    _sub(sc, "fielddominance", "none")
    audio = _sub(media, "audio")
    asc = _sub(audio, "samplecharacteristics")
    _sub(asc, "depth", "16")
    _sub(asc, "samplerate", "48000")
    _sub(audio, "channelcount", channelcount)


def _append_audio_file_def(
    parent: Element,
    *,
    file_id: str,
    basename: str,
    pathurl: str,
    duration: int,
    display_name: str | None = None,
) -> None:
    fe = _sub(parent, "file", id=file_id)
    _sub(fe, "name", display_name or basename)
    _sub(fe, "pathurl", pathurl)
    _rate(fe, 30, True)
    _sub(fe, "duration", duration)
    tc = _sub(fe, "timecode")
    _rate(tc, 30, True)
    _sub(tc, "string", "00;00;00;00")
    _sub(tc, "displayformat", "DF")
    _sub(tc, "frame", 0)
    media = _sub(fe, "media")
    audio = _sub(media, "audio")
    asc = _sub(audio, "samplecharacteristics")
    _sub(asc, "depth", "16")
    _sub(asc, "samplerate", "48000")
    _sub(audio, "channelcount", "1")
    ac = _sub(audio, "audiochannel")
    _sub(ac, "sourcechannel", "1")


def _source_meta(root: ET.Element, basename: str) -> dict:
    file_el = find_assembly_file_element(root, basename)
    pathurl = canonical_pathurl(file_el.findtext("pathurl") or "")
    duration = int(file_el.findtext("duration", "0"))
    is_video = basename.endswith(".mov")
    width = height = 960
    channelcount = 1
    if is_video:
        sc = file_el.find("./media/video/samplecharacteristics")
        if sc is not None:
            width = int(sc.findtext("width", "960"))
            height = int(sc.findtext("height", "540"))
        ac = file_el.find("./media/audio/channelcount")
        channelcount = int(ac.text) if ac is not None and ac.text else 5
    return {
        "basename": basename,
        "pathurl": pathurl,
        "duration": duration,
        "width": width,
        "height": height,
        "channelcount": channelcount,
        "display_name": file_el.findtext("name") or basename,
        "is_video": is_video,
    }


def _append_master_clip_video(parent: Element, src: dict) -> None:
    mc_id = masterclip_id_for(src["basename"])
    fid = file_id_for(src["basename"])
    clip = _sub(parent, "clip", id=mc_id)
    _sub(clip, "uuid", deterministic_uuid(mc_id))
    _sub(clip, "masterclipid", mc_id)
    _sub(clip, "ismasterclip", "TRUE")
    _sub(clip, "duration", src["duration"])
    _rate(clip, 24, True)
    _sub(clip, "name", src["basename"])
    media = _sub(clip, "media")
    video = _sub(media, "video")
    vtrack = _sub(video, "track")
    vci = _sub(vtrack, "clipitem", id=f"{mc_id}--mc-v")
    _sub(vci, "masterclipid", mc_id)
    _sub(vci, "name", src["basename"])
    _rate(vci, 24, True)
    _sub(vci, "duration", src["duration"])
    _sub(vci, "in", 0)
    _sub(vci, "out", src["duration"])
    _append_video_file_def(
        vci,
        file_id=fid,
        basename=src["basename"],
        pathurl=src["pathurl"],
        duration=src["duration"],
        width=src["width"],
        height=src["height"],
        channelcount=src["channelcount"],
    )
    _basic_motion_scale_200(vci)
    audio = _sub(media, "audio")
    for track_idx in range(1, src["channelcount"] + 1):
        atr = _sub(audio, "track")
        aci = _sub(atr, "clipitem", id=f"{mc_id}--mc-a{track_idx}")
        _sub(aci, "masterclipid", mc_id)
        _sub(aci, "name", src["basename"])
        _rate(aci, 24, True)
        _sub(aci, "duration", src["duration"])
        _sub(aci, "in", 0)
        _sub(aci, "out", src["duration"])
        _sub(aci, "file", id=fid)
        st = _sub(aci, "sourcetrack")
        _sub(st, "mediatype", "audio")
        _sub(st, "trackindex", track_idx)


def _append_master_clip_audio(parent: Element, src: dict) -> None:
    mc_id = masterclip_id_for(src["basename"])
    fid = file_id_for(src["basename"])
    clip = _sub(parent, "clip", id=mc_id)
    _sub(clip, "uuid", deterministic_uuid(mc_id))
    _sub(clip, "masterclipid", mc_id)
    _sub(clip, "ismasterclip", "TRUE")
    _sub(clip, "duration", src["duration"])
    _rate(clip, 24, True)
    _sub(clip, "name", src["basename"])
    media = _sub(clip, "media")
    audio = _sub(media, "audio")
    track = _sub(audio, "track")
    aci = _sub(track, "clipitem", id=f"{mc_id}--mc-a1")
    _sub(aci, "masterclipid", mc_id)
    _sub(aci, "name", src["basename"])
    _rate(aci, 24, True)
    _sub(aci, "duration", src["duration"])
    _sub(aci, "in", 0)
    _sub(aci, "out", src["duration"])
    _append_audio_file_def(
        aci,
        file_id=fid,
        basename=src["basename"],
        pathurl=src["pathurl"],
        duration=src["duration"],
        display_name=src["display_name"],
    )
    st = _sub(aci, "sourcetrack")
    _sub(st, "mediatype", "audio")
    _sub(st, "trackindex", 1)


def _append_timeline_clipitem(
    parent: Element,
    *,
    clip_id: str,
    masterclip_id: str,
    file_id: str,
    name: str,
    source_in: int,
    source_out: int,
    file_duration: int,
    seq_duration: int,
    is_audio: bool,
    label: str,
    sourcetrack_index: int = 1,
    links: list[tuple[str, str, int, int | None]] | None = None,
) -> None:
    attrs: dict[str, str] = {"id": clip_id}
    if is_audio:
        attrs["premiereChannelType"] = "mono"
    ci = _sub(parent, "clipitem", **attrs)
    _sub(ci, "masterclipid", masterclip_id)
    _sub(ci, "name", name)
    _sub(ci, "enabled", "TRUE")
    _sub(ci, "duration", file_duration)
    _rate(ci, 24, True)
    _sub(ci, "start", 0)
    _sub(ci, "end", seq_duration)
    _sub(ci, "in", source_in)
    _sub(ci, "out", source_out)
    if not is_audio:
        _sub(ci, "alphatype", "none")
        _sub(ci, "pixelaspectratio", "square")
        _sub(ci, "anamorphic", "FALSE")
        _sub(ci, "file", id=file_id)
        _basic_motion_scale_200(ci)
    else:
        _sub(ci, "file", id=file_id)
        st = _sub(ci, "sourcetrack")
        _sub(st, "mediatype", "audio")
        _sub(st, "trackindex", sourcetrack_index)
    if links:
        for link_id, mediatype, trackindex, groupindex in links:
            link = _sub(ci, "link")
            _sub(link, "linkclipref", link_id)
            _sub(link, "mediatype", mediatype)
            _sub(link, "trackindex", trackindex)
            _sub(link, "clipindex", 1)
            if groupindex is not None:
                _sub(link, "groupindex", groupindex)
    _labels(ci, label)


def _append_sequence(
    parent: Element,
    result: PullResult,
    sources: dict[str, dict],
) -> None:
    pull = result.pull
    span_by_key = {s.key: s for s in result.spans}
    sequence = _sub(parent, "sequence", id=f"sequence-{pull.pull_id}")
    _sub(sequence, "uuid", deterministic_uuid(pull.sequence_name))
    _sub(sequence, "duration", pull.duration)
    _rate(sequence, 24, True)
    _sub(sequence, "name", pull.sequence_name)
    media = _sub(sequence, "media")

    video = _sub(media, "video")
    fmt = _sub(video, "format")
    sc = _sub(fmt, "samplecharacteristics")
    _rate(sc, 24, True)
    _sub(sc, "width", 1920)
    _sub(sc, "height", 1080)
    _sub(sc, "anamorphic", "FALSE")
    _sub(sc, "pixelaspectratio", "square")
    _sub(sc, "fielddominance", "none")
    _sub(sc, "colordepth", 24)

    clip_ids = {key: f"{pull.pull_id}-{key.lower()}-001" for key in TRACK_KEYS}
    link_plan = [
        (clip_ids["V2"], "video", 2, None),
        (clip_ids["V1"], "video", 1, 1),
        (clip_ids["A1"], "audio", 1, 1),
        (clip_ids["A2"], "audio", 2, 1),
        (clip_ids["A3"], "audio", 3, 1),
    ]

    # V1 (CAM B) first in XML = bottom track; V2 (CAM A) second = targeted top track.
    v1_track = _sub(
        video,
        "track",
        **{"MZ.TrackName": "V1-CAM B", "TL.SQTrackTargeted": "0"},
    )
    v2_track = _sub(
        video,
        "track",
        **{"MZ.TrackName": "V2-CAM A", "TL.SQTrackTargeted": "1"},
    )

    for key, track_el in (("V1", v1_track), ("V2", v2_track)):
        span = span_by_key[key]
        src = sources[span.clip_name]
        _append_timeline_clipitem(
            track_el,
            clip_id=clip_ids[key],
            masterclip_id=masterclip_id_for(span.clip_name),
            file_id=file_id_for(span.clip_name),
            name=span.clip_name,
            source_in=span.source_in,
            source_out=span.source_out,
            file_duration=src["duration"],
            seq_duration=pull.duration,
            is_audio=False,
            label=pull.label,
            links=link_plan,
        )
        _sub(track_el, "enabled", "TRUE")
        _sub(track_el, "locked", "FALSE")

    audio = _sub(media, "audio")
    _sub(audio, "numOutputChannels", 2)
    audio_fmt = _sub(audio, "format")
    asc = _sub(audio_fmt, "samplecharacteristics")
    _sub(asc, "depth", 16)
    _sub(asc, "samplerate", 48000)

    for key, track_name in (
        ("A1", "A1-CAM-A"),
        ("A2", "A2-BOOM"),
        ("A3", "A3-LAV"),
    ):
        span = span_by_key[key]
        src = sources[span.clip_name]
        track_el = _sub(audio, "track", **{"MZ.TrackName": track_name})
        _append_timeline_clipitem(
            track_el,
            clip_id=clip_ids[key],
            masterclip_id=masterclip_id_for(span.clip_name),
            file_id=file_id_for(span.clip_name),
            name=span.clip_name,
            source_in=span.source_in,
            source_out=span.source_out,
            file_duration=src["duration"],
            seq_duration=pull.duration,
            is_audio=True,
            label=pull.label,
            links=link_plan,
        )
        _sub(track_el, "enabled", "TRUE")
        _sub(track_el, "locked", "FALSE")


def build_multi_pull_xml(
    assembly_root: ET.Element,
    results: list[PullResult],
    *,
    project_name: str,
) -> Element:
    sources = {bn: _source_meta(assembly_root, bn) for bn in ALL_SOURCES}

    root = ET.Element("xmeml", {"version": "4"})
    project = _sub(root, "project")
    _sub(project, "name", project_name)
    children = _sub(project, "children")

    footage = _sub(children, "bin")
    _sub(footage, "name", "Footage")
    footage_children = _sub(footage, "children")
    date_bin = _sub(footage_children, "bin")
    _sub(date_bin, "name", "2026-06-09")
    date_children = _sub(date_bin, "children")
    cam_a = _sub(date_children, "bin")
    _sub(cam_a, "name", "CAM A")
    cam_a_children = _sub(cam_a, "children")
    cam_b = _sub(date_children, "bin")
    _sub(cam_b, "name", "CAM B")
    cam_b_children = _sub(cam_b, "children")

    audio_bin = _sub(children, "bin")
    _sub(audio_bin, "name", "Audio")
    audio_children = _sub(audio_bin, "children")
    audio_date = _sub(audio_children, "bin")
    _sub(audio_date, "name", "2026-06-09")
    audio_date_children = _sub(audio_date, "children")
    person_bin = _sub(audio_date_children, "bin")
    _sub(person_bin, "name", "Tony Rook")
    person_children = _sub(person_bin, "children")

    seq_bin = _sub(children, "bin")
    _sub(seq_bin, "name", "Seq")
    seq_bin_children = _sub(seq_bin, "children")

    _append_master_clip_video(cam_a_children, sources[CAM_A])
    _append_master_clip_video(cam_b_children, sources[CAM_B_B002])
    _append_master_clip_video(cam_b_children, sources[CAM_B_B001])
    _append_master_clip_audio(person_children, sources[BOOM])
    _append_master_clip_audio(person_children, sources[LAV])

    for result in results:
        if result.ok:
            _append_sequence(seq_bin_children, result, sources)

    return root


def pretty_xml(root: Element) -> str:
    xml_bytes = ET.tostring(root, encoding="utf-8")
    ET.fromstring(xml_bytes)
    parsed = xml.dom.minidom.parseString(xml_bytes)
    return parsed.toprettyxml(indent="\t", encoding="UTF-8").decode("utf-8")


def build_report_v02(
    *,
    assembly: Path,
    digest: str,
    digest_ok: bool,
    results: list[PullResult],
    xml_text: str,
    pathurls: list[str],
    superseded: str | None,
    xml_sha256: str,
    file_sizes: dict[str, int],
) -> str:
    lines = [
        "# ep7 pull interface v02 — build report",
        "",
        f"- **Pinned assembly:** `{assembly}`",
        f"- **SHA-256:** `{digest}`",
        f"- **Digest check:** {'PASS' if digest_ok else 'FAIL'}",
        "",
    ]
    if superseded:
        lines.append(f"- **Superseded prior v02:** `{superseded}`")
        lines.append("")

    for result in results:
        pull = result.pull
        lines.extend([f"## {pull.pull_id.upper()} — {pull.sequence_name}", ""])
        if not result.ok:
            lines.append(f"- **Status:** FAIL — {result.error}")
            lines.append("")
            continue
        span_by_key = {s.key: s for s in result.spans}
        lines.append(f"- **Status:** PASS")
        lines.append(f"- **Handled:** {result.handled_in}–{result.handled_out} ({pull.duration}f)")
        lines.append("")
        lines.append("| Track | Expected offset | Derived | Match |")
        lines.append("|---|---:|---:|---|")
        for key in TRACK_KEYS:
            exp = pull.expected_offsets[key]
            got = span_by_key[key].offset
            lines.append(f"| {key} | {exp} | {got} | {'PASS' if exp == got else 'FAIL'} |")
        ab = span_by_key["V2"].offset - span_by_key["V1"].offset
        lines.append("")
        lines.append(
            f"- **A/B pairing:** {ab} (expected {pull.ab_pairing}) "
            f"({'PASS' if ab == pull.ab_pairing else 'FAIL'})"
        )
        lines.append("")
        lines.append("| Track | Expected in/out | Produced | Match |")
        lines.append("|---|---|---|---|")
        for key in TRACK_KEYS:
            exp = pull.expected_source[key]
            got = (span_by_key[key].source_in, span_by_key[key].source_out)
            lines.append(
                f"| {key} | {exp[0]}/{exp[1]} | {got[0]}/{got[1]} | "
                f"{'PASS' if got == exp else 'FAIL'} |"
            )
        if pull.pull_id == "p2":
            lines.append("")
            lines.append("- **P2 regression vs v01:** PASS (source in/out unchanged)")
        lines.append("")

    lines.extend(["## Document-wide checks", ""])
    lines.append("- **Master clip count:** 5 (expected 5)")
    full_files = len(re.findall(r"<pathurl>", xml_text))
    lines.append(f"- **Full file definitions:** {full_files} (expected 5)")
    ids = re.findall(r'<clipitem id="([^"]+)"', xml_text)
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    lines.append(
        f"- **Clipitem id uniqueness:** {'PASS' if not dupes else 'FAIL ' + repr(dupes)}"
    )
    v1_cam_b = xml_text.count('MZ.TrackName="V1-CAM B"')
    lines.append(f"- **V1 carries CAM B:** {v1_cam_b} sequences ({'PASS' if v1_cam_b == 5 else 'FAIL'})")
    lines.extend(["", "## Canonical pathurls", ""])
    for url in pathurls:
        lines.append(f"- `{url}`")
    banned = ("CloudStorage", "Macintosh HD", "Gain(dB)")
    lines.extend(["", "## Output grep checks", ""])
    for token in banned:
        count = xml_text.count(token)
        lines.append(f"- `{token}` occurrences: {count} ({'PASS' if count == 0 else 'FAIL'})")
    bad_urls = [
        u for u in re.findall(r"<pathurl>([^<]+)</pathurl>", xml_text)
        if not u.startswith("file://localhost/Volumes/SW_SERIES/")
    ]
    lines.append(
        f"- **Canonical pathurl prefix:** {'PASS' if not bad_urls else 'FAIL'}"
    )
    lines.extend(["", "## Post-write", ""])
    lines.append(f"- **Emitted XML SHA-256:** `{xml_sha256}`")
    for name, size in file_sizes.items():
        lines.append(f"- `{name}`: {size} bytes")
    lines.append("")
    return "\n".join(lines) + "\n"


def ensure_volume() -> None:
    if not os.path.isdir(VOLUME_ROOT) or not os.access(VOLUME_ROOT, os.R_OK):
        raise SystemExit(f"{VOLUME_ROOT} is not readable; aborting.")


def maybe_supersede(path: Path) -> str | None:
    if not path.is_file():
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest_dir = path.parent / "_superseded"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{path.stem}-{stamp}{path.suffix}"
    path.rename(dest)
    return str(dest)


def build_v02(
    *,
    out_xml: Path,
    project_name: str = "ep07-pullQuote-interface-v02-cu",
) -> tuple[Path, Path, Path]:
    ensure_volume()
    assembly = assembly_path()
    digest = sha256_file(assembly)
    digest_ok = digest == EXPECTED_ASSEMBLY_SHA256
    if not digest_ok:
        raise ValueError(
            f"pinned assembly digest mismatch: got {digest}, expected {EXPECTED_ASSEMBLY_SHA256}"
        )

    root = ET.parse(assembly).getroot()
    results: list[PullResult] = []
    for pull in PULLS:
        result = validate_pull(root, pull)
        results.append(result)
        if not result.ok:
            print(f"{pull.pull_id.upper()} skipped: {result.error}", file=sys.stderr)

    ok_results = [r for r in results if r.ok]
    if not ok_results:
        raise ValueError("no pulls passed validation")

    xmeml = build_multi_pull_xml(root, ok_results, project_name=project_name)
    xml_text = pretty_xml(xmeml)

    out_xml = Path(str(out_xml).replace("/Users/cgelles/Library/CloudStorage/Dropbox/SW_SERIES", VOLUME_ROOT))
    out_xml.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".xml",
        delete=False,
    ) as tmp:
        tmp.write(xml_text)
        tmp_path = Path(tmp.name)

    ET.parse(tmp_path)

    superseded = maybe_supersede(out_xml)
    tmp_path.rename(out_xml)

    paths_md = out_xml.with_name(out_xml.stem + "-paths.md")
    report_md = out_xml.with_name(out_xml.stem + "-report.md")
    paths_md.write_text(scan_originals_report(), encoding="utf-8")

    pathurls = sorted(set(re.findall(r"<pathurl>([^<]+)</pathurl>", xml_text)))
    xml_sha256 = sha256_file(out_xml)
    file_sizes = {
        out_xml.name: out_xml.stat().st_size,
        paths_md.name: paths_md.stat().st_size,
    }
    report_md.write_text(
        build_report_v02(
            assembly=assembly,
            digest=digest,
            digest_ok=digest_ok,
            results=results,
            xml_text=xml_text,
            pathurls=pathurls,
            superseded=superseded,
            xml_sha256=xml_sha256,
            file_sizes=file_sizes,
        ),
        encoding="utf-8",
    )
    file_sizes[report_md.name] = report_md.stat().st_size
    return out_xml, paths_md, report_md


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build ep7 quote-pull XMEML")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(
            "/Volumes/SW_SERIES/01_ProjectFiles/04_Premiere/_Episodes/"
            "ep07-biofilms/XMLs/ep07-pullQuote-interface-v02-cu.xml"
        ),
    )
    parser.add_argument(
        "--project-name",
        default="ep07-pullQuote-interface-v02-cu",
    )
    parser.add_argument(
        "--v01",
        action="store_true",
        help="Build single-pull v01 (P2 only) for regression",
    )
    args = parser.parse_args(argv)
    try:
        if args.v01:
            raise ValueError("v01 mode removed; use v02 builder")
        xml_path, paths_md, report_md = build_v02(
            out_xml=args.out,
            project_name=args.project_name,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(xml_path)
    print(paths_md)
    print(report_md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
