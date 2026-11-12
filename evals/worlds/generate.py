"""Builds a world: people, the work each agent holds, and the traps cases are written around.

    python -m evals.worlds.generate dev
    python -m evals.worlds.generate heldout

Everything comes from the seed, so a world can be rebuilt exactly. Nothing here calls a model.

A world has two parts. The core is the people and work that cases are about, laid out in
groups that each set a trap (two people with one first name, one person with two pieces of
work, and so on). The filler is everyone else, there to make the roster big.
"""

from __future__ import annotations

import json
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from . import names
from .catalogue import KINDS, Kind

WORLD_DIR = Path(__file__).resolve().parent
SEEDS = {"dev": 20261110, "heldout": 77120411}
# How heavily each world leans on each group of kinds. The held-out world is a different mix.
GROUP_WEIGHTS = {
    "dev": {"client": 3.0, "vendor": 1.5, "colleague": 1.5, "personal": 1.0},
    "heldout": {"client": 1.0, "vendor": 2.0, "colleague": 2.0, "personal": 3.0},
}
N_TWINS, N_DOUBLES, N_CONTACTS, N_SINGLES, N_ADJUSTERS = 12, 12, 12, 18, 3
N_FILL = 1300
CROWD_PER_NAME = 14
START = datetime(2026, 9, 1, 9, 0)


class Builder:
    def __init__(self, world: str):
        self.world = world
        self.rng = random.Random(SEEDS[world])
        self.people: Dict[str, dict] = {}
        self.works: Dict[str, dict] = {}
        self.used_names: set[str] = set()
        self.used_people: set[tuple[str, str]] = set()
        self.first = list(names.CORE_FIRST[world])
        self.last = list(names.CORE_LAST[world])
        self.rng.shuffle(self.first)
        self.rng.shuffle(self.last)
        self.clock = START

    # -- people ------------------------------------------------------------------
    def person(self, first: str, last: str, group: str, core: bool) -> str:
        pid = f"p_{len(self.people) + 1:04d}"
        if group in names.WORK_DOMAINS:
            domain = self.rng.choice(names.WORK_DOMAINS[group])
        else:
            domain = self.rng.choice(names.MAIL_DOMAINS)
        email = f"{first}.{last}@{domain}".lower().replace(" ", "")
        self.people[pid] = {"id": pid, "first": first, "last": last, "email": email, "group": group, "core": core}
        self.used_people.add((first, last))
        return pid

    def core_first(self) -> str:
        return self.first.pop()

    def core_last(self) -> str:
        return self.last.pop()

    # -- kinds -------------------------------------------------------------------
    def pick_kind(self, group: Optional[str] = None, avoid_families: tuple = ()) -> Kind:
        pool = [k for k in KINDS if k.family not in avoid_families and (group is None or k.group == group)]
        weights = [GROUP_WEIGHTS[self.world][k.group] for k in pool]
        return self.rng.choices(pool, weights=weights, k=1)[0]

    # -- work --------------------------------------------------------------------
    def work(self, pid: str, kind: Kind, tag: str, third: Optional[str] = None, name_styles: str = "ABCDE") -> str:
        aid = f"a_{len(self.works) + 1:04d}"
        p = self.people[pid]
        detail = self.rng.choice(kind.details)
        self.clock += timedelta(hours=self.rng.randint(1, 30), minutes=self.rng.randint(0, 59))
        work = {
            "id": aid,
            "person": pid,
            "third": third,
            "kind": kind.key,
            "family": kind.family,
            "label": kind.label,
            "detail": detail,
            "subject": kind.subject.format(d=detail),
            "thread": f"t_{self.rng.getrandbits(40):010x}",
            "summary": kind.summary.format(d=detail),
            "name": self.agent_name(p, kind, detail, name_styles),
            "started": self.clock.strftime("%Y-%m-%d %H:%M:%S"),
            "tag": tag,
            "core": tag not in ("fill", "crowd"),
        }
        work["history"] = self.history(work, p, kind)
        self.works[aid] = work
        return aid

    def agent_name(self, p: dict, kind: Kind, detail: str, styles: str) -> str:
        """A name in the style the original app gives its agents ('Email to Sharanjeet')."""
        full = f"{p['first']} {p['last']}"
        forms = {
            "A": f"{full} {kind.label}",
            "B": f"{kind.label.capitalize()} - {full}",
            "C": f"Email to {full}",
            "D": f"{p['first']} {kind.label}",
            "E": f"{full} - {detail}",
        }
        for style in self.rng.sample(styles, len(styles)):
            if forms[style] not in self.used_names:
                self.used_names.add(forms[style])
                return forms[style]
        fallback = f"{full} {kind.label} ({detail})"
        self.used_names.add(fallback)
        return fallback

    def history(self, work: dict, p: dict, kind: Kind) -> List[dict]:
        """What the agent did so far, as the requests it got and the tool calls it made."""
        full = f"{p['first']} {p['last']}"
        first_request = kind.start.format(full=full, d=work["detail"])
        turns = [{
            "request": first_request[0].upper() + first_request[1:] + ".",
            "calls": [
                {"tool": "gmail_create_draft", "args": {
                    "recipient_email": p["email"], "subject": work["subject"],
                    "body": f"Hi {p['first']},\n\nI'm writing about the {kind.label} ({work['detail']}). Could you get back to me when you can?\n\nThanks"}},
                {"tool": "gmail_execute_draft", "args": {"draft_id": f"d_{self.rng.getrandbits(32):08x}"}},
            ],
            "response": f"Sent the email to {full} ({p['email']}), subject \"{work['subject']}\".",
        }]
        if self.rng.random() < 0.6:
            ask = self.rng.choice([a for a, risk in kind.asks if risk == "send"]).format(who=full)
            turns.append({
                "request": ask[0].upper() + ask[1:] + ".",
                "calls": [{"tool": "gmail_reply_to_thread", "args": {
                    "thread_id": work["thread"], "recipient_email": p["email"],
                    "message_body": f"Hi {p['first']},\n\nA quick follow-up on the {kind.label}.\n\nThanks"}}],
                "response": f"Replied to {full} on the thread \"{work['subject']}\".",
            })
        if work["third"]:
            t = self.people[work["third"]]
            turns.append({
                "request": f"Forward the latest from {full} to {t['first']} {t['last']}.",
                "calls": [{"tool": "gmail_forward_email", "args": {
                    "message_id": f"m_{self.rng.getrandbits(40):010x}", "recipient_email": t["email"]}}],
                "response": f"Forwarded {full}'s email to {t['first']} {t['last']} ({t['email']}).",
            })
        return turns

    # -- the core ----------------------------------------------------------------
    def build_core(self) -> dict:
        groups: dict = {"twins": [], "doubles": [], "contacts": [], "singles": [], "adjusters": {}, "standing": []}

        adjusters = [self.person(self.core_first(), self.core_last(), "adjuster", True) for _ in range(N_ADJUSTERS)]
        groups["adjusters"] = {a: [] for a in adjusters}

        def third_for(kind: Kind) -> Optional[str]:
            return self.rng.choice(adjusters) if kind.third else None

        def add(pid: str, kind: Kind, tag: str, styles: str) -> str:
            third = third_for(kind)
            aid = self.work(pid, kind, tag, third, styles)
            if third:
                groups["adjusters"][third].append(aid)
            return aid

        # Two people with the same first name, each with one piece of work.
        for _ in range(N_TWINS):
            first = self.core_first()
            k1 = self.pick_kind()
            k2 = self.pick_kind(avoid_families=(k1.family,))
            pair = []
            for kind in (k1, k2):
                pid = self.person(first, self.core_last(), kind.group, True)
                pair.append(add(pid, kind, "twin", "ABD"))
            groups["twins"].append(pair)

        # One person with two pieces of work.
        for _ in range(N_DOUBLES):
            k1 = self.pick_kind()
            k2 = self.pick_kind(group=k1.group, avoid_families=(k1.family,))
            pid = self.person(self.core_first(), self.core_last(), k1.group, True)
            groups["doubles"].append([add(pid, k1, "double", "ABDE"), add(pid, k2, "double", "ABDE")])

        # A person with an agent, and a contact with the same first name and no agent.
        for _ in range(N_CONTACTS):
            first = self.core_first()
            kind = self.pick_kind()
            pid = self.person(first, self.core_last(), kind.group, True)
            aid = add(pid, kind, "contact_pair", "ABCD")
            contact = self.person(first, self.core_last(), self.rng.choice(["client", "personal", "colleague"]), True)
            groups["contacts"].append([aid, contact])

        # One person, one piece of work, a first name nobody else has.
        for _ in range(N_SINGLES):
            kind = self.pick_kind()
            pid = self.person(self.core_first(), self.core_last(), kind.group, True)
            groups["singles"].append(add(pid, kind, "single", "ABCDE"))

        # Make sure each adjuster sits on at least two pieces of work.
        claim_kinds = [k for k in KINDS if k.third]
        for adj in adjusters:
            while len(groups["adjusters"][adj]) < 2:
                kind = self.rng.choice(claim_kinds)
                pid = self.person(self.core_first(), self.core_last(), kind.group, True)
                aid = self.work(pid, kind, "single", adj, "ABE")
                groups["adjusters"][adj].append(aid)
                groups["singles"].append(aid)

        groups["scanner"] = self.scanner(groups["singles"])
        groups["standing"] = self.standing()
        return groups

    def scanner(self, singles: List[str]) -> str:
        """An agent that read the whole inbox once. It acted on nobody."""
        aid = f"a_{len(self.works) + 1:04d}"
        seen = [self.people[self.works[a]["person"]] for a in self.rng.sample(singles, 8)]
        listing = "; ".join(f"{p['first']} {p['last']} <{p['email']}>" for p in seen)
        name = "Inbox sweep - last 30 days"
        self.used_names.add(name)
        self.works[aid] = {
            "id": aid, "person": None, "third": None, "kind": "scanner", "family": "scanner",
            "label": "inbox sweep", "detail": "last 30 days", "subject": "", "thread": "",
            "summary": "one-off sweep of the inbox for everyone who wrote in the last 30 days",
            "name": name, "started": START.strftime("%Y-%m-%d %H:%M:%S"), "tag": "scanner", "core": True,
            "seen_people": [p["id"] for p in seen],
            "history": [{
                "request": "Go through my inbox and list everyone who emailed me in the last 30 days.",
                "calls": [{"tool": "task_email_search", "args": {"search_query": "newer_than:30d"}}],
                "response": f"Found mail from: {listing}.",
            }],
        }
        return aid

    def standing(self) -> List[str]:
        out = []
        for name, summary, request in [
            ("Morning inbox digest", "sends a summary of new mail every morning at 7:30",
             "Every weekday at 7:30, summarise what arrived overnight."),
            ("Friday renewals reminder", "reminds the user every Friday of policies renewing next week",
             "Every Friday at 9, remind me which policies renew next week."),
        ]:
            aid = f"a_{len(self.works) + 1:04d}"
            self.used_names.add(name)
            self.works[aid] = {
                "id": aid, "person": None, "third": None, "kind": "standing", "family": "standing",
                "label": name.lower(), "detail": "", "subject": "", "thread": "", "summary": summary,
                "name": name, "started": START.strftime("%Y-%m-%d %H:%M:%S"), "tag": "standing", "core": True,
                "history": [{"request": request,
                             "calls": [{"tool": "createTrigger", "args": {"payload": request, "recurrence_rule": "FREQ=WEEKLY"}}],
                             "response": "Reminder created."}],
            }
            out.append(aid)
        return out

    # -- the filler --------------------------------------------------------------
    def build_fill(self) -> None:
        taken_first = set(names.CORE_FIRST["dev"]) | set(names.CORE_FIRST["heldout"])
        taken_last = set(names.CORE_LAST["dev"]) | set(names.CORE_LAST["heldout"])
        near_first = [n for n in names.NEAR_FIRST if n not in taken_first]
        near_last = [n for n in names.NEAR_LAST if n not in taken_last]
        plain_first = [n for n in names.FILL_FIRST if n not in taken_first]
        plain_last = [n for n in names.FILL_LAST if n not in taken_last]

        while sum(1 for w in self.works.values() if w["tag"] == "fill") < N_FILL:
            if self.rng.random() < 0.5:   # a near miss on one half of the name
                if self.rng.random() < 0.5:
                    first, last = self.rng.choice(near_first), self.rng.choice(plain_last)
                else:
                    first, last = self.rng.choice(plain_first), self.rng.choice(near_last)
            else:
                first, last = self.rng.choice(plain_first), self.rng.choice(plain_last)
            if (first, last) in self.used_people:
                continue
            k1 = self.pick_kind()
            pid = self.person(first, last, k1.group, False)
            self.work(pid, k1, "fill")
            if self.rng.random() < 0.35:
                self.work(pid, self.pick_kind(group=k1.group, avoid_families=(k1.family,)), "fill", name_styles="ABDE")

    # -- the crowd ---------------------------------------------------------------
    def build_crowd(self) -> None:
        """Extra people who share a first name with someone in the core.

        They are left out of the normal roster. The crowded run adds them on purpose, to
        see what happens when a bigger roster also means more people with the same name.
        """
        main_rng, self.rng = self.rng, random.Random(SEEDS[self.world] + 2)
        taken = set(names.CORE_LAST["dev"]) | set(names.CORE_LAST["heldout"])
        lasts = [n for n in names.FILL_LAST + names.NEAR_LAST if n not in taken]
        firsts = sorted({p["first"] for p in self.people.values() if p["core"] and p["group"] != "adjuster"})
        end = self.clock
        for first in firsts:
            for _ in range(CROWD_PER_NAME):
                last = self.rng.choice(lasts)
                while (first, last) in self.used_people:
                    last = self.rng.choice(lasts)
                kind = self.pick_kind()
                pid = self.person(first, last, kind.group, False)
                self.people[pid]["crowd"] = True
                aid = self.work(pid, kind, "crowd", name_styles="ABD")
                when = START + (end - START) * self.rng.random()
                self.works[aid]["started"] = when.strftime("%Y-%m-%d %H:%M:%S")
                self.works[aid]["core"] = False
        self.rng = main_rng

    # -- the whole world ---------------------------------------------------------
    def build(self) -> dict:
        groups = self.build_core()
        self.build_fill()
        order = sorted(self.works)
        self.rng.shuffle(order)
        self.build_crowd()
        return {
            "world": self.world,
            "seed": SEEDS[self.world],
            "people": self.people,
            "works": self.works,
            "groups": groups,
            "pool_order": order,
        }


def load(world: str) -> dict:
    """The world, built from its seed the first time it is asked for. The files are not
    kept in the repository: they are large, and building them again gives the same bytes,
    which evals/CHECKSUMS verifies."""
    path = WORLD_DIR / f"{world}.json"
    if not path.exists():
        path.write_text(json.dumps(Builder(world).build(), indent=1))
    return json.loads(path.read_text())


def main() -> None:
    for world in sys.argv[1:] or ["dev", "heldout"]:
        data = Builder(world).build()
        path = WORLD_DIR / f"{world}.json"
        path.write_text(json.dumps(data, indent=1))
        core = sum(1 for w in data["works"].values() if w["core"])
        print(f"{world}: {len(data['people'])} people, {len(data['works'])} agents ({core} core) -> {path.name}")


if __name__ == "__main__":
    main()
