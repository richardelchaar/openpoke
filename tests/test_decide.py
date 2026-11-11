from server.routing.decide import apply, code_rule, count_labels
from server.routing.lookup import lookup
from server.routing.pipeline import Routing


def routing_for(message, store, recent=()):
    result = lookup(message, store, list(recent))
    return Routing(result, [c.agent_id for c in result.candidates])


def kinds(steps):
    return [step["do"] for step in steps]


# -- the code rule -------------------------------------------------------------------

def test_code_rule_routes_when_the_words_favour_one(store, people):
    steps = code_rule(routing_for("ask Leila for the police report", store), margin=0.25)
    assert kinds(steps) == ["route"] and steps[0]["agents"] == [people["claim"]]


def test_code_rule_asks_when_nothing_favours_either(store, people):
    steps = code_rule(routing_for("nudge Leila, it's been a week", store), margin=0.25)
    assert kinds(steps) == ["ask"]
    assert set(steps[0]["option_agents"]) == {people["claim"], people["boat"]}


def test_code_rule_asks_which_person_when_one_has_no_agent(store, people):
    steps = code_rule(routing_for("send Omar my new phone number", store), margin=0.25)
    assert kinds(steps) == ["ask"]
    assert any("Omar Kaur" in option for option in steps[0]["options"])


def test_code_rule_creates_for_a_named_contact_with_no_agent(store, people):
    steps = code_rule(routing_for("email Omar Kaur about lunch", store), margin=0.25)
    assert kinds(steps) == ["create"] and "Omar Kaur" in steps[0]["person"]


def test_code_rule_leaves_it_open_when_no_one_is_named(store, people):
    assert kinds(code_rule(routing_for("thanks!", store), margin=0.25)) == ["open"]


def test_code_rule_handles_two_people_separately(store, people):
    steps = code_rule(routing_for("email Omar Ivanov about the ring and nudge Leila Sorensen", store), margin=0.25)
    assert sorted(kinds(steps)) == ["ask", "route"]


def test_a_larger_margin_asks_more(store, people):
    message = "ask Leila about the quote for the sailboat claim"
    assert kinds(code_rule(routing_for(message, store), margin=0.0)) == ["route"]
    assert kinds(code_rule(routing_for(message, store), margin=1.0)) == ["ask"]


# -- counting the judge's labels -----------------------------------------------------

def report(agents, contacts=(), sends=True, kind="work", one_off=False):
    return {"kind": kind, "tasks": [{
        "what": "the task", "sends": sends, "one_off": one_off, "person": "",
        "agents": [{"agent_id": a, "label": label} for a, label in agents],
        "contacts": [{"email": e, "label": label} for e, label in contacts]}]}


def test_one_exact_match_routes(store, people):
    r = routing_for("ask Leila for the police report", store)
    steps = count_labels(report([(people["claim"], "exact"), (people["boat"], "same_person_other_work")]), r, "balanced")
    assert kinds(steps) == ["route"] and steps[0]["agents"] == [people["claim"]]


def test_same_person_other_work_never_causes_a_question(store, people):
    r = routing_for("email Leila about her home policy", store)
    labels = [(people["claim"], "same_person_other_work"), (people["boat"], "same_person_other_work")]
    assert kinds(count_labels(report(labels), r, "strict")) == ["create"]


def test_two_plausible_matches_ask(store, people):
    r = routing_for("nudge Leila", store)
    steps = count_labels(report([(people["claim"], "plausible"), (people["boat"], "plausible")]), r, "loose")
    assert kinds(steps) == ["ask"]


def test_a_plausible_contact_with_no_agent_is_an_option(store, people):
    r = routing_for("send Omar my new phone number", store)
    steps = count_labels(report([(people["omar"], "plausible")], [("omar.kaur@example.com", "plausible")]), r, "balanced")
    assert kinds(steps) == ["ask"] and any("Omar Kaur" in o for o in steps[0]["options"])


def test_the_ask_setting_decides_when_one_is_exact_and_another_plausible(store, people):
    r = routing_for("tell Leila it's approved", store)
    labels = [(people["claim"], "exact"), (people["boat"], "plausible")]
    assert kinds(count_labels(report(labels, sends=True), r, "strict")) == ["ask"]
    assert kinds(count_labels(report(labels, sends=True), r, "balanced")) == ["ask"]
    assert kinds(count_labels(report(labels, sends=False), r, "balanced")) == ["route"]
    assert kinds(count_labels(report(labels, sends=True), r, "loose")) == ["route"]


def test_chat_needs_no_agent(store, people):
    r = routing_for("thanks!", store)
    assert kinds(count_labels({"kind": "chat", "tasks": []}, r, "balanced")) == ["none"]


def test_a_one_off_lookup_is_created_as_a_throwaway(store, people):
    r = routing_for("find the wifi password", store)
    steps = count_labels(report([], one_off=True, sends=False), r, "balanced")
    assert kinds(steps) == ["create"] and steps[0]["throwaway"]


# -- what the orchestrator is then allowed to do -------------------------------------

def test_an_ask_leaves_nothing_to_hand_off_to(store, people):
    r = routing_for("nudge Leila", store)
    apply([{"do": "ask", "about": "Leila", "options": ["a", "b"], "option_agents": []}], r)
    assert r.approved == [] and not r.may_create and "ASK" in r.note


def test_a_clear_task_is_still_routed_beside_an_unclear_one(store, people):
    r = routing_for("email Omar Ivanov and nudge Leila", store)
    apply([{"do": "route", "about": "Omar", "agents": [people["omar"]]},
           {"do": "ask", "about": "Leila", "options": ["a", "b"], "option_agents": []}], r)
    assert r.approved == [people["omar"]]
