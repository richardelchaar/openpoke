import asyncio

from evals.grade import grade_turn
from server.agents.interaction_agent import tools
from server.routing.lookup import LookupResult
from server.routing.pipeline import Routing
from server.services.agents import store as store_module


def use(store, monkeypatch):
    monkeypatch.setattr(store_module, "_store", store)

    class Done:
        success = True

    async def no_execution(*args, **kwargs):
        return Done()

    monkeypatch.setattr(tools._EXECUTION_BATCH_MANAGER, "execute_agent", no_execution)


def in_loop(fn):
    async def run():
        return fn()
    return asyncio.run(run())


def test_hand_off_is_refused_for_an_agent_not_approved_this_turn(store, people, monkeypatch):
    use(store, monkeypatch)
    routing = Routing(LookupResult([], []), approved=[people["claim"]])
    refused = in_loop(lambda: tools.hand_off_to_agent(routing, people["boat"], "do it"))
    allowed = in_loop(lambda: tools.hand_off_to_agent(routing, people["claim"], "do it"))
    assert not refused.success and allowed.success


def test_the_hand_off_tool_only_lists_approved_agents(store, people):
    routing = Routing(LookupResult([], []), approved=[people["claim"]])
    schema = next(s for s in tools.get_tool_schemas(routing) if s["function"]["name"] == "send_message_to_agent")
    assert schema["function"]["parameters"]["properties"]["agent_id"]["enum"] == [people["claim"]]
    asking = Routing(LookupResult([], []), approved=[], may_create=False)
    assert {s["function"]["name"] for s in tools.get_tool_schemas(asking)} == {"send_message_to_user", "send_draft", "wait"}


def test_creating_work_that_already_has_an_agent_is_stopped(store, people, monkeypatch):
    use(store, monkeypatch)
    routing = Routing(LookupResult([], []), approved=[])
    result = in_loop(lambda: tools.create_agent(routing, "Leila Sorensen auto claim police report", "chase it",
                                                person_name="Leila Sorensen"))
    assert not result.success and result.payload["existing_agent_id"] == people["claim"]
    assert people["claim"] in routing.approved          # so it can be handed off to instead


def test_new_work_for_the_same_person_is_created(store, people, monkeypatch):
    use(store, monkeypatch)
    routing = Routing(LookupResult([], []), approved=[])
    result = in_loop(lambda: tools.create_agent(routing, "Leila Sorensen - tenant insurance", "set it up",
                                                person_name="Leila Sorensen"))
    assert result.success and result.payload["person_email"] == "leila.sorensen@example.com"


# -- the grader ----------------------------------------------------------------------

WORLD = {
    "works": {"a1": {"person": "p1"}, "a2": {"person": "p1"}, "b1": {"person": "p2"}},
    "people": {"p1": {"first": "Leila", "last": "Sorensen"}, "p2": {"first": "Omar", "last": "Ivanov"}},
}


def turn(existing=(), created=(), reply=""):
    return {"existing": list(existing), "created": list(created), "reply": reply}


def check(expected, the_turn, case=None):
    return grade_turn(expected, the_turn, case or {}, WORLD)


def test_route_is_right_only_for_exactly_the_expected_agents():
    route = {"outcome": "route", "agents": ["a1"]}
    assert check(route, turn(["a1"]))["right"]
    assert check(route, turn(["a2"]))["error"] == "wrong_agent"
    assert check(route, turn(["b1"]))["error"] == "wrong_person"
    assert check(route, turn(["a1", "a2"]))["error"] == "extra_agents"
    assert check(route, turn(created=[{"name": "x"}]))["error"] == "duplicate"
    assert check(route, turn(reply="which one?"))["error"] == "unnecessary_ask"


def test_create_is_wrong_when_someone_elses_agent_is_reused():
    create = {"outcome": "create", "person": {"first": "Omar", "last": "Kaur", "email": "omar.kaur@example.com"}}
    assert check(create, turn(created=[{"name": "Omar Kaur lunch", "instructions": ""}]))["right"]
    assert check(create, turn(created=[{"name": "lunch", "person_email": "omar.kaur@example.com"}]))["right"]
    assert check(create, turn(["b1"]))["error"] == "wrong_person"


def test_ask_needs_a_question_that_names_every_option():
    case = {"option_terms": {"a1": ["claim"], "a2": ["boat"]}}
    ask = {"outcome": "ask", "options_must_include": ["a1", "a2"]}
    assert check(ask, turn(reply="The claim or the boat quote?"), case)["right"]
    assert check(ask, turn(reply="The claim, right?"), case)["error"] == "bad_question"
    missed = check(ask, turn(["a1", "a2"]), case)
    assert missed["error"] == "missed_ask" and missed["guess"] == "all_options"


def test_chat_is_wrong_if_an_agent_is_used():
    assert check({"outcome": "none"}, turn(reply="anytime"))["right"]
    assert check({"outcome": "none"}, turn(created=[{"name": "x"}]))["error"] == "unnecessary_agent"


def test_a_correction_may_also_tell_the_wrong_agent_to_stop():
    case = {"category": "correction", "recent_chat": [{"tag": "handoff", "agent": "b1", "text": "x"}]}
    route = {"outcome": "route", "agents": ["a1"]}
    assert check(route, turn(["a1", "b1"]), case)["right"]
    assert check(route, turn(["b1"]), case)["error"] in ("failed", "unnecessary_ask")
