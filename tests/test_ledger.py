"""Timeline ledger tests."""

from __future__ import annotations

from swpost.ledger import LedgerEntry, TimelineLedger, assert_output_accounting
from swpost.offline import classify_offline
from swpost.prproj import TimelineClip, timeline_clip_id
from swpost.project import ProjectionReport


def _clip(**kwargs) -> TimelineClip:
    defaults = dict(
        track_name="V1",
        track_kind="video",
        track_index=0,
        label="test",
        timeline_start=0,
        timeline_end=100,
        source_in=0,
        source_out=100,
        filepath=None,
        proxy_basename=None,
    )
    defaults.update(kwargs)
    c = TimelineClip(**defaults)
    c.clip_id = timeline_clip_id(c)
    return c


def test_classify_unknown_is_unclassified():
    role, dest, ext = classify_offline("270p_1554", None)
    assert role == "UNCLASSIFIED"
    assert dest == ""
    assert ext == ""


def test_assert_output_accounting_rejects_double_emit():
    clip = _clip(label="ON-SCREEN: hi")
    cid = clip.clip_id
    ledger = TimelineLedger(
        entries={
            cid: LedgerEntry(clip_id=cid, clip=clip, disposition="CARD"),
        },
        proxy_cuts=[],
        projection_report=ProjectionReport(sequence_name="s", sequence_uid="u"),
    )
    try:
        assert_output_accounting(
            ledger,
            offline_clip_ids={cid},
            card_clip_ids={cid},
        )
        raise AssertionError("expected LedgerError")
    except Exception as exc:
        assert "already emitted" in str(exc)
