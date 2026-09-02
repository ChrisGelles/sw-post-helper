# sw-post-helper

SW_SERIES stringout conform tool — replaces proxy cuts in Premiere projects with original camera and field audio as FCP7 XML.

## Status

- **Milestone 1 complete:** reference assemblies pinned, checksum gate, v03 offset tables verified. See `docs/milestone-1-offset-verification.md`.
- **Milestone 2 complete:** `.prproj` reader and `sw-conform list`. Test fixture: `tests/STEM-ep02-v01-cg.prproj`.
- **Milestone 3 complete:** projection engine (ep02-tested). Aug 10 boom/lav via B-keyed v03 tables (gates verified; no Aug 10 fixture cut yet). See `docs/milestone-3-projection.md`.
- Milestones 4–6: not started.

## Setup

Requires Python 3.11+ and `/Volumes/SW_SERIES` symlink (see `docs/SW_SERIES-conform-tool-cursor-brief-v03-cl.md`).

```bash
cd /Users/cgelles/Library/CloudStorage/Dropbox/GitHub/sw-post-helper
python3 -m pytest -q
python3 scripts/verify_v03_offsets.py
python3 scripts/verify_v03_boom_offsets.py
python3 scripts/verify_v03_lav_offsets.py
./sw-conform list tests/STEM-ep02-v01-cg.prproj
```

## Repo layout

```
swpost/          Python package (in progress)
reference/       Pinned assembly XMLs + checksums.json
docs/            Brief, lineage docs, milestone reports
tests/           Fixtures and regression baselines
scripts/         One-off verification scripts
```
