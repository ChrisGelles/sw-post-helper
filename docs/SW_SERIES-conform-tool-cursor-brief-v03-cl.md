# Cursor brief — `sw-post-helper` / stringout conform tool, v3

Supersedes v02. Rewritten against `SW_SERIES-volume-recon-v01.md`, 2026-09-01. Every path in
this document was confirmed on disk unless marked otherwise.

```
Repo    /Users/cgelles/Library/CloudStorage/Dropbox/GitHub/sw-post-helper
Remote  https://github.com/ChrisGelles/sw-post-helper.git
Python  3.11.4 at /usr/local/bin/python3
Media   /Volumes/SW_SERIES/
```

Build a tool that takes a Premiere project cut against a stringout proxy and returns an FCP7
XML in which the original camera and field audio sit where the proxy was, paths point at
`/Volumes/SW_SERIES/`, non-source elements arrive offline at conventional locations, and the
project window is organised to our conventions.

---

## Read this before writing any path code

`/Volumes/SW_SERIES` is a **symlink** owned by `root:wheel` pointing at
`/Users/cgelles/Library/CloudStorage/Dropbox/SW_SERIES`. Each remote worker creates their own.
It is the shared address every project file and every generated XML must use.

Consequences, all mandatory:

- **Never call `os.path.realpath`, `Path.resolve()`, or `os.path.abspath` on a media path.**
  Any of them rewrites `/Volumes/SW_SERIES/…` into `/Users/cgelles/Library/CloudStorage/…`,
  which poisons every `pathurl` in the output and breaks the file for everyone else. Use
  `os.path.normpath` only — it collapses `..` without touching symlinks.
- `os.path.exists` and `open()` follow the symlink and work normally. Existence checks are fine.
- On startup, verify `/Volumes/SW_SERIES` exists and is a symlink or mount. If not, exit with
  a message telling the user to create it. Do not fall back to the Dropbox path.
- Add a unit test that asserts no output `pathurl` contains `CloudStorage`, `Macintosh`,
  `Dropbox`, or `..`.

Sampled media reads clean — no online-only placeholder behaviour on this machine — but the
scan was not exhaustive. Treat a failed read as a warning in the report, never as a hard stop.

---

## Repo layout

```
sw-post-helper/
  swpost/
    prproj.py         .prproj reader
    assemblies.py     reference assembly parser, interval maps
    project.py        projection engine
    paths.py          canonicalisation + asset destinations
    fcpxml.py         xmeml writer
    report.py         markdown + json report
    cli.py            argparse entry point
    web.py            localhost wrapper
  reference/          pinned assembly XMLs + checksums.json
  docs/               this brief, two lineage docs, one worked example
  tests/
    STEM-ep04-v03-cc.prproj
    baseline/         empty until milestone 5
  sw-conform.command
```

---

## Confirmed constants

Write these into `swpost/paths.py` with a comment naming the recon date.

**Proxy registry.** Match on basename, case-sensitive.

| Basename | Path under `/Volumes/SW_SERIES/` | Shoot | Native | Scale on 1080 |
|---|---|---|---|---|
| `270p.mp4` | `04_Renders/04_Premiere/footage/proxy/270p.mp4` | june | 480×270 | 400 |
| `SW-06.2026__stringout_01.mp4` | `04_Renders/04_Premiere/SW-06.2026__stringout_01.mp4` | june | 960×540 | 200 |
| `081026-stringout.mp4` | `04_Renders/04_Premiere/footage/1080p/081026-stringout.mp4` | aug10 | 1920×1080 | none |
| `CMNH-081026-stringout_02.mp4` | `04_Renders/04_Premiere/CMNH-081026-stringout_02.mp4` | aug10 | 1920×1080 | none |

All four are 24 NDF, start at frame 0, and share frame zero with their assembly. A frame
number is the same instant in the proxy, in the render, and in the sequence. No offset between
them.

**Camera proxies.** `02_Assets/01_Video/01_Footage/PROXIES/<YYYY-MM-DD>/`
Dates: `2026-05-27`, `2026-06-09`, `2026-06-10`, `2026-08-10`.
June dates nest `<CAM>-<n>/<REEL>/Proxy/<file>.mov` and carry stray `.ale` and `.bin`
sidecars. August 10 is flat — `.mov` files at the date-folder root. Do not assume one shape.

**Raw audio.** `02_Assets/02_Audio/01_Raw/<YYYY.MM.DD>/`
Dates on disk: `2026.05.27`, `2026.06.09`, `2026.08.10`, `2026.09.10`.
`2026.09.10` contains **June 10** material — the lav-internal filenames read `20260610`. The
folder name is wrong and is not being renamed. Bin dates come from the segment's shoot date,
never from the folder name.

**Asset destinations for offline passthrough.**

| Kind | Folder | Observed contents |
|---|---|---|
| VO pickups | `02_Assets/02_Audio/04_VO/temp VO/` | one `.wav`, `Ep02-Ep09-Joey-Temp-VO-esv2-30p-bg-m-music-10p.wav` |
| Concept art | `02_Assets/03_Images/_ConceptArt/` | `.png`, named `<n>.<n>.<n>.png` |
| Animation | `02_Assets/04_Graphics/03_Animation/` | empty — assume `.mov` |
| Narration cards | — | no folder exists, and none is wanted |

The VO folder holds one omnibus file covering episodes 2 through 9, not per-pickup files.
Offline VO clipitems point at that folder; the editor relinks by hand. Do not try to construct
a per-pickup filename.

**Project files.** Episode projects: `01_ProjectFiles/04_Premiere/_Episodes/<episode-folder>/`,
folders named `ep01-humans&color`, `ep02-physics`, `ep03`, `ep04-photosynthesis`,
`ep05-structural-color`, `ep06` … `ep09`, plus `all` and `series`. Note the `&` in the ep01
folder name — quote paths everywhere.

**Output.** Create `01_ProjectFiles/05_XMLs/_conform/` on first run. Conform XMLs and reports
go there, not next to the input project.

---

## The division that governs every decision

**Source clips reconnect by arithmetic and must be frame-exact.** If an offset cannot be
established, fail loudly and name the clip. Never guess, never substitute adjacent media,
never round.

**Everything else reconnects by convention and may arrive offline.** A wrong folder guess
costs one relink. A wrong offset costs a silent sync error nobody catches until the mix.

---

## Milestone 1 — pin the reference assemblies, and verify them

Copy these three from `01_ProjectFiles/05_XMLs/_stringout-source/` into `reference/`:

| File | On-disk SHA-256 |
|---|---|
| `CMNH-SW-stringout-ref-270.xml` | `5b3d6a6906833ec69389baa2d38aaa10e38502ecb85e3f589962e16c4f37e863` |
| `081026-Stringout-Source-v02-cg.xml` | `46d1bf651f336e3fd9d4d98e8e120191a92d7493f9726cf59011824a324d9338` |
| `081026-Stringout-Source-v02b-cg.xml` | `b55e19c95cb164b963236ef1ca19af46cd8917c1e32882a6ea54268455d647f6` |

Record them in `reference/checksums.json`. The tool verifies on every run and refuses to
proceed on a mismatch, printing both digests.

Do **not** pin `_old/SW-Shoot-Stringout-Source-v03-cg.xml`. It is the same June assembly as
`CMNH-SW-stringout-ref-270.xml` — identical sequence UUID, identical clip data on all nine
tracks, differing only in internal id numbering and one track-enable flag. Pinning both would
create two sources of truth for the same offsets.

**Verification gate, and it is not optional.** The lineage documents were written against a
copy of `081026-Stringout-Source-v02b-cg.xml` with digest
`a712aeb7e83b0a354597049f26adb4469971d32eb290210479fc172c457d5442`. The file on disk is
`b55e19c9…`. **It is a different file.** Every Aug 10 A-camera offset in
`SW_SERIES-081026-stringout-lineage-v01-cl.md` came from the other copy.

Before writing any projection code, write a throwaway script that recomputes the B→A offset
table from the on-disk v02b and prints it beside the published table:

| CAM B | B source range | CAM A | offset |
|---|---|---|---|
| `B009C001_130101_R1IB.mov` | 0–36875 | `A009C002_130101_R5DJ.mov` | −1 |
| `B010C001_130101_R1IB.mov` | 0–25531 | `A009C003_130101_R5DJ.mov` | −1 |
| `B011C001_130101_R1IB.mov` | 0–18252 | `A010C001_130101_R5DJ.mov` | +0 |
| `B012C001_130101_R1IB.mov` | 0–14588 | `A010C002_130101_R5DJ.mov` | +6 |
| `B013C001_130101_R1IB.mov` | 748–21659 | `A011C001_130101_R5DJ.mov` | +1 |
| `B013C001_130101_R1IB.mov` | 21329–36417 | `A011C001_130101_R5DJ.mov` | +1 |
| `B014C001_130101_R1IB.mov` | 0–7155 | `A012C001_130101_R5DJ.mov` | +1 |
| `B014C002_130101_R1IB.mov` | 0–12855 | `A012C002_130101_R5DJ.mov` | −1 |
| `B014C002_130101_R1IB.mov` | 12960–47486 | `A012C002_130101_R5DJ.mov` | −1 |
| `B015C001_130101_R1IB.mov` | 1348–8521 | `A013C001_120101_R5DJ.mov` | −3 |
| `B015C001_130101_R1IB.mov` | 8625–32515 | `A013C001_120101_R5DJ.mov` | +1 |
| `B015C002_130101_R1IB.mov` | 220–33732 | `A014C001_120101_R5DJ.mov` | +0 |
| `B016C001_130101_R1IB.mov` | 244–25278 | `A015C001_130101_R5DJ.mov` | +1 |
| `B016C001_130101_R1IB.mov` | 25388–29021 | `A015C001_130101_R5DJ.mov` | +1 |

Also check whether the on-disk v02b still has the `A009C002` link defect: the clipitem *named*
`A009C002_130101_R5DJ.mov` resolving to a `<file>` whose basename is
`B015C002_130101_R1IB.mov`, with no file definition for `A009C002` anywhere in the document.

Report which of the two situations you are in:

- **Tables match and the defect is present** — the on-disk file is a re-export of the same
  edit. Proceed, keep the defect branch in milestone 3.
- **Tables match and the defect is gone** — someone relinked it. Excellent. Note that Chi Lee
  take 01's offset is now trustworthy, and say so in the report.
- **Tables differ anywhere** — stop and report the differences before writing anything else.
  A changed offset means the sync edit moved, and every downstream number is suspect.

`A009C002_130101_R5DJ.mov` **does exist** at
`02_Assets/01_Video/01_Footage/PROXIES/2026-08-10/A009C002_130101_R5DJ.mov`, 1,000,489,688
bytes, readable. So if the defect is still present, it is a broken link in the assembly and
not missing media — a one-clip relink in Premiere and a re-export would retire the defect
branch permanently. Flag that as a recommendation; do not attempt to patch the XML yourself.

**Check:** `checksums.json` written; a one-byte edit to a reference file makes the tool refuse
to run; the offset comparison is printed and its verdict recorded in `docs/`.

---

## Milestone 2 — read a `.prproj`

A `.prproj` is gzipped XML. `gzip.open(path).read()`, parse with `xml.etree.ElementTree`.

**Object model.** Referenceable objects carry `ObjectID` + `ClassID`, or `ObjectUID` +
`ClassID`. References are `<Tag ObjectRef="N"/>` and `<Tag ObjectURef="uuid"/>`.

`ObjectID` is unique per `ClassID`, not per file — low IDs (roughly 1 through 10) appear on two
different classes. Index every element carrying both `ObjectID` and `ClassID` into id → list,
and resolve by taking the entry whose tag matches what the caller expects. Do not index
elements lacking `ClassID`; those are inline structure.

**Sequences.** `<Sequence ObjectUID="…" ClassID="6a15d903-8739-11d5-af2d-9b7855ad8974">`, with
a `<Name>` child and a `<TrackGroups>` block mapping a media-type GUID to a track group:

```
228cda18-3625-4d2d-951e-348879e4ed93   video
80b8e3d5-6dca-4195-aefb-cb5f407ab009   audio
d8143ffe-eec4-4d2a-a909-d5f7bf094dc5   data
```

Follow `<Second ObjectRef="N"/>` to the `VideoTrackGroup` or `AudioTrackGroup`. Do not assume
one sequence per project, and do not assume the first `VideoTrackGroup` in the document belongs
to the sequence the user picked. This is the likeliest place to get a plausible wrong answer,
and the `_Episodes` folders hold up to fourteen projects each.

**Tracks.** A track group holds `<Track Index="N" ObjectURef="uuid"/>`; resolve to a
`VideoClipTrack` or `AudioClipTrack`. `MZ.TrackName` is the display name. `<TrackItems>` holds
`<TrackItem Index="N" ObjectRef="N"/>` in order.

**Clips.**

```
item -> TrackItem/Start, TrackItem/End       timeline position, ticks
item -> SubClip ObjectRef -> Name            editor's label
                          -> Clip ObjectRef
clip -> InPoint, OutPoint                    source position, ticks
clip -> Source ObjectRef -> Stream ObjectRef -> Media ObjectURef -> FilePath
```

Some items carry `Clip` directly with no `SubClip`. Handle both.

**Ticks.** `TICKS_PER_FRAME = 10594584000` at 23.976. `frames = round(ticks / TICKS_PER_FRAME)`.
Everything in this series is a 24 NDF integer timebase over 23.976 media. Missing `<Start>`
means frame 0.

**Check:** `sw-conform list tests/STEM-ep04-v03-cc.prproj` prints one sequence with its name,
UID, and a count of proxy-referencing clips. On a multi-sequence project it prints all of them.

---

## Milestone 3 — projection

**Reference maps.** Parse each assembly into per-track interval lists:
`(file_basename, file_path, tl_in, tl_out, source_in, source_out, sourcetrack_index)`. Build
the `<file id>` → definition map in a first pass over the whole document before reading any
track — the first appearance carries the full definition, later ones are bare
`<file id="…"/>` references.

Track roles, hard-coded. Do not infer from track names; the assemblies do not carry them.

| Role | june — `CMNH-SW-stringout-ref-270.xml` | aug10 — `081026-Stringout-Source-v02-cg.xml` |
|---|---|---|
| CAM_B | V1 | V1 |
| CAM_A | V2 | *not present* |
| BOOM | A2 | *not present* |
| LAV | A3 | A2 |
| LAV_INT | A4 | *not present* |

**Formula.**

```
source_frame = stringout_frame - segment_tl_in + segment_source_in
```

A cut clip covers a stringout range `[in, out)`. Intersect with the role's interval list; each
overlap is one output clip. One cut clip does not yield one output clip — cuts straddle segment
boundaries, and each audio role splits in different places than picture does.

```
piece_tl_start = cut_timeline_start + (overlap_start - cut_in)
piece_tl_end   = cut_timeline_start + (overlap_end   - cut_in)
piece_src_in   = interval.source_in + (overlap_start - interval.tl_in)
piece_src_out  = interval.source_in + (overlap_end   - interval.tl_in)
```

A role legitimately produces nothing over a range — lav-internal does not exist before June 10,
and the Aug 10 shoot has no separate boom track. Emit nothing, note the range in the report.

**Aug 10 A camera is a two-step lookup.** The v02 assembly has no A camera in it.

```
A_source_frame = B_source_frame + offset
```

Look the offset up by the B source range the piece falls in, using the table verified in
milestone 1. Offsets are per range, not per file — `B015C001` reads −3 below source frame 8521
and +1 above 8625. If a piece straddles two ranges with different offsets, split it and warn.

If the `A009C002` defect survived into the pinned v02b: detect it generically by comparing every
clipitem's `<name>` against its resolved file basename, and where they disagree, build no offset
entry. Emit the B-camera piece, skip the A-camera piece, name it in the report. Never substitute
the wrong media.

**Check:** on the ep04 fixture the first V1 clip projects to `A007C001_260610_R0DH.mov`
53237–53357 and `B003C001_260610_R51N.mov` 53336–53456. Every projected clip resolves to a
single source file and a single person. Verify by hand against two or three select labels: a
label such as `MORGAN 05:20:05:12` converts to frame `5*86400 + 20*1440 + 5*24 + 12` and must
land inside the clip carrying it.

---

## Milestone 4 — paths, offline passthrough, and the XML

### Canonicalisation

```python
def canon(path):
    path = urllib.parse.unquote(path).replace('file://localhost', '')
    path = os.path.normpath(path)          # collapses ../ — does NOT resolve symlinks
    i = path.find('SW_SERIES/')
    if i < 0:
        raise ValueError(f'path is not under SW_SERIES: {path}')
    return '/Volumes/SW_SERIES/' + path[i + len('SW_SERIES/'):]
```

Forms you will encounter, all the same volume:

```
/Volumes/Macintosh HD/Users/cgelles/Dropbox/SW_SERIES/…
/Users/cgelles/Library/CloudStorage/Dropbox/SW_SERIES/…
/Users/cgelles/CMNH Dropbox/Chris Gelles/SW_SERIES/…
/Volumes/Macintosh HD/Users/ccalder/CMNH Dropbox/Clover Calder/…
```

The last is Clover's mount and contains no `SW_SERIES/` element. It appears in
`MediaFileHistory` fields, which you are not reading. If it turns up in a `FilePath`, raise.

At least one Aug 10 audio path traverses out of another person's folder —
`…/03. Catilin/Take 02/../../05. Miranda/Take 01/Miranda Take 01 Lav.wav`. `normpath` handles
it; write the resolved form, never the traversal.

For `pathurl`, percent-encode with `urllib.parse.quote` and prefix `file://localhost`.
Absolute only — relative paths do not resolve on Premiere import.

### Offline passthrough

Clips referencing no known proxy are still part of the cut. Emit them with original timeline
position, duration and name, pointing at an absolute path that need not exist.

Classify by what the input tells you:

- **Real files already on the volume** — canonicalise and carry through. No guessing needed.
- **Premiere synthetic media** — numeric `FilePath` such as `1196574294`, with `Title` of
  `Graphic` or `SyntheticTranscript`. Essential Graphics, no FCP7 XML form. The ep04 cut holds
  a full track of narration cards and two `VO PICKUP` clips on this media.

Route synthetic media by clip name:

| Name contains | Destination |
|---|---|
| `VO PICKUP` | `02_Assets/02_Audio/04_VO/temp VO/` |
| `ANIM` | `02_Assets/04_Graphics/03_Animation/` |
| `NARRATOR` or `CARD` | `02_Assets/04_Graphics/` |
| anything else | `02_Assets/03_Images/_ConceptArt/` |

Narration cards are expected to stay offline permanently — there is no destination folder and
none is wanted. What matters is that their timeline position, duration and name survive the
round trip so the editor's card layout is not lost. Say so plainly in the report rather than
listing them as failures.

Filename: sanitise the clip name to a filesystem-safe string, append `.wav` for VO, `.mov` for
animation, `.png` for concept art and cards.

Put these on their own tracks above the camera tracks. Never interleaved with source.

### The XML

`xmeml` version 4:

```
<xmeml version="4">
  <project>
    <name>…</name>
    <children>
      <bin><name>Footage</name>…</bin>
      <bin><name>Audio</name>…</bin>
      <bin><name>Graphics</name>…</bin>
      <bin><name>Seq</name><children><sequence>…</sequence></children></bin>
    </children>
  </project>
</xmeml>
```

Bins come before the sequence so file definitions are in scope when it references them.

**Bin conventions — not negotiable.**

```
Footage  / <YYYY-MM-DD> / CAM A | CAM B
Audio    / <YYYY-MM-DD> / <Person>
Graphics
Seq
```

Date is the **shoot date**, read from the `PROXIES/<YYYY-MM-DD>/` element of the camera path.
Audio inherits the shoot date of the segment it was synced to, never the date in its own folder
name. `CAM A` if the basename starts with `A`, `CAM B` if `B`.

Person bins use correct spellings; filenames and paths stay verbatim.

| On disk | Bin name |
|---|---|
| `Stacy Contii` | Stacy Conté |
| `Toni Rook` | Tony Rook |
| `Morgan Sibald` | Morgan Sibbald |
| `Forest Blackburn` | Forrest Blackburn |
| `03. Catilin` / `Caitlin` | Caitlin Colleary |
| `04. Nicole` | Nikki Burt |
| `01. Dr. Lee` | Chi Lee |
| `05. Miranda` | Miranda Sinnott-Armstrong |
| `02. Destiny` | Destiny Thomas |
| `06. Emma` | Emma Finestone |
| `Jim Leonard` | Jim Leonard |
| `Stephanie Castro` | Stephanie Castro |
| `Take 01` / `Take 02` under `2026.05.27` | Kiki Redhead |

Lav-internal files named `20260610_2141_0146_32Float_3JN9.wav` and
`Lav 03 Caitlin Take 01.wav` carry no reliable person in the name. Assign by the segment they
were synced to, not by parsing the filename.

**Master clips.** One `<clip>` per distinct source file, inside its bin, carrying
`<masterclipid>` equal to its own id, `<ismasterclip>TRUE</ismasterclip>`, duration, rate, name,
and a `<media>` block with one video track clipitem (if the file has picture) and one audio
track clipitem per channel. The full `<file>` definition lives inside the master clip's first
clipitem; sequence clipitems reference `<file id="…"/>` only.

Derive ids from the filename so they are identical across runs and across episodes:

```
masterclip-<basename without extension, non-alphanumerics replaced with ->
file-<same>
```

**This is the one thing that must never drift.** Transcripts live on master clips. If two
episodes emit different `masterclipid` strings for the same media, Premiere mints duplicate
master clips and every transcript has to be regenerated. Same for `pathurl` — byte-identical
across all episodes and versions.

**Sequence clipitem `<name>` is the source filename.** Not the select label, not the subclip
name. The project window shows original file names.

Every clipitem needs a unique `id`, namespaced `<seqprefix>-<role>-<index>`. Duplicate `id`
attributes cause a silent import failure with no error message.

Every clipitem needs `<masterclipid>`. An unbound timeline clipitem makes Premiere mint a fresh
master clip on import, which is what bloats the project window.

**Tracks**, bottom to top:

| Track | `MZ.TrackName` | Contents |
|---|---|---|
| V1 | `V1-CAM-B` | B camera |
| V2 | `V2-CAM-A` | A camera |
| V3 | `V3-CARDS` | offline graphics |
| A1 | `A1-BOOM` | boom |
| A2 | `A2-LAV` | lav |
| A3 | `A3-LAV-INTERNAL` | lav internal |
| A4 | `A4-VO` | offline VO |

**Enable rule.** A-camera clips import enabled only where A camera was the picture that read in
the stringout. The June assembly lays A over B, so June A-camera clips are enabled. The Aug 10
assembly has B alone, so Aug 10 A-camera clips import `<enabled>FALSE</enabled>` and B reads
through from V1. The editor toggles to flip cameras.

**Scale.** Basic Motion scale derived from the *source file's* native size against the output
sequence size, never from what the input project carried. 960×540 on a 1080 sequence gets 200.
1920×1080 gets nothing. Drop the input's `scale=400` — it belonged to the 270p proxy, which is
no longer in the timeline.

**Labels.** `<labels><label2>ColorName</label2></labels>` in every clipitem, one colour per
person across all their clips. Premiere's names: Violet, Iris, Caribbean, Lavender, Cerulean,
Forest, Rose, Mango.

**Audio clipitems** need
`<sourcetrack><mediatype>audio</mediatype><trackindex>N</trackindex></sourcetrack>`. Field
recordings are mono, index 1.

**Gain.** v1 carries no levels. If a level is ever carried, write it as a linear `Audio Levels`
value, never `Gain(dB)` — Premiere imports a `Gain(dB)` filter as a linear value and clamps
negative dB to silence. This has already cost one silent-audio debugging session.

**Check:** output parses. Every referenced `<file>` defined exactly once. No duplicate clipitem
ids. No dangling `masterclipid`. Per track: no overlaps, `end - start == out - in` for every
clip, no clip whose `out` exceeds its source file's duration. And the symlink test — no
`pathurl` containing `CloudStorage`, `Macintosh`, `Dropbox`, or `..`.

---

## Milestone 5 — report, and establishing the baseline

Alongside the XML, write a `.md` and a `.json` sidecar into
`01_ProjectFiles/05_XMLs/_conform/`. The markdown lists:

- input project path, sequence name and UID, reference checksums used
- clip counts per role
- every offline clipitem, with the path it will relink from, and a plain statement that
  narration cards are expected to remain offline
- every A-camera piece dropped for the `A009C002` defect, if it survived the pin
- every piece that straddled an offset change, with both values
- every role that produced nothing over a range, with the range
- any media file that failed a read check
- the full clip map: role, timeline in/out as timecode, source file, source in/out

Timecode from frames: `h = f//86400, m = (f%86400)//1440, s = (f%1440)//24, fr = f%24`.

`tests/baseline/` starts **empty**. Run the tool on the ep04 fixture, open the output in
Premiere, confirm by eye that the cuts land where they should and the source clips show the
right people. Only then copy the XML and JSON into `tests/baseline/`. From that point the
regression test is a diff of the JSON sidecar against the baseline, and any change in source
in-points, master clip ids or path strings is a failure until a human overrides it.

Do not seed the baseline from anything you were handed. It comes from a run that was verified.

---

## Milestone 6 — the face

`sw-conform.command` at the repo root, `chmod +x`, double-clickable from Finder. It starts a
local HTTP server on a free port, opens the browser, and serves one page:

1. file picker for a `.prproj`, defaulting to `01_ProjectFiles/04_Premiere/_Episodes/`
2. dropdown of the sequences found in it
3. Build button
4. the report rendered on the page, with the two output paths shown

Standard library only for the server — no framework, no packaging, no code signing. A signed
`.app` is weeks of process for no gain before the November 30 cutoff.

The CLI stays the real interface and must work without the web layer:

```
sw-conform list  <project.prproj>
sw-conform build <project.prproj> --sequence <name-or-uid> [--out <path.xml>]
```

`build` refuses to run without `--sequence`. If the name matches more than one sequence, it
prints the matches and exits non-zero rather than picking one. `--out` defaults to
`01_ProjectFiles/05_XMLs/_conform/`.

---

## Naming

```
STEM-ep{NN}-conform-v{NN}-cl.xml
SW_SERIES-ep{NN}-source-conform-v{NN}-cl.md
```

Hyphens throughout, no underscores or spaces, version zero-padded to two digits. Derive the
episode number from the input project's parent folder name under `_Episodes/`; if it cannot be
derived, require it as a flag rather than guessing.

---

## Ask before proceeding if

- the milestone 1 offset comparison shows any difference from the published table
- a `.prproj` contains a sequence cutting against a proxy not in the registry
- a projected clip resolves to two different people
- any source file referenced by the projection is missing from the volume
