"""Core ban-extraction logic for Rainbow Six Siege .rec replay files.

Operator draft bans are emitted in the prep-phase timeline as operator
*roleimage* asset-id references using the same marker as operator picks --
distinguished by a trailing ban field:

  pick/ban operator ref :  da 69 14 d5 | 08 | <roleimage uint64 LE> | 23 <8b ts>
  BAN entries ALSO carry :  18 ff ca 5e | 04 | <side> 00 00 00      (side: 1=ATK op, 2=DEF op)
  each ban then carries  :  22 2e 61 a2 a9 | 04 | <team uint32 LE>   (team: 1 or 2)

Two things matter beyond the operator:

* **op-side** (1=attacker, 2=defender) -- the banned operator's role.
* **team** (0/1) -- which of the two teams issued the ban. This is a *persistent*
  team identity: when the teams swap sides at half/overtime, a team's bans flip
  from banning attackers to banning defenders, but its team id stays the same.

Bans are NOT all in Round 1. In competitive play each team bans across several
rounds (2 up front, more a few rounds later), and the ban phase restarts when
sides swap. So bans must be collected from every round, keeping each ban with
the team that made it. The same operator banned by both teams is two bans, not a
duplicate.
"""
from __future__ import annotations

import os
import re
import struct
from dataclasses import dataclass
from typing import Optional

import zstandard as zstd

OP_MARK = bytes.fromhex("da6914d5")       # operator roleimage reference
BAN_FIELD = bytes.fromhex("18ffca5e")     # present only on ban entries
TEAM_ATTR = bytes.fromhex("222e61a2a904")  # '22' + attr-id 2e61a2a9 + '04' length prefix
ZSTD_MAGIC = bytes([0x28, 0xB5, 0x2F, 0xFD])

SIDE_NAMES = {1: "ATK", 2: "DEF"}


@dataclass(frozen=True)
class Ban:
    """A single operator ban, attributed to the team that made it."""

    roleimage: int
    side: int                        # banned operator's role: 1=ATK, 2=DEF
    team: int                        # 0 or 1 (which team banned); -1 if unknown
    operator: Optional[str] = None   # resolved name, or None if unknown

    @property
    def side_name(self) -> str:
        return SIDE_NAMES.get(self.side, f"?{self.side}")

    @property
    def display_name(self) -> str:
        return self.operator or f"UNKNOWN({self.roleimage})"


@dataclass(frozen=True)
class RoundBans:
    """All bans present in a single round, in file order."""

    round_no: int
    filename: str
    bans: list[Ban]


def decompress(rec_path: str) -> bytes:
    """Concatenate and decompress every zstd frame in a .rec file."""
    data = open(rec_path, "rb").read()
    first = data.find(ZSTD_MAGIC)
    if first < 0:
        return b""
    out = bytearray()
    pos = first
    dctx = zstd.ZstdDecompressor()
    while True:
        nxt = data.find(ZSTD_MAGIC, pos)
        if nxt < 0:
            break
        try:
            ob = dctx.decompressobj()
            out += ob.decompress(data[nxt:])
            pos = nxt + (len(data) - nxt - len(ob.unused_data))
        except Exception:
            pos = nxt + 1
    return bytes(out)


def extract_bans(rec_path: str, db=None) -> list[Ban]:
    """Extract the operator bans present in a single round .rec.

    Each ban is attributed to its team. De-duplication is by (roleimage, team):
    a ban recurs at the round summary (collapsed), but the same operator banned
    by both teams is kept as two bans.
    """
    tl = decompress(rec_path)
    bans: list[Ban] = []
    seen: set[tuple[int, int]] = set()
    pos = 0
    n = len(tl)
    while True:
        p = tl.find(OP_MARK, pos)
        if p < 0:
            break
        pos = p + 1
        if p + 13 > n or tl[p + 4] != 0x08:
            continue
        roleimage = struct.unpack_from("<Q", tl, p + 5)[0]
        bp = tl.find(BAN_FIELD, p + 13, p + 30)
        if bp < 0:
            continue
        if bp + 5 >= n:
            continue
        side = tl[bp + 5]                       # 1=ATK op, 2=DEF op
        # team attribute follows the ban field within a small window
        tp = tl.find(TEAM_ATTR, bp, bp + 48)
        team = -1
        if 0 <= tp and tp + 10 <= n:
            raw = struct.unpack_from("<I", tl, tp + 6)[0]
            team = raw - 1 if raw in (1, 2) else -1  # 1/2 -> 0/1
        key = (roleimage, team)
        if key in seen:                          # bans recur at round-summary; keep first
            continue
        seen.add(key)
        name = db.name(roleimage) if db is not None else None
        bans.append(Ban(roleimage=roleimage, side=side, team=team, operator=name))
    bans.sort(key=lambda b: (b.team, b.side, b.roleimage))
    return bans


_ROUND_RE = re.compile(r"-R0*(\d+)\.rec$", re.IGNORECASE)


def round_number(rec_path: str) -> int:
    m = _ROUND_RE.search(os.path.basename(rec_path))
    return int(m.group(1)) if m else 0


def team_names(rec_path: str) -> tuple[str, str]:
    """Read teamname0 / teamname1 from the plaintext round header (best effort).

    The header is stored uncompressed at the start of the file as length-prefixed
    strings: ``<key>`` then ``<len byte><7 zero bytes><value>``. (It is not in the
    decompressed timeline.)
    """
    raw = open(rec_path, "rb").read(50000)
    names = ["Team 1", "Team 2"]
    for idx in (0, 1):
        key = f"teamname{idx}".encode()
        k = raw.find(key)
        if k < 0:
            continue
        j = k + len(key)
        if j + 8 > len(raw):
            continue
        length = raw[j]
        value = raw[j + 8 : j + 8 + length]
        if 0 < length <= 40 and all(32 <= b < 127 for b in value):
            names[idx] = value.decode()
    return names[0], names[1]


def extract_match_bans(recs: list[str], db=None) -> list[RoundBans]:
    """Extract bans from every round file (sorted by round number)."""
    ordered = sorted(recs, key=round_number)
    return [
        RoundBans(round_no=round_number(r), filename=os.path.basename(r), bans=extract_bans(r, db))
        for r in ordered
    ]
