import asyncio

import pytest

from server.agents.execution_agent.tools import gmail
from server.agents.interaction_agent import tools
from server.services import approvals
from server.services.approvals import ApprovalStore


@pytest.fixture
def held(tmp_path, monkeypatch):
    """A fresh approval store, a fake Gmail that records what it is asked to do, and a
    conversation log the user's shown messages can be added to."""
    store = ApprovalStore(tmp_path / "approvals.db")
    monkeypatch.setattr(approvals, "_store", store)
    calls = []

    def fake_gmail(tool_name, user_id, arguments=None):
        calls.append((tool_name, dict(arguments or {})))
        if tool_name == "GMAIL_CREATE_EMAIL_DRAFT":
            return {"data": {"response_data": {"id": "r-draft-1", "message": {"id": "m1", "threadId": "t1"}}}}
        return {"successful": True}

    monkeypatch.setattr(gmail, "execute_gmail_tool", fake_gmail)
    monkeypatch.setattr(gmail, "get_active_gmail_user_id", lambda: "user-1")
    shown = []

    class Log:
        def iter_entries(self):
            return [("poke_reply", "", text) for text in shown]

    monkeypatch.setattr(tools, "get_conversation_log", lambda: Log())
    return store, calls, shown


def sends(calls):
    return [name for name, _ in calls if name in ("GMAIL_SEND_DRAFT", "GMAIL_REPLY_TO_THREAD", "GMAIL_FORWARD_MESSAGE")]


def approve(approval_id, *, from_user=True):
    tools.set_turn_origin(from_user)
    return tools.approve_send(approval_id)


REPLY = dict(thread_id="t_88", recipient_email="dana.lee@example.com", message_body="Thursday at two works for me.")


def test_a_reply_is_held_and_nothing_is_sent(held):
    _, calls, _ = held
    result = gmail.gmail_reply_to_thread(**REPLY)
    assert result["sent"] is False and result["approval_id"].startswith("ap_")
    assert calls == []


def test_a_forward_is_held_and_nothing_is_sent(held):
    _, calls, _ = held
    result = gmail.gmail_forward_email("m_42", "adjuster@example.com", "Photos attached.")
    assert result["sent"] is False and calls == []


def test_a_draft_is_created_but_not_sent(held):
    _, calls, _ = held
    result = gmail.gmail_create_draft("dana.lee@example.com", "Lease", "Can you send the renewal terms?")
    assert [name for name, _ in calls] == ["GMAIL_CREATE_EMAIL_DRAFT"]
    assert result["sent"] is False and result["approval_id"].startswith("ap_")
    assert gmail.gmail_execute_draft("r-draft-1")["sent"] is False
    assert sends(calls) == []


def test_nothing_is_sent_without_approval(held):
    _, calls, _ = held
    approval_id = gmail.gmail_reply_to_thread(**REPLY)["approval_id"]
    result = gmail.gmail_send_approved(approval_id)
    assert result["sent"] is False and sends(calls) == []


def test_approval_needs_the_user_to_have_seen_the_exact_text(held):
    _, _, shown = held
    approval_id = gmail.gmail_reply_to_thread(**REPLY)["approval_id"]
    assert not approve(approval_id).success
    shown.append("To: dana.lee@example.com\nSubject: Re: viewing\n\nThursday at three works for me.")
    assert not approve(approval_id).success          # different text was shown
    shown.append("To: dana.lee@example.com\nSubject: Re: viewing\n\nThursday   at two works\nfor me.")
    assert approve(approval_id).success              # the same text, laid out differently


def test_an_agent_or_an_email_alert_cannot_approve(held):
    _, calls, shown = held
    approval_id = gmail.gmail_reply_to_thread(**REPLY)["approval_id"]
    shown.append("To: dana.lee@example.com\n\nThursday at two works for me.")
    result = approve(approval_id, from_user=False)
    assert not result.success and "user" in result.payload["error"]
    assert gmail.gmail_send_approved(approval_id)["sent"] is False and sends(calls) == []


def test_an_approved_email_is_sent_once_and_exactly_as_approved(held):
    _, calls, shown = held
    approval_id = gmail.gmail_reply_to_thread(**REPLY)["approval_id"]
    shown.append("To: dana.lee@example.com\n\nThursday at two works for me.")
    assert approve(approval_id).success
    assert gmail.gmail_send_approved(approval_id)["sent"] is True
    assert calls == [("GMAIL_REPLY_TO_THREAD", REPLY)]
    assert gmail.gmail_send_approved(approval_id)["sent"] is False     # one approval, one send
    assert len(sends(calls)) == 1


def test_changed_text_is_a_new_email_that_needs_its_own_approval(held):
    _, calls, shown = held
    first = gmail.gmail_reply_to_thread(**REPLY)["approval_id"]
    shown.append("To: dana.lee@example.com\n\nThursday at two works for me.")
    assert approve(first).success
    second = gmail.gmail_reply_to_thread(**{**REPLY, "message_body": "Thursday works. Also, please cc Sam."})
    assert second["approval_id"] != first
    assert gmail.gmail_send_approved(second["approval_id"])["sent"] is False and sends(calls) == []


def test_an_approved_draft_can_be_sent_by_its_draft_id(held):
    _, calls, shown = held
    approval_id = gmail.gmail_create_draft("dana.lee@example.com", "Lease", "Can you send the renewal terms?")["approval_id"]
    shown.append("To: dana.lee@example.com\nSubject: Lease\n\nCan you send the renewal terms?")
    assert approve(approval_id).success
    assert gmail.gmail_execute_draft("r-draft-1")["sent"] is True
    assert ("GMAIL_SEND_DRAFT", {"draft_id": "r-draft-1"}) in calls


def test_a_failed_send_can_be_retried(held, monkeypatch):
    _, _, shown = held
    approval_id = gmail.gmail_reply_to_thread(**REPLY)["approval_id"]
    shown.append("To: dana.lee@example.com\n\nThursday at two works for me.")
    assert approve(approval_id).success
    monkeypatch.setattr(gmail, "execute_gmail_tool", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("Gmail down")))
    with pytest.raises(RuntimeError):
        gmail.gmail_send_approved(approval_id)
    monkeypatch.setattr(gmail, "execute_gmail_tool", lambda *a, **k: {"successful": True})
    assert gmail.gmail_send_approved(approval_id)["sent"] is True


def test_the_approve_tool_is_offered_only_on_the_users_turn_and_only_when_something_waits(held):
    def names(**kwargs):
        return {s["function"]["name"] for s in tools.get_tool_schemas(**kwargs)}

    assert "approve_send" not in names(from_user=True)            # nothing waiting
    gmail.gmail_reply_to_thread(**REPLY)
    assert "approve_send" in names(from_user=True)
    assert "approve_send" not in names(from_user=False)           # an agent's report or an email alert


def test_the_runtime_marks_whose_turn_it_is(held, monkeypatch):
    from server.agents.interaction_agent import runtime as runtime_module

    gmail.gmail_reply_to_thread(**REPLY)
    rt = runtime_module.InteractionAgentRuntime()

    async def route(from_user):
        await rt._route("ok send it", from_user=from_user)
        return {s["function"]["name"] for s in rt.tool_schemas}, tools._from_user.get()

    offered, from_user = asyncio.run(route(True))
    assert "approve_send" in offered and from_user is True
    offered, from_user = asyncio.run(route(False))
    assert "approve_send" not in offered and from_user is False
