"""Simplified configuration management."""

import os
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field


def _load_env_file() -> None:
    """Load .env from root directory if present."""
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.is_file():
        return
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key, value = stripped.split("=", 1)
                key, value = key.strip(), value.strip().strip("'\"")
                if key and value and key not in os.environ:
                    os.environ[key] = value
    except Exception:
        pass


_load_env_file()


DEFAULT_APP_NAME = "OpenPoke Server"
DEFAULT_APP_VERSION = "0.3.0"
DEFAULT_MODEL = os.getenv("OPENPOKE_MODEL", "anthropic/claude-haiku-5.5")


def get_data_dir() -> Path:
    """Directory for everything the server stores on disk."""
    override = os.getenv("OPENPOKE_DATA_DIR")
    return Path(override) if override else Path(__file__).resolve().parent / "data"


def _env_int(name: str, fallback: int) -> int:
    try:
        return int(os.getenv(name, str(fallback)))
    except (TypeError, ValueError):
        return fallback


def _env_float(name: str, fallback: float) -> float:
    try:
        return float(os.getenv(name, str(fallback)))
    except (TypeError, ValueError):
        return fallback


class Settings(BaseModel):
    """Application settings with lightweight env fallbacks."""

    # App metadata
    app_name: str = Field(default=DEFAULT_APP_NAME)
    app_version: str = Field(default=DEFAULT_APP_VERSION)

    # Server runtime
    server_host: str = Field(default=os.getenv("OPENPOKE_HOST", "0.0.0.0"))
    server_port: int = Field(default=_env_int("OPENPOKE_PORT", 8001))

    # LLM model selection: OPENPOKE_MODEL sets every role, the per-role vars override it
    interaction_agent_model: str = Field(default=os.getenv("OPENPOKE_INTERACTION_MODEL", DEFAULT_MODEL))
    execution_agent_model: str = Field(default=os.getenv("OPENPOKE_EXECUTION_MODEL", DEFAULT_MODEL))
    execution_agent_search_model: str = Field(default=os.getenv("OPENPOKE_SEARCH_MODEL", DEFAULT_MODEL))
    summarizer_model: str = Field(default=os.getenv("OPENPOKE_SUMMARIZER_MODEL", DEFAULT_MODEL))
    email_classifier_model: str = Field(default=os.getenv("OPENPOKE_CLASSIFIER_MODEL", DEFAULT_MODEL))

    # Routing: how the orchestrator finds and chooses an agent.
    #   lookup   none = every agent's name in the prompt (the original)
    #            records = a handful of candidates found by searching agents' work records
    #   decider  who decides whether to route, create or ask:
    #            orchestrator | told_to_ask | code_rule | judge
    #   prompt   v1 = the original orchestrator prompt, v2 = the rewrite
    #   ask      how readily to ask when one candidate fits and another might: strict | balanced | loose
    routing_lookup: str = Field(default=os.getenv("OPENPOKE_LOOKUP", "none"))
    routing_decider: str = Field(default=os.getenv("OPENPOKE_DECIDER", "orchestrator"))
    routing_prompt: str = Field(default=os.getenv("OPENPOKE_PROMPT", "v1"))
    routing_ask: str = Field(default=os.getenv("OPENPOKE_ASK", "balanced"))
    routing_ask_margin: float = Field(default=_env_float("OPENPOKE_ASK_MARGIN", 0.25))
    judge_model: str = Field(default=os.getenv("OPENPOKE_JUDGE_MODEL", DEFAULT_MODEL))

    # Credentials / integrations
    openrouter_api_key: Optional[str] = Field(default=os.getenv("OPENROUTER_API_KEY"))
    composio_gmail_auth_config_id: Optional[str] = Field(default=os.getenv("COMPOSIO_GMAIL_AUTH_CONFIG_ID"))
    composio_api_key: Optional[str] = Field(default=os.getenv("COMPOSIO_API_KEY"))

    # HTTP behaviour
    cors_allow_origins_raw: str = Field(default=os.getenv("OPENPOKE_CORS_ALLOW_ORIGINS", "*"))
    enable_docs: bool = Field(default=os.getenv("OPENPOKE_ENABLE_DOCS", "1") != "0")
    docs_url: Optional[str] = Field(default=os.getenv("OPENPOKE_DOCS_URL", "/docs"))

    # Summarisation controls
    conversation_summary_threshold: int = Field(default=100)
    conversation_summary_tail_size: int = Field(default=10)

    @property
    def cors_allow_origins(self) -> List[str]:
        """Parse CORS origins from comma-separated string."""
        if self.cors_allow_origins_raw.strip() in {"", "*"}:
            return ["*"]
        return [origin.strip() for origin in self.cors_allow_origins_raw.split(",") if origin.strip()]

    @property
    def resolved_docs_url(self) -> Optional[str]:
        """Return documentation URL when docs are enabled."""
        return (self.docs_url or "/docs") if self.enable_docs else None

    @property
    def summarization_enabled(self) -> bool:
        """Flag indicating conversation summarisation is active."""
        return self.conversation_summary_threshold > 0


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
