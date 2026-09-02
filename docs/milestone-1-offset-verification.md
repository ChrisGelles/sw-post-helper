# Milestone 1 — reference pin and v03 offset verification

**Date:** 2026-09-02 (v03 re-pin)  
**Pinned digest (v03 sync assembly):** `fa083815ab8706346caac10fa34e48c3b1760d257e24a69d2deae92586ee09c4`  
**Stringout arithmetic (unchanged):** `081026-Stringout-Source-v02-cg.xml` at `46d1bf65…`  
**Superseded:** `081026-Stringout-Source-v02b-cg.xml` → `reference/_old/`

## Verdict

**All 14 B→A rows match.** A009C002 link defect **resolved** in v03 — `B009C001` → `A009C002` offset −1 now derives from correct media. No name≠file defects on V1.

## Computed vs published B→A table

| CAM B | B source range | CAM A | offset | match |
|---|---|---|---|---|
| `B009C001_130101_R1IB.mov` | 0–36875 | `A009C002_130101_R5DJ.mov` | −1 | yes |
| `B010C001_130101_R1IB.mov` | 0–25531 | `A009C003_130101_R5DJ.mov` | −1 | yes |
| `B011C001_130101_R1IB.mov` | 0–18252 | `A010C001_130101_R5DJ.mov` | +0 | yes |
| `B012C001_130101_R1IB.mov` | 0–14588 | `A010C002_130101_R5DJ.mov` | +6 | yes |
| `B013C001_130101_R1IB.mov` | 748–21659 | `A011C001_130101_R5DJ.mov` | +1 | yes |
| `B013C001_130101_R1IB.mov` | 21329–36417 | `A011C001_130101_R5DJ.mov` | +1 | yes |
| `B014C001_130101_R1IB.mov` | 0–7155 | `A012C001_130101_R5DJ.mov` | +1 | yes |
| `B014C002_130101_R1IB.mov` | 0–12855 | `A012C002_130101_R5DJ.mov` | −1 | yes |
| `B014C002_130101_R1IB.mov` | 12960–47486 | `A012C002_130101_R5DJ.mov` | −1 | yes |
| `B015C001_130101_R1IB.mov` | 1348–8521 | `A013C001_120101_R5DJ.mov` | −3 | yes |
| `B015C001_130101_R1IB.mov` | 8625–32515 | `A013C001_120101_R5DJ.mov` | +1 | yes |
| `B015C002_130101_R1IB.mov` | 220–33732 | `A014C001_120101_R5DJ.mov` | +0 | yes |
| `B016C001_130101_R1IB.mov` | 244–25278 | `A015C001_130101_R5DJ.mov` | +1 | yes |
| `B016C001_130101_R1IB.mov` | 25388–29021 | `A015C001_130101_R5DJ.mov` | +1 | yes |

`B015C001` still reads −3 below source 8521 and +1 above 8625.

## v03 changes from v02b

- **A009C002 relinked** — V1 clipitem points at real `PROXIES/2026-08-10/A009C002_130101_R5DJ.mov`
- **A011 clamped** — `A011C001` duration 33986 frames; B-source **33986–36417** has no A-camera coverage (~101 s Caitlin take 01 tail)
- **Sequence name** — `081026 Stringout v03 cg` (same sequence UID)
- **Short-run filter** — B-keyed rows &lt; 2 frames dropped (e.g. B013/A012 boundary artifact at 36416–36417)

## Offset gates

```bash
python3 scripts/verify_v03_offsets.py      # B→A — 14/14
python3 scripts/verify_v03_boom_offsets.py  # B→boom — 16/16
python3 scripts/verify_v03_lav_offsets.py     # B→lav — 15/15
python3 -m pytest tests/test_reference.py -q
```

## Checksums

See `reference/checksums.json`. `swpost.reference.verify_references()` refuses to run on mismatch.
