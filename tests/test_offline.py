"""Offline synthetic naming tests."""

from __future__ import annotations

from swpost.offline import (
    ascii_safe_basename,
    assign_synthetic_offline_names,
    assert_offline_file_ids_distinct_sources,
    build_offline_clip,
)


class _Clip:
    def __init__(self, **kwargs):
        kwargs.setdefault("track_index", 0)
        for k, v in kwargs.items():
            setattr(self, k, v)


def test_ascii_safe_basename():
    assert ascii_safe_basename("NARRATOR + ANIM — title") == "NARRATOR-ANIM-title"
    assert ascii_safe_basename("Card-01-Miranda.mov") == "Card-01-Miranda.mov"


def test_synthetic_video_clips_become_color_matte_candidates():
    clip = build_offline_clip(
        _Clip(
            label="Graphic",
            track_name="V3",
            track_kind="video",
            timeline_start=100,
            timeline_end=200,
            source_in=0,
            source_out=100,
            filepath="1196574294",
            proxy_basename=None,
        )
    )
    assert clip.empty_graphic is True
    assert clip.synthetic is True
    assert clip.output_basename == ""
    assert clip.output_path == ""


def test_synthetic_narrator_video_is_card_placeholder_not_color_matte():
    offline = [
        build_offline_clip(
            _Clip(
                label="NARRATOR + ANIM — The planet is full of life at every scal",
                track_name="",
                track_kind="video",
                timeline_start=100,
                timeline_end=200,
                source_in=0,
                source_out=100,
                filepath="1196574294",
                proxy_basename=None,
            )
        ),
        build_offline_clip(
            _Clip(
                label="NARRATOR + ANIM — second card",
                track_name="",
                track_kind="video",
                timeline_start=300,
                timeline_end=400,
                source_in=0,
                source_out=100,
                filepath="1196574295",
                proxy_basename=None,
            )
        ),
    ]
    named = assign_synthetic_offline_names(offline, [])
    assert all(not c.empty_graphic for c in named)
    assert all(c.output_basename == "placeholder.mov" for c in named)


def test_unresolved_clip_keeps_source_basename_not_offline_ext():
    clip = build_offline_clip(
        _Clip(
            label="reference render",
            track_name="V4",
            track_kind="video",
            timeline_start=100,
            timeline_end=200,
            source_in=0,
            source_out=100,
            filepath="/editor/for_review/ep05-rough-cut.mov",
            proxy_basename=None,
        ),
        relink_map={},
    )
    assert clip.output_basename == "ep05-rough-cut.mov"
    assert "offline.mov" not in clip.output_basename
    assert clip.output_path.endswith("ep05-rough-cut.mov")
    assert clip.media_key == clip.filepath.replace("\\", "/")


def test_vo_scratch_path_resolves_via_relink_fallback():
    clip = build_offline_clip(
        _Clip(
            label="bg music",
            track_name="A5",
            track_kind="audio",
            timeline_start=100,
            timeline_end=200,
            source_in=0,
            source_out=100,
            filepath="/editor/02_Audio/04_VO/Ep02-Ep09-Joey-Temp-VO-esv2-30p-bg-m-music-10p.wav",
            proxy_basename=None,
        ),
        relink_map={},
    )
    assert clip.output_basename == "Ep02-Ep09-Joey-Temp-VO-esv2-30p-bg-m-music-10p.wav"
    assert clip.output_path.endswith("temp VO/Ep02-Ep09-Joey-Temp-VO-esv2-30p-bg-m-music-10p.wav")
    assert "offline.wav" not in clip.output_path


def test_vo_counters_still_assign_sequential_names():
    offline = [
        build_offline_clip(
            _Clip(
                label="VO PICKUP — Miranda line",
                track_name="",
                track_kind="audio",
                timeline_start=150,
                timeline_end=250,
                source_in=0,
                source_out=100,
                filepath="222",
                proxy_basename=None,
            )
        ),
        build_offline_clip(
            _Clip(
                label="VO PICKUP — Miranda line two",
                track_name="",
                track_kind="audio",
                timeline_start=350,
                timeline_end=450,
                source_in=0,
                source_out=100,
                filepath="444",
                proxy_basename=None,
            )
        ),
    ]
    named = assign_synthetic_offline_names(offline, [])
    assert [c.output_basename for c in named] == ["VO-01.wav", "VO-02.wav"]


def test_assert_offline_file_ids_distinct_sources_rejects_merged_paths():
    same = build_offline_clip(
        _Clip(
            label="a",
            track_name="",
            track_kind="audio",
            timeline_start=0,
            timeline_end=10,
            source_in=0,
            source_out=10,
            filepath="/a/one.wav",
            proxy_basename=None,
        ),
        relink_map={},
    )
    other = build_offline_clip(
        _Clip(
            label="b",
            track_name="",
            track_kind="audio",
            timeline_start=20,
            timeline_end=30,
            source_in=0,
            source_out=10,
            filepath="/b/two.wav",
            proxy_basename=None,
        ),
        relink_map={},
    )
    assert_offline_file_ids_distinct_sources([same, other])


def test_drop_embedded_camera_audio_when_field_recording_covers_range():
    from swpost.offline import OfflineClip, drop_embedded_camera_audio

    camera = OfflineClip(
        clip_id="cam-audio",
        label="",
        track_name="",
        track_kind="audio",
        track_index=1,
        timeline_start=100,
        timeline_end=200,
        source_in=0,
        source_out=100,
        filepath="/proxy/A006C001_260609_R0DH.mov",
        synthetic=False,
        empty_graphic=False,
        output_role="PASSTHROUGH",
        destination_dir="",
        output_basename="A006C001_260609_R0DH.mov",
        output_path="/Volumes/SW_SERIES/x/A006C001_260609_R0DH.mov",
        media_key="/Volumes/SW_SERIES/x/A006C001_260609_R0DH.mov",
    )
    picture = OfflineClip(
        clip_id="cam-video",
        label="",
        track_name="",
        track_kind="video",
        track_index=0,
        timeline_start=100,
        timeline_end=200,
        source_in=0,
        source_out=100,
        filepath="/proxy/A006C001_260609_R0DH.mov",
        synthetic=False,
        empty_graphic=False,
        output_role="PASSTHROUGH",
        destination_dir="",
        output_basename="A006C001_260609_R0DH.mov",
        output_path="/Volumes/SW_SERIES/x/A006C001_260609_R0DH.mov",
        media_key="/Volumes/SW_SERIES/x/A006C001_260609_R0DH.mov",
    )
    boom = OfflineClip(
        clip_id="boom",
        label="",
        track_name="",
        track_kind="audio",
        track_index=2,
        timeline_start=100,
        timeline_end=200,
        source_in=500,
        source_out=600,
        filepath="/boom.wav",
        synthetic=False,
        empty_graphic=False,
        output_role="PASSTHROUGH",
        destination_dir="",
        output_basename="Toni Rook Take 01 Boom.wav",
        output_path="/Volumes/SW_SERIES/x/Toni Rook Take 01 Boom.wav",
        media_key="/Volumes/SW_SERIES/x/Toni Rook Take 01 Boom.wav",
    )
    dropped_ids: set[str] = set()
    kept = drop_embedded_camera_audio(
        [camera, picture, boom], dropped_clip_ids=dropped_ids
    )
    assert len(kept) == 2
    assert "cam-audio" in dropped_ids
    assert all(c.clip_id != "cam-audio" for c in kept)


def test_keep_embedded_camera_audio_without_field_recording_overlap():
    from swpost.offline import OfflineClip, drop_embedded_camera_audio

    camera = OfflineClip(
        clip_id="cam-audio",
        label="",
        track_name="",
        track_kind="audio",
        track_index=1,
        timeline_start=100,
        timeline_end=200,
        source_in=0,
        source_out=100,
        filepath="/proxy/A004C001_260609_R0DH.mov",
        synthetic=False,
        empty_graphic=False,
        output_role="PASSTHROUGH",
        destination_dir="",
        output_basename="A004C001_260609_R0DH.mov",
        output_path="/Volumes/SW_SERIES/x/A004C001_260609_R0DH.mov",
        media_key="/Volumes/SW_SERIES/x/A004C001_260609_R0DH.mov",
    )
    picture = OfflineClip(
        clip_id="cam-video",
        label="",
        track_name="",
        track_kind="video",
        track_index=0,
        timeline_start=100,
        timeline_end=200,
        source_in=0,
        source_out=100,
        filepath="/proxy/A004C001_260609_R0DH.mov",
        synthetic=False,
        empty_graphic=False,
        output_role="PASSTHROUGH",
        destination_dir="",
        output_basename="A004C001_260609_R0DH.mov",
        output_path="/Volumes/SW_SERIES/x/A004C001_260609_R0DH.mov",
        media_key="/Volumes/SW_SERIES/x/A004C001_260609_R0DH.mov",
    )
    kept = drop_embedded_camera_audio([camera, picture])
    assert len(kept) == 2
