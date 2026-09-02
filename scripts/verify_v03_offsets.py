#!/usr/bin/env python3
"""Gate: recompute Aug 10 B→A offsets from pinned v03 sync assembly."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from swpost.assemblies import parse_v03_offsets  # noqa: E402

V03 = REPO / "reference" / "081026-Stringout-Source-v03-cg.xml"

PUBLISHED = [
    ("B009C001_130101_R1IB.mov", 0, 36875, "A009C002_130101_R5DJ.mov", -1),
    ("B010C001_130101_R1IB.mov", 0, 25531, "A009C003_130101_R5DJ.mov", -1),
    ("B011C001_130101_R1IB.mov", 0, 18252, "A010C001_130101_R5DJ.mov", 0),
    ("B012C001_130101_R1IB.mov", 0, 14588, "A010C002_130101_R5DJ.mov", 6),
    ("B013C001_130101_R1IB.mov", 748, 21659, "A011C001_130101_R5DJ.mov", 1),
    ("B013C001_130101_R1IB.mov", 21329, 36417, "A011C001_130101_R5DJ.mov", 1),
    ("B014C001_130101_R1IB.mov", 0, 7155, "A012C001_130101_R5DJ.mov", 1),
    ("B014C002_130101_R1IB.mov", 0, 12855, "A012C002_130101_R5DJ.mov", -1),
    ("B014C002_130101_R1IB.mov", 12960, 47486, "A012C002_130101_R5DJ.mov", -1),
    ("B015C001_130101_R1IB.mov", 1348, 8521, "A013C001_120101_R5DJ.mov", -3),
    ("B015C001_130101_R1IB.mov", 8625, 32515, "A013C001_120101_R5DJ.mov", 1),
    ("B015C002_130101_R1IB.mov", 220, 33732, "A014C001_120101_R5DJ.mov", 0),
    ("B016C001_130101_R1IB.mov", 244, 25278, "A015C001_130101_R5DJ.mov", 1),
    ("B016C001_130101_R1IB.mov", 25388, 29021, "A015C001_130101_R5DJ.mov", 1),
]


def main() -> int:
    computed = parse_v03_offsets(V03)

    print("Computed B→A offset table from pinned v03:\n")
    print(f"{'CAM B':<32} {'B source range':<20} {'CAM A':<32} {'offset':>6}  note")
    print("-" * 100)
    for row in computed:
        note = "" if row.name_matches_file else "NAME≠FILE"
        print(
            f"{row.b_file:<32} {row.b_src_in}–{row.b_src_out:<14} "
            f"{row.a_file:<32} {row.offset:+4d}  {note}"
        )

    print("\nPublished table comparison:\n")
    print(f"{'CAM B':<32} {'B range':<20} {'CAM A':<32} {'pub':>4} {'calc':>4} {'match'}")
    print("-" * 100)

    calc_by_key = {
        (r.b_file, r.b_src_in, r.b_src_out): (r.a_file, r.offset, r.name_matches_file)
        for r in computed
    }

    all_match = True
    for b_file, b_in, b_out, a_file, pub_off in PUBLISHED:
        key = (b_file, b_in, b_out)
        if key not in calc_by_key:
            print(f"{b_file:<32} {b_in}–{b_out:<14} {a_file:<32} {pub_off:+4d}  ----  MISSING")
            all_match = False
            continue
        calc_a, calc_off, name_ok = calc_by_key[key]
        match = calc_off == pub_off and calc_a == a_file
        if not match:
            all_match = False
        flag = "yes" if match else "NO"
        extra = "" if name_ok else " (A name≠file — emit anyway)"
        print(
            f"{b_file:<32} {b_in}–{b_out:<14} {a_file:<32} {pub_off:+4d} {calc_off:+4d}  {flag}{extra}"
        )

    print("\nCamera-prefix gate runs at load_reference_assemblies().")

    if all_match:
        print(
            "\nVERDICT: All 14 rows match — B009→A009C002 offset derives from correct media."
        )
    else:
        print("\nVERDICT: Tables differ — stop before projection code.")

    return 0 if all_match else 1


if __name__ == "__main__":
    sys.exit(main())
