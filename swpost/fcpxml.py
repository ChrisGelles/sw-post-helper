"""FCP7 xmeml writer for stringout conform output."""

from __future__ import annotations

import copy
import re
import subprocess
import uuid
import wave
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote, unquote

from swpost.cards import (
    CardClip,
    build_color_matte_generatoritem,
    has_graphic_and_type_source_text,
    renamespace_card_clipitem,
)
from swpost.conform_report import ConformBuildReport
from swpost.offline import OfflineClip, person_under_cam_b
from swpost.overlap import OverlapTrim, trim_track_overlaps
from swpost.paths import ASSET_VO, FORBIDDEN_PATHURL_FRAGMENTS, PROXY_REGISTRY, VOLUME_ROOT
from swpost.person import label_color_for_person, person_for_basename
from swpost.project import ProjectedPiece, ProjectionReport

OUTPUT_WIDTH = 1920
OUTPUT_HEIGHT = 1080
SEQ_RATE = (24, True)
STILL_FILE_RATE = (30, True)
PPRO_TICKS_PER_FRAME = 254016000000 * 1001 // 24000
CONFORM_UUID_NS = uuid.UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")

CONFORM_VIDEO_TRACKS = 2  # V1-CAM-B=div0, V2-CAM-A=1; passthrough track 1+ sits above


def _passthrough_video_track_index(input_index: int) -> int:
    """Passthrough video sits above both camera conform tracks (B8)."""
    return CONFORM_VIDEO_TRACKS + input_index


CONFORM_VIDEO = (
    ("CAM_B", "V1-CAM-B", 0),
    ("CAM_A", "V2-CAM-A", 1),
)
CONFORM_AUDIO_LOGICAL = 4  # BOOM, LAV, LAV_INT, VO — passthrough audio sits above


def _passthrough_audio_logical_index(input_index: int) -> int:
    return CONFORM_AUDIO_LOGICAL + input_index


CONFORM_AUDIO = (
    ("BOOM", "A1-BOOM", 0),
    ("LAV", "A2-LAV", 1),
    ("LAV_INT", "A3-LAV-INTERNAL", 2),
    ("VO", "A4-VO", 3),
)

# Copied from reference/CMNH-SW-stringout-ref-270.xml (Premiere export).
PREMIERE_AUDIO_TRACK_ATTRS: dict[str, str] = {
    "TL.SQTrackAudioKeyframeStyle": "0",
    "TL.SQTrackShy": "0",
    "TL.SQTrackExpandedHeight": "41",
    "TL.SQTrackExpanded": "0",
    "PannerCurrentValue": "0.5",
    "PannerStartKeyframe": "-91445760000000000,0.5,0,0,0,0,0,0",
    "PannerName": "Balance",
    "premiereTrackType": "Stereo",
}
PREMIERE_PANNER_INVERTED = "true"
PREMIERE_TRACK_TARGETED_MONO = "1"
PREMIERE_TRACK_TARGETED_STEREO = "0"


class XmemlError(Exception):
    """Invalid xmeml output."""


class _ClipIdGen:
    def __init__(self, prefix: str) -> None:
        self._prefix = prefix
        self._n = 0

    def next(self, kind: str = "ci") -> str:
        self._n += 1
        return f"{self._prefix}-{kind}-{self._n:05d}"


@dataclass(frozen=True)
class XmemlInventory:
    master_clip_count: int
    real_source_master_clip_count: int
    offline_placeholder_count: int
    bin_tree_lines: list[str]
    master_clip_timeline_refs: dict[str, int]  # basename → sequence clipitem count
    master_clip_bins: dict[str, str]  # basename → bin path
    card_masterclip_ids: set[str] = field(default_factory=set)


def distinct_source_basenames(
    pieces: list[ProjectedPiece],
    offline: list[OfflineClip],
) -> set[str]:
    names = {p.file_basename for p in pieces}
    names.update(o.output_basename for o in offline if o.output_basename)
    return names


def real_source_basenames(pieces: list[ProjectedPiece]) -> set[str]:
    return {p.file_basename for p in pieces}


def offline_placeholder_basenames(offline: list[OfflineClip]) -> set[str]:
    return {
        o.output_basename
        for o in offline
        if o.synthetic and not o.empty_graphic and o.output_basename
    }


@dataclass(frozen=True)
class MediaDef:
    basename: str
    path: str
    masterclip_id: str
    file_id: str
    person: str
    shoot_date: str
    bin_camera: str | None  # CAM A | CAM B | None for audio
    bin_kind: str  # footage | audio | audio_passthrough | graphics | graphics_reference | vo
    file_rate: tuple[int, bool]  # timebase, ntsc
    is_still: bool
    needs_video: bool
    needs_audio: bool
    width: int | None
    height: int | None
    scale: int | None
    clip_duration: int  # master clip / clipitem duration
    file_duration: int | None  # on <file> when not still
    channelcount: int = 1
    is_offline_placeholder: bool = False
    lognote: str | None = None


def id_slug(basename: str) -> str:
    stem = Path(basename).stem
    return re.sub(r"[^A-Za-z0-9]+", "-", stem)


def masterclip_id(basename: str) -> str:
    return f"masterclip-{id_slug(basename)}"


def file_id(basename: str) -> str:
    return f"file-{id_slug(basename)}"


def masterclip_id_for_media_key(media_key: str) -> str:
    return f"masterclip-{id_slug(media_key)}"


def file_id_for_media_key(media_key: str) -> str:
    return f"file-{id_slug(media_key)}"


def deterministic_uuid(key: str) -> str:
    return str(uuid.uuid5(CONFORM_UUID_NS, key))


def frames_to_ppro_ticks(frames: int) -> int:
    return frames * PPRO_TICKS_PER_FRAME


def pathurl(path: str) -> str:
    return "file://localhost" + quote(path, safe="/:")


def shoot_date_from_proxy_path(path: str) -> str | None:
    m = re.search(r"/PROXIES/(20\d\d-\d\d-\d\d)/", path)
    return m.group(1) if m else None


def native_video_scale(path: str, basename: str) -> tuple[int, int, int | None]:
    if basename in PROXY_REGISTRY:
        meta = PROXY_REGISTRY[basename]
        return meta["width"], meta["height"], meta["scale_1080"]
    if "/2026-08-10/" in path or "_130101_" in basename or "_120101_" in basename:
        return 1920, 1080, None
    return 960, 540, 200


def _default_file_rate(basename: str) -> tuple[int, bool]:
    ext = Path(basename).suffix.lower()
    if ext in (".png", ".jpg", ".jpeg", ".wav"):
        return STILL_FILE_RATE
    return SEQ_RATE


def _is_still_basename(basename: str) -> bool:
    return Path(basename).suffix.lower() in (".png", ".jpg", ".jpeg")


def _track_usage(basename: str, track_kind: str) -> tuple[bool, bool]:
    ext = Path(basename).suffix.lower()
    if ext == ".wav":
        return False, True
    if ext in (".png", ".jpg", ".jpeg"):
        return True, False
    if track_kind == "video":
        return True, False
    if track_kind == "audio":
        return False, True
    return False, False


def _usage_refs(
    pieces: list[ProjectedPiece],
    offline: list[OfflineClip],
) -> tuple[dict[str, int], set[str], set[str]]:
    """Max source_out per basename; track which kinds reference each file."""
    max_out: dict[str, int] = {}
    video_refs: set[str] = set()
    audio_refs: set[str] = set()

    def note(basename: str, source_out: int, *, video: bool, audio: bool) -> None:
        max_out[basename] = max(max_out.get(basename, 0), source_out)
        if video:
            video_refs.add(basename)
        if audio:
            audio_refs.add(basename)

    for p in pieces:
        is_cam = p.role in ("CAM_A", "CAM_B")
        note(p.file_basename, p.source_out, video=is_cam, audio=not is_cam)
    for o in offline:
        video, audio = _track_usage(o.output_basename, o.track_kind)
        note(o.output_basename, o.source_out, video=video, audio=audio)
    return max_out, video_refs, audio_refs


def _camera_bin_label(basename: str) -> str | None:
    if basename.startswith("A"):
        return "CAM A"
    if basename.startswith("B"):
        return "CAM B"
    return None


def _cut_shoot_dates(pieces: list[ProjectedPiece]) -> dict[str, str]:
    by_cut: dict[str, str] = {}
    grouped: dict[str, list[ProjectedPiece]] = {}
    for p in pieces:
        grouped.setdefault(p.cut_label, []).append(p)
    for label, cut_pieces in grouped.items():
        for p in cut_pieces:
            if p.role == "CAM_B":
                d = shoot_date_from_proxy_path(p.file_path)
                if d:
                    by_cut[label] = d
                    break
        if label not in by_cut:
            for p in cut_pieces:
                d = shoot_date_from_proxy_path(p.file_path)
                if d:
                    by_cut[label] = d
                    break
        if label not in by_cut:
            by_cut[label] = "2026-06-09"
    return by_cut


CAPTURED_GENERATED_MARKER = "Captured and Generated"
VO_ASSET_MARKER = "02_Audio/04_VO/"


def _audio_channelcount(path: str) -> int:
    """Read channel count from media on disk; default mono when unavailable."""
    p = Path(path)
    if not p.is_file():
        return 1
    ext = p.suffix.lower()
    if ext == ".wav":
        try:
            with wave.open(str(p), "rb") as handle:
                return max(1, handle.getnchannels())
        except (OSError, wave.Error):
            return 1
    if ext in (".mov", ".mp4", ".m4a"):
        try:
            proc = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "a:0",
                    "-show_entries",
                    "stream=channels",
                    "-of",
                    "csv=p=0",
                    str(p),
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout.strip().isdigit():
                return max(1, int(proc.stdout.strip()))
        except (OSError, subprocess.TimeoutExpired):
            pass
    return 1


def _path_is_under_vo_asset(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return VO_ASSET_MARKER in normalized or normalized.startswith(ASSET_VO.rstrip("/"))


def _path_is_captured_generated(path: str) -> bool:
    return CAPTURED_GENERATED_MARKER in path.replace("\\", "/")


def _is_reference_render(o: OfflineClip) -> bool:
    name = o.output_basename.lower()
    path = o.output_path.lower()
    ext = Path(o.output_basename).suffix.lower()
    if ext not in (".mp4", ".mov"):
        return False
    if "rough" in name or "stringout" in name:
        return True
    return "/for_review/" in path or "/06_delivery/" in path


def _offline_bin_kind(o: OfflineClip) -> str:
    path = o.output_path.replace("\\", "/")
    if _path_is_under_vo_asset(path):
        return "vo"
    if o.synthetic and o.output_role == "VO":
        return "vo"
    if o.synthetic:
        return "graphics"
    ext = Path(o.output_basename).suffix.lower()
    if ext == ".wav" and _path_is_captured_generated(path):
        return "vo"
    if ext == ".wav":
        return "audio_passthrough"
    if _is_reference_render(o):
        return "graphics_reference"
    return "graphics"


def _shoot_date_for_timeline(
    timeline_start: int,
    timeline_end: int,
    pieces: list[ProjectedPiece],
    cut_dates: dict[str, str],
) -> str:
    for piece in pieces:
        if piece.role != "CAM_B":
            continue
        if piece.timeline_start < timeline_end and piece.timeline_end > timeline_start:
            return cut_dates.get(piece.cut_label, shoot_date_from_proxy_path(piece.file_path) or "2026-06-09")
    for piece in pieces:
        if piece.timeline_start < timeline_end and piece.timeline_end > timeline_start:
            d = shoot_date_from_proxy_path(piece.file_path)
            if d:
                return d
    return "2026-06-09"


def _collect_media(
    pieces: list[ProjectedPiece],
    offline: list[OfflineClip],
    cut_dates: dict[str, str],
    build_report: ConformBuildReport | None = None,
) -> dict[str, MediaDef]:
    max_out, video_refs, audio_refs = _usage_refs(pieces, offline)
    media: dict[str, MediaDef] = {}

    def build_def(
        *,
        basename: str,
        path: str,
        person: str,
        shoot_date: str,
        bin_camera: str | None,
        bin_kind: str,
        is_offline_placeholder: bool = False,
        lognote: str | None = None,
        channelcount: int = 1,
        masterclip_id_override: str | None = None,
        file_id_override: str | None = None,
    ) -> MediaDef:
        is_still = _is_still_basename(basename)
        file_rate = _default_file_rate(basename)
        needs_video = basename in video_refs
        needs_audio = basename in audio_refs
        if not needs_video and not needs_audio:
            raise XmemlError(f"no track references for media {basename!r}")
        w = h = sc = None
        if needs_video:
            w, h, sc = native_video_scale(path, basename)
        clip_dur = max(max_out.get(basename, 1), 1)
        if is_still:
            clip_dur = max(clip_dur + 86400, clip_dur + 1)
        file_dur = None if is_still else max(max_out.get(basename, 1), 1)
        if needs_video and not is_still:
            channelcount = _audio_channelcount(path)
            if channelcount >= 1:
                needs_audio = True
        elif needs_audio:
            channelcount = _audio_channelcount(path)
        return MediaDef(
            basename=basename,
            path=path,
            masterclip_id=masterclip_id_override or masterclip_id(basename),
            file_id=file_id_override or file_id(basename),
            person=person,
            shoot_date=shoot_date,
            bin_camera=bin_camera,
            bin_kind=bin_kind,
            file_rate=file_rate,
            is_still=is_still,
            needs_video=needs_video,
            needs_audio=needs_audio,
            width=w,
            height=h,
            scale=sc,
            clip_duration=clip_dur,
            file_duration=file_dur,
            channelcount=channelcount,
            is_offline_placeholder=is_offline_placeholder,
            lognote=lognote,
        )

    for p in pieces:
        if p.file_basename in media:
            continue
        if p.person == "Unknown":
            raise XmemlError(
                f"person attribution returned Unknown for projected source "
                f"{p.file_basename!r} ({p.role})"
            )
        is_cam = p.role in ("CAM_A", "CAM_B")
        shoot = cut_dates.get(p.cut_label, "2026-06-09")
        media[p.file_basename] = build_def(
            basename=p.file_basename,
            path=p.file_path,
            person=p.person,
            shoot_date=shoot,
            bin_camera=_camera_bin_label(p.file_basename) if is_cam else None,
            bin_kind="footage" if is_cam else "audio",
        )

    known_basenames = {md.basename for md in media.values()}

    for o in offline:
        if o.empty_graphic or not o.output_basename or not o.media_key:
            continue
        if o.media_key in media or o.output_basename in known_basenames:
            continue
        bin_kind = _offline_bin_kind(o)
        path = o.output_path.replace("\\", "/")
        if (
            bin_kind == "vo"
            and _path_is_captured_generated(path)
            and build_report is not None
        ):
            build_report.scratch_vo_relocate.append(
                {
                    "basename": o.output_basename,
                    "path": o.output_path,
                }
            )
        shoot = _shoot_date_for_timeline(o.timeline_start, o.timeline_end, pieces, cut_dates)
        label_person = "Passthrough"
        media[o.media_key] = build_def(
            basename=o.output_basename,
            path=o.output_path,
            person=label_person,
            shoot_date=shoot,
            bin_camera=None,
            bin_kind=bin_kind,
            is_offline_placeholder=o.synthetic,
            lognote=o.label if o.synthetic else None,
            masterclip_id_override=masterclip_id_for_media_key(o.media_key),
            file_id_override=file_id_for_media_key(o.media_key),
        )
        known_basenames.add(o.output_basename)
    return media


def _subel(
    parent: ET.Element,
    tag: str,
    text: str | int | None = None,
    **attrib: str,
) -> ET.Element:
    el = ET.SubElement(parent, tag, attrib)
    if text is not None:
        el.text = str(text)
    return el


def _append_rate(parent: ET.Element, rate: tuple[int, bool]) -> None:
    r = _subel(parent, "rate")
    _subel(r, "timebase", rate[0])
    _subel(r, "ntsc", "TRUE" if rate[1] else "FALSE")


def _seq_rate(parent: ET.Element) -> None:
    _append_rate(parent, SEQ_RATE)


def _append_file_timecode(parent: ET.Element, rate: tuple[int, bool]) -> None:
    tc = _subel(parent, "timecode")
    _append_rate(tc, rate)
    if rate[0] == 30 and rate[1]:
        _subel(tc, "string", "00;00;00;00")
        _subel(tc, "displayformat", "DF")
    else:
        _subel(tc, "string", "00:00:00:00")
        _subel(tc, "displayformat", "NDF")
    _subel(tc, "frame", 0)


def _append_file_def(parent: ET.Element, md: MediaDef, *, full: bool) -> None:
    if not full:
        _subel(parent, "file", id=md.file_id)
        return
    fe = _subel(parent, "file", id=md.file_id)
    _subel(fe, "name", Path(md.path).name)
    _subel(fe, "pathurl", pathurl(md.path))
    _append_rate(fe, md.file_rate)
    if not md.is_still and md.file_duration is not None:
        _subel(fe, "duration", md.file_duration)
    _append_file_timecode(fe, md.file_rate)
    med = _subel(fe, "media")
    if md.needs_video:
        vid = _subel(med, "video")
        sc = _subel(vid, "samplecharacteristics")
        _append_rate(sc, md.file_rate)
        _subel(sc, "width", md.width or OUTPUT_WIDTH)
        _subel(sc, "height", md.height or OUTPUT_HEIGHT)
        _subel(sc, "anamorphic", "FALSE")
        _subel(sc, "pixelaspectratio", "square")
        _subel(sc, "fielddominance", "none")
    if md.needs_audio:
        aud = _subel(med, "audio")
        asc = _subel(aud, "samplecharacteristics")
        _subel(asc, "depth", 16)
        _subel(asc, "samplerate", 48000)
        _subel(aud, "channelcount", md.channelcount)


def _append_scale_filter(parent: ET.Element, scale: int | None) -> None:
    if scale is None:
        return
    filt = _subel(parent, "filter")
    eff = _subel(filt, "effect")
    _subel(eff, "name", "Basic Motion")
    _subel(eff, "effectid", "basic")
    _subel(eff, "effectcategory", "motion")
    _subel(eff, "effecttype", "motion")
    _subel(eff, "mediatype", "video")
    param = _subel(eff, "parameter")
    _subel(param, "parameterid", "scale")
    _subel(param, "name", "Scale")
    _subel(param, "valuemin", 0)
    _subel(param, "valuemax", 1000)
    _subel(param, "value", scale)


def _append_sequence_logginginfo(
    parent: ET.Element,
    *,
    description: str | None = None,
    lognote: str | None = None,
) -> None:
    info = _subel(parent, "logginginfo")
    _subel(info, "description", description or "")
    _subel(info, "scene", "")
    _subel(info, "shottake", "")
    _subel(info, "lognote", lognote or "")
    _subel(info, "good", "")


def _append_colorinfo(parent: ET.Element) -> None:
    info = _subel(parent, "colorinfo")
    for tag in ("lut", "lut1", "asc_sop", "asc_sat", "lut2"):
        _subel(info, tag, "")


def _append_lognote(parent: ET.Element, text: str | None) -> None:
    if not text:
        return
    _append_sequence_logginginfo(parent, lognote=text)


def _append_master_clipitem(
    track_el: ET.Element,
    *,
    clip_id: str,
    md: MediaDef,
    full_file: bool,
    audio_track_index: int | None = None,
) -> None:
    ci = _subel(track_el, "clipitem", id=clip_id)
    _subel(ci, "masterclipid", md.masterclip_id)
    _subel(ci, "name", md.basename)
    _seq_rate(ci)
    _subel(ci, "duration", md.clip_duration)
    _subel(ci, "in", 0)
    _subel(ci, "out", md.clip_duration)
    _append_file_def(ci, md, full=full_file)
    if md.needs_video and full_file:
        _append_scale_filter(ci, md.scale)
    if audio_track_index is not None:
        st = _subel(ci, "sourcetrack")
        _subel(st, "mediatype", "audio")
        _subel(st, "trackindex", audio_track_index)


def _append_master_clip(bin_el: ET.Element, md: MediaDef, ids: _ClipIdGen) -> None:
    clip = _subel(bin_el, "clip", id=md.masterclip_id)
    _subel(clip, "uuid", deterministic_uuid(md.masterclip_id))
    _subel(clip, "masterclipid", md.masterclip_id)
    _subel(clip, "ismasterclip", "TRUE")
    _subel(clip, "duration", md.clip_duration)
    _seq_rate(clip)
    _subel(clip, "name", md.basename)
    media = _subel(clip, "media")
    if md.needs_video:
        video = _subel(media, "video")
        track = _subel(video, "track")
        _append_master_clipitem(
            track,
            clip_id=ids.next("mc"),
            md=md,
            full_file=True,
        )
    if md.needs_audio:
        audio = _subel(media, "audio")
        channels = max(1, md.channelcount)
        for ch_idx in range(1, channels + 1):
            track = _subel(audio, "track")
            _append_master_clipitem(
                track,
                clip_id=ids.next("mc"),
                md=md,
                full_file=not md.needs_video and ch_idx == 1,
                audio_track_index=ch_idx,
            )


def _append_sequence_clipitem(
    track_el: ET.Element,
    *,
    clip_id: str,
    md: MediaDef,
    piece_tl_start: int,
    piece_tl_end: int,
    source_in: int,
    source_out: int,
    enabled: bool,
    person: str,
    log_description: str | None = None,
    lognote: str | None = None,
    on_audio_track: bool = False,
    premiere_channel_type: str | None = None,
) -> None:
    ci = _subel(track_el, "clipitem", id=clip_id)
    _subel(ci, "masterclipid", md.masterclip_id)
    _subel(ci, "name", md.basename)
    _subel(ci, "enabled", "TRUE" if enabled else "FALSE")
    _subel(ci, "duration", md.clip_duration)
    _seq_rate(ci)
    _subel(ci, "start", piece_tl_start)
    _subel(ci, "end", piece_tl_end)
    _subel(ci, "in", source_in)
    _subel(ci, "out", source_out)
    _subel(ci, "pproTicksIn", frames_to_ppro_ticks(source_in))
    _subel(ci, "pproTicksOut", frames_to_ppro_ticks(source_out))
    is_audio = on_audio_track or (md.needs_audio and not md.needs_video)
    if is_audio:
        channel_type = premiere_channel_type or (
            "stereo" if md.channelcount >= 2 else "mono"
        )
        ci.set("premiereChannelType", channel_type)
        _append_file_def(ci, md, full=False)
        st = _subel(ci, "sourcetrack")
        _subel(st, "mediatype", "audio")
        _subel(st, "trackindex", 1)
        _append_sequence_logginginfo(
            ci,
            description=log_description,
            lognote=lognote,
        )
        _append_colorinfo(ci)
    else:
        _subel(ci, "alphatype", "none")
        _subel(ci, "pixelaspectratio", "square")
        _subel(ci, "anamorphic", "FALSE")
        _append_file_def(ci, md, full=False)
        if md.needs_video:
            _append_scale_filter(ci, md.scale)
        _append_sequence_logginginfo(
            ci,
            description=log_description,
            lognote=lognote,
        )
        _append_colorinfo(ci)
    labels = _subel(ci, "labels")
    _subel(labels, "label2", label_color_for_person(person))


def _append_audio_clipitems(
    track_els: list[ET.Element],
    *,
    clip_id: str,
    md: MediaDef,
    piece_tl_start: int,
    piece_tl_end: int,
    source_in: int,
    source_out: int,
    enabled: bool,
    person: str,
    log_description: str | None = None,
    lognote: str | None = None,
) -> None:
    if md.channelcount >= 2:
        if len(track_els) < 2:
            raise XmemlError(
                f"stereo clip {md.basename!r} needs exploded pair tracks, got {len(track_els)}"
            )
        for idx, track_el in enumerate(track_els[:2]):
            _append_sequence_clipitem(
                track_el,
                clip_id=f"{clip_id}-ch{idx}",
                md=md,
                piece_tl_start=piece_tl_start,
                piece_tl_end=piece_tl_end,
                source_in=source_in,
                source_out=source_out,
                enabled=enabled,
                person=person,
                log_description=log_description,
                lognote=lognote,
                on_audio_track=True,
                premiere_channel_type="stereo",
            )
    else:
        _append_sequence_clipitem(
            track_els[0],
            clip_id=clip_id,
            md=md,
            piece_tl_start=piece_tl_start,
            piece_tl_end=piece_tl_end,
            source_in=source_in,
            source_out=source_out,
            enabled=enabled,
            person=person,
            log_description=log_description,
            lognote=lognote,
            on_audio_track=True,
            premiere_channel_type="mono",
        )


def _validate_clipitem_ids(root: ET.Element) -> None:
    missing = [ci for ci in root.iter("clipitem") if not ci.get("id")]
    if missing:
        raise XmemlError(f"{len(missing)} clipitems missing id attribute")
    ids = [el.get("id") for el in root.iter("clipitem") if el.get("id")]
    if len(ids) != len(set(ids)):
        dupes = {i for i in ids if ids.count(i) > 1}
        raise XmemlError(f"duplicate clipitem ids: {sorted(dupes)}")


def _master_clips_in_bins(root: ET.Element) -> list[tuple[str, str, str]]:
    """Return (basename, masterclip_id, bin_path) for each bin master clip."""
    project = root.find("project")
    if project is None:
        raise XmemlError("missing project element")
    children = project.find("children")
    if children is None:
        raise XmemlError("missing project children")

    found: list[tuple[str, str, str]] = []

    def walk_bin(bin_el: ET.Element, path: list[str]) -> None:
        name = bin_el.findtext("name") or "?"
        here = path + [name]
        kids = bin_el.find("children")
        if kids is None:
            return
        for child in kids:
            if child.tag == "bin":
                walk_bin(child, here)
            elif child.tag == "clip" and child.findtext("ismasterclip") == "TRUE":
                basename = child.findtext("name") or ""
                mc_id = child.get("id") or child.findtext("masterclipid") or ""
                found.append((basename, mc_id, "/".join(here)))

    for top_bin in children.findall("bin"):
        walk_bin(top_bin, [])

    return found


def _validate_master_clip_bins(root: ET.Element, expected_basenames: set[str]) -> None:
    found = _master_clips_in_bins(root)
    basenames = [b for b, _, _ in found]
    basename_set = set(basenames)

    if len(found) != len(expected_basenames):
        raise XmemlError(
            f"master clip count {len(found)} != distinct source basenames "
            f"{len(expected_basenames)}"
        )
    if basename_set != expected_basenames:
        missing = expected_basenames - basename_set
        extra = basename_set - expected_basenames
        raise XmemlError(
            f"master clip basenames mismatch; missing={sorted(missing)!r} "
            f"extra={sorted(extra)!r}"
        )
    if len(basenames) != len(basename_set):
        by_bin: dict[str, list[str]] = {}
        for bn, _, bp in found:
            by_bin.setdefault(bn, []).append(bp)
        multi = {b: paths for b, paths in by_bin.items() if len(paths) > 1}
        raise XmemlError(
            "basename appears in multiple bins: "
            + ", ".join(f"{b!r} in {paths}" for b, paths in sorted(multi.items()))
        )


def _validate_masterclipid_resolution(
    root: ET.Element,
    *,
    exempt_masterclip_ids: set[str] | None = None,
) -> None:
    exempt = exempt_masterclip_ids or set()
    defined = {
        mc_id
        for _, mc_id, _ in _master_clips_in_bins(root)
        if mc_id
    }
    dangling: list[str] = []
    for ci in root.iter("clipitem"):
        if ci.find("start") is None:
            continue
        mc_el = ci.find("masterclipid")
        if mc_el is None or not mc_el.text:
            file_el = ci.find("file")
            if (
                file_el is not None
                and file_el.findtext("mediaSource") == "GraphicAndType"
                and file_el.find("pathurl") is None
            ):
                continue
            dangling.append("(missing masterclipid)")
            continue
        if mc_el.text in exempt:
            continue
        if mc_el.text not in defined:
            dangling.append(mc_el.text)
    if dangling:
        raise XmemlError(
            f"sequence clipitems with unresolved masterclipid: {sorted(set(dangling))}"
        )


def collect_card_masterclip_ids(root: ET.Element) -> set[str]:
    """Masterclip ids for inline GraphicAndType cards (exempt from bin lookup)."""
    exempt: set[str] = set()
    for ci in root.iter("clipitem"):
        if ci.find("start") is None:
            continue
        file_el = ci.find("file")
        if file_el is None or file_el.findtext("mediaSource") != "GraphicAndType":
            continue
        mc_el = ci.find("masterclipid")
        if mc_el is not None and mc_el.text:
            exempt.add(mc_el.text)
    return exempt


def _file_is_inline_definition(file_el: ET.Element) -> bool:
    return len(list(file_el)) > 0


def _assert_full_file_structure(file_el: ET.Element, *, fid: str) -> None:
    """Every full <file> definition requires name, rate, timecode, and <media>."""
    missing = [
        tag
        for tag in ("name", "rate", "timecode", "media")
        if file_el.find(tag) is None
    ]
    if missing:
        raise XmemlError(
            f"file {fid!r} missing required elements: {', '.join(missing)}"
        )
    media = file_el.find("media")
    assert media is not None
    has_video = media.find("video") is not None
    has_audio = media.find("audio") is not None
    if not has_video and not has_audio:
        raise XmemlError(f"file {fid!r} <media> has neither <video> nor <audio>")


def count_full_file_violations(root: ET.Element) -> list[str]:
    """Return file ids whose full definitions lack name/rate/timecode/media."""
    violations: list[str] = []
    for file_el in root.iter("file"):
        if not _file_is_inline_definition(file_el):
            continue
        fid = file_el.get("id") or "?"
        missing = [
            tag
            for tag in ("name", "rate", "timecode", "media")
            if file_el.find(tag) is None
        ]
        if missing:
            violations.append(fid)
    return violations


def _file_is_full_definition(file_el: ET.Element) -> bool:
    if file_el.find("pathurl") is not None:
        return True
    if file_el.findtext("mediaSource"):
        return True
    if file_el.find("media") is not None:
        return True
    return False


def _validate_file_definitions(root: ET.Element) -> None:
    full_defs: dict[str, ET.Element] = {}
    for file_el in root.iter("file"):
        fid = file_el.get("id")
        if fid is None:
            continue
        if _file_is_full_definition(file_el) and fid not in full_defs:
            full_defs[fid] = file_el

    for file_el in root.iter("file"):
        fid = file_el.get("id")
        if fid is None:
            continue
        if _file_is_full_definition(file_el):
            if fid in full_defs and full_defs[fid] is not file_el:
                raise XmemlError(f"duplicate full <file> definition for id {fid!r}")
            continue
        if fid not in full_defs:
            raise XmemlError(f"bare <file id={fid!r}/> with no prior full definition")

    pathurl_ids: set[str] = set()
    for file_el in root.iter("file"):
        fid = file_el.get("id")
        if fid is None:
            continue
        has_url = file_el.find("pathurl") is not None
        if has_url:
            if fid in pathurl_ids:
                raise XmemlError(f"<pathurl> appears more than once for file id {fid!r}")
            pathurl_ids.add(fid)
        elif fid not in full_defs:
            raise XmemlError(f"undefined file reference id={fid!r}")


def _validate_pathurls(root: ET.Element) -> None:
    for el in root.iter("pathurl"):
        text = el.text or ""
        for frag in FORBIDDEN_PATHURL_FRAGMENTS:
            if frag in text:
                raise XmemlError(f"forbidden pathurl fragment {frag!r} in {text!r}")


def _file_durations(root: ET.Element) -> dict[str, int | None]:
    durations: dict[str, int | None] = {}
    for file_el in root.iter("file"):
        fid = file_el.get("id")
        if fid is None or file_el.find("pathurl") is None:
            continue
        dur_el = file_el.find("duration")
        durations[fid] = int(dur_el.text) if dur_el is not None and dur_el.text else None
    return durations


def _validate_source_out_within_file_duration(root: ET.Element) -> None:
    durations = _file_durations(root)
    for ci in root.iter("clipitem"):
        if ci.find("start") is None:
            continue
        out_el = ci.find("out")
        file_el = ci.find("file")
        if out_el is None or out_el.text is None or file_el is None:
            continue
        fid = file_el.get("id")
        if fid is None:
            continue
        file_dur = durations.get(fid)
        if file_dur is None:
            continue
        out_val = int(out_el.text)
        if out_val > file_dur:
            name = ci.findtext("name") or "?"
            raise XmemlError(
                f"clipitem {name!r} out={out_val} exceeds file duration {file_dur}"
            )


def _validate_no_track_overlaps(root: ET.Element) -> None:
    seq = _find_sequence(root)
    if seq is None:
        return
    media = seq.find("media")
    if media is None:
        return
    for group_tag in ("video", "audio"):
        group = media.find(group_tag)
        if group is None:
            continue
        for tr in group.findall("track"):
            spans: list[tuple[int, int, str]] = []
            for ci in tr.findall("clipitem"):
                if ci.find("start") is None:
                    continue
                start = int(ci.findtext("start", "0"))
                end = int(ci.findtext("end", "0"))
                name = ci.findtext("name") or "?"
                spans.append((start, end, name))
            spans.sort(key=lambda x: x[0])
            for i in range(1, len(spans)):
                prev_start, prev_end, prev_name = spans[i - 1]
                start, _, name = spans[i]
                if start < prev_end:
                    track_name = tr.get("MZ.TrackName") or group_tag
                    raise XmemlError(
                        f"overlapping clipitems on {track_name!r}: "
                        f"{prev_name!r} ends {prev_end}, {name!r} starts {start}"
                    )


def _find_sequence(root: ET.Element) -> ET.Element | None:
    for seq in root.iter("sequence"):
        if seq.find("media") is not None:
            return seq
    return None


def _file_has_video(file_el: ET.Element) -> bool:
    media = file_el.find("media")
    return media is not None and media.find("video") is not None


def _file_has_audio(file_el: ET.Element) -> bool:
    media = file_el.find("media")
    return media is not None and media.find("audio") is not None


def _resolve_file_el(root: ET.Element, file_ref: ET.Element) -> ET.Element | None:
    fid = file_ref.get("id")
    if fid is None:
        return file_ref if file_ref.find("pathurl") is not None else None
    for file_el in root.iter("file"):
        if file_el.get("id") == fid and file_el.find("pathurl") is not None:
            return file_el
    return None


def _validate_track_media_kind(root: ET.Element) -> None:
    seq = _find_sequence(root)
    if seq is None:
        return
    media = seq.find("media")
    if media is None:
        return
    video_group = media.find("video")
    if video_group is not None:
        for tr in video_group.findall("track"):
            for ci in tr.findall("clipitem"):
                if ci.find("start") is None:
                    continue
                file_ref = ci.find("file")
                if file_ref is None:
                    continue
                file_el = _resolve_file_el(root, file_ref)
                if file_el is None:
                    continue
                if not _file_has_video(file_el):
                    name = ci.findtext("name") or "?"
                    raise XmemlError(
                        f"video track clipitem {name!r} references file without <video> media"
                    )
    audio_group = media.find("audio")
    if audio_group is not None:
        for tr in audio_group.findall("track"):
            for ci in tr.findall("clipitem"):
                if ci.find("start") is None:
                    continue
                file_ref = ci.find("file")
                if file_ref is None:
                    continue
                file_el = _resolve_file_el(root, file_ref)
                if file_el is None:
                    continue
                if not _file_has_audio(file_el):
                    name = ci.findtext("name") or "?"
                    raise XmemlError(
                        f"audio track clipitem {name!r} references file without <audio> media"
                    )


def _validate_file_media_blocks(root: ET.Element) -> None:
    """B2: every full <file> definition requires name, rate, timecode, and <media>."""
    for file_el in root.iter("file"):
        if not _file_is_inline_definition(file_el):
            continue
        fid = file_el.get("id") or "?"
        _assert_full_file_structure(file_el, fid=fid)
    for clip in root.iter("clip"):
        if clip.findtext("ismasterclip") != "TRUE":
            continue
        name = clip.findtext("name") or "?"
        media = clip.find("media")
        if media is None:
            raise XmemlError(f"master clip {name!r} missing <media>")
        video = media.find("video")
        if video is not None:
            track = video.find("track")
            if track is None or track.find("clipitem") is None:
                raise XmemlError(
                    f"master clip {name!r} missing clip/media/video/track/clipitem"
                )
        audio = media.find("audio")
        if audio is not None:
            tracks = audio.findall("track")
            if not tracks or not any(t.find("clipitem") is not None for t in tracks):
                raise XmemlError(
                    f"master clip {name!r} missing clip/media/audio/track/clipitem"
                )
        if video is None and audio is None:
            raise XmemlError(f"master clip {name!r} has empty <media>")


ALLOWED_MASTER_CLIP_BIN = (
    re.compile(r"^Footage/\d{4}-\d{2}-\d{2}/CAM A$"),
    re.compile(r"^Footage/\d{4}-\d{2}-\d{2}/CAM B$"),
    re.compile(r"^Audio/\d{4}-\d{2}-\d{2}/[^/]+$"),
    re.compile(r"^Audio/_Passthrough$"),
    re.compile(r"^Graphics$"),
    re.compile(r"^Graphics/_Reference$"),
    re.compile(r"^VO$"),
    re.compile(r"^Seq$"),
)


def _bin_path_allowed(path: str) -> bool:
    if path.endswith("/Unknown") or "/Unknown/" in path:
        return False
    if path.endswith("/Passthrough") and path != "Audio/_Passthrough":
        return False
    return any(p.match(path) for p in ALLOWED_MASTER_CLIP_BIN)


def _validate_master_clip_bin_paths(root: ET.Element) -> None:
    for basename, _mc_id, bin_path in _master_clips_in_bins(root):
        if not _bin_path_allowed(bin_path):
            raise XmemlError(
                f"master clip {basename!r} in disallowed bin {bin_path!r}"
            )
        parts = bin_path.split("/")
        if parts[0] == "Audio" and len(parts) == 3 and parts[1] != "_Passthrough":
            person = parts[2]
            if person in ("Unknown", "Passthrough"):
                raise XmemlError(
                    f"master clip {basename!r} in invalid person bin {person!r}"
                )


def _pathurl_contains_basename(url: str, basename: str) -> bool:
    if not basename:
        return True
    if basename in unquote(url):
        return True
    return quote(basename, safe="/") in url


def _validate_ids_from_basenames(root: ET.Element) -> None:
    for basename, mc_id, bin_path in _master_clips_in_bins(root):
        if not bin_path.startswith("Footage/"):
            continue
        expected = masterclip_id(basename)
        if mc_id != expected:
            raise XmemlError(
                f"masterclip id for {basename!r} is {mc_id!r}, expected {expected!r}"
            )
    seen_full: set[str] = set()
    for file_el in root.iter("file"):
        if file_el.find("pathurl") is None:
            continue
        fid = file_el.get("id")
        name = file_el.findtext("name") or ""
        expected_fid = file_id(name)
        url = file_el.findtext("pathurl") or ""
        if fid != expected_fid and "/PROXIES/" in url:
            raise XmemlError(
                f"file id for {name!r} is {fid!r}, expected {expected_fid!r}"
            )
        if fid in seen_full:
            raise XmemlError(f"duplicate full file definition for {fid!r}")
        seen_full.add(fid)
        if not _pathurl_contains_basename(url, name):
            raise XmemlError(
                f"pathurl for {name!r} does not contain basename: {url!r}"
            )


def _validate_sequence_clipitem_names(root: ET.Element) -> None:
    mc_id_to_basename = {
        mc_id: bn for bn, mc_id, _ in _master_clips_in_bins(root) if mc_id
    }
    seq = _find_sequence(root)
    if seq is None:
        return
    for ci in seq.iter("clipitem"):
        if ci.find("start") is None:
            continue
        name = ci.findtext("name") or ""
        mc_el = ci.find("masterclipid")
        if mc_el is None or not mc_el.text:
            continue
        expected = mc_id_to_basename.get(mc_el.text)
        if expected is None:
            continue
        if name != expected:
            raise XmemlError(
                f"sequence clipitem name {name!r} != source filename {expected!r}"
            )


def _prune_empty_bin(bin_el: ET.Element) -> bool:
    """Remove empty sub-bins; return True if this bin has content."""
    kids = bin_el.find("children")
    if kids is None:
        return False
    has_content = False
    for child in list(kids):
        if child.tag == "bin":
            if _prune_empty_bin(child):
                has_content = True
            else:
                kids.remove(child)
        elif child.tag in ("clip", "sequence"):
            has_content = True
    return has_content


def _sort_track_clipitems(track_el: ET.Element) -> None:
    clipitems = [
        ci
        for ci in track_el.findall("clipitem")
        if ci.find("start") is not None
    ]
    for ci in clipitems:
        track_el.remove(ci)
    clipitems.sort(key=lambda ci: int(ci.findtext("start", "0")))
    for ci in clipitems:
        track_el.append(ci)


def _prune_empty_sequence_tracks(media_group: ET.Element | None) -> None:
    if media_group is None:
        return
    for track in list(media_group.findall("track")):
        if track.find("clipitem") is None and track.find("generatoritem") is None:
            media_group.remove(track)


def prune_empty_bins(root: ET.Element) -> None:
    project = root.find("project")
    if project is None:
        return
    children = project.find("children")
    if children is None:
        return
    for bin_el in list(children.findall("bin")):
        if not _prune_empty_bin(bin_el):
            children.remove(bin_el)


def _file_channelcount(root: ET.Element, file_ref: ET.Element) -> int | None:
    file_el = _resolve_file_el(root, file_ref)
    if file_el is None:
        return None
    aud = file_el.find("media/audio")
    if aud is None:
        return None
    cc = aud.find("channelcount")
    if cc is None or cc.text is None:
        return None
    return int(cc.text)


def _validate_sequence_audio_schema(root: ET.Element) -> None:
    seq = _find_sequence(root)
    if seq is None:
        return
    media = seq.find("media")
    if media is None:
        return
    audio_group = media.find("audio")
    if audio_group is None:
        return
    if audio_group.find("numOutputChannels") is None:
        raise XmemlError("sequence audio missing numOutputChannels")
    if audio_group.find("format") is None:
        raise XmemlError("sequence audio missing format")
    outputs = audio_group.find("outputs")
    if outputs is None or not outputs.findall("group"):
        raise XmemlError("sequence audio missing outputs groups")
    for tr in audio_group.findall("track"):
        if tr.find("clipitem") is None:
            continue
        exploded = int(tr.get("totalExplodedTrackCount", "1"))
        for ci in tr.findall("clipitem"):
            if ci.find("start") is None:
                continue
            file_ref = ci.find("file")
            if file_ref is None:
                continue
            ch = _file_channelcount(root, file_ref)
            if ch is None:
                continue
            ctype = ci.get("premiereChannelType", "")
            track_name = tr.get("MZ.TrackName") or "audio"
            if ch < 2:
                if exploded != 1:
                    raise XmemlError(
                        f"mono file {ci.findtext('name')!r} on {track_name!r} "
                        f"has totalExplodedTrackCount={exploded}, expected 1"
                    )
                if ctype != "mono":
                    raise XmemlError(
                        f"mono file {ci.findtext('name')!r} on {track_name!r} "
                        f"has premiereChannelType={ctype!r}, expected mono"
                    )
            else:
                if exploded != 2:
                    raise XmemlError(
                        f"stereo file {ci.findtext('name')!r} on {track_name!r} "
                        f"has totalExplodedTrackCount={exploded}, expected 2"
                    )
                if ctype != "stereo":
                    raise XmemlError(
                        f"stereo file {ci.findtext('name')!r} on {track_name!r} "
                        f"has premiereChannelType={ctype!r}, expected stereo"
                    )


def _validate_track_clipitem_order(root: ET.Element) -> None:
    seq = _find_sequence(root)
    if seq is None:
        return
    media = seq.find("media")
    if media is None:
        return
    for group_tag in ("video", "audio"):
        group = media.find(group_tag)
        if group is None:
            continue
        for tr in group.findall("track"):
            starts: list[int] = []
            for ci in tr.findall("clipitem"):
                if ci.find("start") is None:
                    continue
                starts.append(int(ci.findtext("start", "0")))
            if starts != sorted(starts):
                track_name = tr.get("MZ.TrackName") or group_tag
                raise XmemlError(
                    f"clipitems on {track_name!r} are not sorted by ascending start"
                )


def validate_xmeml(
    root: ET.Element,
    expected_basenames: set[str],
    *,
    card_masterclip_ids: set[str] | None = None,
) -> None:
    _validate_master_clip_bins(root, expected_basenames)
    _validate_master_clip_bin_paths(root)
    _validate_ids_from_basenames(root)
    _validate_masterclipid_resolution(root, exempt_masterclip_ids=card_masterclip_ids)
    _validate_file_definitions(root)
    _validate_file_media_blocks(root)
    _validate_clipitem_ids(root)
    _validate_sequence_clipitem_names(root)
    _validate_source_out_within_file_duration(root)
    _validate_no_track_overlaps(root)
    _validate_track_media_kind(root)
    _validate_sequence_audio_schema(root)
    _validate_track_clipitem_order(root)
    _validate_premiere_audio_track_types(root)
    _validate_graphic_and_type_source_text(root)
    _validate_track_controls(root)
    _validate_pathurls(root)


def _render_bin_tree(bin_el: ET.Element, depth: int = 0) -> list[str]:
    lines: list[str] = []
    indent = "  " * depth
    if depth == 0:
        lines.append(bin_el.findtext("name") or "?")
    kids = bin_el.find("children")
    if kids is None:
        return lines

    sub_bins = sorted(
        (c for c in kids if c.tag == "bin"),
        key=lambda b: (b.findtext("name") or "").lower(),
    )
    master_clips = sorted(
        (
            c
            for c in kids
            if c.tag == "clip" and c.findtext("ismasterclip") == "TRUE"
        ),
        key=lambda c: (c.findtext("name") or "").lower(),
    )
    sequences = sorted(
        (c for c in kids if c.tag == "sequence"),
        key=lambda s: (s.findtext("name") or "").lower(),
    )

    for sb in sub_bins:
        lines.append(f"{indent}  {sb.findtext('name') or '?'}")
        lines.extend(_render_bin_tree(sb, depth + 1))

    clip_indent = "  " * (depth + 1)
    for clip in master_clips:
        lines.append(f"{clip_indent}{clip.findtext('name') or '?'}")

    for seq in sequences:
        lines.append(f"{clip_indent}[sequence] {seq.findtext('name') or '?'}")

    return lines


def analyze_xmeml(
    root: ET.Element,
    expected_basenames: set[str],
    *,
    offline_basenames: set[str] | None = None,
    card_masterclip_ids: set[str] | None = None,
) -> XmemlInventory:
    found = _master_clips_in_bins(root)
    offline_basenames = offline_basenames or set()
    real_count = sum(1 for bn, _, _ in found if bn not in offline_basenames)
    offline_count = sum(1 for bn, _, _ in found if bn in offline_basenames)
    mc_id_to_basename = {mc_id: bn for bn, mc_id, _ in found if mc_id}
    master_clip_bins = {bn: bp for bn, _, bp in found}

    refs_by_id: dict[str, int] = {}
    for ci in root.iter("clipitem"):
        if ci.find("start") is None:
            continue
        mc_el = ci.find("masterclipid")
        if mc_el is None or not mc_el.text:
            continue
        refs_by_id[mc_el.text] = refs_by_id.get(mc_el.text, 0) + 1

    refs_by_basename: dict[str, int] = {}
    for mc_id, count in refs_by_id.items():
        bn = mc_id_to_basename.get(mc_id, mc_id)
        refs_by_basename[bn] = refs_by_basename.get(bn, 0) + count

    project = root.find("project")
    tree_lines: list[str] = []
    if project is not None:
        children = project.find("children")
        if children is not None:
            for top_bin in children.findall("bin"):
                tree_lines.extend(_render_bin_tree(top_bin))

    return XmemlInventory(
        master_clip_count=len(found),
        real_source_master_clip_count=real_count,
        offline_placeholder_count=offline_count,
        bin_tree_lines=tree_lines,
        master_clip_timeline_refs=dict(sorted(refs_by_basename.items())),
        master_clip_bins=dict(sorted(master_clip_bins.items())),
        card_masterclip_ids=card_masterclip_ids or set(),
    )


def _apply_overlap_trims(
    pieces: list[ProjectedPiece],
    offline: list[OfflineClip],
    build_report: ConformBuildReport | None,
) -> None:
    by_track: dict[str, list[ProjectedPiece | OfflineClip]] = {}
    for piece in pieces:
        by_track.setdefault(piece.role, []).append(piece)
    for clip in offline:
        if clip.output_role == "VO" or (
            Path(clip.output_basename).suffix.lower() == ".wav" and clip.track_kind == "video"
        ):
            key = "VO"
        elif clip.track_kind == "video":
            key = f"V{_passthrough_video_track_index(clip.track_index)}"
        elif clip.track_kind == "audio":
            key = f"A{_passthrough_audio_logical_index(clip.track_index)}"
        else:
            key = clip.track_name
        by_track.setdefault(key, []).append(clip)

    trims: list[OverlapTrim] = []
    for track_label, clips in by_track.items():
        _, track_trims = trim_track_overlaps(
            clips,
            track_label=track_label,
            get_start=lambda c: c.timeline_start,
            get_end=lambda c: c.timeline_end,
            set_end=lambda c, v: setattr(c, "timeline_end", v),
            set_out=lambda c, v: setattr(c, "source_out", v),
            get_source_in=lambda c: c.source_in,
            get_name=lambda c: getattr(c, "file_basename", getattr(c, "output_basename", "?")),
        )
        trims.extend(track_trims)
    if build_report is not None:
        build_report.overlap_trims = trims


def _append_sequence_audio_header(audio: ET.Element) -> None:
    _subel(audio, "numOutputChannels", 2)
    fmt = _subel(audio, "format")
    asc = _subel(fmt, "samplecharacteristics")
    _subel(asc, "depth", 16)
    _subel(asc, "samplerate", 48000)
    outputs = _subel(audio, "outputs")
    for idx in (1, 2):
        group = _subel(outputs, "group")
        _subel(group, "index", idx)
        _subel(group, "numchannels", 1)
        _subel(group, "downmix", 0)
        channel = _subel(group, "channel")
        _subel(channel, "index", idx)


def _audio_track_layout(channelcount: int) -> str:
    return "stereo" if channelcount >= 2 else "mono"


def _apply_premiere_audio_track_attrs(
    track: ET.Element,
    *,
    exploded_index: int,
    exploded_total: int,
) -> None:
    """Apply Premiere sequence audio track attributes from pinned assembly export."""
    for key, value in PREMIERE_AUDIO_TRACK_ATTRS.items():
        track.set(key, value)
    track.set("currentExplodedTrackIndex", str(exploded_index))
    track.set("totalExplodedTrackCount", str(exploded_total))
    if exploded_total == 1:
        track.set("MZ.TrackTargeted", PREMIERE_TRACK_TARGETED_MONO)
    else:
        track.set("MZ.TrackTargeted", PREMIERE_TRACK_TARGETED_STEREO)
        track.set("PannerIsInverted", PREMIERE_PANNER_INVERTED)


def _create_premiere_audio_track(
    audio: ET.Element,
    *,
    track_name: str,
    exploded_index: int,
    exploded_total: int,
) -> ET.Element:
    tr = _subel(audio, "track")
    tr.set("MZ.TrackName", track_name)
    _apply_premiere_audio_track_attrs(
        tr,
        exploded_index=exploded_index,
        exploded_total=exploded_total,
    )
    return tr


def _append_track_controls(
    track: ET.Element,
    *,
    is_audio: bool,
    output_channel_index: int | None = None,
) -> None:
    _subel(track, "enabled", "TRUE")
    _subel(track, "locked", "FALSE")
    if is_audio:
        if output_channel_index is None:
            raise XmemlError("audio track missing outputchannelindex")
        _subel(track, "outputchannelindex", output_channel_index)


def _assign_audio_output_channel_indices(audio: ET.Element) -> None:
    """Mono tracks route to 1; stereo exploded pairs use 1 and 2."""
    for track in audio.findall("track"):
        if track.find("clipitem") is None:
            continue
        exploded = int(track.get("totalExplodedTrackCount", "1"))
        if exploded == 2:
            pair_idx = int(track.get("currentExplodedTrackIndex", "0"))
            _append_track_controls(track, is_audio=True, output_channel_index=pair_idx + 1)
        else:
            _append_track_controls(track, is_audio=True, output_channel_index=1)


def _build_audio_track_names(
    needs: set[tuple[int, str]],
    offline: list[OfflineClip],
    media: dict[str, MediaDef],
) -> dict[tuple[int, str], str]:
    names: dict[tuple[int, str], str] = {}
    for _role, label, logical in CONFORM_AUDIO:
        for layout in ("mono", "stereo"):
            if (logical, layout) in needs:
                names[(logical, layout)] = label

    editor_names: dict[int, str] = {}
    for clip in offline:
        if clip.track_kind == "audio" and clip.track_name:
            editor_names.setdefault(clip.track_index, clip.track_name)

    input_layouts: dict[int, set[str]] = {}
    for clip in offline:
        if clip.track_kind != "audio":
            continue
        md = media.get(clip.media_key)
        if md is None:
            continue
        layout = _audio_track_layout(md.channelcount)
        input_layouts.setdefault(clip.track_index, set()).add(layout)

    for input_index, layouts in input_layouts.items():
        logical = _passthrough_audio_logical_index(input_index)
        base = editor_names.get(input_index) or f"A{input_index + 1}-PASSTHROUGH"
        disambiguate = len(layouts) > 1
        for layout in layouts:
            key = (logical, layout)
            if key not in needs:
                continue
            if disambiguate and layout == "mono":
                names[key] = f"{base}-mono"
            else:
                names[key] = base

    for logical in {idx for idx, _ in needs}:
        layouts = {layout for idx, layout in needs if idx == logical}
        if len(layouts) <= 1:
            continue
        base = next(
            (names[(logical, layout)] for layout in ("stereo", "mono") if (logical, layout) in names),
            _track_name_for_logical(logical),
        )
        if base.endswith("-mono"):
            base = base[: -len("-mono")]
        for layout in layouts:
            key = (logical, layout)
            if layout == "mono":
                names[key] = f"{base}-mono"
            else:
                names[key] = base
    return names


def _assert_unique_track_names(video: ET.Element, audio: ET.Element) -> None:
    """Physical sequence tracks must not share MZ.TrackName except stereo pairs."""
    seen: dict[str, list[ET.Element]] = {}
    for track in video.findall("track"):
        if track.find("clipitem") is None:
            continue
        name = track.get("MZ.TrackName") or ""
        seen.setdefault(name, []).append(track)
    for track in audio.findall("track"):
        if track.find("clipitem") is None:
            continue
        name = track.get("MZ.TrackName") or ""
        seen.setdefault(name, []).append(track)

    for name, tracks in seen.items():
        if len(tracks) == 1:
            continue
        if len(tracks) == 2 and all(
            int(tr.get("totalExplodedTrackCount", "1")) == 2 for tr in tracks
        ):
            indices = {tr.get("currentExplodedTrackIndex") for tr in tracks}
            if indices == {"0", "1"}:
                continue
        raise XmemlError(
            f"duplicate MZ.TrackName {name!r} on {len(tracks)} sequence tracks"
        )


def _validate_graphic_and_type_source_text(root: ET.Element) -> None:
    for ci in root.iter("clipitem"):
        if ci.find("start") is None:
            continue
        file_el = ci.find("file")
        if file_el is None or file_el.findtext("mediaSource") != "GraphicAndType":
            continue
        if not has_graphic_and_type_source_text(ci):
            name = ci.findtext("name") or "?"
            raise XmemlError(
                f"GraphicAndType clipitem {name!r} missing Source Text parameter"
            )
    for file_el in root.iter("file"):
        if file_el.findtext("mediaSource") != "GraphicAndType":
            continue
        if file_el.find("pathurl") is not None:
            continue
        if file_el.find("start") is not None:
            continue
        parent = None
        for ci in root.iter("clipitem"):
            if ci.find("file") is file_el or (
                ci.find("file") is not None
                and ci.find("file").get("id") == file_el.get("id")
            ):
                parent = ci
                break
        if parent is not None and has_graphic_and_type_source_text(parent):
            continue
        if not has_graphic_and_type_source_text(file_el):
            name = file_el.findtext("name") or "?"
            raise XmemlError(
                f"GraphicAndType file {name!r} missing Source Text parameter"
            )


def _validate_premiere_audio_track_types(root: ET.Element) -> None:
    seq = _find_sequence(root)
    if seq is None:
        return
    audio_group = seq.find("media/audio")
    if audio_group is None:
        return
    for track in audio_group.findall("track"):
        if track.find("clipitem") is None:
            continue
        track_type = track.get("premiereTrackType")
        if track_type != "Stereo":
            name = track.get("MZ.TrackName") or "audio"
            raise XmemlError(
                f"audio track {name!r} has premiereTrackType={track_type!r}, expected 'Stereo'"
            )


def _validate_track_controls(root: ET.Element) -> None:
    seq = _find_sequence(root)
    if seq is None:
        return
    media = seq.find("media")
    if media is None:
        return
    for group_tag, is_audio in (("video", False), ("audio", True)):
        group = media.find(group_tag)
        if group is None:
            continue
        for track in group.findall("track"):
            if track.find("clipitem") is None:
                continue
            if track.findtext("enabled") != "TRUE":
                raise XmemlError(f"{group_tag} track missing enabled=TRUE")
            if track.findtext("locked") != "FALSE":
                raise XmemlError(f"{group_tag} track missing locked=FALSE")
            if is_audio and track.find("outputchannelindex") is None:
                name = track.get("MZ.TrackName") or group_tag
                raise XmemlError(f"audio track {name!r} missing outputchannelindex")


def _track_name_for_logical(logical: int) -> str:
    return next(
        (label for _, label, ti in CONFORM_AUDIO if ti == logical),
        f"A{logical + 1}-PASSTHROUGH",
    )


def _collect_audio_track_needs(
    pieces: list[ProjectedPiece],
    offline: list[OfflineClip],
    media: dict[str, MediaDef],
) -> set[tuple[int, str]]:
    role_to_logical = {role: idx for role, _, idx in CONFORM_AUDIO}
    needs: set[tuple[int, str]] = set()
    for piece in pieces:
        if piece.role not in role_to_logical:
            continue
        md = media.get(piece.file_basename)
        if md is None:
            continue
        needs.add((role_to_logical[piece.role], _audio_track_layout(md.channelcount)))
    for clip in offline:
        md = media.get(clip.media_key)
        if md is None:
            continue
        is_wav = Path(clip.output_basename).suffix.lower() == ".wav"
        if clip.output_role == "VO" or (is_wav and clip.track_kind == "video"):
            logical = role_to_logical["VO"]
        elif clip.track_kind == "audio":
            logical = _passthrough_audio_logical_index(clip.track_index)
        else:
            continue
        needs.add((logical, _audio_track_layout(md.channelcount)))
    return needs


def _create_audio_track_groups(
    audio: ET.Element,
    needs: set[tuple[int, str]],
    logical_count: int,
    track_names: dict[tuple[int, str], str],
) -> dict[tuple[int, str], list[ET.Element]]:
    groups: dict[tuple[int, str], list[ET.Element]] = {}
    for logical in range(logical_count):
        for layout in ("mono", "stereo"):
            if (logical, layout) not in needs:
                continue
            track_name = track_names.get((logical, layout)) or _track_name_for_logical(
                logical
            )
            if layout == "stereo":
                tracks: list[ET.Element] = []
                for pair_idx in range(2):
                    tracks.append(
                        _create_premiere_audio_track(
                            audio,
                            track_name=track_name,
                            exploded_index=pair_idx,
                            exploded_total=2,
                        )
                    )
                groups[(logical, layout)] = tracks
            else:
                groups[(logical, layout)] = [
                    _create_premiere_audio_track(
                        audio,
                        track_name=track_name,
                        exploded_index=0,
                        exploded_total=1,
                    )
                ]
    return groups


def _audio_tracks_for_clip(
    groups: dict[tuple[int, str], list[ET.Element]],
    logical: int,
    channelcount: int,
    *,
    context: str,
) -> list[ET.Element]:
    layout = _audio_track_layout(channelcount)
    key = (logical, layout)
    tracks = groups.get(key)
    if tracks is None:
        raise XmemlError(
            f"{context}: no {layout} audio track group for logical index {logical}"
        )
    return tracks


def build_xmeml(
    *,
    sequence_name: str,
    seq_prefix: str,
    pieces: list[ProjectedPiece],
    offline: list[OfflineClip],
    report: ProjectionReport,
    build_report: ConformBuildReport | None = None,
    cards: list[CardClip] | None = None,
) -> ET.Element:
    cut_dates = _cut_shoot_dates(pieces)
    _apply_overlap_trims(pieces, offline, build_report)
    media = _collect_media(pieces, offline, cut_dates, build_report)
    role_to_logical = {role: idx for role, _, idx in CONFORM_AUDIO}
    cards = cards or []

    seq_duration = 0
    for p in pieces:
        seq_duration = max(seq_duration, p.timeline_end)
    for o in offline:
        seq_duration = max(seq_duration, o.timeline_end)
    seq_duration = max(seq_duration, 1)

    root = ET.Element("xmeml", {"version": "4"})
    project = _subel(root, "project")
    _subel(project, "name", sequence_name)
    children = _subel(project, "children")

    footage = _subel(children, "bin")
    _subel(footage, "name", "Footage")
    footage_children = _subel(footage, "children")
    audio_bin = _subel(children, "bin")
    _subel(audio_bin, "name", "Audio")
    audio_children = _subel(audio_bin, "children")
    graphics = _subel(children, "bin")
    _subel(graphics, "name", "Graphics")
    graphics_children = _subel(graphics, "children")
    graphics_ref = _subel(graphics_children, "bin")
    _subel(graphics_ref, "name", "_Reference")
    graphics_ref_children = _subel(graphics_ref, "children")
    has_vo = any(md.bin_kind == "vo" for md in media.values())
    vo_children = None
    if has_vo:
        vo_bin = _subel(children, "bin")
        _subel(vo_bin, "name", "VO")
        vo_children = _subel(vo_bin, "children")
    audio_passthrough = _subel(audio_children, "bin")
    _subel(audio_passthrough, "name", "_Passthrough")
    audio_passthrough_children = _subel(audio_passthrough, "children")
    seq_bin = _subel(children, "bin")
    _subel(seq_bin, "name", "Seq")
    seq_bin_children = _subel(seq_bin, "children")

    footage_date_children: dict[str, ET.Element] = {}
    footage_camera_bins: dict[tuple[str, str], ET.Element] = {}
    audio_date_children: dict[str, ET.Element] = {}
    audio_person_bins: dict[tuple[str, str], ET.Element] = {}

    ids = _ClipIdGen(seq_prefix)

    for md in media.values():
        if md.bin_kind == "footage" and md.bin_camera:
            if md.shoot_date not in footage_date_children:
                dbin = _subel(footage_children, "bin")
                _subel(dbin, "name", md.shoot_date)
                footage_date_children[md.shoot_date] = _subel(dbin, "children")
            date_children = footage_date_children[md.shoot_date]
            cam_key = (md.shoot_date, md.bin_camera)
            if cam_key not in footage_camera_bins:
                cam_bin = _subel(date_children, "bin")
                _subel(cam_bin, "name", md.bin_camera)
                footage_camera_bins[cam_key] = _subel(cam_bin, "children")
            _append_master_clip(footage_camera_bins[cam_key], md, ids)
        elif md.bin_kind == "graphics":
            _append_master_clip(graphics_children, md, ids)
        elif md.bin_kind == "graphics_reference":
            _append_master_clip(graphics_ref_children, md, ids)
        elif md.bin_kind == "vo":
            assert vo_children is not None
            _append_master_clip(vo_children, md, ids)
        elif md.bin_kind == "audio_passthrough":
            _append_master_clip(audio_passthrough_children, md, ids)
        elif md.bin_kind == "audio":
            if md.person in ("Unknown", "Passthrough"):
                raise XmemlError(
                    f"projected audio {md.basename!r} has invalid person {md.person!r}"
                )
            if md.shoot_date not in audio_date_children:
                dbin = _subel(audio_children, "bin")
                _subel(dbin, "name", md.shoot_date)
                audio_date_children[md.shoot_date] = _subel(dbin, "children")
            date_children = audio_date_children[md.shoot_date]
            person_key = (md.shoot_date, md.person)
            if person_key not in audio_person_bins:
                pbin = _subel(date_children, "bin")
                _subel(pbin, "name", md.person)
                audio_person_bins[person_key] = _subel(pbin, "children")
            _append_master_clip(audio_person_bins[person_key], md, ids)
        else:
            raise XmemlError(f"unplaced master clip {md.basename!r} (bin_kind={md.bin_kind!r})")

    sequence = _subel(seq_bin_children, "sequence", id=f"sequence-{seq_prefix}")
    _subel(sequence, "uuid", deterministic_uuid(sequence_name))
    _subel(sequence, "duration", seq_duration)
    _seq_rate(sequence)
    _subel(sequence, "name", sequence_name)
    tc = _subel(sequence, "timecode")
    _seq_rate(tc)
    _subel(tc, "string", "00:00:00:00")
    _subel(tc, "frame", 0)
    _subel(tc, "displayformat", "NDF")

    media_el = _subel(sequence, "media")
    video = _subel(media_el, "video")
    fmt = _subel(video, "format")
    sc = _subel(fmt, "samplecharacteristics")
    _seq_rate(sc)
    _subel(sc, "width", OUTPUT_WIDTH)
    _subel(sc, "height", OUTPUT_HEIGHT)
    _subel(sc, "anamorphic", "FALSE")
    _subel(sc, "pixelaspectratio", "square")
    _subel(sc, "fielddominance", "none")
    _subel(sc, "colordepth", 24)

    audio = _subel(media_el, "audio")
    _append_sequence_audio_header(audio)

    input_audio_tracks = max(
        [0] + [o.track_index + 1 for o in offline if o.track_kind == "audio"]
    )
    logical_audio_count = max(
        CONFORM_AUDIO_LOGICAL,
        input_audio_tracks + CONFORM_AUDIO_LOGICAL,
    )

    video_tracks: list[ET.Element] = []

    def ensure_video_track(idx: int) -> ET.Element:
        while len(video_tracks) <= idx:
            track_idx = len(video_tracks)
            tr = _subel(video, "track")
            name = next(
                (label for _, label, ti in CONFORM_VIDEO if ti == track_idx),
                f"V{track_idx + 1}-PASSTHROUGH",
            )
            tr.set("MZ.TrackName", name)
            video_tracks.append(tr)
        return video_tracks[idx]

    for idx in range(CONFORM_VIDEO_TRACKS):
        ensure_video_track(idx)

    audio_track_needs = _collect_audio_track_needs(pieces, offline, media)
    audio_track_names = _build_audio_track_names(audio_track_needs, offline, media)
    audio_track_groups = _create_audio_track_groups(
        audio, audio_track_needs, logical_audio_count, audio_track_names
    )

    conform_video: dict[str, ET.Element] = {
        role: video_tracks[idx] for role, _, idx in CONFORM_VIDEO if idx < len(video_tracks)
    }
    conform_audio_roles = {role for role, _, _ in CONFORM_AUDIO}
    role_counters: dict[str, int] = {}

    def next_seq_id(role: str) -> str:
        role_counters[role] = role_counters.get(role, 0) + 1
        return ids.next(f"{role}-{role_counters[role]:04d}")

    for p in sorted(pieces, key=lambda x: (x.timeline_start, x.role)):
        if p.role not in conform_video and p.role not in conform_audio_roles:
            continue
        md = media.get(p.file_basename)
        if md is None:
            continue
        on_audio = p.role in conform_audio_roles
        if on_audio:
            logical = role_to_logical[p.role]
            track_els = _audio_tracks_for_clip(
                audio_track_groups,
                logical,
                md.channelcount,
                context=f"projected {p.file_basename!r}",
            )
            _append_audio_clipitems(
                track_els,
                clip_id=next_seq_id(p.role),
                md=md,
                piece_tl_start=p.timeline_start,
                piece_tl_end=p.timeline_end,
                source_in=p.source_in,
                source_out=p.source_out,
                enabled=p.enabled,
                person=p.person,
                log_description=p.cut_label,
            )
        else:
            track_el = conform_video[p.role]
            _append_sequence_clipitem(
                track_el,
                clip_id=next_seq_id(p.role),
                md=md,
                piece_tl_start=p.timeline_start,
                piece_tl_end=p.timeline_end,
                source_in=p.source_in,
                source_out=p.source_out,
                enabled=p.enabled,
                person=p.person,
                log_description=p.cut_label,
                on_audio_track=False,
            )

    for o in sorted(offline, key=lambda x: (x.timeline_start, x.output_role)):
        if o.empty_graphic and o.track_kind == "video":
            out_idx = _passthrough_video_track_index(o.track_index)
            track_el = ensure_video_track(out_idx)
            if o.track_name:
                track_el.set("MZ.TrackName", o.track_name)
            gi = build_color_matte_generatoritem(
                label=o.label,
                timeline_start=o.timeline_start,
                timeline_end=o.timeline_end,
                source_in=o.source_in,
                source_out=o.source_out,
                clip_id=ids.next("color-matte"),
                rate=SEQ_RATE,
            )
            track_el.append(gi)
            if build_report is not None:
                build_report.color_mattes_emitted += 1
            continue
        md = media.get(o.media_key)
        if md is None:
            continue
        is_wav = Path(o.output_basename).suffix.lower() == ".wav"
        if o.output_role == "VO" or (is_wav and o.track_kind == "video"):
            logical = role_to_logical["VO"]
            track_els = _audio_tracks_for_clip(
                audio_track_groups,
                logical,
                md.channelcount,
                context=f"offline VO {o.output_basename!r}",
            )
            role_key = "VO"
        elif o.track_kind == "video":
            out_idx = _passthrough_video_track_index(o.track_index)
            track_els = [ensure_video_track(out_idx)]
            role_key = f"V{out_idx}"
            _append_sequence_clipitem(
                track_els[0],
                clip_id=next_seq_id(role_key),
                md=md,
                piece_tl_start=o.timeline_start,
                piece_tl_end=o.timeline_end,
                source_in=o.source_in,
                source_out=o.source_out,
                enabled=True,
                person=md.person,
                log_description=o.label if o.synthetic else None,
                lognote=o.label if o.synthetic else None,
                on_audio_track=False,
            )
            continue
        elif o.track_kind == "audio":
            logical = _passthrough_audio_logical_index(o.track_index)
            track_els = _audio_tracks_for_clip(
                audio_track_groups,
                logical,
                md.channelcount,
                context=f"offline audio {o.output_basename!r}",
            )
            role_key = f"A{logical}"
        else:
            raise XmemlError(f"unknown offline track_kind {o.track_kind!r}")
        _append_audio_clipitems(
            track_els,
            clip_id=next_seq_id(role_key),
            md=md,
            piece_tl_start=o.timeline_start,
            piece_tl_end=o.timeline_end,
            source_in=o.source_in,
            source_out=o.source_out,
            enabled=True,
            person=md.person,
            log_description=o.label if o.synthetic else None,
            lognote=o.label if o.synthetic else None,
        )

    max_card_track = max(
        [_passthrough_video_track_index(c.track_index) for c in cards]
        + [CONFORM_VIDEO_TRACKS - 1],
        default=CONFORM_VIDEO_TRACKS - 1,
    )
    for track_idx in range(CONFORM_VIDEO_TRACKS, max_card_track + 1):
        ensure_video_track(track_idx)

    for card in sorted(cards, key=lambda c: c.timeline_start):
        out_idx = _passthrough_video_track_index(card.track_index)
        track_el = ensure_video_track(out_idx)
        if card.track_name:
            track_el.set("MZ.TrackName", card.track_name)
        ci = copy.deepcopy(card.clipitem)
        file_name = card.name or card.clipitem.findtext("name") or "Graphic"
        renamespace_card_clipitem(
            ci,
            clip_id=ids.next("card"),
            masterclip_id=ids.next("cardmc"),
            file_id=ids.next("cardfile"),
            file_name=file_name,
            width=OUTPUT_WIDTH,
            height=OUTPUT_HEIGHT,
            rate=SEQ_RATE,
        )
        track_el.append(ci)

    for tr in video.findall("track"):
        _sort_track_clipitems(tr)
        if tr.find("clipitem") is not None or tr.find("generatoritem") is not None:
            _append_track_controls(tr, is_audio=False)
    for tr in audio.findall("track"):
        _sort_track_clipitems(tr)

    _assign_audio_output_channel_indices(audio)
    _assert_unique_track_names(video, audio)

    _prune_empty_sequence_tracks(video)
    _prune_empty_sequence_tracks(audio)
    prune_empty_bins(root)
    return root


def write_xmeml(
    path: Path,
    root: ET.Element,
    *,
    expected_basenames: set[str] | None = None,
    card_masterclip_ids: set[str] | None = None,
) -> None:
    if expected_basenames is not None:
        validate_xmeml(
            root,
            expected_basenames,
            card_masterclip_ids=card_masterclip_ids,
        )
    tree = ET.ElementTree(root)
    ET.indent(tree, space="\t")
    path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(path, encoding="UTF-8", xml_declaration=True)
