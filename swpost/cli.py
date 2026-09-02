#!/usr/bin/env python3
"""CLI entry point for sw-conform."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from swpost.build import build_conform
from swpost.paths import require_volume
from swpost.prproj import iter_sequences, load_prproj
from swpost.project import ProjectionError


NESTED_PROXY_SEQUENCE = re.compile(r"270p_\d+$")


def cmd_list(project: Path, show_all: bool) -> int:
    root = load_prproj(project)
    sequences = iter_sequences(root)
    if not sequences:
        print("No sequences found.", file=sys.stderr)
        return 1
    if show_all:
        visible = sequences
    else:
        visible = [
            s
            for s in sequences
            if s.proxy_clip_count > 0 and not NESTED_PROXY_SEQUENCE.match(s.name)
        ]
        visible.sort(key=lambda s: (-s.proxy_clip_count, s.name.lower()))
    hidden = len(sequences) - len(visible)
    for seq in visible:
        print(f"{seq.name}\tuid={seq.uid}\tproxy_clips={seq.proxy_clip_count}")
    if hidden and not show_all:
        print(f"({hidden} nested sequences hidden; use --all to show)", file=sys.stderr)
    return 0


def cmd_build(
    project: Path,
    sequence: str,
    out: Path | None,
    cards_from: Path | None,
) -> int:
    try:
        xml_path, md_path, json_path, _payload = build_conform(
            project, sequence, out, cards_from=cards_from
        )
    except ProjectionError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(xml_path)
    print(md_path)
    print(json_path)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sw-conform")
    sub = parser.add_subparsers(dest="command", required=True)

    list_p = sub.add_parser("list", help="List sequences in a .prproj")
    list_p.add_argument("project", type=Path)
    list_p.add_argument(
        "--all",
        action="store_true",
        help="Include nested proxy sequences (e.g. 270p_NNNN) with zero timeline proxy count",
    )

    build_p = sub.add_parser("build", help="Build conform XML from a .prproj")
    build_p.add_argument("project", type=Path)
    build_p.add_argument("--sequence", required=True)
    build_p.add_argument("--out", type=Path, default=None)
    build_p.add_argument(
        "--cards-from",
        type=Path,
        default=None,
        help="Exported Premiere XML to lift Essential Graphics card clipitems from",
    )

    args = parser.parse_args(argv)
    require_volume()

    if not args.project.is_file():
        print(f"Not found: {args.project}", file=sys.stderr)
        return 1

    if args.command == "list":
        return cmd_list(args.project, args.all)

    if args.command == "build":
        return cmd_build(args.project, args.sequence, args.out, args.cards_from)

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
