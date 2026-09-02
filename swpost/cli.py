#!/usr/bin/env python3
"""CLI entry point for sw-conform."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from swpost.paths import require_volume
from swpost.prproj import iter_sequences, load_prproj


def cmd_list(project: Path) -> int:
    root = load_prproj(project)
    sequences = iter_sequences(root)
    if not sequences:
        print("No sequences found.", file=sys.stderr)
        return 1
    for seq in sequences:
        print(f"{seq.name}\tuid={seq.uid}\tproxy_clips={seq.proxy_clip_count}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sw-conform")
    sub = parser.add_subparsers(dest="command", required=True)

    list_p = sub.add_parser("list", help="List sequences in a .prproj")
    list_p.add_argument("project", type=Path)

    build_p = sub.add_parser("build", help="Build conform XML from a .prproj")
    build_p.add_argument("project", type=Path)
    build_p.add_argument("--sequence", required=True)
    build_p.add_argument("--out", type=Path, default=None)

    args = parser.parse_args(argv)
    require_volume()

    if args.command == "list":
        if not args.project.is_file():
            print(f"Not found: {args.project}", file=sys.stderr)
            return 1
        return cmd_list(args.project)

    if args.command == "build":
        print("build: not implemented yet (Milestone 3+)", file=sys.stderr)
        return 2

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
