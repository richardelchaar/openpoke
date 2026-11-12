"""Extra work for the people in the core, for the heavy-use roster.

    python -m evals.worlds.heavy dev heldout

In the normal roster nobody has more than two pieces of work, so making the roster bigger
never makes one person harder to place. The heavy-use roster gives each person in a case
six more pieces of work, and ten more people share their first name.

The extra work is written to its own file. The frozen world is not touched.
"""

from __future__ import annotations

import json
import random
import sys

from .generate import SEEDS, WORLD_DIR, Builder, load

EXTRA_PER_PERSON = 6
NAMESAKES = 10


def build(world_name: str) -> dict:
    world = load(world_name)
    b = Builder(world_name)
    b.rng = random.Random(SEEDS[world_name] + 3)
    b.people, b.works = world["people"], dict(world["works"])
    b.used_names = {w["name"] for w in b.works.values()}
    before = set(b.works)

    owners = sorted({w["person"] for w in world["works"].values() if w["core"] and w["person"]})
    for pid in owners:
        person = b.people[pid]
        if person["group"] == "adjuster":
            continue
        families = {w["family"] for w in world["works"].values() if w["person"] == pid}
        for _ in range(EXTRA_PER_PERSON):
            kind = b.pick_kind(avoid_families=tuple(families))
            families.add(kind.family)
            aid = b.work(pid, kind, "heavy", name_styles="ABDE")
            b.works[aid]["core"] = False
    return {aid: w for aid, w in b.works.items() if aid not in before}


def load_heavy(world: dict) -> dict:
    """The world with the extra work added."""
    path = WORLD_DIR / f"{world['world']}.heavy.json"
    if not path.exists():
        path.write_text(json.dumps(build(world["world"]), indent=1))
    extra = json.loads(path.read_text())
    return {**world, "works": {**world["works"], **extra}}


def main() -> None:
    for world_name in sys.argv[1:] or ["dev", "heldout"]:
        extra = build(world_name)
        (WORLD_DIR / f"{world_name}.heavy.json").write_text(json.dumps(extra, indent=1))
        print(f"{world_name}: {len(extra)} extra pieces of work for {len({w['person'] for w in extra.values()})} people")


if __name__ == "__main__":
    main()
