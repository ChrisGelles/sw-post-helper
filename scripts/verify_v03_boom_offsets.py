#!/usr/bin/env python3
"""Gate: recompute Aug 10 B→boom offsets from pinned v03 sync assembly."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from swpost.assemblies import parse_v03_b_keyed_offsets  # noqa: E402

V03 = REPO / "reference" / "081026-Stringout-Source-v03-cg.xml"

# Published v03 table (recomputed from pinned assembly).
PUBLISHED = [
    ("B009C001_130101_R1IB.mov", 132, 36831, "Dr. Lee Take 01 Boom.wav", -132),
    ("B009C001_130101_R1IB.mov", 36834, 36875, "Dr. Lee Take 02 Boom.wav", -36834),
    ("B010C001_130101_R1IB.mov", 0, 25420, "Dr. Lee Take 02 Boom.wav", 42),
    ("B011C001_130101_R1IB.mov", 81, 1812, "Destiny Take 01 Boom.wav", 335),
    ("B011C001_130101_R1IB.mov", 2031, 18249, "Destiny Take 01 Boom.wav", 226),
    ("B012C001_130101_R1IB.mov", 73, 14585, "Destiny Take 02 Lav.wav", 137),
    ("B013C001_130101_R1IB.mov", 748, 21793, "Caitlin Take 01 Boom.wav", -485),
    ("B013C001_130101_R1IB.mov", 21920, 36416, "Caitlin Take 01 Boom.wav", -593),
    ("B014C001_130101_R1IB.mov", 3, 7155, "Caitlin Take 02 Boom.wav", 70),
    ("B014C002_130101_R1IB.mov", 0, 12855, "Nicole Take 01 Boom.wav", 12),
    ("B014C002_130101_R1IB.mov", 12960, 47486, "Nicole Take 01 Boom.wav", -95),
    ("B015C001_130101_R1IB.mov", 1348, 8521, "Miranda Take 01 Boom.wav", -503),
    ("B015C001_130101_R1IB.mov", 8625, 32515, "Miranda Take 01 Boom.wav", -607),
    ("B015C002_130101_R1IB.mov", 220, 33732, "Miranda Take 02 Boom.wav", 519),
    ("B016C001_130101_R1IB.mov", 244, 25278, "Emma Boom.wav", -244),
    ("B016C001_130101_R1IB.mov", 25388, 29021, "Emma Boom.wav", -353),
]

# Brief expected audio-pass shift (one frame earlier than v02b published lineage).
EXPECTED_AUDIO_PASS_SHIFT = [
    ("B015C001_130101_R1IB.mov", 1348, 8521, "Miranda Take 01 Boom.wav", -504),
    ("B014C002_130101_R1IB.mov", 0, 12855, "Nicole Take 01 Boom.wav", 11),
    ("B014C001_130101_R1IB.mov", 3, 7155, "Caitlin Take 02 Boom.wav", 69),
    ("B016C001_130101_R1IB.mov", 25388, 29021, "Emma Boom.wav", -354),
    ("B013C001_130101_R1IB.mov", 21920, 36416, "Caitlin Take 01 Boom.wav", -594),
    ("B015C002_130101_R1IB.mov", 220, 33732, "Miranda Take 02 Boom.wav", 518),
]


def main() -> int:
    computed = parse_v03_b_keyed_offsets(V03, "BOOM")

    print("Computed B→boom offset table from pinned v03:\n")
    print(f"{'CAM B':<32} {'B source range':<20} {'Boom file':<36} {'offset':>6}  note")
    print("-" * 110)
    for row in computed:
        note = "NOT BOOM (lav on boom track)" if row.is_lav_on_boom_track else ""
        print(
            f"{row.b_file:<32} {row.b_src_in}–{row.b_src_out:<14} "
            f"{row.media_file:<36} {row.offset:+4d}  {note}"
        )

    print("\nPublished v03 table comparison:\n")
    calc_by_key = {
        (r.b_file, r.b_src_in, r.b_src_out): (r.media_file, r.offset)
        for r in computed
    }
    all_match = True
    for b_file, b_in, b_out, boom_file, pub_off in PUBLISHED:
        key = (b_file, b_in, b_out)
        if key not in calc_by_key:
            print(f"{b_file} {b_in}-{b_out} {boom_file} pub={pub_off:+d}  MISSING")
            all_match = False
            continue
        calc_file, calc_off = calc_by_key[key]
        match = calc_off == pub_off and calc_file == boom_file
        if not match:
            all_match = False
            print(
                f"MISMATCH {b_file} {b_in}-{b_out}: pub {boom_file} {pub_off:+d} "
                f"vs calc {calc_file} {calc_off:+d}"
            )
        else:
            print(f"OK {b_file} {b_in}-{b_out} {boom_file} {pub_off:+d}")

    print("\nExpected audio-pass shift check (brief: boom one frame earlier than v02b):\n")
    shift_ok = True
    for b_file, b_in, b_out, boom_file, expected_off in EXPECTED_AUDIO_PASS_SHIFT:
        key = (b_file, b_in, b_out)
        calc_file, calc_off = calc_by_key.get(key, ("?", 0))
        if calc_off != expected_off:
            shift_ok = False
            print(
                f"NOT SHIFTED {b_file} {b_in}-{b_out}: expected {expected_off:+d}, "
                f"got {calc_off:+d} ({calc_file})"
            )
        else:
            print(f"SHIFT OK {b_file} {b_in}-{b_out} {boom_file} {expected_off:+d}")

    if not shift_ok:
        print(
            "\nNOTE: Pinned v03 BOOM track is byte-identical to v02b — "
            "no one-frame audio-pass shift in this export. Published table "
            "matches v02b; boom and lav now agree where brief expected them to differ."
        )

    print("\nVERDICT:", "Tables match" if all_match else "Tables differ — stop")
    if not shift_ok:
        print("AUDIO-PASS SHIFT: not present in pinned v03 — report to Chris.")

    return 0 if all_match else 1


if __name__ == "__main__":
    sys.exit(main())
