"""A small set of messier messages, written after the main results to look for weak spots.

    python -m evals.cases.stress dev

The main cases always spell a person's name the way the contacts do. These don't: a short
form, a misspelling, a surname alone, or no name at all. Each still has one right agent.
They are reported separately from the main set and were not used to tune anything.
"""

from __future__ import annotations

import json
import random
import sys
from collections import Counter
from typing import List

from ..worlds.catalogue import BY_KEY
from ..worlds.generate import SEEDS, load
from .build import CASE_DIR

SHORT = {"Daniel": "Dan", "Victor": "Vic", "Marcus": "Marc", "Sofia": "Sof", "Julian": "Jules", "Tobias": "Toby",
         "Rafael": "Rafa", "Desmond": "Des", "Nikolai": "Niko", "Samir": "Sam", "Wesley": "Wes", "Valentina": "Val",
         "Gustavo": "Gus", "Jasmine": "Jas", "Quentin": "Quent", "Winston": "Win", "Dmitri": "Dima", "Olivia": "Liv",
         "Lorenzo": "Enzo", "Hannah": "Han", "Ximena": "Xime", "Leila": "Lei", "Imani": "Mani", "Mateo": "Teo",
         "Abigail": "Abby", "Gabriela": "Gabi", "Joaquin": "Quino", "Camille": "Cam", "Fabian": "Fabi", "Henrik": "Henk",
         "Vivian": "Viv", "Yolanda": "Yoli", "Katya": "Kat", "Xavier": "Xavi", "Darius": "Dar", "Ulrich": "Uli"}
PER_KIND = 6


def misspell(name: str, rng: random.Random) -> str:
    """Two neighbouring letters the wrong way round."""
    while True:
        i = rng.randrange(1, len(name) - 2)
        wrong = name[:i] + name[i + 1] + name[i] + name[i + 2:]
        if wrong != name:
            return wrong


def build(world_name: str) -> List[dict]:
    world = load(world_name)
    works, people = world["works"], world["people"]
    rng = random.Random(SEEDS[world_name] + 9)
    groups = world["groups"]
    singles = [a for a in groups["singles"] if works[a]["person"]]
    doubles = [a for pair in groups["doubles"] for a in pair]
    anyone = singles + doubles + [a for pair in groups["twins"] for a in pair] + [pair[0] for pair in groups["contacts"]]
    one_first_name = singles + doubles          # people whose first name nobody else in the core has
    for pool in (singles, anyone, one_first_name):
        rng.shuffle(pool)
    # A (kind, detail) pair that one agent alone has, in the largest roster tested, can be
    # named without a person.
    largest = set(world["pool_order"][:640]) | {a for a, w in works.items() if w["core"]}
    pairs = Counter((works[a]["kind"], works[a]["detail"]) for a in largest)
    unique = [a for a in anyone if pairs[(works[a]["kind"], works[a]["detail"])] == 1]
    cases: List[dict] = []

    def add(category: str, aid: str, message: str, also: List[str] = ()) -> None:
        n = sum(1 for c in cases if c["category"] == category) + 1
        cases.append({"id": f"{category}-{n:03d}", "category": category, "group": "stress", "risk": "send",
                      "recent_chat": [], "message": message,
                      "expected": {"outcome": "route", "agents": [aid]}, "required": [aid, *also]})

    def same_person(aid: str) -> List[str]:
        return [a for a, w in works.items() if w["person"] == works[aid]["person"] and w["core"] and a != aid]

    def ask(aid: str, who: str) -> str:
        kind = BY_KEY[works[aid]["kind"]]
        return rng.choice(kind.asks[:2])[0].format(who=who)

    for aid in [a for a in one_first_name if people[works[a]["person"]]["first"] in SHORT][:PER_KIND]:
        add("short_name", aid, ask(aid, SHORT[people[works[aid]["person"]]["first"]]), same_person(aid))
    for aid in anyone[:PER_KIND]:
        p = people[works[aid]["person"]]
        add("misspelt_name", aid, ask(aid, f"{p['first']} {misspell(p['last'], rng)}"), same_person(aid))
    for aid in anyone[PER_KIND:2 * PER_KIND]:
        add("surname_only", aid, ask(aid, people[works[aid]["person"]]["last"]), same_person(aid))
    for aid in one_first_name[-PER_KIND:]:
        p = people[works[aid]["person"]]
        add("lowercase_typo", aid, ask(aid, misspell(p["first"], rng)).lower().rstrip("?."), same_person(aid))
    for aid in unique[:PER_KIND]:
        w = works[aid]
        add("no_name", aid, f"any update on the {w['label']} for the {w['detail']}?", same_person(aid))
    for aid in unique[:PER_KIND]:
        w = works[aid]
        alias = BY_KEY[w["kind"]].alias
        alias = alias if alias.split()[0] in ("the", "my", "getting", "putting", "moving", "signing", "whether",
                                              "dropping", "insuring", "what") else f"the {alias}"
        add("no_name_other_words", aid, f"where are we on {alias}, the {w['detail']} one?", same_person(aid))
    for aid, other in zip(singles[:PER_KIND], singles[PER_KIND:2 * PER_KIND]):
        p, q = people[works[aid]["person"]], people[works[other]["person"]]
        add("two_people_one_recipient", aid,
            f"tell {p['first']} {p['last']} that {q['first']} {q['last']} is covering for me this week", [other])
    return cases


def main() -> None:
    for world_name in sys.argv[1:] or ["dev"]:
        cases = build(world_name)
        path = CASE_DIR / f"{world_name}.stress.jsonl"
        path.write_text("".join(json.dumps(c) + "\n" for c in cases))
        print(f"{world_name}: {len(cases)} stress cases -> {path.name}  {dict(Counter(c['category'] for c in cases))}")
        for c in cases[::4]:
            print("   ", c["message"])


if __name__ == "__main__":
    main()
