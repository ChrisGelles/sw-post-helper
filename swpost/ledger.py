"""Single ledger for timeline clipitem disposition (projection vs passthrough vs cards)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Literal

from swpost.offline import classify_offline
from swpost.prproj import SequenceInfo, TimelineClip, timeline_clip_id
from swpost.project import ProjectionReport, ProxyCut, extract_proxy_cuts

Disposition = Literal["PROJECTED", "CARD", "PASSTHROUGH", "UNCLASSIFIED"]


class LedgerError(RuntimeError):
    """Timeline accounting or disposition failure."""


def _clip_matches_cut(clip: TimelineClip, cut: ProxyCut) -> bool:
    if (
        clip.timeline_start != cut.timeline_start
        or clip.timeline_end != cut.timeline_end
    ):
        return False
    if clip.label == cut.label:
        return True
    if clip.proxy_basename and clip.proxy_basename == cut.proxy_basename:
        return True
    return False


def _disposition_for_clip(clip: TimelineClip, *, projected: bool) -> Disposition:
    if projected:
        return "PROJECTED"
    role, _, _ = classify_offline(clip.label, clip.filepath)
    if role == "UNCLASSIFIED":
        return "UNCLASSIFIED"
    if role == "CARDS":
        return "CARD"
    return "PASSTHROUGH"


@dataclass
class LedgerEntry:
    clip_id: str
    clip: TimelineClip
    disposition: Disposition


@dataclass
class TimelineLedger:
    entries: dict[str, LedgerEntry]
    proxy_cuts: list[ProxyCut]
    projection_report: ProjectionReport

    def projected_entries(self) -> list[LedgerEntry]:
        return [e for e in self.entries.values() if e.disposition == "PROJECTED"]

    def passthrough_entries(self) -> list[LedgerEntry]:
        return [e for e in self.entries.values() if e.disposition == "PASSTHROUGH"]

    def card_entries(self) -> list[LedgerEntry]:
        return [e for e in self.entries.values() if e.disposition == "CARD"]

    def unclassified_entries(self) -> list[LedgerEntry]:
        return [e for e in self.entries.values() if e.disposition == "UNCLASSIFIED"]

    def assert_complete(self, sequence: SequenceInfo) -> None:
        clip_ids = [timeline_clip_id(c) for c in sequence.clips]
        if len(self.entries) != len(clip_ids):
            raise LedgerError(
                f"ledger has {len(self.entries)} entries but sequence has "
                f"{len(clip_ids)} timeline clipitems"
            )
        if set(self.entries) != set(clip_ids):
            missing = set(clip_ids) - set(self.entries)
            extra = set(self.entries) - set(clip_ids)
            raise LedgerError(
                f"ledger clip_id mismatch: missing={sorted(missing)!r} extra={sorted(extra)!r}"
            )

    def raise_if_unclassified(self) -> None:
        bad = self.unclassified_entries()
        if not bad:
            return
        lines = "\n".join(
            f"  - {e.clip_id!r} label={e.clip.label!r}" for e in bad[:20]
        )
        more = f"\n  … and {len(bad) - 20} more" if len(bad) > 20 else ""
        raise LedgerError(
            f"{len(bad)} timeline clipitem(s) are UNCLASSIFIED (refusing to guess):\n"
            f"{lines}{more}"
        )


def build_timeline_ledger(root: ET.Element, sequence: SequenceInfo) -> TimelineLedger:
    report = ProjectionReport(sequence_name=sequence.name, sequence_uid=sequence.uid)
    cuts = extract_proxy_cuts(root, sequence, report)

    projected_ids: set[str] = set()
    for cut in cuts:
        for clip in sequence.clips:
            if _clip_matches_cut(clip, cut):
                projected_ids.add(timeline_clip_id(clip))

    entries: dict[str, LedgerEntry] = {}
    for clip in sequence.clips:
        cid = timeline_clip_id(clip)
        disp = _disposition_for_clip(clip, projected=cid in projected_ids)
        entries[cid] = LedgerEntry(clip_id=cid, clip=clip, disposition=disp)

    ledger = TimelineLedger(entries=entries, proxy_cuts=cuts, projection_report=report)
    ledger.assert_complete(sequence)
    return ledger


def assert_output_accounting(
    ledger: TimelineLedger,
    *,
    offline_clip_ids: set[str],
    card_clip_ids: set[str],
    dropped_clip_ids: set[str] | None = None,
) -> None:
    """Every clipitem appears in exactly one output set before XML write."""
    seen: dict[str, str] = {}
    for entry in ledger.projected_entries():
        seen[entry.clip_id] = "PROJECTED"
    for cid in dropped_clip_ids or ():
        if cid in seen:
            raise LedgerError(
                f"clipitem {cid!r} already emitted as {seen[cid]!r}; also dropped"
            )
        seen[cid] = "DROPPED"
    for cid in offline_clip_ids:
        if cid in seen:
            raise LedgerError(
                f"clipitem {cid!r} already emitted as {seen[cid]!r}; "
                f"also in offline passthrough set"
            )
        seen[cid] = "OFFLINE"
    for cid in card_clip_ids:
        if cid in seen:
            raise LedgerError(
                f"clipitem {cid!r} already emitted as {seen[cid]!r}; also in card set"
            )
        seen[cid] = "CARD"
    accounted = set(seen)
    for cid in ledger.entries:
        if ledger.entries[cid].disposition == "UNCLASSIFIED":
            if cid in accounted:
                raise LedgerError(f"UNCLASSIFIED clipitem {cid!r} was emitted")
            continue
        if cid not in accounted:
            disp = ledger.entries[cid].disposition
            raise LedgerError(
                f"clipitem {cid!r} disposition={disp!r} missing from output sets"
            )
    if len(accounted) != len(ledger.entries) - len(ledger.unclassified_entries()):
        raise LedgerError(
            f"output accounting: {len(accounted)} emitted vs "
            f"{len(ledger.entries) - len(ledger.unclassified_entries())} expected"
        )
