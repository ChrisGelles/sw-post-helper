"""Offline synthetic naming tests."""

from __future__ import annotations

from swpost.offline import ascii_safe_basename, assign_synthetic_offline_names, build_offline_clip


class _Clip:
    def __init__(self, **kwargs):
        kwargs.setdefault("track_index", 0)
        for k, v in kwargs.items():
            setattr(self, k, v)


def test_ascii_safe_basename():
    assert ascii_safe_basename("NARRATOR + ANIM — title") == "NARRATOR-ANIM-title"
    assert ascii_safe_basename("Card-01-Miranda.mov") == "Card-01-Miranda.mov"


def test_synthetic_cards_get_unique_sequential_names():
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
                label="NARRATOR + ANIM — The planet is full of life at every scal",
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
    from swpost.project import ProjectedPiece

    pieces = [
        ProjectedPiece(
            role="CAM_B",
            timeline_start=50,
            timeline_end=250,
            source_in=0,
            source_out=100,
            file_basename="B003C001_260610_R51N.mov",
            file_path="/Volumes/SW_SERIES/x.mov",
            person="Miranda Sinnott-Armstrong",
            sourcetrack_index=1,
            cut_label="cut",
            enabled=True,
        )
    ]
    named = assign_synthetic_offline_names(offline, pieces)
    basenames = [c.output_basename for c in named]
    assert basenames[0] == "Card-01-Miranda.mov"
    assert basenames[1] == "Card-02.mov"
    assert len(set(basenames)) == 2


def test_card_and_vo_counters_are_independent():
    offline = [
        build_offline_clip(
            _Clip(
                label="NARRATOR + ANIM — first card",
                track_name="",
                track_kind="video",
                timeline_start=100,
                timeline_end=200,
                source_in=0,
                source_out=100,
                filepath="111",
                proxy_basename=None,
            )
        ),
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
                label="NARRATOR + ANIM — second card",
                track_name="",
                track_kind="video",
                timeline_start=300,
                timeline_end=400,
                source_in=0,
                source_out=100,
                filepath="333",
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
    assert [c.output_basename for c in named] == [
        "Card-01.mov",
        "VO-01.wav",
        "Card-02.mov",
        "VO-02.wav",
    ]
