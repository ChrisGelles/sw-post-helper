# sw-post-helper

SW_SERIES stringout conform tool — replaces proxy cuts in Premiere projects with original camera and field audio as FCP7 XML.

## Status

- **Milestone 1 complete:** reference assemblies pinned, checksum gate, v02b offset table verified. See `docs/milestone-1-offset-verification.md`.
- Milestones 2–6: not started.

## Setup

Requires Python 3.11+ and `/Volumes/SW_SERIES` symlink (see `docs/SW_SERIES-conform-tool-cursor-brief-v03-cl.md`).

```bash
cd /Users/cgelles/Library/CloudStorage/Dropbox/GitHub/sw-post-helper
python3 -m pytest -q
python3 scripts/verify_v02b_offsets.py
```

## Repo layout

```
swpost/          Python package (in progress)
reference/       Pinned assembly XMLs + checksums.json
docs/            Brief, lineage docs, milestone reports
tests/           Fixtures and regression baselines
scripts/         One-off verification scripts
```
