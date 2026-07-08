"""Operator database: resolves a banned ``roleimage`` asset id to a name/side.

The database ships with the package as ``data/operators.json``. Override with the
``R6BANS_DB`` environment variable or the ``--db`` CLI flag.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_PKG_DIR = Path(__file__).resolve().parent
_BUNDLED_DB = _PKG_DIR / "data" / "operators.json"


@dataclass(frozen=True)
class OperatorDB:
    """Lookup table from roleimage id -> operator name, plus fixed-side ops."""

    roleimage_to_op: dict[int, str]
    sides: dict[str, str]  # operator name -> "ATK"/"DEF" (only ops locked to a side)
    source: Path

    def name(self, roleimage: int) -> Optional[str]:
        return self.roleimage_to_op.get(roleimage)

    def side_for(self, name: str) -> Optional[str]:
        return self.sides.get(name)


def _resolve_path(explicit: Optional[str | os.PathLike]) -> Path:
    if explicit:
        return Path(explicit)
    env = os.environ.get("R6BANS_DB")
    if env:
        return Path(env)
    return _BUNDLED_DB


def load_db(path: Optional[str | os.PathLike] = None) -> OperatorDB:
    """Load the operator database. Raises FileNotFoundError if none is found."""
    resolved = _resolve_path(path)
    if not resolved.is_file():
        raise FileNotFoundError(
            f"operator database not found at {resolved}. "
            "Set R6BANS_DB or pass --db to point at an operators json file."
        )
    raw = json.loads(resolved.read_text(encoding="utf-8"))
    r2o = {int(k): v for k, v in raw.get("roleimage_to_op", {}).items()}
    sides: dict[str, str] = {}
    for name, meta in raw.get("operators", {}).items():
        if isinstance(meta, dict) and meta.get("side"):
            sides[name] = meta["side"]
    return OperatorDB(roleimage_to_op=r2o, sides=sides, source=resolved)
