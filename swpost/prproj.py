"""Premiere .prproj reader."""

from __future__ import annotations

import gzip
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from swpost.paths import TICKS_PER_FRAME, proxy_basename

SEQUENCE_CLASS = "6a15d903-8739-11d5-af2d-9b7855ad8974"
VIDEO_TRACK_GROUP = "228cda18-3625-4d2d-951e-348879e4ed93"
AUDIO_TRACK_GROUP = "80b8e3d5-6dca-4195-aefb-cb5f407ab009"


@dataclass
class TimelineClip:
    track_name: str
    track_kind: str  # video | audio
    track_index: int  # 0-based within video or audio group
    label: str
    timeline_start: int  # frames
    timeline_end: int  # frames
    source_in: int  # frames
    source_out: int  # frames
    filepath: str | None
    proxy_basename: str | None
    clip_id: str = ""


def timeline_clip_id(clip: TimelineClip) -> str:
    if clip.clip_id:
        return clip.clip_id
    return (
        f"{clip.track_kind}:{clip.track_index}:"
        f"{clip.timeline_start}:{clip.timeline_end}:{clip.label}"
    )


@dataclass
class SequenceInfo:
    name: str
    uid: str
    proxy_clip_count: int = 0
    clips: list[TimelineClip] = field(default_factory=list)


class ObjectIndex:
    """Index ObjectID and ObjectUID referenceable objects."""

    def __init__(self, root: ET.Element) -> None:
        self.by_oid: dict[str, list[ET.Element]] = {}
        self.by_uid: dict[str, ET.Element] = {}
        for el in root.iter():
            oid, cid, uid = el.get("ObjectID"), el.get("ClassID"), el.get("ObjectUID")
            if oid and cid:
                self.by_oid.setdefault(oid, []).append(el)
            if uid and cid:
                self.by_uid[uid] = el

    def ref_oid(self, ref: str | None, tag: str | None = None) -> ET.Element | None:
        if not ref:
            return None
        for el in self.by_oid.get(ref, []):
            if tag is None or el.tag == tag:
                return el
        return None

    def ref_uid(self, ref: str | None, tag: str | None = None) -> ET.Element | None:
        if not ref:
            return None
        el = self.by_uid.get(ref)
        if el is None:
            return None
        if tag is None or el.tag == tag:
            return el
        return None


def load_prproj(path: str | Path) -> ET.Element:
    with gzip.open(path, "rb") as fh:
        return ET.fromstring(fh.read())


def ticks_to_frames(ticks: int | str | None) -> int:
    if ticks is None or ticks == "":
        return 0
    return round(int(ticks) / TICKS_PER_FRAME)


def _filepath_from_media_source(src_el: ET.Element, index: ObjectIndex) -> str | None:
    ms = src_el.find("MediaSource")
    if ms is None:
        return None
    media_ref = ms.find("Media")
    if media_ref is None:
        return None
    media = index.ref_uid(media_ref.get("ObjectURef"), "Media")
    if media is None:
        return None
    return media.findtext("FilePath")


def _clip_payload_from_video_audio(el: ET.Element, index: ObjectIndex) -> ET.Element | None:
    """Return the element carrying Source / InPoint / OutPoint."""
    if el.tag in ("VideoClip", "AudioClip"):
        inline = el.find("Clip")
        if inline is not None and inline.find("Source") is not None:
            return inline
    if el.tag == "Clip":
        return el
    inner = el.find("Clip")
    if inner is not None:
        if inner.get("ObjectRef"):
            resolved = index.ref_oid(inner.get("ObjectRef"), "Clip")
            if resolved is not None:
                return resolved
        if inner.find("Source") is not None:
            return inner
    return None


def _resolve_media_from_clip_ref(clip_ref_el: ET.Element | None, index: ObjectIndex) -> tuple[str | None, int, int]:
    if clip_ref_el is None:
        return None, 0, 0
    holder = index.ref_oid(clip_ref_el.get("ObjectRef"))
    if holder is None:
        return None, 0, 0
    payload = _clip_payload_from_video_audio(holder, index)
    if payload is None:
        return None, 0, 0
    src_ref = payload.find("Source")
    filepath = None
    if src_ref is not None:
        src = index.ref_oid(src_ref.get("ObjectRef"))
        if src is not None:
            filepath = _filepath_from_media_source(src, index)
            if filepath is None and src.tag == "Media":
                filepath = src.findtext("FilePath")
    src_in = ticks_to_frames(payload.findtext("InPoint"))
    src_out = ticks_to_frames(payload.findtext("OutPoint"))
    return filepath, src_in, src_out


def _track_items_from_track(track_el: ET.Element) -> list[ET.Element]:
    clip_track = track_el.find("ClipTrack")
    if clip_track is None:
        items_parent = track_el.find("TrackItems")
        if items_parent is None:
            return []
        return items_parent.findall("TrackItem")
    clip_items = clip_track.find("ClipItems")
    if clip_items is None:
        return []
    track_items = clip_items.find("TrackItems")
    if track_items is None:
        return []
    return track_items.findall("TrackItem")


def _parse_track_item(
    track_item_ref: str,
    track_name: str,
    track_kind: str,
    index: ObjectIndex,
    track_index: int,
) -> TimelineClip | None:
    wrapper = index.ref_oid(track_item_ref)
    if wrapper is None:
        return None

    cti = wrapper if wrapper.tag == "ClipTrackItem" else wrapper.find("ClipTrackItem")
    if cti is None:
        return None

    ti = cti.find("TrackItem")
    if ti is None:
        return None

    tl_start = ticks_to_frames(ti.findtext("Start"))
    tl_end = ticks_to_frames(ti.findtext("End"))

    label = ""
    filepath = None
    src_in = src_out = 0

    sub = cti.find("SubClip")
    if sub is not None:
        subclip = index.ref_oid(sub.get("ObjectRef"), "SubClip")
        if subclip is not None:
            label = subclip.findtext("Name", default="")
            clip_ref = subclip.find("Clip")
            filepath, src_in, src_out = _resolve_media_from_clip_ref(clip_ref, index)

    if filepath is None:
        clip_ref = cti.find("Clip")
        filepath, src_in, src_out = _resolve_media_from_clip_ref(clip_ref, index)

    base = proxy_basename(filepath)
    clip = TimelineClip(
        track_name=track_name,
        track_kind=track_kind,
        track_index=track_index,
        label=label,
        timeline_start=tl_start,
        timeline_end=tl_end,
        source_in=src_in,
        source_out=src_out,
        filepath=filepath,
        proxy_basename=base,
    )
    clip.clip_id = timeline_clip_id(clip)
    return clip


def _track_display_name(track: ET.Element) -> str:
    for el in track.iter("MZ.TrackName"):
        text = (el.text or "").strip()
        if text:
            return text
    return ""


def _tracks_from_group(group_el: ET.Element, index: ObjectIndex, kind: str) -> list[tuple[str, ET.Element]]:
    tracks: list[tuple[str, ET.Element]] = []
    tg = group_el.find("TrackGroup")
    if tg is None:
        return tracks
    tracks_container = tg.find("Tracks")
    if tracks_container is None:
        return tracks
    for tr in tracks_container.findall("Track"):
        track = index.ref_uid(tr.get("ObjectURef"))
        if track is None:
            continue
        tracks.append((_track_display_name(track), track))
    return tracks


def iter_sequences(root: ET.Element) -> list[SequenceInfo]:
    index = ObjectIndex(root)
    sequences: list[SequenceInfo] = []

    for seq_el in root.iter("Sequence"):
        if seq_el.get("ClassID") != SEQUENCE_CLASS:
            continue
        name = seq_el.findtext("Name", default="")
        uid = seq_el.get("ObjectUID", "")
        info = SequenceInfo(name=name, uid=uid)

        tgs = seq_el.find("TrackGroups")
        if tgs is None:
            sequences.append(info)
            continue

        for tg_entry in tgs.findall("TrackGroup"):
            media_type = tg_entry.findtext("First")
            group_ref = tg_entry.find("Second")
            if group_ref is None:
                continue
            group_el = index.ref_oid(group_ref.get("ObjectRef"))
            if group_el is None:
                continue

            if media_type == VIDEO_TRACK_GROUP and group_el.tag == "VideoTrackGroup":
                kind = "video"
            elif media_type == AUDIO_TRACK_GROUP and group_el.tag == "AudioTrackGroup":
                kind = "audio"
            else:
                continue

            for track_index, (track_name, track_el) in enumerate(
                _tracks_from_group(group_el, index, kind)
            ):
                for ti in _track_items_from_track(track_el):
                    clip = _parse_track_item(
                        ti.get("ObjectRef"), track_name, kind, index, track_index
                    )
                    if clip is None:
                        continue
                    info.clips.append(clip)
                    if clip.proxy_basename:
                        info.proxy_clip_count += 1

        sequences.append(info)

    return sequences
