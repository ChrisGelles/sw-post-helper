# Milestone 3 — projection

**Date:** 2026-09-02  
**Fixture:** `tests/STEM-ep02-v01-cg.prproj`, sequence `STEM-ep2-edit-v01-cl`  
**Expected data:** `tests/fixtures/projection_ep02.json`

## Offset gates (v03 sync assembly)

On-disk `081026-Stringout-Source-v03-cg.xml` SHA-256: `fa083815…`

| Gate | Rows | Verdict |
|---|---|---|
| B→A (`verify_v03_offsets.py`) | 14/14 | match; A009C002 defect resolved |
| B→boom (`verify_v03_boom_offsets.py`) | 16/16 | match v02b values |
| B→lav (`verify_v03_lav_offsets.py`) | 15/15 | unchanged from v02b |

**B→boom note:** Brief expected a one-frame audio-pass shift (Miranda −503→−504, etc.). Pinned v03 BOOM track is byte-identical to v02b — shift not present in this export. Boom and lav agree where brief expected a one-frame divergence.

## What shipped

- `swpost/assemblies.py` — interval maps from pinned assemblies; v03 B-keyed offset tables
- `swpost/project.py` — proxy cut extraction (nested `270p_*` sequences + direct file refs), five-role projection, collision guard, label cross-check, report payload
- `swpost/labels.py` — `NAME HH:MM:SS:FF` select label parser
- Data-driven tests: `tests/test_projection_ep02.py` + `tests/fixtures/projection_ep02.json`
- Stub (skipped): `tests/test_projection_ep04.py`

## Design decisions (Chris, 2026-09-02; v03 update)

| Topic | Decision |
|---|---|
| Fixture | ep02 now; ep04 gate deferred |
| Role scope | All five roles every cut; empty intervals → report line |
| Proxy cuts | Every video-track nested/direct proxy clip; dedupe vs audio |
| Collisions | Overlap on same output role → hard failure |
| Name≠file | Report mismatch, emit normally — nothing excluded |
| Caitlin lav | `Lav 03 Caitlin Take 01.wav` emitted; report notes internal pack |
| A011 gap | B-source 33986–36417: emit B only, report empty CAM_A |
| Short runs | B-keyed rows &lt; 2 frames filtered from offset tables |

## ep02 results

- 12 proxy cuts extracted (nested `270p_*` on V1)
- 54 projected pieces: CAM_B/A/BOOM/LAV × 12, LAV_INT × 6 (empty before June 10 segments)
- Sample cut `270p_1554` verified against fixture data (Forrest Blackburn take 02)
- **June projection untouched** by v03 re-pin (uses `CMNH-SW-stringout-ref-270.xml` + v02 arithmetic only)

## Aug 10 audio (v03)

**B→boom** keyed by B source frame via v03 BOOM track.

**B→lav** keyed by v03 LAV track (not v02 A2 mixed field-select).

**Special cases**
- Caitlin take 01 lav (`Lav 03 Caitlin Take 01.wav`) — emitted; subclip name reads `Caitlin Take 01 Lav.wav`
- Destiny take 02 lav on boom track — emitted on BOOM track, flagged as not boom

**Accuracy note:** Destiny take 01 boom offsets differ from v02 by ~3 frames (error floor).

## Explicitly untested in M3

**Aug 10 end-to-end against a real cut** — lookup tables verified from v03; no fixture cut exercises Aug 10 projection yet.

**ep04 Morgan gate** — documented in skipped `test_projection_ep04.py`.

## Report fields collected (written in M5)

`ProjectionReport` carries: `piece_counts`, `empty_role_ranges`, `offset_boundary_splits`, `absent_roles`, `link_defects`, `collisions`, `label_mismatches`, `name_file_mismatches`, `internal_lav_pack`, `boom_track_not_boom`, `b_keyed_accuracy_notes`.
