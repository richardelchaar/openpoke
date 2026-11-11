"""Builds the test cases for a world.

    python -m evals.cases.build dev
    python -m evals.cases.build heldout

Each category is one situation the router has to handle. A case is a message, the chat
before it, and the right outcome. The right outcome is known because the world generator
laid out who holds which work.

Nothing here calls a model. Wording comes from the phrasings in the catalogue and below.
"""

from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..worlds import names
from ..worlds.catalogue import BY_KEY, CHAT, KINDS, LOOKUPS, PERSON_ONLY, PRONOUN_ASKS, VAGUE_PERSON, VAGUE_TOPIC, Kind
from ..worlds.generate import SEEDS, load

CASE_DIR = Path(__file__).resolve().parent

# How many cases per category in the dev world. The held-out world gets about a third.
COUNTS = {
    "clear_followup": 22, "pronoun_followup": 16, "after_gap": 15, "two_works_topic_named": 34,
    "same_first_name_topic_settles": 34, "different_wording": 18, "shared_contact": 12,
    "email_alert_followup": 12, "correction": 14,
    "same_person_new_topic": 30, "known_first_name_new_person": 30, "brand_new_person": 14,
    "same_person_vague": 34, "same_first_name_vague": 34, "agent_or_contact": 30,
    "chat": 15, "one_off_lookup": 12,
    "two_tasks": 14, "topic_switch": 12, "inbox_scanner": 12, "messy_text": 20, "after_a_question": 14,
}
GROUPS = {
    "route": ["clear_followup", "pronoun_followup", "after_gap", "two_works_topic_named",
              "same_first_name_topic_settles", "different_wording", "shared_contact",
              "email_alert_followup", "correction"],
    "create": ["same_person_new_topic", "known_first_name_new_person", "brand_new_person"],
    "ask": ["same_person_vague", "same_first_name_vague", "agent_or_contact"],
    "no_lasting_agent": ["chat", "one_off_lookup"],
    "robustness": ["two_tasks", "topic_switch", "inbox_scanner", "messy_text", "after_a_question"],
}
GROUP_OF = {cat: group for group, cats in GROUPS.items() for cat in cats}

STOP = set("a an the of for to and on in with new my our is at by or".split())


def cap(text: str) -> str:
    return text[0].upper() + text[1:]


def words(text: str) -> List[str]:
    return re.findall(r"[a-z0-9#']+", text.lower())


class CaseBuilder:
    def __init__(self, world: str):
        self.name = world
        self.w = load(world)
        self.rng = random.Random(SEEDS[world] + 1)
        # The crowd is only used by the crowded run; cases are written without it.
        self.people = {pid: p for pid, p in self.w["people"].items() if not p.get("crowd")}
        self.works = {aid: x for aid, x in self.w["works"].items() if x["tag"] != "crowd"}
        self.g = self.w["groups"]
        self.cases: List[dict] = []
        scale = 1.0 if world == "dev" else 0.36
        self.counts = {cat: max(4, round(n * scale)) for cat, n in COUNTS.items()}
        other = "heldout" if world == "dev" else "dev"
        # Names no one in this world has: the other world's.
        self.new_first = list(names.CORE_FIRST[other])
        self.new_last = list(names.CORE_LAST[other])

    # -- small helpers -------------------------------------------------------------
    def P(self, aid: str) -> dict:
        return self.people[self.works[aid]["person"]]

    def K(self, aid: str) -> Kind:
        return BY_KEY[self.works[aid]["kind"]]

    def full(self, aid: str) -> str:
        p = self.P(aid)
        return f"{p['first']} {p['last']}"

    def cycle(self, items: list, n: int) -> list:
        """n items, spread as evenly as the list allows, in a shuffled order."""
        items = list(items)
        out = []
        while len(out) < n:
            self.rng.shuffle(items)
            out.extend(items)
        return out[:n]

    def spread(self, items: list, phrases: list, n: int) -> List[tuple]:
        """n (item, phrase) pairs with no pair repeated and both sides used evenly."""
        combos = [(i, p) for i in range(len(items)) for p in range(len(phrases))]
        self.rng.shuffle(combos)
        used_i, used_p, out = [0] * len(items), [0] * len(phrases), []
        while len(out) < n and combos:
            combos.sort(key=lambda c: (used_i[c[0]], used_p[c[1]]))
            i, p = combos.pop(0)
            used_i[i] += 1
            used_p[p] += 1
            out.append((items[i], phrases[p]))
        return out

    def anchored(self, aid: str, who: str) -> Tuple[str, str]:
        """A request that names the topic, so it can only be about this piece of work."""
        kind, label = self.K(aid), self.works[aid]["label"]
        options = [
            (kind.asks[0][0].format(who=who), kind.asks[0][1]),
            (kind.asks[1][0].format(who=who), kind.asks[1][1]),
            (f"ask {who} about the {label}", "send"),
            (f"any update from {who} on the {label}?", "read"),
            (f"tell {who} I'll have news on the {label} tomorrow", "send"),
        ]
        return self.rng.choice(options)

    def topical(self, aid: str, who: str) -> Tuple[str, str]:
        text, risk = self.rng.choice(self.K(aid).asks)
        return text.format(who=who), risk

    def alias(self, aid: str) -> str:
        alias = self.K(aid).alias
        return alias if alias.split()[0] in {"the", "my", "getting", "putting", "moving", "signing", "whether",
                                             "dropping", "insuring", "what"} else f"the {alias}"

    def new_kind_for(self, aids: List[str]) -> Kind:
        taken = {self.works[a]["family"] for a in aids}
        group = self.P(aids[0])["group"]
        pool = [k for k in KINDS if k.family not in taken and k.group == group] or \
               [k for k in KINDS if k.family not in taken]
        return self.rng.choice(pool)

    def start(self, kind: Kind, full: str) -> str:
        return kind.start.format(full=full, d=self.rng.choice(kind.details))

    def chat_about(self, aid: str, who: Optional[str] = None) -> List[dict]:
        """An earlier exchange about one piece of work, as the app would have logged it."""
        work, p = self.works[aid], self.P(aid)
        ask, _ = self.anchored(aid, who or self.full(aid))
        return [
            {"tag": "user_message", "text": ask},
            {"tag": "handoff", "agent": aid, "text": cap(ask)},
            {"tag": "poke_reply", "text": f"On it, drafting that for {p['first']} now."},
            {"tag": "agent_message", "text": f"[SUCCESS] {work['name']}: Drafted a message to {self.full(aid)} "
                                             f"({p['email']}) on \"{work['subject']}\". It is waiting for approval."},
            {"tag": "poke_reply", "text": f"Draft to {self.full(aid)} is ready about the {work['label']}. Want me to send it?"},
        ]

    def distinct_terms(self, aid: str, other: str) -> List[str]:
        """Words that tell this piece of work from another when a question lists both."""
        def bag(a: str) -> set:
            w = self.works[a]
            return {t for t in words(f"{w['label']} {w['detail']}") if t not in STOP and len(t) > 2}
        terms = bag(aid) - bag(other)
        if self.works[aid]["person"] != self.works[other]["person"]:
            terms.add(self.P(aid)["last"].lower())
        return sorted(terms)

    def add(self, category: str, message: str, expected: dict, required: List[str], *,
            risk: str = "send", chat: Optional[List[dict]] = None, **extra) -> dict:
        n = sum(1 for c in self.cases if c["category"] == category) + 1
        case = {
            "id": f"{category}-{n:03d}",
            "category": category,
            "group": GROUP_OF[category],
            "risk": risk,
            "recent_chat": chat or [],
            "message": message,
            "expected": expected,
            "required": sorted(set(required)),
            **extra,
        }
        self.cases.append(case)
        return case

    def route(self, *aids: str) -> dict:
        return {"outcome": "route", "agents": sorted(aids)}

    def create(self, first: str, last: str, email: Optional[str] = None) -> dict:
        return {"outcome": "create", "person": {"first": first, "last": last, "email": email}}

    def person_works(self, aid: str) -> List[str]:
        pid = self.works[aid]["person"]
        return [a for a, w in self.works.items() if w["person"] == pid]

    # -- should route ----------------------------------------------------------------
    def clear_followup(self, n: int) -> None:
        pool = self.g["singles"] + [pair[0] for pair in self.g["contacts"]] + [a for pair in self.g["twins"] for a in pair]
        for aid in self.cycle(pool, n):
            text, risk = self.anchored(aid, self.full(aid))
            self.add("clear_followup", text, self.route(aid), self.person_works(aid) + self.same_first(aid), risk=risk)

    def pronoun_followup(self, n: int) -> None:
        pool = self.g["singles"] + [a for pair in self.g["doubles"] + self.g["twins"] for a in pair]
        for aid, (text, risk) in zip(self.cycle(pool, n), self.cycle(PRONOUN_ASKS, n)):
            required = self.person_works(aid) + self.same_first(aid)
            self.add("pronoun_followup", text, self.route(aid), required, risk=risk, chat=self.chat_about(aid))

    def same_first(self, aid: str) -> List[str]:
        first = self.P(aid)["first"]
        return [a for a, w in self.works.items() if w["person"] and self.people[w["person"]]["first"] == first]

    def after_gap(self, n: int) -> None:
        pool = self.g["singles"]
        for aid in self.cycle(pool, n):
            other = self.rng.choice([a for a in pool if a != aid])
            text, risk = self.anchored(aid, self.P(aid)["first"])
            self.add("after_gap", text, self.route(aid), [aid, other], risk=risk, chat=self.chat_about(other))

    def two_works_topic_named(self, n: int) -> None:
        for pair in self.cycle(self.g["doubles"], n):
            aid = self.rng.choice(pair)
            who = self.rng.choice([self.P(aid)["first"], self.full(aid)])
            text, risk = self.anchored(aid, who)
            self.add("two_works_topic_named", text, self.route(aid), pair, risk=risk)

    def same_first_name_topic_settles(self, n: int) -> None:
        for pair in self.cycle(self.g["twins"], n):
            aid = self.rng.choice(pair)
            text, risk = self.anchored(aid, self.P(aid)["first"])
            self.add("same_first_name_topic_settles", text, self.route(aid), pair, risk=risk)

    def different_wording(self, n: int) -> None:
        templates = [("where are we with {who} on {alias}?", "read"), ("tell {who} I'm still working on {alias}", "send"),
                     ("ask {who} if there's anything new about {alias}", "send"), ("any word from {who} about {alias}?", "read")]
        pool = self.g["singles"] + [a for pair in self.g["doubles"] for a in pair]
        for aid, (template, risk) in zip(self.cycle(pool, n), self.cycle(templates, n)):
            who = self.full(aid) if self.works[aid]["tag"] == "single" else self.P(aid)["first"]
            self.add("different_wording", template.format(who=who, alias=self.alias(aid)), self.route(aid),
                     self.person_works(aid), risk=risk)

    def shared_contact(self, n: int) -> None:
        adjusters = [(adj, aids) for adj, aids in self.g["adjusters"].items() if len(aids) >= 2]
        templates = ["ask {adj} where {client}'s claim stands", "email {adj} that {client} sent the photos",
                     "check with the adjuster on the {last} claim", "tell {adj} that {client} is still waiting on the estimate"]
        for (adj, aids), template in zip(self.cycle(adjusters, n), self.cycle(templates, n)):
            aid = self.rng.choice(aids)
            a = self.people[adj]
            text = template.format(adj=f"{a['first']} {a['last']}", client=self.full(aid), last=self.P(aid)["last"])
            self.add("shared_contact", text, self.route(aid), aids)

    def email_alert_followup(self, n: int) -> None:
        replies = ["reply to that and say I'll call this afternoon", "answer that one: yes, go ahead",
                   "reply saying I need until Monday", "tell them thanks, got it"]
        pool = self.g["singles"] + [a for pair in self.g["doubles"] for a in pair]
        for aid, reply in zip(self.cycle(pool, n), self.cycle(replies, n)):
            work = self.works[aid]
            chat = [{"tag": "poke_reply", "text": f"New email from {self.full(aid)} on \"{work['subject']}\": "
                                                  f"they're asking for an update on the {work['label']}."}]
            self.add("email_alert_followup", reply, self.route(aid), self.person_works(aid), chat=chat)

    def correction(self, n: int) -> None:
        for pair in self.cycle(self.g["twins"], n):
            wrong, right = self.rng.sample(pair, 2)
            first = self.P(wrong)["first"]
            vague, _ = self.rng.choice(VAGUE_PERSON)
            chat = [
                {"tag": "user_message", "text": vague.format(who=first)},
                {"tag": "handoff", "agent": wrong, "text": cap(vague.format(who=self.full(wrong)))},
                {"tag": "poke_reply", "text": f"Drafting that for {self.full(wrong)} ({self.works[wrong]['label']})."},
            ]
            text = self.rng.choice([f"no, the other {first}", f"wrong {first}, I meant {self.full(right)}",
                                    f"not that one, {first} {self.P(right)['last']}"])
            self.add("correction", text, self.route(right), pair, chat=chat)

    # -- should create ---------------------------------------------------------------
    def same_person_new_topic(self, n: int) -> None:
        pool = [[a] for a in self.g["singles"]] + self.g["doubles"]
        for aids in self.cycle(pool, n):
            p = self.P(aids[0])
            kind = self.new_kind_for(aids)
            text = self.start(kind, self.full(aids[0]))
            if self.rng.random() < 0.5:
                text = self.rng.choice(["also, ", "separate thing: ", "new one: "]) + text
            self.add("same_person_new_topic", text, self.create(p["first"], p["last"], p["email"]), aids,
                     new_kind=kind.key)

    def known_first_name_new_person(self, n: int) -> None:
        for aid, contact in self.cycle(self.g["contacts"], n):
            c = self.people[contact]
            kind = self.new_kind_for([aid])
            text = self.start(kind, f"{c['first']} {c['last']}")
            self.add("known_first_name_new_person", text, self.create(c["first"], c["last"], c["email"]), [aid],
                     new_kind=kind.key)

    def brand_new_person(self, n: int) -> None:
        for _ in range(n):
            first, last = self.rng.choice(self.new_first), self.rng.choice(self.new_last)
            kind = self.rng.choice(KINDS)
            self.add("brand_new_person", self.start(kind, f"{first} {last}"), self.create(first, last), [],
                     new_kind=kind.key)

    # -- should ask ------------------------------------------------------------------
    def answers_for_works(self, pair: List[str], pick_text: Dict[str, str], new_text: str, new_expected: dict) -> List[dict]:
        pick = self.rng.choice(pair)
        return [
            {"kind": "picks", "text": pick_text[pick], "expected": self.route(pick)},
            {"kind": "new", "text": new_text, "expected": new_expected},
            {"kind": "vague", "text": self.rng.choice(["the usual one", "you know which", "whichever, just do it"]),
             "expected": {"outcome": "ask_or_act", "agents": sorted(pair)}},
        ]

    def same_person_vague(self, n: int) -> None:
        for pair, (vague, risk) in self.spread(self.g["doubles"], VAGUE_TOPIC, n):
            p = self.P(pair[0])
            who = self.rng.choice([p["first"], self.full(pair[0])])
            kind = self.new_kind_for(pair)
            answers = self.answers_for_works(
                pair, {a: f"the {self.works[a]['label']}" for a in pair},
                f"neither, it's about {self.alias_of(kind)}", self.create(p["first"], p["last"], p["email"]))
            self.add("same_person_vague", vague.format(who=who),
                     {"outcome": "ask", "options_must_include": sorted(pair)}, pair, risk=risk,
                     option_terms={pair[0]: self.distinct_terms(pair[0], pair[1]),
                                   pair[1]: self.distinct_terms(pair[1], pair[0])},
                     answers=answers)

    def alias_of(self, kind: Kind) -> str:
        return f"a {kind.label}" if kind.label[0] not in "aeiou" else f"an {kind.label}"

    def same_first_name_vague(self, n: int) -> None:
        for pair, (vague, risk) in self.spread(self.g["twins"], VAGUE_PERSON, n):
            first = self.P(pair[0])["first"]
            last = self.rng.choice(self.new_last)
            answers = self.answers_for_works(
                pair, {a: self.full(a) for a in pair},
                f"neither, a different {first}: {first} {last}", self.create(first, last))
            self.add("same_first_name_vague", vague.format(who=first),
                     {"outcome": "ask", "options_must_include": sorted(pair)}, pair, risk=risk,
                     option_terms={pair[0]: self.distinct_terms(pair[0], pair[1]),
                                   pair[1]: self.distinct_terms(pair[1], pair[0])},
                     answers=answers)

    def agent_or_contact(self, n: int) -> None:
        # Only requests that don't imply an earlier thread: "chase Omar on that" could only
        # mean the Omar who already has work open.
        for (aid, contact), (text, risk) in self.spread(self.g["contacts"], PERSON_ONLY, n):
            p, c = self.P(aid), self.people[contact]
            key = f"contact:{contact}"
            pick_contact = self.rng.random() < 0.5
            answers = [
                {"kind": "picks", "text": f"{c['first']} {c['last']}" if pick_contact else self.full(aid),
                 "expected": self.create(c["first"], c["last"], c["email"]) if pick_contact else self.route(aid)},
                {"kind": "vague", "text": self.rng.choice(["the usual one", "you know which"]),
                 "expected": {"outcome": "ask_or_act", "agents": [aid]}},
            ]
            self.add("agent_or_contact", text.format(who=p["first"]),
                     {"outcome": "ask", "options_must_include": sorted([aid, key])}, [aid], risk=risk,
                     option_terms={aid: [p["last"].lower()], key: [c["last"].lower()]}, answers=answers)

    # -- should not use a lasting agent ------------------------------------------------
    def chat(self, n: int) -> None:
        for text in self.cycle(CHAT, n):
            self.add("chat", text, {"outcome": "none"}, [], risk="read")

    def one_off_lookup(self, n: int) -> None:
        for text in self.cycle(LOOKUPS, n):
            self.add("one_off_lookup", text, {"outcome": "throwaway"}, self.g["standing"] + [self.g["scanner"]], risk="read")

    # -- robustness ------------------------------------------------------------------
    def two_tasks(self, n: int) -> None:
        for _ in range(n):
            a, b = self.rng.sample(self.g["singles"], 2)
            ta, ra = self.anchored(a, self.full(a))
            tb, rb = self.anchored(b, self.full(b))
            joiner = self.rng.choice([" and ", ", and also ", ". Then "])
            self.add("two_tasks", ta.rstrip("?") + joiner + tb, self.route(a, b), [a, b],
                     risk="send" if "send" in (ra, rb) else "read")

    def topic_switch(self, n: int) -> None:
        pool = self.g["singles"] + [a for pair in self.g["doubles"] for a in pair]
        for aid in self.cycle(pool, n):
            other = self.rng.choice([a for a in pool if self.works[a]["person"] != self.works[aid]["person"]])
            text, risk = self.anchored(aid, self.full(aid))
            self.add("topic_switch", text, self.route(aid), self.person_works(aid) + [other], risk=risk,
                     chat=self.chat_about(other))

    def inbox_scanner(self, n: int) -> None:
        scanner = self.g["scanner"]
        seen = set(self.works[scanner]["seen_people"])
        pool = [a for a in self.g["singles"] if self.works[a]["person"] in seen]
        for aid in self.cycle(pool, n):
            text, risk = self.topical(aid, self.full(aid))
            self.add("inbox_scanner", text, self.route(aid), [aid, scanner], risk=risk)

    def messy_text(self, n: int) -> None:
        makers = [self.clear_followup, self.two_works_topic_named, self.same_first_name_topic_settles,
                  self.same_person_vague, self.same_first_name_vague]
        per = -(-n // len(makers))
        for maker in makers:
            before = len(self.cases)
            maker(per)
            for case in self.cases[before:]:
                case["base_category"] = case["category"]
                case["category"], case["group"] = "messy_text", "robustness"
                case["message"] = self.messy(case["message"])
        extra = [c for c in self.cases if c["category"] == "messy_text"][n:]
        self.cases = [c for c in self.cases if c not in extra]
        for i, case in enumerate(c for c in self.cases if c["category"] == "messy_text"):
            case["id"] = f"messy_text-{i + 1:03d}"

    def messy(self, text: str) -> str:
        """The same request typed in a hurry: lowercase, shorthand, one slip."""
        out = text.lower().rstrip(".?!")
        for a, b in [(" please", " pls"), ("tomorrow", "tmrw"), (" about ", " abt "), (" and ", " & "),
                     (" you ", " u "), ("message", "msg"), (" with ", " w "), ("because", "bc")]:
            out = out.replace(a, b)
        tokens = out.split()
        name_tokens = {t for p in self.people.values() for t in (p["first"].lower(), p["last"].lower())}
        slips = [i for i, t in enumerate(tokens) if len(t) > 5 and t.isalpha() and t not in name_tokens]
        if slips:
            i = self.rng.choice(slips)
            j = self.rng.randrange(1, len(tokens[i]) - 2)
            t = tokens[i]
            tokens[i] = t[:j] + t[j + 1] + t[j] + t[j + 2:]
        return " ".join(tokens)

    def after_a_question(self, n: int) -> None:
        for pair, (follow, risk) in zip(self.cycle(self.g["doubles"], n), self.cycle(PRONOUN_ASKS, n)):
            chosen, other = self.rng.sample(pair, 2)
            p = self.P(chosen)
            vague, _ = self.rng.choice(VAGUE_TOPIC)
            chat = [
                {"tag": "user_message", "text": vague.format(who=p["first"])},
                {"tag": "poke_reply", "text": f"Which one for {p['first']}: the {self.works[chosen]['label']} "
                                              f"or the {self.works[other]['label']}? Or something new?"},
                {"tag": "user_message", "text": f"the {self.works[chosen]['label']}"},
                {"tag": "handoff", "agent": chosen, "text": cap(vague.format(who=self.full(chosen)))},
                {"tag": "poke_reply", "text": f"Got it, the {self.works[chosen]['label']}. Drafting now."},
                {"tag": "agent_message", "text": f"[SUCCESS] {self.works[chosen]['name']}: Drafted a message to "
                                                 f"{self.full(chosen)} ({p['email']}). It is waiting for approval."},
                {"tag": "poke_reply", "text": f"Draft to {self.full(chosen)} is ready. Want me to send it?"},
            ]
            self.add("after_a_question", follow, self.route(chosen), pair, risk=risk, chat=chat)

    # -- all of it -------------------------------------------------------------------
    def build(self) -> List[dict]:
        for category, n in self.counts.items():
            # Each category draws from its own stream, so changing one never moves another.
            self.rng = random.Random(f"{SEEDS[self.name]}-{category}")
            getattr(self, category)(n)
        return self.cases


def load_cases(world: str) -> List[dict]:
    """The frozen cases for a world. "dev.stress" names the separate stress set."""
    return [json.loads(line) for line in (CASE_DIR / f"{world}.jsonl").read_text().splitlines() if line.strip()]


def main() -> None:
    for world in sys.argv[1:] or ["dev", "heldout"]:
        cases = CaseBuilder(world).build()
        path = CASE_DIR / f"{world}.jsonl"
        path.write_text("".join(json.dumps(c) + "\n" for c in cases))
        by_group: Dict[str, int] = {}
        for c in cases:
            by_group[c["group"]] = by_group.get(c["group"], 0) + 1
        print(f"{world}: {len(cases)} cases -> {path.name}  {by_group}")


if __name__ == "__main__":
    main()
