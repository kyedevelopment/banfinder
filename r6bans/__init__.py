"""r6bans - extract Rainbow Six Siege operator bans from .rec replay files.

Bans live only in the Round-1 .rec of a match. They are emitted in the prep
timeline as operator *roleimage* asset-id references and are distinguished from
picks by a trailing ban field. See :mod:`r6bans.extractor` for the details.
"""
from .extractor import (
    Ban,
    RoundBans,
    extract_bans,
    extract_match_bans,
    team_names,
    decompress,
)
from .operators import OperatorDB, load_db

__version__ = "2.0.0"
__all__ = [
    "Ban",
    "RoundBans",
    "extract_bans",
    "extract_match_bans",
    "team_names",
    "decompress",
    "OperatorDB",
    "load_db",
    "__version__",
]
