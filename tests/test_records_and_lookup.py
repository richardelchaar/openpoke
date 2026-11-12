from server.routing.lookup import lookup
from server.services.agents import record_tool_call


def ids(result):
    return [c.agent_id for c in result.candidates]


def test_a_draft_puts_the_recipient_and_subject_on_the_record(store):
    agent = store.create("Dana Lee - lease renewal")
    record_tool_call(store, agent, "gmail_create_draft",
                     {"recipient_email": "Dana.Lee@example.com", "subject": "Lease renewal", "body": "hi"})
    record = store.get(agent)
    assert [p["email"] for p in record["people"]] == ["dana.lee@example.com"]
    assert [t["subject"] for t in record["threads"]] == ["Lease renewal"]


def test_a_search_records_the_query_and_nobody_it_found(store):
    store.add_contact("dana.lee@example.com", "Dana Lee")
    sweep = store.create("Inbox sweep")
    record_tool_call(store, sweep, "task_email_search", {"search_query": "from:dana newer_than:30d"})
    assert store.get(sweep)["people"] == []
    # So the agent that read Dana's mail is not a candidate when the user names Dana.
    assert sweep not in ids(lookup("email Dana Lee about lunch", store, recent=[]))


def test_a_record_stops_growing_at_its_cap(store):
    agent = store.create("Newsletter")
    for n in range(60):
        store.add_person(agent, f"reader{n}@example.com")
    assert len(store.get(agent)["people"]) == 25


def test_a_first_name_finds_every_person_who_has_it(store, people):
    result = lookup("send Omar my new phone number", store, recent=[])
    assert {p.name for p in result.people} == {"Omar Ivanov", "Omar Kaur"}
    assert ids(result) == [people["omar"]]          # only one of them has an agent
    assert not any(p.full_name for p in result.people)


def test_a_full_name_shuts_out_people_who_share_the_first_name(store, people):
    result = lookup("email Omar Kaur about the appraisal", store, recent=[])
    assert [p.name for p in result.people] == ["Omar Kaur"]
    assert result.people[0].agents == []


def test_topic_words_rank_one_persons_work(store, people):
    result = lookup("ask Leila for the police report", store, recent=[])
    scores = {c.agent_id: c.score for c in result.candidates}
    assert scores[people["claim"]] > scores[people["boat"]]


def test_recent_agents_are_candidates_whatever_the_message_says(store, people):
    result = lookup("ok send that", store, recent=[people["boat"]])
    assert ids(result)[0] == people["boat"]
    assert "recent" in result.candidates[0].why


def test_reply_to_that_uses_the_person_in_the_last_thing_shown(store, people):
    result = lookup("reply to that and say yes", store, recent=[],
                    last_shown="New email from Omar Ivanov about the appraisal.")
    assert ids(result) == [people["omar"]]
    assert result.candidates[0].why == ["chat"]


def test_a_discarded_agent_never_comes_back(store, people):
    store.discard(people["omar"])
    assert ids(lookup("email Omar Ivanov", store, recent=[people["omar"]])) == []


def test_word_endings_are_ignored(store):
    agent = store.create("March renewals", summary="policies renewing in March")
    assert agent in ids(lookup("anything on the renewal?", store, recent=[]))


def test_agents_in_the_old_roster_file_are_adopted(tmp_path, monkeypatch):
    import json

    from server.services.agents import store as store_module

    folder = tmp_path / "execution_agents"
    folder.mkdir()
    (folder / "roster.json").write_text(json.dumps(["Email to Dana Lee"]))
    (folder / "email-to-dana-lee.log").write_text("<agent_request>hi</agent_request>\n")
    monkeypatch.setattr(store_module, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(store_module, "_store", None)
    store = store_module.get_agent_store()
    agent_id = lookup("anything on dana lee?", store, recent=[]).candidates[0].agent_id
    assert store.get(agent_id)["title"] == "Email to Dana Lee"
    assert (folder / f"{agent_id.replace('_', '-')}.log").exists()


def test_a_throwaway_agent_is_never_a_candidate(store):
    agent = store.create("Wifi password lookup", throwaway=True)
    assert lookup("wifi password", store, recent=[agent]).candidates == []
