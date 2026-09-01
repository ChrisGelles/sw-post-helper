# Sherwin Shoot Stringout: source clips to the 270 proxy and `SW-06.2026__stringout_01`

Derived from `CMNH-SW-stringout-ref-270.xml`. This is the assembly that both June renders
came out of, and it is the reference for every episode timeline that cuts against either one.

## Lineage

```
camera proxies + field audio
        |
        v
CMNH-SW_stringout          960x540 - 24 NDF (23.976) - 643326 frames - 07:26:45:06 - starts 00:00:00:00
        |
        +--> SW-06.2026__stringout_01.mp4   960x540   643326 frames   (export of this sequence)
                    |
                    +--> 270p.mp4           480x270   643326 frames   (downscale of the export)
```

All three share one frame count and one frame-zero. A frame number is the same instant in the
sequence, in `SW-06.2026__stringout_01.mp4`, and in `270p.mp4`. No offset anywhere.

`SW-06.2026__stringout_01.mp4` is also laid back into its own sequence on V3 at `start=0, in=0`
with Opacity 66 as a self-check overlay. Its stereo audio sits on A5 and A6, also at frame 0.
That round trip is what proves the frame-zero alignment.

## Transform when referencing a render on a 1920x1080 episode timeline

| Media | Native | Basic Motion scale |
|---|---|---|
| `270p.mp4` | 480x270 | 400 |
| `SW-06.2026__stringout_01.mp4` | 960x540 | 200 |
| June camera proxies (A and B) | 960x540 | 200 |
| Aug 10 camera proxies (A and B) | 1920x1080 | 100 (none) |

On the native 960x540 stringout timeline, `270p.mp4` takes scale 200 instead of 400. The scale
value is an artifact of the proxy size, not of the edit, and it comes off at every conform.

## Track layout

| Track | Contents |
|---|---|
| V3 | `SW-06.2026__stringout_01.mp4`, full length, Opacity 66 |
| V2 | CAM A - the picture that reads in the render |
| V1 | CAM B - covered by V2 everywhere V2 is present |
| A1 | camera embedded audio, source channel 1 |
| A2 | boom |
| A3 | lav |
| A4 | lav internal - June 10 only, partial |
| A5 / A6 | `SW-06.2026__stringout_01.mp4` stereo, source channels 1 and 2 |

Every video and audio track cuts on the same eleven segment boundaries, so one segment is one
take by one person, with picture from both cameras and up to three audio sources stacked
underneath it. A2, A3 and A4 do not share the boom's offset with each other - each recorder ran
on its own clock, so each track carries its own `source_in` per segment.

A1 is not a single camera. It follows A camera on the two 05-27 segments and on 03:52:28:03,
and B camera everywhere else.

## Projection

```
source_frame = stringout_frame - segment_tl_in + segment_source_in
```
Applies unchanged to any of the three renders, since they share frame zero. Frame arithmetic:
`h*86400 + m*1440 + s*24 + fr`, timecode from seconds: `round(seconds * 23.976)`.

## Segment map

Eleven segments. `source_in` is the source frame that lands on the segment's first frame.

| # | Person | Shoot date | Stringout in | Stringout out | CAM A | in | CAM B | in |
|---|---|---|---|---|---|---|---|---|
| 1 | Kiki Redhead | 2026-05-27 | 00:00:00:00 | 00:57:50:15 | `A001_A001_0527UO_001.mov` | 172 | `B001_C001_01308G_001.mov` | 199 |
| 2 | Kiki Redhead | 2026-05-27 | 00:57:50:15 | 01:15:29:20 | `A001_A003_052701_001.mov` | 216 | `B002_C002_01300X_001.mov` | 217 |
| 3 | Jim Leonard | 2026-06-09 | 01:15:29:20 | 02:24:38:12 | `A004C001_260609_R0DH.mov` | 295 | `B001C001_260609_R51N.mov` | 187 |
| 4 | Stacy Conté | 2026-06-09 | 02:24:38:12 | 03:16:16:18 | `A004C002_260609_R0DH.mov` | 848 | `B001C002_260609_R51N.mov` | 726 |
| 5 | Stephanie Castro | 2026-06-09 | 03:16:16:18 | 03:52:28:03 | `A005C001_260609_R0DH.mov` | 292 | `B002C001_260609_R51N.mov` | 153 |
| 6 | Tony Rook | 2026-06-09 | 03:52:28:03 | 04:45:14:21 | `A006C001_260609_R0DH.mov` | 554 | `B002C002_260609_R51N.mov` | 701 |
| 7 | Morgan Sibbald | 2026-06-10 | 04:45:14:21 | 05:55:58:12 | `A007C001_260610_R0DH.mov` | 0 | `B003C001_260610_R51N.mov` | 99 |
| 8 | Tony Rook (redo) | 2026-06-10 | 05:55:58:12 | 06:11:51:04 | `A007C002_260610_R0DH.mov` | 404 | `B003C002_260610_R51N.mov` | 524 |
| 9 | Forrest Blackburn | 2026-06-10 | 06:11:51:04 | 06:50:55:23 | `A007C003_260610_R0DH.mov` | 505 | `B003C003_260610_R51N.mov` | 386 |
| 10 | Forrest Blackburn | 2026-06-10 | 06:50:55:23 | 07:09:42:03 | `A008C001_260610_R0DH.mov` | 647 | `B004C001_260610_R51N.mov` | 299 |
| 11 | Jim Leonard (redo) | 2026-06-10 | 07:09:42:03 | 07:26:45:06 | `A008C002_260610_R0DH.mov` | 115 | `B004C002_260610_R51N.mov` | 0 |

| # | Person | Camera audio (A1) | Boom (A2) | in | Lav (A3) | in | Lav internal (A4) | in |
|---|---|---|---|---|---|---|---|---|
| 1 | Kiki Redhead | `A001_A001_0527UO_001.mov` | `Take 01 - Boom.wav` | 0 | `Take 01 - Lav.wav` | 1 | — | — |
| 2 | Kiki Redhead | `A001_A003_052701_001.mov` | `Take 02 - Boom.wav` | 0 | `Take 02 - Lav.wav` | 0 | — | — |
| 3 | Jim Leonard | `B001C001_260609_R51N.mov` | `B001C001_260609_R51N.mov` | 187 | `Jim Leonard Take 01 Lav.WAV` | 292 | — | — |
| 4 | Stacy Conté | `B001C002_260609_R51N.mov` | `Stacy Contii Take 01 Boom.wav` | 942 | `Stacy Contii Take 01 Lav.wav` | 943 | — | — |
| 5 | Stephanie Castro | `B002C001_260609_R51N.mov` | `Stephanie Castro Take 01 Boom.wav` | 262 | `Stephanie Castro Take 01 Lav.wav` | 262 | — | — |
| 6 | Tony Rook | `A006C001_260609_R0DH.mov` | `Toni Rook Take 01 Boom.wav` | 1176 | `Toni Rook Take 01 Lav.wav` | 1176 | — | — |
| 7 | Morgan Sibbald | `B003C001_260610_R51N.mov` | `Morgan Sibald Take 01 Boom.WAV` | 131 | `Morgan Sibald Take 01 Lav.WAV` | 131 | `20260610_2141_0146_32Float_3JN9.wav` | 103 |
| 8 | Tony Rook (redo) | `B003C002_260610_R51N.mov` | `Toni Rook (Redo) Boom.wav` | 593 | `Toni Rook (Redo) Lav.wav` | 593 | `20260610_2308_0150_32Float_3JN9.wav` | 619 |
| 9 | Forrest Blackburn | `B003C003_260610_R51N.mov` | `Forest Blackburn Take 01 Boom.wav` | 282 | `Forest Blackburn Take 01 Lav.wav` | 282 | `Forest Blackburn Take 01.wav` | 52 |
| 10 | Forrest Blackburn | `B004C001_260610_R51N.mov` | `Forest Blackburn Take 02 Boom.wav` | 421 | `Forest Blackburn Take 02 Lav.wav` | 421 | `Forest Blackburn Take 02.wav` | 21 |
| 11 | Jim Leonard (redo) | `B004C002_260610_R51N.mov` | `Jim Leonard Boom.wav` | 44 | `Jim Leonard Lav.wav` | 44 | `20260611_0221_0156_32Float_3JN9.wav` | 48 |

## Anomalies to carry forward

**Jim Leonard, June 9, has no boom.** On segment 3 the A2 boom track is occupied by
`B001C001_260609_R51N.mov` camera audio at the picture clip's own offset. There is no boom file
for that interview. Lav is `Jim Leonard Take 01 Lav.WAV`.

**B camera restart at 03:52:28:03.** V2 runs one continuous clip `A006C001_260609_R0DH.mov`
across the whole Tony Rook segment. V1 splits: `B002C002_260609_R51N.mov` ends at 04:33:52:06
and `B001C003_260609_R51N.mov` picks up 682 frames later at 04:34:20:16. A camera covers the
hole; there is no B-camera picture for those 28 seconds.

**Lav internal covers June 10 only.** A4 is empty before 04:45:14:21 and has a 397-frame gap
between the two Forrest Blackburn takes. Roughly a third of the shoot.

**Raw audio folder dates are wrong on disk.** Segments 7 through 11 are June 10 material -
camera files read `260610`, the lav-internal filenames read `20260610` - but the field
recordings live under `02_Assets/02_Audio/01_Raw/2026.09.10/`. Bin dates follow the shoot date,
not the folder name. The folder should be `2026.06.10`.

**Name spellings on disk do not match the people.** `Stacy Contii` is Stacy Conté, `Toni Rook`
is Tony Rook, `Morgan Sibald` is Morgan Sibbald, `Forest Blackburn` is Forrest Blackburn.
Paths are left verbatim; bin names use the correct spellings.

**Audio Levels are linear, not dB.** Levels on this timeline read 1, 1.45781 and 3.98109 -
unity, +3.3 dB and +12 dB. Anything written as `Gain(dB)` imports as a linear value and clamps
negative dB to silence, so gain has to be emitted as linear Audio Levels.

## Files

| Role | Path |
|---|---|
| Assembly | `04_Renders/04_Premiere/…` sequence `CMNH-SW_stringout` |
| Export | `/Volumes/SW_SERIES/04_Renders/04_Premiere/SW-06.2026__stringout_01.mp4` |
| Working proxy | `/Volumes/SW_SERIES/04_Renders/04_Premiere/footage/proxy/270p.mp4` |
| Camera proxies | `/Volumes/SW_SERIES/02_Assets/01_Video/01_Footage/PROXIES/<date>/…` |
| Field audio | `/Volumes/SW_SERIES/02_Assets/02_Audio/01_Raw/<date>/<person>/…` |

Transcript for this stringout is `270-full-text.txt`, 2540 blocks, timed to frame 0.
