# Milestone 1 — reference pin and v02b offset verification

**Date:** 2026-09-01  
**Pinned digest (v02b):** `b55e19c95cb164b963236ef1ca19af46cd8917c1e32882a6ea54268455d647f6`  
**Lineage doc digest (stale copy):** `a712aeb7e83b0a354597049f26adb4469971d32eb290210479fc172c457d5442`

## Verdict

**Tables match and the defect is present** — the on-disk v02b is a re-export of the same edit described in `SW_SERIES-081026-stringout-lineage-v01-cl.md`. Proceed with the defect branch in milestone 3.

## Computed vs published offset table

All 14 published rows match recomputation from pinned `081026-Stringout-Source-v02b-cg.xml`.

| CAM B | B source range | CAM A | offset | match |
|---|---|---|---|---|
| `B009C001_130101_R1IB.mov` | 0–36875 | `A009C002_130101_R5DJ.mov` | −1 | yes (name≠file) |
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

## A009C002 link defect

**Present:** yes

The first V1 clipitem is *named* `A009C002_130101_R5DJ.mov` but its `<file>` resolves to `B015C002_130101_R1IB.mov`. No file definition for `A009C002` exists in the assembly.

**Recommendation (from brief):** relink that one clip in Premiere and re-export v02b. The media file exists at `02_Assets/01_Video/01_Footage/PROXIES/2026-08-10/A009C002_130101_R5DJ.mov`. Until then, Chi Lee take 01 A-camera projection must be skipped, not guessed.

## Checksums

See `reference/checksums.json`. `swpost.reference.verify_references()` refuses to run on mismatch.

Re-run verification:

```bash
python3 scripts/verify_v02b_offsets.py
python3 -m pytest tests/test_reference.py -q
```
