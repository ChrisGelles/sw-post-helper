"""FCP7 xmeml writer for stringout conform output."""

from __future__ import annotations

import copy
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote, unquote

from swpost.cards import CardClip
from swpost.conform_report import ConformBuildReport
from swpost.offline import OfflineClip, person_under_cam_b
from swpost.overlap import OverlapTrim, trim_track_overlaps
from swpost.paths import FORBIDDEN_PATHURL_FRAGMENTS, PROXY_REGISTRY, VOLUME_ROOT
from swpost.person import label_color_for_person, person_for_basename
from swpost.project import ProjectedPiece, ProjectionReport

OUTPUT_WIDTH = 1920
OUTPUT_HEIGHT = 1080
SEQ_RATE = (24, True)
STILL_FILE_RATE = (30, True)

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
    names.update(o.output_basename for o in offline)
    return names


def real_source_basenames(pieces: list[ProjectedPiece]) -> set[str]:
    return {p.file_basename for p in pieces}


def offline_placeholder_basenames(offline: list[OfflineClip]) -> set[str]:
    return {o.output_basename for o in offline if o.synthetic}


@dataclass(frozen=True)
class MediaDef:
    basename: str
    path: str
    masterclip_id: str
    file_id: str
    person: str
    shoot_date: str
    bin_camera: str | None  # CAM A | CAM B | None for audio
    bin_kind: str  # footage | audio | graphics | vo
    file_rate: tuple[int, bool]  # timebase, ntsc
    is_still: bool
    needs_video: bool
    needs_audio: bool
    width: int | None
    height: int | None
    scale: int | None
    clip_duration: int  # master clip / clipitem duration
    file_duration: int | None  # on <file> when not still
    channelcount: int = 2
    is_offline_placeholder: bool = False
    lognote: str | None = None


def id_slug(basename: str) -> str:
    stem = Path(basename).stem
    return re.sub(r"[^A-Za-z0-9]+", "-", stem)


def masterclip_id(basename: str) -> str:
    return f"masterclip-{id_slug(basename)}"


def file_id(basename: str) -> str:
    return f"file-{id_slug(basename)}"


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


def _person_for_offline_audio(
    timeline_start: int,
    timeline_end: int,
    pieces: list[ProjectedPiece],
) -> str | None:
    person = person_under_cam_b(timeline_start, timeline_end, pieces)
    if person and person not in ("Unknown", "Passthrough"):
        return person
    cam_b = sorted(
        (p for p in pieces if p.role == "CAM_B"),
        key=lambda p: p.timeline_start,
    )
    for piece in cam_b:
        if piece.timeline_start <= timeline_start < piece.timeline_end:
            return piece.person
    return cam_b[0].person if cam_b else None


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


def _offline_bin_kind(o: OfflineClip) -> str:
    if o.output_role == "VO":
        return "vo"
    if o.synthetic:
        return "graphics"
    ext = Path(o.output_basename).suffix.lower()
    if ext == ".wav":
        return "audio"
    return "graphics"


def _collect_media(
    pieces: list[ProjectedPiece],
    offline: list[OfflineClip],
    cut_dates: dict[str, str],
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
        return MediaDef(
            basename=basename,
            path=path,
            masterclip_id=masterclip_id(basename),
            file_id=file_id(basename),
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

    for o in offline:
        if o.output_basename in media:
            continue
        bin_kind = _offline_bin_kind(o)
        person = _person_for_offline_audio(o.timeline_start, o.timeline_end, pieces) or "Unknown"
        if bin_kind == "audio" and person in ("Unknown", "Passthrough"):
            raise XmemlError(
                f"passthrough audio {o.output_basename!r} at timeline "
                f"{o.timeline_start}-{o.timeline_end} has unresolved person"
            )
        shoot = _shoot_date_for_timeline(o.timeline_start, o.timeline_end, pieces, cut_dates)
        media[o.output_basename] = build_def(
            basename=o.output_basename,
            path=o.output_path,
            person=person if bin_kind == "audio" else "Graphics",
            shoot_date=shoot,
            bin_camera=None,
            bin_kind=bin_kind,
            is_offline_placeholder=o.synthetic,
            lognote=o.label if o.synthetic else None,
        )
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
    _subel(fe, "name", md.basename)
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


def _append_lognote(parent: ET.Element, text: str | None) -> None:
    if not text:
        return
    info = _subel(parent, "logginginfo")
    _subel(info, "lognote", text)


def _append_master_clip(bin_el: ET.Element, md: MediaDef, ids: _ClipIdGen) -> None:
    clip = _subel(bin_el, "clip", id=md.masterclip_id)
    _subel(clip, "masterclipid", md.masterclip_id)
    _subel(clip, "ismasterclip", "TRUE")
    _subel(clip, "duration", md.clip_duration)
    _seq_rate(clip)
    _subel(clip, "name", md.basename)
    _append_lognote(clip, md.lognote)
    media = _subel(clip, "media")
    track_kind = "video" if md.needs_video else "audio"
    tr = _subel(media, track_kind)
    ci = _subel(tr, "clipitem", id=ids.next("mc"))
    _subel(ci, "masterclipid", md.masterclip_id)
    _subel(ci, "name", md.basename)
    _subel(ci, "enabled", "TRUE")
    _subel(ci, "duration", md.clip_duration)
    _seq_rate(ci)
    _subel(ci, "in", 0)
    _subel(ci, "out", md.clip_duration)
    _append_file_def(ci, md, full=True)
    if md.needs_video:
        _append_scale_filter(ci, md.scale)
    if md.needs_audio and not md.needs_video:
        st = _subel(ci, "sourcetrack")
        _subel(st, "mediatype", "audio")
        _subel(st, "trackindex", 1)


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
    lognote: str | None = None,
    on_audio_track: bool = False,
) -> None:
    ci = _subel(track_el, "clipitem", id=clip_id)
    _subel(ci, "masterclipid", md.masterclip_id)
    _subel(ci, "name", md.basename)
    _append_lognote(ci, lognote)
    _subel(ci, "enabled", "TRUE" if enabled else "FALSE")
    _subel(ci, "duration", md.clip_duration)
    _seq_rate(ci)
    _subel(ci, "start", piece_tl_start)
    _subel(ci, "end", piece_tl_end)
    _subel(ci, "in", source_in)
    _subel(ci, "out", source_out)
    _append_file_def(ci, md, full=False)
    if md.needs_video:
        _append_scale_filter(ci, md.scale)
    if on_audio_track or (md.needs_audio and not md.needs_video):
        ci.set("premiereChannelType", "mono")
        st = _subel(ci, "sourcetrack")
        _subel(st, "mediatype", "audio")
        _subel(st, "trackindex", 1)
    labels = _subel(ci, "labels")
    _subel(labels, "label2", label_color_for_person(person))


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


def _validate_file_definitions(root: ET.Element) -> None:
    full_defs: dict[str, ET.Element] = {}
    for file_el in root.iter("file"):
        fid = file_el.get("id")
        if fid is None:
            continue
        if file_el.find("pathurl") is not None:
            if fid in full_defs:
                raise XmemlError(f"duplicate full <file> definition for id {fid!r}")
            full_defs[fid] = file_el
        else:
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
    for file_el in root.iter("file"):
        if file_el.find("pathurl") is None:
            continue
        if file_el.find("media") is None:
            fid = file_el.get("id") or "?"
            raise XmemlError(f"file {fid!r} with pathurl missing <media> block")


ALLOWED_MASTER_CLIP_BIN = (
    re.compile(r"^Footage/\d{4}-\d{2}-\d{2}/CAM A$"),
    re.compile(r"^Footage/\d{4}-\d{2}-\d{2}/CAM B$"),
    re.compile(r"^Audio/\d{4}-\d{2}-\d{2}/[^/]+$"),
    re.compile(r"^Graphics$"),
    re.compile(r"^VO$"),
    re.compile(r"^Seq$"),
)


def _bin_path_allowed(path: str) -> bool:
    if path.endswith("/Unknown") or "/Unknown/" in path:
        return False
    if path.endswith("/Passthrough") or "/Passthrough/" in path:
        return False
    return any(p.match(path) for p in ALLOWED_MASTER_CLIP_BIN)


def _validate_master_clip_bin_paths(root: ET.Element) -> None:
    for basename, _mc_id, bin_path in _master_clips_in_bins(root):
        if not _bin_path_allowed(bin_path):
            raise XmemlError(
                f"master clip {basename!r} in disallowed bin {bin_path!r}"
            )
        parts = bin_path.split("/")
        if parts[0] == "Audio" and len(parts) == 3:
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
    for basename, mc_id, _ in _master_clips_in_bins(root):
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
        if fid != expected_fid:
            raise XmemlError(
                f"file id for {name!r} is {fid!r}, expected {expected_fid!r}"
            )
        if fid in seen_full:
            raise XmemlError(f"duplicate full file definition for {fid!r}")
        seen_full.add(fid)
        url = file_el.findtext("pathurl") or ""
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
        if tr.get("totalExplodedTrackCount") == "2":
            raise XmemlError(
                f"audio track {tr.get('MZ.TrackName')!r} uses stereo exploded pair"
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
    media = _collect_media(pieces, offline, cut_dates)
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
    has_vo = any(md.bin_kind == "vo" for md in media.values())
    vo_children = None
    if has_vo:
        vo_bin = _subel(children, "bin")
        _subel(vo_bin, "name", "VO")
        vo_children = _subel(vo_bin, "children")
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
        elif md.bin_kind == "vo":
            assert vo_children is not None
            _append_master_clip(vo_children, md, ids)
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
    _subel(sequence, "name", sequence_name)
    _subel(sequence, "duration", seq_duration)
    _seq_rate(sequence)
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

    input_video_tracks = max(
        [0] + [o.track_index + 1 for o in offline if o.track_kind == "video"]
    )
    input_audio_tracks = max(
        [0] + [o.track_index + 1 for o in offline if o.track_kind == "audio"]
    )
    max_passthrough_v = max(
        [_passthrough_video_track_index(o.track_index) + 1 for o in offline if o.track_kind == "video"],
        default=CONFORM_VIDEO_TRACKS,
    )
    video_track_count = max(CONFORM_VIDEO_TRACKS, max_passthrough_v, input_video_tracks)
    logical_audio_count = max(
        CONFORM_AUDIO_LOGICAL,
        input_audio_tracks + CONFORM_AUDIO_LOGICAL,
    )

    video_tracks: list[ET.Element] = []
    for idx in range(video_track_count):
        tr = _subel(video, "track")
        name = next(
            (label for _, label, ti in CONFORM_VIDEO if ti == idx),
            f"V{idx + 1}-PASSTHROUGH",
        )
        tr.set("MZ.TrackName", name)
        video_tracks.append(tr)

    audio_tracks: list[ET.Element] = []
    for logical in range(logical_audio_count):
        tr = _subel(audio, "track")
        tr.set("premiereTrackType", "Stereo")
        tr.set("currentExplodedTrackIndex", "0")
        tr.set("totalExplodedTrackCount", "1")
        name = next(
            (label for _, label, ti in CONFORM_AUDIO if ti == logical),
            f"A{logical + 1}-PASSTHROUGH",
        )
        tr.set("MZ.TrackName", name)
        audio_tracks.append(tr)

    conform_video: dict[str, ET.Element] = {
        role: video_tracks[idx] for role, _, idx in CONFORM_VIDEO if idx < len(video_tracks)
    }
    conform_audio: dict[str, ET.Element] = {
        role: audio_tracks[idx]
        for role, _, idx in CONFORM_AUDIO
        if idx < len(audio_tracks)
    }
    role_counters: dict[str, int] = {}

    def next_seq_id(role: str) -> str:
        role_counters[role] = role_counters.get(role, 0) + 1
        return ids.next(f"{role}-{role_counters[role]:04d}")

    for p in sorted(pieces, key=lambda x: (x.timeline_start, x.role)):
        if p.role not in conform_video and p.role not in conform_audio:
            continue
        md = media.get(p.file_basename)
        if md is None:
            continue
        on_audio = p.role in conform_audio
        track_el = conform_audio[p.role] if on_audio else conform_video[p.role]
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
            on_audio_track=on_audio,
        )

    for o in sorted(offline, key=lambda x: (x.timeline_start, x.output_role)):
        md = media.get(o.output_basename)
        if md is None:
            continue
        is_wav = Path(o.output_basename).suffix.lower() == ".wav"
        if o.output_role == "VO" or (is_wav and o.track_kind == "video"):
            if "VO" not in conform_audio:
                raise XmemlError("missing VO conform audio track")
            track_el = conform_audio["VO"]
            role_key = "VO"
            on_audio = True
        elif o.track_kind == "video":
            out_idx = _passthrough_video_track_index(o.track_index)
            if out_idx >= len(video_tracks):
                raise XmemlError(
                    f"offline video clip {o.output_basename!r} maps to track "
                    f"{out_idx} but only {len(video_tracks)} video tracks exist"
                )
            track_el = video_tracks[out_idx]
            role_key = f"V{out_idx}"
            on_audio = False
        elif o.track_kind == "audio":
            logical = _passthrough_audio_logical_index(o.track_index)
            if logical >= logical_audio_count:
                raise XmemlError(
                    f"offline audio clip {o.output_basename!r} maps to logical track "
                    f"{logical} but only {logical_audio_count} logical audio tracks exist"
                )
            track_el = audio_tracks[logical]
            role_key = f"A{logical}"
            on_audio = True
        else:
            raise XmemlError(f"unknown offline track_kind {o.track_kind!r}")
        under = person_under_cam_b(o.timeline_start, o.timeline_end, pieces)
        person = under or md.person or "Unknown"
        _append_sequence_clipitem(
            track_el,
            clip_id=next_seq_id(role_key),
            md=md,
            piece_tl_start=o.timeline_start,
            piece_tl_end=o.timeline_end,
            source_in=o.source_in,
            source_out=o.source_out,
            enabled=True,
            person=person,
            lognote=o.label if o.synthetic else None,
            on_audio_track=on_audio,
        )

    max_card_track = max(
        [c.track_index for c in cards] + [CONFORM_VIDEO_TRACKS - 1],
        default=CONFORM_VIDEO_TRACKS - 1,
    )
    while len(video_tracks) <= max_card_track:
        tr = _subel(video, "track")
        tr.set("MZ.TrackName", f"V{len(video_tracks) + 1}-PASSTHROUGH")
        video_tracks.append(tr)

    for card in sorted(cards, key=lambda c: c.timeline_start):
        track_idx = card.track_index
        if track_idx >= len(video_tracks):
            raise XmemlError(
                f"card {card.name!r} targets video track {track_idx} "
                f"but only {len(video_tracks)} exist"
            )
        track_el = video_tracks[track_idx]
        ci = copy.deepcopy(card.clipitem)
        ci.set("id", ids.next("card"))
        track_el.append(ci)

    for tr in video.findall("track"):
        _sort_track_clipitems(tr)
    for tr in audio.findall("track"):
        _sort_track_clipitems(tr)

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
