# Milestone 3 — projection

**Date:** 2026-09-02  
**Fixture:** `tests/STEM-ep02-v01-cg.prproj`, sequence `STEM-ep2-edit-v01-cl`  
**Expected data:** `tests/fixtures/projection_ep02.json`

## Offset gate (re-run before M3)

On-disk `081026-Stringout-Source-v02b-cg.xml` SHA-256: `b55e19c9…`  
Stale lineage copy SHA-256: `a712aeb7…`

**Verdict:** all 14 published B→A offset rows match recomputation from the on-disk file. A009C002 link defect present (clipitem name ≠ resolved file). Proceed with skip-A-camera branch.

Run: `python3 scripts/verify_v02b_offsets.py`

## What shipped

- `swpost/assemblies.py` — interval maps from pinned assemblies; v02b offset table (defect rows excluded from lookup)
- `swpost/project.py` — proxy cut extraction (nested `270p_*` sequences + direct file refs), five-role projection, collision guard, label cross-check, report payload
- `swpost/labels.py` — `NAME HH:MM:SS:FF` select label parser
- Data-driven tests: `tests/test_projection_ep02.py` + `tests/fixtures/projection_ep02.json`
- Stub (skipped): `tests/test_projection_ep04.py`

## Design decisions (Chris, 2026-09-02)

| Topic | Decision |
|---|---|
| Fixture | ep02 now; ep04 gate deferred |
| Role scope | All five roles every cut; empty intervals → report line |
| Proxy cuts | Every video-track nested/direct proxy clip; dedupe vs audio |
| Collisions | Overlap on same output role → hard failure |
| A009C002 | Skip A-camera when no offset entry; generic name≠file detection |
| Aug 10 boom | Never emit; report as absent role |
| Person | Assembly segment authoritative; label cross-check when parseable |

## ep02 results

- 12 proxy cuts extracted (nested `270p_*` on V1)
- 54 projected pieces: CAM_B/A/BOOM/LAV × 12, LAV_INT × 6 (empty before June 10 segments)
- Sample cut `270p_1554` verified against fixture data (Forrest Blackburn take 02)

## Aug 10 audio (addendum 2026-09-02)

**B→boom** is in scope. Keyed by B source frame via v02b BOOM track (same shape as B→A). Gate: `python3 scripts/verify_v02b_boom_offsets.py` — **16/16 rows match**.

**B→lav** uses v02b LAV track (not v02 A2 mixed field-select).

**Hard exclusions**
- Caitlin take 01 lav (`Lav 03 Caitlin Take 01.wav`) — excluded; boom only; 263-frame drift noted in report
- Destiny take 02 lav on boom track — emitted on BOOM track, flagged as not boom

**Accuracy note:** Destiny take 01 boom offsets differ from v02 by ~3 frames (error floor).

## Explicitly untested in M3

**Aug 10 B→A / B→boom / B→lav end-to-end** — lookup tables verified from v02b; no fixture cut exercises Aug 10 projection yet.

**ep04 Morgan gate** — documented in skipped `test_projection_ep04.py`.

## Report fields collected (written in M5)

`ProjectionReport` carries: `piece_counts`, `empty_role_ranges`, `offset_boundary_splits`, `dropped_a_camera`, `absent_roles`, `link_defects`, `collisions`, `label_mismatches`.
