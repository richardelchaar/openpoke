"""Interaction agent helpers for prompt construction."""

from html import escape
from pathlib import Path
from typing import Dict, List, Optional

from ...config import get_settings
from ...routing.pipeline import Routing, render_candidates, render_contacts
from ...services.execution import get_agent_roster

_dir = Path(__file__).parent
SYSTEM_PROMPT = (_dir / "system_prompt.md").read_text(encoding="utf-8").strip()


def _part(name: str) -> str:
    return (_dir / name).read_text(encoding="utf-8").rstrip()


# Pick the system prompt for the configured routing mode
def build_system_prompt() -> str:
    """Return the system prompt for the interaction agent.

    v1 is the original prompt. v2 is the rewrite, with the section on agents chosen to
    match how agents are found (every name, or candidates from the lookup) and who
    decides whether to ask.
    """
    settings = get_settings()
    if settings.routing_prompt != "v2":
        return SYSTEM_PROMPT
    if settings.routing_lookup == "records":
        section = _part("agent_tools_records.md")
        if settings.routing_explain:
            section += "\n" + _part("agent_tools_explain.md")
        if settings.routing_decider == "told_to_ask":
            section += "\n" + _part("agent_tools_ask_rule.md")
        elif settings.routing_decider in ("code_rule", "judge"):
            section += "\n" + _part("agent_tools_decision.md")
    else:
        section = _part("agent_tools_names.md")
    return _part("system_prompt_v2.md").replace("{{AGENT_TOOLS}}", section).strip()


# Build structured message with conversation history, active agents, and current turn
def prepare_message_with_history(
    latest_text: str,
    transcript: str,
    message_type: str = "user",
    routing: Optional[Routing] = None,
) -> List[Dict[str, str]]:
    """Compose a message that bundles history, the agents to choose from, and the latest turn."""
    sections: List[str] = []

    sections.append(_render_conversation_history(transcript))
    if routing is None:
        sections.append(f"<active_agents>\n{_render_active_agents()}\n</active_agents>")
    else:
        sections.append(render_candidates(routing))
        contacts = render_contacts(routing)
        if contacts:
            sections.append(contacts)
        if routing.note:
            sections.append(f"<routing_decision>\n{routing.note}\n</routing_decision>")
    sections.append(_render_current_turn(latest_text, message_type))

    content = "\n\n".join(sections)
    return [{"role": "user", "content": content}]


# Format conversation transcript into XML tags for LLM context
def _render_conversation_history(transcript: str) -> str:
    history = transcript.strip()
    if not history:
        history = "None"
    return f"<conversation_history>\n{history}\n</conversation_history>"


# Format currently active execution agents into XML tags for LLM awareness
def _render_active_agents() -> str:
    roster = get_agent_roster()
    roster.load()
    agents = roster.get_agents()

    if not agents:
        return "None"

    rendered: List[str] = []
    for agent_name in agents:
        name = escape(agent_name or "agent", quote=True)
        rendered.append(f'<agent name="{name}" />')

    return "\n".join(rendered)


# Wrap the current message in appropriate XML tags based on sender type
def _render_current_turn(latest_text: str, message_type: str) -> str:
    tag = "new_agent_message" if message_type == "agent" else "new_user_message"
    body = latest_text.strip()
    return f"<{tag}>\n{body}\n</{tag}>"
