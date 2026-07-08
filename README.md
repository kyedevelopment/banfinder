# banfinder / r6bans

Extract **Rainbow Six Siege operator bans** from `.rec` replay files — **per round
and per team**.

Operator bans are surprisingly hard to recover from replays, and not for one
reason but three:

1. They are emitted in the prep-phase timeline as operator **`roleimage`**
   asset-id references — the *same* marker used for operator picks — and are only
   told apart by a trailing ban field. They are **not** the operator ids that
   parsers like [`r6-dissect`](https://github.com/redraskal/r6-dissect) key on.
2. **They are not all in Round 1.** In competitive play each team bans across
   several rounds (a couple up front, more a few rounds later), and the ban phase
   **restarts when teams swap sides** at half / overtime. You have to read every
   round.
3. **Bans belong to teams.** Each ban is made by a specific team, and the same
   operator banned by both teams (e.g. each side bans an operator while
   defending) is two separate bans, not a duplicate.

`r6bans` handles all three: it walks every round, resolves each `roleimage` to an
operator, and keeps each ban with the team that made it.

```
$ r6-bans path/to/match-folder

Match: match-folder
Teams: [0] Team Falcon   [1] Team Cobra

  Rounds 01-03:
    Team Falcon:  Bandit (DEF), Mute (DEF)
    Team Cobra:   Ash (ATK), Thermite (ATK)
  Rounds 04-06:
    Team Falcon:  Smoke (DEF), Bandit (DEF), Mute (DEF)
    Team Cobra:   Ash (ATK), Sledge (ATK), Thermite (ATK)
  Rounds 07-08:                                     # <- sides swapped, bans restart
    Team Falcon:  Ash (ATK), Sledge (ATK)
    Team Cobra:   Bandit (DEF), Mute (DEF)

All bans by team (deduplicated per team):
  Team Falcon:  Ash (ATK), Sledge (ATK), Bandit (DEF), Mute (DEF), Smoke (DEF)
  Team Cobra:   Ash (ATK), Sledge (ATK), Thermite (ATK), Bandit (DEF), Mute (DEF)
```

*(Illustrative output — teams and bans above are made up.)* Note Ash appears under
**both** teams: Team Cobra banned it in the first phase while defending, Team
Falcon banned it after the side swap. Both are kept.

## Install

```bash
pip install .
# or, without installing:
pip install -r requirements.txt
```

Requires Python 3.9+ and [`zstandard`](https://pypi.org/project/zstandard/).

## Usage

```bash
r6-bans <match-folder>        # collect bans across every round (recommended)
r6-bans <round.rec>           # just one round
r6-bans <path> --json         # machine-readable JSON
r6-bans <path> --db my.json   # use a custom operator database
python -m r6bans <path>       # module form (no install needed)
```

Consecutive rounds with an identical ban set are collapsed into a range
(`Rounds 01-03`) so the phase structure is easy to read.

### JSON shape

```json
{
  "match": "match-folder",
  "teams": ["Team Falcon", "Team Cobra"],
  "rounds": [
    { "round": 1, "bans": [
      { "operator": "Bandit", "opSide": "DEF", "team": 0, "teamName": "Team Falcon",
        "roleimage": 1326495671, "known": true }
    ] }
  ]
}
```

### As a library

```python
from r6bans import extract_match_bans, team_names, load_db
import glob

db = load_db()
recs = glob.glob("path/to/match-folder/*.rec")
rounds = extract_match_bans(recs, db)        # list[RoundBans]
for rb in rounds:
    for b in rb.bans:
        print(rb.round_no, b.team, b.side_name, b.display_name)
```

## How it works

For each pick/ban the round timeline contains:

```
da 69 14 d5 | 08 | <roleimage uint64 LE> | 23 <8-byte timestamp>
```

Ban entries additionally carry a discriminator and a team attribute:

```
18 ff ca 5e | 04 | <side> 00 00 00           side: 1 = ATK op, 2 = DEF op
22 2e 61 a2 a9 | 04 | <team uint32 LE>        team: 1 or 2  (-> 0 / 1)
```

Picks carry a different trailing field and appear twice; bans carry `18 ff ca 5e`
and appear once. `r6bans` walks every `da6914d5` marker across every round, keeps
only ban entries, reads the `roleimage`, side and team, and de-duplicates by
`(roleimage, team)` — collapsing a ban's recurrence at the round summary while
keeping the same operator banned by two different teams as two bans.

The **team attribute is a persistent team identity**: when the teams swap sides,
a team's bans flip from banning attackers to banning defenders, but its team id
stays the same. That is how the tool tells "the ban phase restarted after the
swap" from "a new ban was added within the same phase."

Because banned operators are never *picked*, their name never appears in a
replay header, so the `roleimage → name` mapping is shipped as the operator
database at [`r6bans/data/operators.json`](r6bans/data/operators.json). Two
operators are locked to a single side and carry an explicit `"side"`: **Striker**
(ATK) and **Sentry** (DEF).

### Adding a new / unknown operator

If a ban resolves to `UNKNOWN(<roleimage>)`, add the `roleimage` to
`r6bans/data/operators.json` under both `operators` and `roleimage_to_op`, then
re-run. The IDs are stable per operator across replays.

## License

MIT — see [LICENSE](LICENSE).
