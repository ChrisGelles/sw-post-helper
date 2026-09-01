# Aug 10 Stringout: source clips to `081026-stringout.mp4`

Companion to `SW_SERIES-sherwin-stringout-270-lineage-v01-cl.md`. Same job, other shoot. The two
shoots do not share a structure, so nothing here carries over from the June side except the
projection formula.

## Lineage
```
camera proxies + field audio
        |
        v
081026 Stringout Source v02       1920x1080 - 24 NDF (23.976) - 279671 frames - 03:14:12:23 - starts 00:00:00:00
        |
        +--> CMNH-081026-stringout_02.mp4   1920x1080   279671 frames
                    |
                    +--> 081026-stringout.mp4          1920x1080   279671 frames   (working copy)
```

**The Aug 10 proxy is not downscaled.** `081026-stringout.mp4` is 1920×1080 and 279671 frames,
identical to the render it came from. It takes **no scale filter** on a 1080 timeline. This is
the opposite of the June side, where `270p.mp4` is 480×270 and needs scale 400. Any episode
timeline carrying a transform on an Aug 10 stringout clip has one it should not have.

The render is laid back into its own sequence on V2 at `start=0, in=0` at Opacity 78. Its stereo
audio sits on A7 and A8, also at frame 0. Frame zero is confirmed by that round trip.

## Scale reference

| Media | Native | Scale on a 1920×1080 timeline |
|---|---|---|
| `081026-stringout.mp4` | 1920×1080 | 100 — none |
| `CMNH-081026-stringout_02.mp4` | 1920×1080 | 100 — none |
| Aug 10 camera proxies, A and B | 1920×1080 | 100 — none |
| `270p.mp4` (June) | 480×270 | 400 |

## Two assemblies, two jobs

| | `081026-Stringout-Source-v02-cg.xml` | `081026-Stringout-Source-v02b-cg.xml` |
|---|---|---|
| Sequence | `B009C001_130101_R1IB` | `081026 Stringout (CAM B incl)` |
| Length | 279671 · 03:14:12:23 | 279045 · 03:13:46:21 |
| Picture | B camera only | V1 A camera, V2 B camera |
| Audio | 6 tracks + render stereo | 13 tracks, both cameras' 5 channels plus boom and lav |
| Use | **source of truth** for the render, the transcript and all stringout arithmetic | **A↔B offsets only** |

The two are 626 frames apart and cut in different places. Nothing derived from v02b may be used
to convert a stringout frame into a source frame. It exists because it carries the A camera and
more field audio than v02 does.

## v02 track layout

| Track | Contents |
|---|---|
| V2 | `CMNH-081026-stringout_02.mp4`, full length, Opacity 78 |
| V1 | B camera — the only picture in the render |
| A1 | B camera embedded, channel 1 |
| A2 | field select — one track, boom or lav depending on the take |
| A3–A6 | B camera embedded, channels 2 through 5 |
| A7 / A8 | render stereo, channels 1 and 2 |

A2 sits between camera channel 1 and channel 2 rather than above or below the camera block. It
is a single mixed track: Chi Lee, Destiny take 02, Caitlin, Nikki, Miranda and Emma are lav;
Destiny take 01 is boom. There is no separate boom track in v02 — v02b has that split, on A3.

## v02b track layout

| Track | Contents |
|---|---|
| V1 | A camera |
| V2 | B camera |
| A1, A6–A9 | B camera embedded, channels 1–5 |
| A2 | lav |
| A3 | boom |
| A10–A14 | A camera embedded, channels 1–5 |

## Projection
```
source_frame = stringout_frame - segment_tl_in + segment_source_in
```
Unchanged from the June side, and it applies to `081026-stringout.mp4` and
`CMNH-081026-stringout_02.mp4` interchangeably. Frame arithmetic: `h*86400 + m*1440 + s*24 + fr`.

A camera is reached in two steps: stringout frame → B source frame through the table below, then
B source frame → A source frame through the offset table after it. There is no direct
stringout-to-A-camera map, because v02 has no A camera in it.

## Segment map — v02, thirteen segments

| # | Person | Take | Stringout in | Stringout out | CAM B | in | Field audio (A2) | in |
|---|---|---|---|---|---|---|---|---|
| 1 | Chi Lee | Take 01 | 00:00:00:00 | 00:25:36:11 | `B009C001_130101_R1IB.mov` | 0 | `Dr. Lee Take 01 Lav.wav` | 0 |
| 2 | Chi Lee | Take 02 | 00:25:36:11 | 00:43:20:06 | `B010C001_130101_R1IB.mov` | 0 | `Dr. Lee Take 02 Lav.wav` | 43 |
| 3 | Destiny Thomas | Take 01 | 00:43:20:06 | 00:56:00:18 | `B011C001_130101_R1IB.mov` | 0 | `Destiny Take 01 Boom.wav` | 2257 |
| 4 | Destiny Thomas | Take 02 | 00:56:00:18 | 01:06:08:14 | `B012C001_130101_R1IB.mov` | 0 | `Destiny Take 02 Lav.wav` | 209 |
| 5 | Caitlin Colleary | Take 01 | 01:06:08:14 | 01:21:11:01 | `B013C001_130101_R1IB.mov` | 0 | `Lav 03 Caitlin Take 01.wav` | 0 |
| 6 | Caitlin Colleary | Take 01 | 01:21:11:01 | 01:31:25:23 | `B013C001_130101_R1IB.mov` | 21659 | `Lav 03 Caitlin Take 01.wav` | 21754 |
| 7 | Caitlin Colleary | Take 02 | 01:31:25:23 | 01:36:24:15 | `B014C001_130101_R1IB.mov` | 0 | `Caitlin Take 02 Lav.wav` | 73 |
| 8 | Nikki Burt | Take 01 | 01:36:24:15 | 01:45:20:06 | `B014C002_130101_R1IB.mov` | 0 | `Nicole Take 01 Lav.wav` | 10 |
| 9 | Nikki Burt | Take 01 | 01:45:20:06 | 02:09:18:21 | `B014C002_130101_R1IB.mov` | 12959 | `Nicole Take 01 Lav.wav` | 12865 |
| 10 | Miranda Sinnott-Armstrong | Take 01 | 02:09:18:21 | 02:30:57:12 | `B015C001_130101_R1IB.mov` | 1348 | `Miranda Take 01 Lav.wav` | 8018 |
| 11 | Miranda Sinnott-Armstrong | Take 02 | 02:30:57:12 | 02:54:13:21 | `B015C002_130101_R1IB.mov` | 220 | `Miranda Take 02 Lav.wav` | 738 |
| 12 | Emma Finestone | — | 02:54:13:21 | 03:11:37:00 | `B016C001_130101_R1IB.mov` | 243 | `Emma Lav.wav` | 0 |
| 13 | Emma Finestone | — | 03:11:37:00 | 03:14:12:23 | `B016C001_130101_R1IB.mov` | 25278 | `Emma Lav.wav` | 25035 |

Ten source files across thirteen segments: `B013C001`, `B014C002` and `B016C001` each appear
twice, split at a lift rather than a camera restart, so their two pieces are continuous in the
source with a gap in the middle.

## B camera → A camera offsets

Read off v02b. `A_source = B_source + offset`, valid only inside the stated B source range.

| CAM B | B source range | CAM A | offset |
|---|---|---|---|
| `B009C001_130101_R1IB.mov` | 0–36875 | `A009C002_130101_R5DJ.mov` | -1 **(see defect 1)** |
| `B010C001_130101_R1IB.mov` | 0–25531 | `A009C003_130101_R5DJ.mov` | -1 |
| `B011C001_130101_R1IB.mov` | 0–18252 | `A010C001_130101_R5DJ.mov` | +0 |
| `B012C001_130101_R1IB.mov` | 0–14588 | `A010C002_130101_R5DJ.mov` | +6 |
| `B013C001_130101_R1IB.mov` | 748–21659 | `A011C001_130101_R5DJ.mov` | +1 |
| `B013C001_130101_R1IB.mov` | 21329–36417 | `A011C001_130101_R5DJ.mov` | +1 |
| `B014C001_130101_R1IB.mov` | 0–7155 | `A012C001_130101_R5DJ.mov` | +1 |
| `B014C002_130101_R1IB.mov` | 0–12855 | `A012C002_130101_R5DJ.mov` | -1 |
| `B014C002_130101_R1IB.mov` | 12960–47486 | `A012C002_130101_R5DJ.mov` | -1 |
| `B015C001_130101_R1IB.mov` | 1348–8521 | `A013C001_120101_R5DJ.mov` | -3 |
| `B015C001_130101_R1IB.mov` | 8625–32515 | `A013C001_120101_R5DJ.mov` | +1 |
| `B015C002_130101_R1IB.mov` | 220–33732 | `A014C001_120101_R5DJ.mov` | +0 |
| `B016C001_130101_R1IB.mov` | 244–25278 | `A015C001_130101_R5DJ.mov` | +1 |
| `B016C001_130101_R1IB.mov` | 25388–29021 | `A015C001_130101_R5DJ.mov` | +1 |

The cameras were effectively frame-locked. Two entries are not one-frame: `B012C001` at +6, and
`B015C001`, which reads −3 below source frame 8521 and +1 above 8625. Those two values cannot
both be right for a pair of continuous recordings — one of the two v02b segments carries a
four-frame error introduced when that sync timeline was recut. Anything cutting Miranda take 01
on A camera below source frame 8521 needs a look.

## Defects in the assemblies

**1 — A009C002 is not linked to A009C002.** In v02b, the first A-camera clipitem is *named*
`A009C002_130101_R5DJ.mov` but its `<file>` points at `B015C002_130101_R1IB.mov`. No file
definition for `A009C002_130101_R5DJ.mov` exists anywhere in the assembly. Six clipitems are
affected — the video item and its five linked audio items. The consequence: the published −1
offset for Chi Lee take 01 was derived from a clipitem pointing at Miranda's take 02 media and
is unverified. Chi Lee take 01 has no trustworthy A-camera pairing until that clip is relinked.

**2 — Caitlin's take 01 lav is the internal pack.** Clipitems named `Caitlin Take 01 Lav.wav`
resolve to `01. Lavalier Internal Packs/Lav 03 Caitlin Take 01.wav`. Four such items in v02, two
in v02b. There is no `Caitlin Take 01 Lav.wav` on the field recorder — only
`Caitlin Take 01 Boom.wav`. The internal pack was substituted and the clip kept the expected
name. Take 02 has both boom and lav as normal.

**3 — Destiny take 02 has a lav on the boom track.** In v02b, A3 is boom throughout except at
Destiny take 02, where `Destiny Take 02 Lav.wav` sits on it. `Destiny Take 02 Boom.wav` is not
in either assembly.

**4 — Miranda's take 01 lav path traverses out of another person's folder.**
`…/03. Catilin/Take 02/../../05. Miranda/Take 01/Miranda Take 01 Lav.wav`. It resolves to the
right file. Normalise it on any regenerated XML rather than writing the traversal through.

**5 — Name spellings.** `03. Catilin` should be Caitlin; `04. Nicole` is Nikki Burt's legal
name; `01. Dr. Lee` is Chi Lee. Paths verbatim, bins spelled correctly.

## Files

| Role | Path |
|---|---|
| Assembly, source of truth | `081026-Stringout-Source-v02-cg.xml` |
| Assembly, offsets only | `081026-Stringout-Source-v02b-cg.xml` |
| Render | `/Volumes/SW_SERIES/04_Renders/04_Premiere/CMNH-081026-stringout_02.mp4` |
| Working copy | `/Volumes/SW_SERIES/04_Renders/04_Premiere/footage/1080p/081026-stringout.mp4` |
| Camera proxies | `/Volumes/SW_SERIES/02_Assets/01_Video/01_Footage/PROXIES/2026-08-10/` — flat, no card or reel folders |
| Field audio | `/Volumes/SW_SERIES/02_Assets/02_Audio/01_Raw/2026.08.10/00. Field Recorder [Boom and Lav]/<person>/<take>/` |
| Lav internal | `…/2026.08.10/01. Lavalier Internal Packs/` |

Transcript for this stringout is `081026-full-text.txt`, 1156 blocks, timed to frame 0.

The uploaded `081026-Stringout-Source-v02-cg.xml` and the copy in the project are byte-different
but timeline-identical: every clipitem on every track matches on file, start, end, in and out.
