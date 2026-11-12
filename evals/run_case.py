"""Runs one case through the real orchestrator and prints what it did as JSON.

Used by evals/run.py, one process per case, so every case gets its own data directory:

    echo '{"world": "dev", "case_id": "chat-001", "size": 50, "version": "v0", "repeat": 0}' \
        | python -m evals.run_case

The orchestrator code is the app's own. Three things are swapped out:
  - execution agents don't run: a hand-off is recorded and nothing else happens;
  - model responses are saved, so the same request replays for free;
  - the clock for conversation log entries is fixed, so a replay sends identical prompts.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

EVAL_DIR = Path(__file__).resolve().parent
CACHE_PATH = EVAL_DIR / "recorded" / "responses.db"

# The switches that make up each version. The app reads them from the environment.
VERSIONS: Dict[str, Dict[str, str]] = {
    "v0": {"OPENPOKE_LOOKUP": "none", "OPENPOKE_DECIDER": "orchestrator", "OPENPOKE_PROMPT": "v1"},
    "v1": {"OPENPOKE_LOOKUP": "none", "OPENPOKE_DECIDER": "orchestrator", "OPENPOKE_PROMPT": "v2"},
    "v2": {"OPENPOKE_LOOKUP": "records", "OPENPOKE_DECIDER": "orchestrator", "OPENPOKE_PROMPT": "v2"},
    # v2 with one change from reading its failures: each candidate says how it was found.
    "v2b": {"OPENPOKE_LOOKUP": "records", "OPENPOKE_DECIDER": "orchestrator", "OPENPOKE_PROMPT": "v2",
            "OPENPOKE_EXPLAIN_CANDIDATES": "1"},
    # v2 with only a title and a one-line description kept per agent: no people by address,
    # no threads, no contacts.
    "v2d": {"OPENPOKE_LOOKUP": "records", "OPENPOKE_DECIDER": "orchestrator", "OPENPOKE_PROMPT": "v2",
            "OPENPOKE_RECORD": "description"},
    "v3": {"OPENPOKE_LOOKUP": "records", "OPENPOKE_DECIDER": "told_to_ask", "OPENPOKE_PROMPT": "v2"},
    "v4": {"OPENPOKE_LOOKUP": "records", "OPENPOKE_DECIDER": "code_rule", "OPENPOKE_PROMPT": "v2"},
    "v5": {"OPENPOKE_LOOKUP": "records", "OPENPOKE_DECIDER": "judge", "OPENPOKE_PROMPT": "v2"},
}


# -- the roster for one case ---------------------------------------------------------

def roster_for(world: dict, case: dict, size: int, crowd: int = 0, heavy: bool = False) -> List[str]:
    """The agents that exist for this case: the ones it needs, then filler up to `size`.

    Filler is taken from the front of one fixed order, so a bigger roster is a smaller
    one with more added. Agents are listed oldest first, as the app would have them.

    With `crowd`, that many extra people are added for each first name in the case. With
    `heavy`, each person in the case also gets six more pieces of work. Both share nothing
    with what the case is about, so the right answer stays the same, and both count toward
    `size`: the roster is no bigger, only more crowded around the people in the case.
    """
    required = list(case["required"])
    extra = extra_for(world, case, "crowd", crowd) if crowd else []
    if heavy:
        extra += extra_for(world, case, "heavy", 6)
    taken = set(required) | set(extra)
    fill = [aid for aid in world["pool_order"] if aid not in taken]
    chosen = required + extra + fill[: max(0, size - len(taken))]
    return sorted(chosen, key=lambda aid: (world["works"][aid]["started"], aid))


def extra_for(world: dict, case: dict, tag: str, limit: int) -> List[str]:
    """Extra agents around the people in a case: other people with the same first name
    (`crowd`), or more work for the same people (`heavy`)."""
    from evals.cases.build import STOP, words
    from evals.worlds.catalogue import BY_KEY

    works, people = world["works"], world["people"]
    owners = {works[aid]["person"] for aid in case["required"] if works[aid]["person"]}
    firsts = {people[pid]["first"] for pid in owners}
    if case["expected"].get("person"):
        firsts.add(case["expected"]["person"]["first"])
    # Nothing added may be about the same kind of thing as the case, or share a telling
    # word with the message.
    families = {works[aid]["family"] for aid in case["required"]}
    if case.get("new_kind"):
        families.add(BY_KEY[case["new_kind"]].family)
    name_words = {n.lower() for p in people.values() for n in (p["first"], p["last"])}
    telling = {t for t in words(case["message"]) if t not in STOP and t not in name_words and len(t) > 3}

    def fits(aid: str) -> bool:
        w = works[aid]
        return (w["tag"] == tag and w["family"] not in families
                and not telling & set(words(" ".join(w[k] for k in ("label", "detail", "subject", "summary")))))

    out: List[str] = []
    groups = sorted(firsts) if tag == "crowd" else sorted(owners)
    for group in groups:
        if tag == "crowd":
            matches = [aid for aid in sorted(works) if fits(aid) and people[works[aid]["person"]]["first"] == group]
        else:
            matches = [aid for aid in sorted(works) if fits(aid) and works[aid]["person"] == group]
        out.extend(matches[:limit])
    return out


# -- saved model responses -----------------------------------------------------------

class ResponseCache:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=60)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS responses (key TEXT PRIMARY KEY, response TEXT NOT NULL)")
        self.db.commit()

    @staticmethod
    def key(payload: dict, repeat: int) -> str:
        blob = json.dumps({"payload": payload, "repeat": repeat}, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()

    def get(self, key: str) -> Optional[dict]:
        row = self.db.execute("SELECT response FROM responses WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, key: str, response: dict) -> None:
        self.db.execute("INSERT OR REPLACE INTO responses VALUES (?, ?)", (key, json.dumps(response)))
        self.db.commit()


# -- one case ------------------------------------------------------------------------

async def run(job: dict) -> dict:
    from evals.cases.build import load_cases
    from evals.worlds.generate import load

    world = load(job["world"])
    if job.get("heavy"):
        from evals.worlds.heavy import NAMESAKES, load_heavy
        world = load_heavy(world)
        job = {**job, "crowd": NAMESAKES}
    case = next(c for c in load_cases(job.get("case_set") or job["world"]) if c["id"] == job["case_id"])
    version, repeat = job["version"], job["repeat"]
    replay_only = bool(job.get("replay_only"))

    data_dir = Path(tempfile.mkdtemp(prefix="openpoke-eval-"))
    os.environ["OPENPOKE_DATA_DIR"] = str(data_dir)
    os.environ.update(VERSIONS[version])
    os.environ.setdefault("COMPOSIO_API_KEY", "")
    os.environ.setdefault("COMPOSIO_GMAIL_AUTH_CONFIG_ID", "")
    if replay_only:
        os.environ.setdefault("OPENROUTER_API_KEY", "replay")

    # The app is imported only now, after the data directory is set.
    from evals import materialize
    from server.agents.interaction_agent import runtime as runtime_module
    from server.agents.interaction_agent import tools as tools_module
    from server.openrouter_client import client as client_module
    from server.services.conversation import log as conversation_log_module

    # A fixed clock for log entries, so a replay sends identical prompts.
    clock = {"now": datetime(2026, 11, 2, 9, 0)}

    def fixed_now(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
        clock["now"] += timedelta(minutes=1)
        return clock["now"].strftime(fmt)

    conversation_log_module.now_in_user_timezone = fixed_now

    roster = roster_for(world, case, job["size"], job.get("crowd", 0), bool(job.get("heavy")))
    materialize.write_world(world, roster, case, version, data_dir)

    # Save and replay model responses.
    cache = ResponseCache(CACHE_PATH)
    calls: List[dict] = []
    real_request = client_module.request_chat_completion

    async def recorded_request(**kwargs: Any) -> dict:
        payload = {k: v for k, v in kwargs.items() if k not in {"api_key", "base_url"}}
        key = cache.key(payload, repeat)
        started = time.monotonic()
        response = cache.get(key)
        cached = response is not None
        if response is None:
            if replay_only:
                raise RuntimeError("no saved response for this request (replay only)")
            response = await real_request(**kwargs)
            cache.put(key, response)
        usage = response.get("usage") or {}
        calls.append({
            "model": kwargs.get("model"),
            "cached": cached,
            "seconds": round(time.monotonic() - started, 3),
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "cost": usage.get("cost", 0.0),
        })
        return response

    runtime_module.request_chat_completion = recorded_request
    from server.routing import decide as decide_module
    decide_module.request_chat_completion = recorded_request   # the judge's call is saved and counted too

    # Execution agents don't run.
    class _Done:
        success = True
        response = ""

    async def no_execution(agent_name: str, instructions: str, *args: Any, **kwargs: Any) -> _Done:
        return _Done()

    tools_module._EXECUTION_BATCH_MANAGER.execute_agent = no_execution

    names = {world["works"][aid]["name"]: aid for aid in roster}

    async def one_turn(message: str) -> dict:
        runtime = runtime_module.InteractionAgentRuntime()
        tool_calls: List[dict] = []
        real_execute = runtime._execute_tool

        def recording_execute(tool_call: Any) -> Any:
            result = real_execute(tool_call)
            tool_calls.append({"name": tool_call.name, "arguments": tool_call.arguments,
                               "payload": result.payload if isinstance(result.payload, dict) else None})
            return result

        runtime._execute_tool = recording_execute
        first_call = len(calls)
        result = await runtime.execute(message)
        await asyncio.sleep(0)   # let the recorded hand-offs settle

        turn = materialize.read_turn(version, tool_calls, names)
        if runtime.last_routing is not None:
            turn["routing"] = runtime.last_routing.trace()
        turn.update({
            "message": message,
            "reply": "\n".join([c["arguments"].get("message", "") for c in tool_calls
                                if c["name"] == "send_message_to_user"] or [result.response or ""]).strip(),
            "tool_calls": tool_calls,
            "error": result.error,
            "calls": calls[first_call:],
        })
        return turn

    trace: Dict[str, Any] = {
        "case_id": case["id"], "world": job["world"], "version": version, "size": job["size"],
        "repeat": repeat, "crowd": job.get("crowd", 0), "heavy": bool(job.get("heavy")), "roster_size": len(roster), "answer_kind": job.get("answer_kind"), "turns": [],
    }
    trace["turns"].append(await one_turn(case["message"]))
    answer = next((a for a in case.get("answers", []) if a["kind"] == job.get("answer_kind")), None)
    if answer:
        trace["turns"].append(await one_turn(answer["text"]))
    return trace


def main() -> None:
    job = json.loads(sys.stdin.read())
    try:
        trace = asyncio.run(run(job))
    except Exception as exc:   # the runner records the failure against the case
        trace = {"case_id": job.get("case_id"), "version": job.get("version"), "size": job.get("size"),
                 "repeat": job.get("repeat"), "answer_kind": job.get("answer_kind"),
                 "turns": [], "crash": f"{type(exc).__name__}: {exc}"}
    sys.stdout.write("\n@@TRACE@@" + json.dumps(trace))


if __name__ == "__main__":
    main()
