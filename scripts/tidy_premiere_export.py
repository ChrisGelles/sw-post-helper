#!/usr/bin/env python3
"""Wrap a sequence-only Premiere XMEML export with conform bin layout + canonical paths."""

from __future__ import annotations

import copy
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote

from swpost.fcpxml import deterministic_uuid, file_id, masterclip_id, write_xmeml
from swpost.pull_quote import canonical_pathurl

CAM_FOOTAGE = {
    "A012C002_130101_R5DJ.mov": ("2026-08-10", "CAM A"),
    "B014C002_130101_R1IB.mov": ("2026-08-10", "CAM B"),
}

SEQ_RATE = ("24", "TRUE")


def _sub(parent: ET.Element, tag: str, text: str | None = None, **attrib: str) -> ET.Element:
    el = ET.SubElement(parent, tag, attrib)
    if text is not None:
        el.text = text
    return el


def _append_seq_rate(parent: ET.Element) -> None:
    rate = _sub(parent, "rate")
    _sub(rate, "timebase", SEQ_RATE[0])
    _sub(rate, "ntsc", SEQ_RATE[1])


def classify_bin(basename: str, pathurl: str) -> tuple:
    path_lower = unquote(pathurl).lower()
    ext = Path(basename).suffix.lower()
    if "/04_vo/" in path_lower or "temp vo" in path_lower:
        return ("vo",)
    if ext == ".wav":
        if "nicole" in path_lower:
            return ("audio", "2026-08-10", "Nikki Burt")
        return ("audio_passthrough",)
    if "stringout" in basename.lower() or ext == ".mp4":
        return ("graphics_reference",)
    if basename in CAM_FOOTAGE:
        date, cam = CAM_FOOTAGE[basename]
        return ("footage", date, cam)
    if ext == ".mov":
        return ("graphics",)
    return ("graphics",)


def collect_full_files(root: ET.Element) -> dict[str, ET.Element]:
    out: dict[str, ET.Element] = {}
    for fe in root.iter("file"):
        if fe.find("pathurl") is not None:
            out[fe.get("id") or ""] = fe
    return out


def patch_master_clip(
    clip: ET.Element,
    *,
    basename: str,
    mc_id: str,
    fi_id: str,
    file_el: ET.Element,
) -> None:
    clip.set("id", mc_id)
    clip.find("masterclipid").text = mc_id
    clip.find("name").text = basename
    uuid_el = clip.find("uuid")
    if uuid_el is not None:
        uuid_el.text = deterministic_uuid(mc_id)
    duration = file_el.findtext("duration")
    if duration and clip.find("duration") is not None:
        clip.find("duration").text = duration
    for ci in clip.iter("clipitem"):
        mc = ci.find("masterclipid")
        if mc is not None:
            mc.text = mc_id
        name = ci.find("name")
        if name is not None:
            name.text = basename
        f = ci.find("file")
        if f is None:
            continue
        f.set("id", fi_id)
        if f.find("pathurl") is not None:
            ci.remove(f)
            patched = copy.deepcopy(file_el)
            patched.set("id", fi_id)
            ci.insert(list(ci).index(ci.find("out")) + 1, patched)


def build_master_from_file(
    file_el: ET.Element,
    *,
    basename: str,
    mc_id: str,
    fi_id: str,
    prefix: str,
    start_idx: int,
) -> tuple[ET.Element, int]:
    duration = int(file_el.findtext("duration") or "1")
    channelcount = int(file_el.findtext(".//channelcount") or "0")
    has_video = file_el.find("media/video") is not None
    fe = copy.deepcopy(file_el)
    fe.set("id", fi_id)

    clip = ET.Element("clip", {"id": mc_id})
    _sub(clip, "uuid", deterministic_uuid(mc_id))
    _sub(clip, "masterclipid", mc_id)
    _sub(clip, "ismasterclip", "TRUE")
    _sub(clip, "duration", str(duration))
    _append_seq_rate(clip)
    _sub(clip, "name", basename)
    media = _sub(clip, "media")
    idx = start_idx

    def add_clipitem(parent_track: ET.Element, *, full_file: bool, audio_track_index: int | None) -> None:
        nonlocal idx
        idx += 1
        ci = _sub(parent_track, "clipitem", id=f"{prefix}-mc-{idx:05d}")
        _sub(ci, "masterclipid", mc_id)
        _sub(ci, "name", basename)
        _append_seq_rate(ci)
        _sub(ci, "duration", str(duration))
        _sub(ci, "in", "0")
        _sub(ci, "out", str(duration))
        if full_file:
            ci.append(copy.deepcopy(fe))
        else:
            _sub(ci, "file", id=fi_id)
        if audio_track_index is not None:
            st = _sub(ci, "sourcetrack")
            _sub(st, "mediatype", "audio")
            _sub(st, "trackindex", str(audio_track_index))

    if has_video:
        vtrack = _sub(_sub(media, "video"), "track")
        add_clipitem(vtrack, full_file=True, audio_track_index=None)
        if channelcount > 0:
            audio = _sub(media, "audio")
            for ch in range(1, channelcount + 1):
                add_clipitem(_sub(audio, "track"), full_file=False, audio_track_index=ch)
    else:
        add_clipitem(_sub(_sub(media, "audio"), "track"), full_file=True, audio_track_index=1)

    return clip, idx


def strip_transitions(root: ET.Element) -> int:
    """Remove all transitionitem elements (overlapping transitions break FCP import)."""
    removed = 0
    for parent in root.iter():
        for ti in list(parent.findall("transitionitem")):
            parent.remove(ti)
            removed += 1
    return removed


def normalize_file_ref(file_el: ET.Element, file_id: str) -> None:
    """Replace inline file payload with an empty idref (serializes self-closing)."""
    for child in list(file_el):
        file_el.remove(child)
    file_el.set("id", file_id)
    file_el.text = None
    file_el.tail = None


def strip_inline_files(sequence: ET.Element, file_meta: dict[str, tuple[str, str, str]]) -> None:
    for ci in sequence.iter("clipitem"):
        f = ci.find("file")
        if f is None:
            continue
        fid = f.get("id")
        if fid not in file_meta:
            continue
        _basename, mc_id, fi_id = file_meta[fid]
        mc = ci.find("masterclipid")
        if mc is None:
            mc = ET.Element("masterclipid")
            ci.insert(0, mc)
        mc.text = mc_id
        normalize_file_ref(f, fi_id)


def is_offline_stub_file(file_el: ET.Element) -> bool:
    if file_el.find("pathurl") is not None:
        return False
    if file_el.find("mediaSource") is not None:
        return True
    return bool(list(file_el))


def hoist_offline_stubs(
    sequence: ET.Element,
    graphics_children: ET.Element,
    *,
    prefix: str,
) -> int:
    """Move pathurl-less Graphic/offline file defs from the sequence into Graphics bin."""
    stub_defs: dict[str, tuple[ET.Element, ET.Element]] = {}
    for ci in sequence.iter("clipitem"):
        f = ci.find("file")
        if f is None or not is_offline_stub_file(f):
            continue
        fid = f.get("id")
        if not fid or fid in stub_defs:
            continue
        stub_defs[fid] = (copy.deepcopy(f), ci)

    hoisted = 0
    for fid, (stub, src_ci) in sorted(stub_defs.items()):
        mc_id = f"masterclip-{fid.removeprefix('file-')}"
        basename = stub.findtext("name") or fid
        duration = int(src_ci.findtext("duration") or stub.findtext("duration") or "1")
        clip = ET.Element("clip", {"id": mc_id})
        _sub(clip, "uuid", deterministic_uuid(mc_id))
        _sub(clip, "masterclipid", mc_id)
        _sub(clip, "ismasterclip", "TRUE")
        _sub(clip, "duration", str(duration))
        _append_seq_rate(clip)
        _sub(clip, "name", basename)
        media = _sub(clip, "media")
        track = _sub(_sub(media, "video"), "track")
        ci = _sub(track, "clipitem", id=f"{prefix}-offline-{fid}")
        _sub(ci, "masterclipid", mc_id)
        _sub(ci, "name", basename)
        _append_seq_rate(ci)
        _sub(ci, "duration", str(duration))
        _sub(ci, "in", "0")
        _sub(ci, "out", str(duration))
        stub_copy = copy.deepcopy(stub)
        stub_copy.set("id", fid)
        ci.append(stub_copy)
        graphics_children.append(clip)
        hoisted += 1

    for ci in sequence.iter("clipitem"):
        f = ci.find("file")
        if f is None:
            continue
        fid = f.get("id")
        if fid in stub_defs and is_offline_stub_file(f):
            normalize_file_ref(f, fid)

    return hoisted


def write_xmeml_with_doctype(path: Path, root: ET.Element) -> None:
    write_xmeml(path, root)
    text = path.read_text(encoding="UTF-8")
    if "<!DOCTYPE xmeml>" not in text:
        text = text.replace(
            '<?xml version=\'1.0\' encoding=\'UTF-8\'?>',
            "<?xml version='1.0' encoding='UTF-8'?>\n<!DOCTYPE xmeml>",
            1,
        ).replace(
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>',
            1,
        )
    # Normalize empty file idrefs to self-closing form.
    text = re.sub(r"<file id=\"([^\"]+)\">\s*</file>", r'<file id="\1"/>', text)
    path.write_text(text, encoding="UTF-8")


def tidy_export(
    *,
    src_path: Path,
    ref_path: Path,
    out_path: Path,
    project_name: str,
) -> None:
    src_root = ET.parse(src_path).getroot()
    ref_root = ET.parse(ref_path).getroot()
    sequence = src_root.find("sequence")
    if sequence is None:
        raise SystemExit("input XML has no sequence element")

    sequence = copy.deepcopy(sequence)
    full_files = collect_full_files(src_root)
    if not full_files:
        full_files = collect_full_files(sequence)

    ref_mcs: dict[str, ET.Element] = {}
    for clip in ref_root.iter("clip"):
        if clip.findtext("ismasterclip") == "TRUE":
            ref_mcs[(clip.findtext("name") or "").lower()] = clip

    file_meta: dict[str, tuple[str, str, str]] = {}
    canonical_files: dict[str, ET.Element] = {}
    by_mc: dict[str, tuple[str, ET.Element, tuple]] = {}
    prefix = re.sub(r"[^A-Za-z0-9]+", "-", project_name).strip("-")
    mc_idx = 0

    for fid, fe in full_files.items():
        canon_url = canonical_pathurl(fe.findtext("pathurl") or "")
        fe = copy.deepcopy(fe)
        fe.find("pathurl").text = canon_url
        basename = fe.findtext("name") or Path(unquote(canon_url)).name
        mc = masterclip_id(basename)
        fi = file_id(basename)
        file_meta[fid] = (basename, mc, fi)
        canonical_files[fid] = fe
        if mc in by_mc:
            continue
        bin_info = classify_bin(basename, canon_url)
        ref = ref_mcs.get(basename.lower())
        if ref is not None:
            clip = copy.deepcopy(ref)
            patch_master_clip(clip, basename=basename, mc_id=mc, fi_id=fi, file_el=fe)
        else:
            clip, mc_idx = build_master_from_file(
                fe,
                basename=basename,
                mc_id=mc,
                fi_id=fi,
                prefix=prefix,
                start_idx=mc_idx,
            )
        by_mc[mc] = (basename, clip, bin_info)

    strip_inline_files(sequence, file_meta)
    strip_transitions(sequence)

    root = ET.Element("xmeml", {"version": "4"})
    project = _sub(root, "project")
    _sub(project, "name", project_name)
    children = _sub(project, "children")

    footage = _sub(children, "bin")
    _sub(footage, "name", "Footage")
    footage_children = _sub(footage, "children")
    audio_bin = _sub(children, "bin")
    _sub(audio_bin, "name", "Audio")
    audio_children = _sub(audio_bin, "children")
    graphics = _sub(children, "bin")
    _sub(graphics, "name", "Graphics")
    graphics_children = _sub(graphics, "children")
    graphics_ref = _sub(graphics_children, "bin")
    _sub(graphics_ref, "name", "_Reference")
    graphics_ref_children = _sub(graphics_ref, "children")
    vo_bin = _sub(children, "bin")
    _sub(vo_bin, "name", "VO")
    vo_children = _sub(vo_bin, "children")
    audio_passthrough = _sub(audio_children, "bin")
    _sub(audio_passthrough, "name", "_Passthrough")
    audio_passthrough_children = _sub(audio_passthrough, "children")
    seq_bin = _sub(children, "bin")
    _sub(seq_bin, "name", "Seq")
    seq_bin_children = _sub(seq_bin, "children")

    footage_date_children: dict[str, ET.Element] = {}
    footage_camera_bins: dict[tuple[str, str], ET.Element] = {}
    audio_date_children: dict[str, ET.Element] = {}
    audio_person_bins: dict[tuple[str, str], ET.Element] = {}

    for _basename, clip, bin_info in sorted(by_mc.values(), key=lambda x: x[0].lower()):
        kind = bin_info[0]
        if kind == "footage":
            date, cam = bin_info[1], bin_info[2]
            if date not in footage_date_children:
                dbin = _sub(footage_children, "bin")
                _sub(dbin, "name", date)
                footage_date_children[date] = _sub(dbin, "children")
            date_children = footage_date_children[date]
            key = (date, cam)
            if key not in footage_camera_bins:
                cbin = _sub(date_children, "bin")
                _sub(cbin, "name", cam)
                footage_camera_bins[key] = _sub(cbin, "children")
            footage_camera_bins[key].append(clip)
        elif kind == "graphics":
            graphics_children.append(clip)
        elif kind == "graphics_reference":
            graphics_ref_children.append(clip)
        elif kind == "vo":
            vo_children.append(clip)
        elif kind == "audio_passthrough":
            audio_passthrough_children.append(clip)
        elif kind == "audio":
            date, person = bin_info[1], bin_info[2]
            if date not in audio_date_children:
                dbin = _sub(audio_children, "bin")
                _sub(dbin, "name", date)
                audio_date_children[date] = _sub(dbin, "children")
            date_children = audio_date_children[date]
            key = (date, person)
            if key not in audio_person_bins:
                pbin = _sub(date_children, "bin")
                _sub(pbin, "name", person)
                audio_person_bins[key] = _sub(pbin, "children")
            audio_person_bins[key].append(clip)

    hoist_offline_stubs(sequence, graphics_children, prefix=prefix)
    seq_bin_children.append(sequence)
    write_xmeml_with_doctype(out_path, root)


def strip_transitions_file(src_path: Path, out_path: Path, *, project_name: str | None = None) -> int:
    root = ET.parse(src_path).getroot()
    if project_name:
        name_el = root.find("project/name")
        if name_el is not None:
            name_el.text = project_name
    removed = strip_transitions(root)
    write_xmeml(out_path, root)
    return removed


def main() -> None:
    if len(sys.argv) == 4 and sys.argv[1] != "--strip-transitions-only":
        src, ref, out = (Path(a) for a in sys.argv[1:])
        tidy_export(
            src_path=src,
            ref_path=ref,
            out_path=out,
            project_name=out.stem,
        )
        print(f"wrote {out}")
        return
    if len(sys.argv) == 4 and sys.argv[1] == "--strip-transitions-only":
        src, out = Path(sys.argv[2]), Path(sys.argv[3])
        n = strip_transitions_file(src, out, project_name=out.stem)
        print(f"removed {n} transitionitem elements; wrote {out}")
        return
    raise SystemExit(
        "usage:\n"
        "  tidy_premiere_export.py SRC.xml REF.xml OUT.xml\n"
        "  tidy_premiere_export.py --strip-transitions-only SRC.xml OUT.xml"
    )


if __name__ == "__main__":
    main()
