"""Tests run without a model and without touching real data."""

import os
import tempfile

# Set before the app is imported: its stores bind to the data directory at import.
os.environ["OPENPOKE_DATA_DIR"] = tempfile.mkdtemp(prefix="openpoke-tests-")
os.environ.setdefault("OPENROUTER_API_KEY", "test")

import pytest  # noqa: E402

from server.services.agents.store import AgentStore  # noqa: E402


@pytest.fixture
def store(tmp_path):
    return AgentStore(tmp_path / "agents.db")


@pytest.fixture
def people(store):
    """Two Omars (one with an agent), and Leila with two pieces of work."""
    store.add_contact("omar.ivanov@example.com", "Omar Ivanov")
    store.add_contact("omar.kaur@example.com", "Omar Kaur")
    store.add_contact("leila.sorensen@example.com", "Leila Sorensen")
    ids = {
        "omar": store.create("Omar Ivanov jewellery rider", summary="scheduling an engagement ring; appraisal requested"),
        "claim": store.create("Leila Sorensen auto claim", summary="auto claim for a rear-end collision; waiting on the police report"),
        "boat": store.create("Boat insurance quote - Leila Sorensen", summary="boat insurance quote for a sailboat; waiting on hull details"),
    }
    store.add_person(ids["omar"], "omar.ivanov@example.com")
    store.add_person(ids["claim"], "leila.sorensen@example.com")
    store.add_person(ids["boat"], "leila.sorensen@example.com")
    return ids
