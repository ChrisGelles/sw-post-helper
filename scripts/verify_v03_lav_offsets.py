#!/usr/bin/env python3
"""Gate: recompute Aug 10 B→lav offsets from pinned v03 sync assembly."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from swpost.assemblies import parse_v03_b_keyed_offsets  # noqa: E402

V03 = REPO / "reference" / "081026-Stringout-Source-v03-cg.xml"

# Unchanged from v02b — lav track identical between v02b and v03.
PUBLISHED = [
    ("B009C001_130101_R1IB.mov", 132, 36831, "Dr. Lee Take 01 Lav.wav", -132),
    ("B009C001_130101_R1IB.mov", 36834, 36875, "Dr. Lee Take 02 Lav.wav", -36834),
    ("B010C001_130101_R1IB.mov", 0, 25420, "Dr. Lee Take 02 Lav.wav", 42),
    ("B011C001_130101_R1IB.mov", 81, 1812, "Destiny Take 01 Lav.wav", 336),
    ("B011C001_130101_R1IB.mov", 2031, 18249, "Destiny Take 01 Lav.wav", 227),
    ("B012C001_130101_R1IB.mov", 73, 14585, "Destiny Take 02 Lav.wav", 136),
    ("B013C001_130101_R1IB.mov", 748, 36417, "Lav 03 Caitlin Take 01.wav", -748),
    ("B014C001_130101_R1IB.mov", 3, 7155, "Caitlin Take 02 Lav.wav", 70),
    ("B014C002_130101_R1IB.mov", 0, 12855, "Nicole Take 01 Lav.wav", 12),
    ("B014C002_130101_R1IB.mov", 12960, 47486, "Nicole Take 01 Lav.wav", -95),
    ("B015C001_130101_R1IB.mov", 1348, 8521, "Miranda Take 01 Lav.wav", -503),
    ("B015C001_130101_R1IB.mov", 8625, 32515, "Miranda Take 01 Lav.wav", -607),
    ("B015C002_130101_R1IB.mov", 220, 33732, "Miranda Take 02 Lav.wav", 519),
    ("B016C001_130101_R1IB.mov", 244, 25278, "Emma Lav.wav", -244),
    ("B016C001_130101_R1IB.mov", 25388, 29021, "Emma Lav.wav", -353),
]


def main() -> int:
    computed = parse_v03_b_keyed_offsets(V03, "LAV")

    print("Computed B→lav offset table from pinned v03:\n")
    print(f"{'CAM B':<32} {'B source range':<20} {'Lav file':<36} {'offset':>6}  note")
    print("-" * 110)
    for row in computed:
        note = ""
        if row.media_file == "Lav 03 Caitlin Take 01.wav":
            note = "internal pack (subclip name: Caitlin Take 01 Lav.wav)"
        print(
            f"{row.b_file:<32} {row.b_src_in}–{row.b_src_out:<14} "
            f"{row.media_file:<36} {row.offset:+4d}  {note}"
        )

    print("\nPublished table comparison (unchanged from v02b):\n")
    calc_by_key = {
        (r.b_file, r.b_src_in, r.b_src_out): (r.media_file, r.offset)
        for r in computed
    }
    all_match = True
    for b_file, b_in, b_out, lav_file, pub_off in PUBLISHED:
        key = (b_file, b_in, b_out)
        if key not in calc_by_key:
            print(f"{b_file} {b_in}-{b_out} {lav_file} pub={pub_off:+d}  MISSING")
            all_match = False
            continue
        calc_file, calc_off = calc_by_key[key]
        match = calc_off == pub_off and calc_file == lav_file
        if not match:
            all_match = False
            print(
                f"MISMATCH {b_file} {b_in}-{b_out}: pub {lav_file} {pub_off:+d} "
                f"vs calc {calc_file} {calc_off:+d}"
            )
        else:
            print(f"OK {b_file} {b_in}-{b_out} {lav_file} {pub_off:+d}")

    print("\nVERDICT:", "Tables match" if all_match else "Tables differ — stop")
    return 0 if all_match else 1


if __name__ == "__main__":
    sys.exit(main())
