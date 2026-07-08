"""Command-line interface for r6bans.

Usage:
    r6-bans <match-folder | round.rec> [--json] [--db path]

Bans are collected from every round and kept with the team that made them.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

from . import __version__
from .extractor import RoundBans, extract_match_bans, round_number, team_names
from .operators import load_db


def _resolve_recs(target: str) -> tuple[list[str], str]:
    """Return (sorted rec paths, a reference rec for header lookups)."""
    if os.path.isfile(target):
        return [target], target
    if os.path.isdir(target):
        recs = sorted(glob.glob(os.path.join(target, "*.rec")), key=round_number)
        if not recs:
            raise FileNotFoundError(f"no .rec files found in {target}")
        return recs, recs[0]
    raise FileNotFoundError(f"path not found: {target}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="r6-bans",
        description="Extract Rainbow Six Siege operator bans, per round and per team, "
        "from a .rec replay.",
        epilog="Pass a match folder to collect bans across all rounds (recommended), "
        "or a single .rec for just that round.",
    )
    p.add_argument("path", help="a match folder or a single .rec round file")
    p.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    p.add_argument(
        "--db",
        metavar="FILE",
        default=None,
        help="path to an operators json (overrides bundled DB / R6BANS_DB)",
    )
    p.add_argument("-v", "--version", action="version", version=f"r6-bans {__version__}")
    return p


def _team_line(rb: RoundBans, team: int, names: tuple[str, str]) -> str | None:
    ops = [b for b in rb.bans if b.team == team]
    if not ops:
        return None
    label = names[team] if team in (0, 1) else f"Team {team + 1}"
    ops_str = ", ".join(f"{b.display_name} ({b.side_name})" for b in ops)
    return f"    {label}: {ops_str}"


def _signature(rb: RoundBans) -> tuple:
    return tuple(sorted((b.team, b.side, b.roleimage) for b in rb.bans))


def _print_table(match_name: str, names: tuple[str, str], rounds: list[RoundBans]) -> None:
    print(f"\nMatch: {match_name}")
    print(f"Teams: [0] {names[0]}   [1] {names[1]}\n")

    # Collapse consecutive rounds with an identical ban set into a range.
    i = 0
    while i < len(rounds):
        j = i
        while j + 1 < len(rounds) and _signature(rounds[j + 1]) == _signature(rounds[i]):
            j += 1
        first, last = rounds[i].round_no, rounds[j].round_no
        header = f"Round {first:02d}" if first == last else f"Rounds {first:02d}-{last:02d}"
        rb = rounds[i]
        if not rb.bans:
            print(f"  {header}: (no bans)")
        else:
            print(f"  {header}:")
            for team in (0, 1):
                line = _team_line(rb, team, names)
                if line:
                    print(line)
        i = j + 1

    # Per-team summary: distinct operators each team banned at any point.
    print("\nAll bans by team (deduplicated per team):")
    for team in (0, 1):
        distinct = {}
        for rb in rounds:
            for b in rb.bans:
                if b.team == team:
                    distinct.setdefault(b.roleimage, b)
        ops = sorted(distinct.values(), key=lambda b: (b.side, b.display_name))
        ops_str = ", ".join(f"{b.display_name} ({b.side_name})" for b in ops) or "(none)"
        print(f"  {names[team]}: {ops_str}")


def _json_payload(match_name: str, names: tuple[str, str], rounds: list[RoundBans]) -> dict:
    return {
        "match": match_name,
        "teams": [names[0], names[1]],
        "rounds": [
            {
                "round": rb.round_no,
                "bans": [
                    {
                        "operator": b.operator,
                        "opSide": b.side_name,
                        "team": b.team,
                        "teamName": names[b.team] if b.team in (0, 1) else None,
                        "roleimage": b.roleimage,
                        "known": b.operator is not None,
                    }
                    for b in rb.bans
                ],
            }
            for rb in rounds
        ],
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        recs, ref = _resolve_recs(args.path)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    try:
        db = load_db(args.db)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    rounds = extract_match_bans(recs, db)
    names = team_names(ref)
    match_name = os.path.basename(os.path.normpath(args.path))

    if args.json:
        json.dump(_json_payload(match_name, names, rounds), sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    _print_table(match_name, names, rounds)
    unknown = {b.roleimage for rb in rounds for b in rb.bans if not b.operator}
    if unknown:
        print(
            f"\n{len(unknown)} unknown roleimage id(s): {sorted(unknown)}. "
            "Seed them into the operator database to resolve names.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
