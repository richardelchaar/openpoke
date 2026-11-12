"""Tool definitions for interaction agent."""

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Optional

from ...config import get_settings
from ...logging_config import logger
from ...routing.lookup import STOP_WORDS, words
from ...routing.pipeline import Routing, current_routing
from ...services.agents import get_agent_store
from ...services.conversation import get_conversation_log
from ...services.execution import get_agent_roster, get_execution_agent_logs
from ..execution_agent.batch_manager import ExecutionBatchManager


@dataclass
class ToolResult:
    """Standardized payload returned by interaction-agent tools."""

    success: bool
    payload: Any = None
    user_message: Optional[str] = None
    recorded_reply: bool = False

# Tool schemas for OpenRouter
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "send_message_to_agent",
            "description": "Deliver instructions to a specific execution agent. Creates a new agent if the name doesn't exist in the roster, or reuses an existing one.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_name": {
                        "type": "string",
                        "description": "Human-readable agent name describing its purpose (e.g., 'Vercel Job Offer', 'Email to Sharanjeet'). This name will be used to identify and potentially reuse the agent."
                    },
                    "instructions": {"type": "string", "description": "Instructions for the agent to execute."},
                },
                "required": ["agent_name", "instructions"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_message_to_user",
            "description": "Deliver a natural-language response directly to the user. Use this for updates, confirmations, or any assistant response the user should see immediately.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Plain-text message that will be shown to the user and recorded in the conversation log.",
                    },
                },
                "required": ["message"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_draft",
            "description": "Record an email draft so the user can review the exact text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": "Recipient email for the draft.",
                    },
                    "subject": {
                        "type": "string",
                        "description": "Email subject for the draft.",
                    },
                    "body": {
                        "type": "string",
                        "description": "Email body content (plain text).",
                    },
                },
                "required": ["to", "subject", "body"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wait",
            "description": "Wait silently when a message is already in conversation history to avoid duplicating responses. Adds a <wait> log entry that is not visible to the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Brief explanation of why waiting (e.g., 'Message already sent', 'Draft already created').",
                    },
                },
                "required": ["reason"],
                "additionalProperties": False,
            },
        },
    },
]

_EXECUTION_BATCH_MANAGER = ExecutionBatchManager()


# Create or reuse execution agent and dispatch instructions asynchronously
def send_message_to_agent(agent_name: str, instructions: str) -> ToolResult:
    """Send instructions to an execution agent."""
    roster = get_agent_roster()
    roster.load()
    existing_agents = set(roster.get_agents())
    is_new = agent_name not in existing_agents

    if is_new:
        roster.add_agent(agent_name)

    get_execution_agent_logs().record_request(agent_name, instructions)

    action = "Created" if is_new else "Reused"
    logger.info(f"{action} agent: {agent_name}")

    async def _execute_async() -> None:
        try:
            result = await _EXECUTION_BATCH_MANAGER.execute_agent(agent_name, instructions)
            status = "SUCCESS" if result.success else "FAILED"
            logger.info(f"Agent '{agent_name}' completed: {status}")
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(f"Agent '{agent_name}' failed: {str(exc)}")

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.error("No running event loop available for async execution")
        return ToolResult(success=False, payload={"error": "No event loop available"})

    loop.create_task(_execute_async())

    return ToolResult(
        success=True,
        payload={
            "status": "submitted",
            "agent_name": agent_name,
            "new_agent_created": is_new,
        },
    )


# ---- With the lookup on, agents are addressed by id and created on purpose ----------

def _handoff_schema(approved: list) -> dict:
    return {
        "type": "function",
        "function": {
            "name": "send_message_to_agent",
            "description": "Hand instructions to an existing execution agent, to continue its piece of work.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string", "enum": approved,
                                 "description": "The id of one of the candidate agents."},
                    "instructions": {"type": "string", "description": "Instructions for the agent to execute."},
                },
                "required": ["agent_id", "instructions"],
                "additionalProperties": False,
            },
        },
    }


CREATE_AGENT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "create_agent",
        "description": "Start a new execution agent for a new piece of work and hand it instructions.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Who and what, e.g. 'Dana Lee - lease renewal'."},
                "person_name": {"type": "string", "description": "Full name of the person the work is with, if there is one."},
                "person_email": {"type": "string", "description": "Their email address, if known."},
                "instructions": {"type": "string", "description": "Instructions for the agent to execute."},
                "throwaway": {"type": "boolean", "description": "True for a one-off lookup that belongs to no ongoing work."},
                "allow_duplicate": {"type": "boolean", "description": "True only after being told a similar agent exists and deciding this is still separate work."},
            },
            "required": ["title", "instructions"],
            "additionalProperties": False,
        },
    },
}

# A new agent is a duplicate when more than this share of its title's words are already on
# an agent for the same person. Exactly half is not enough: "tenant insurance" and "boat
# insurance" share one word of two and are different work.
DUPLICATE_OVERLAP = 0.5


def _dispatch(agent_ref: str, instructions: str) -> Optional[ToolResult]:
    """Start the execution agent in the background. Returns a result only on failure."""
    async def _execute_async() -> None:
        try:
            result = await _EXECUTION_BATCH_MANAGER.execute_agent(agent_ref, instructions)
            logger.info(f"Agent '{agent_ref}' completed: {'SUCCESS' if result.success else 'FAILED'}")
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(f"Agent '{agent_ref}' failed: {str(exc)}")

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.error("No running event loop available for async execution")
        return ToolResult(success=False, payload={"error": "No event loop available"})
    loop.create_task(_execute_async())
    return None


def hand_off_to_agent(routing: Routing, agent_id: str, instructions: str) -> ToolResult:
    """Hand work to an existing agent, if it is one this turn may use."""
    store = get_agent_store()
    if agent_id not in routing.approved or not store.exists(agent_id):
        return ToolResult(success=False, payload={
            "error": "That agent can't be used for this message.",
            "approved_agent_ids": routing.approved,
            "hint": "Use an approved agent, create a new one, or ask the user which they mean.",
        })
    record = store.get(agent_id)
    get_conversation_log().record_handoff(agent_id, record["title"], instructions)
    get_execution_agent_logs().record_request(agent_id, instructions)
    store.touch(agent_id)
    failed = _dispatch(agent_id, instructions)
    return failed or ToolResult(success=True, payload={
        "status": "submitted", "agent_id": agent_id, "title": record["title"], "new_agent_created": False})


def _find_duplicate(title: str, person_email: str) -> Optional[dict]:
    """An agent that already holds this work: same person, and most of the title's words."""
    store = get_agent_store()
    person = next((p for p in store.known_people() if p["email"] == person_email), None)
    if not person:
        return None
    name_words = set(words(person["name"]))
    wanted = {w for w in words(title) if w not in STOP_WORDS and w not in name_words and len(w) > 2}
    if not wanted:
        return None
    for agent_id in person["agents"]:
        record = store.get(agent_id)
        have = set(words(f"{record['title']} {record['summary']} " + " ".join(t["subject"] for t in record["threads"])))
        if len(wanted & have) / len(wanted) > DUPLICATE_OVERLAP:
            return record
    return None


def _first_sentence(text: str, limit: int = 160) -> str:
    """The opening of the first instructions, as the one line on what the work is about."""
    line = " ".join(text.split())
    end = line.find(". ")
    line = line[: end + 1] if 0 < end < limit else line
    return line if len(line) <= limit else line[: limit - 1].rstrip() + "…"


def create_agent(routing: Routing, title: str, instructions: str, person_name: str = "", person_email: str = "",
                 throwaway: bool = False, allow_duplicate: bool = False) -> ToolResult:
    """Create an agent for new work and hand it its first instructions."""
    if not routing.may_create:
        return ToolResult(success=False, payload={
            "error": "A new agent isn't allowed for this message.",
            "hint": "Ask the user which existing work they mean."})
    store = get_agent_store()
    person_email = (person_email or "").strip().lower()
    person_name = (person_name or "").strip()
    if person_name and not person_email:
        matches = [p for p in store.known_people() if p["name"].lower() == person_name.lower()]
        if len(matches) == 1:
            person_email = matches[0]["email"]

    if person_email and not throwaway and not allow_duplicate:
        existing = _find_duplicate(title, person_email)
        if existing:
            if existing["id"] not in routing.approved:
                routing.approved.append(existing["id"])
            return ToolResult(success=False, payload={
                "error": "An agent already holds this work.",
                "existing_agent_id": existing["id"], "existing_title": existing["title"],
                "hint": "Hand off to it with send_message_to_agent. If this really is separate work, "
                        "call create_agent again with allow_duplicate set to true."})

    # The record starts with what is known now: what the work is, and who it is with. The
    # person also becomes a contact, so a later message with their name can find them.
    summary = _first_sentence(instructions)
    if get_settings().routing_record == "description":
        # Description only: the person is named in the description and nowhere else.
        if person_name and person_name.lower() not in f"{title} {summary}".lower():
            summary = f"{summary} (with {person_name})"
        agent_id = store.create(title, summary=summary, throwaway=throwaway)
    else:
        agent_id = store.create(title, summary=summary, throwaway=throwaway)
        if person_email:
            store.add_person(agent_id, person_email, person_name)
            if person_name:
                store.add_contact(person_email, person_name)
    get_conversation_log().record_handoff(agent_id, title, instructions)
    get_execution_agent_logs().record_request(agent_id, instructions)
    failed = _dispatch(agent_id, instructions)
    return failed or ToolResult(success=True, payload={
        "status": "submitted", "agent_id": agent_id, "title": title, "new_agent_created": True,
        "person_name": person_name, "person_email": person_email, "throwaway": throwaway})


# Send immediate message to user and record in conversation history
def send_message_to_user(message: str) -> ToolResult:
    """Record a user-visible reply in the conversation log."""
    log = get_conversation_log()
    log.record_reply(message)

    return ToolResult(
        success=True,
        payload={"status": "delivered"},
        user_message=message,
        recorded_reply=True,
    )


# Format and record email draft for user review
def send_draft(
    to: str,
    subject: str,
    body: str,
) -> ToolResult:
    """Record a draft update in the conversation log for the interaction agent."""
    log = get_conversation_log()

    message = f"To: {to}\nSubject: {subject}\n\n{body}"

    log.record_reply(message)
    logger.info(f"Draft recorded for: {to}")

    return ToolResult(
        success=True,
        payload={
            "status": "draft_recorded",
            "to": to,
            "subject": subject,
        },
        recorded_reply=True,
    )


# Record silent wait state to avoid duplicate responses
def wait(reason: str) -> ToolResult:
    """Wait silently and add a wait log entry that is not visible to the user."""
    log = get_conversation_log()
    
    # Record a dedicated wait entry so the UI knows to ignore it
    log.record_wait(reason)
    

    return ToolResult(
        success=True,
        payload={
            "status": "waiting",
            "reason": reason,
        },
        recorded_reply=True,
    )


# Return predefined tool schemas for LLM function calling
def get_tool_schemas(routing: Optional[Routing] = None):
    """Return OpenAI-compatible tool schemas.

    With the lookup on, hand-off takes an agent id limited to the agents approved for this
    turn, and creating an agent is its own tool.
    """
    if routing is None:
        return TOOL_SCHEMAS
    schemas = [schema for schema in TOOL_SCHEMAS if schema["function"]["name"] != "send_message_to_agent"]
    if routing.approved:
        schemas.insert(0, _handoff_schema(list(routing.approved)))
    if routing.may_create:
        schemas.insert(1 if routing.approved else 0, CREATE_AGENT_SCHEMA)
    return schemas


# Route tool calls to appropriate handlers with argument validation and error handling
def handle_tool_call(name: str, arguments: Any) -> ToolResult:
    """Handle tool calls from interaction agent."""
    try:
        if isinstance(arguments, str):
            args = json.loads(arguments) if arguments.strip() else {}
        elif isinstance(arguments, dict):
            args = arguments
        else:
            return ToolResult(success=False, payload={"error": "Invalid arguments format"})

        routing = current_routing()
        if routing is not None:
            if name == "send_message_to_agent":
                return hand_off_to_agent(routing, str(args.get("agent_id", "")), str(args.get("instructions", "")))
            if name == "create_agent":
                return create_agent(routing, **args)
        if name == "send_message_to_agent":
            return send_message_to_agent(**args)
        if name == "send_message_to_user":
            return send_message_to_user(**args)
        if name == "send_draft":
            return send_draft(**args)
        if name == "wait":
            return wait(**args)

        logger.warning("unexpected tool", extra={"tool": name})
        return ToolResult(success=False, payload={"error": f"Unknown tool: {name}"})
    except json.JSONDecodeError:
        return ToolResult(success=False, payload={"error": "Invalid JSON"})
    except TypeError as exc:
        return ToolResult(success=False, payload={"error": f"Missing or invalid arguments: {exc}"})
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("tool call failed", extra={"tool": name, "error": str(exc)})
        return ToolResult(success=False, payload={"error": "Failed to execute"})
