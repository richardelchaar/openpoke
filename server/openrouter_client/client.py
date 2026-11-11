from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional

import httpx

from ..config import get_settings

OpenRouterBaseURL = "https://openrouter.ai/api/v1"

# Without a cap OpenRouter reserves the model's full output limit against the
# account balance, and refuses the request when the balance can't cover it.
DEFAULT_MAX_TOKENS = 4096

MAX_ATTEMPTS = 3
RETRY_STATUS = {429, 500, 502, 503, 504}


class OpenRouterError(RuntimeError):
    """Raised when the OpenRouter API returns an error response."""


def _headers(*, api_key: Optional[str] = None) -> Dict[str, str]:
    settings = get_settings()
    key = (api_key or settings.openrouter_api_key or "").strip()
    if not key:
        raise OpenRouterError("Missing OpenRouter API key")

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    return headers


def _cached(text: str) -> List[Dict[str, Any]]:
    """Text marked as a point the provider may cache the prompt up to."""
    return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]


def _build_messages(messages: List[Dict[str, Any]], system: Optional[str]) -> List[Dict[str, Any]]:
    """Put the system prompt first and mark the two stable parts of the prompt for caching.

    The system prompt is the same on every call, and the first message is the same on
    every step of one tool loop, so later calls can read both from the cache.
    """
    built = [dict(message) for message in messages]
    if built and isinstance(built[0].get("content"), str) and built[0]["content"]:
        built[0]["content"] = _cached(built[0]["content"])
    if system:
        return [{"role": "system", "content": _cached(system)}, *built]
    return built


def _handle_response_error(exc: httpx.HTTPStatusError) -> None:
    response = exc.response
    detail: str
    try:
        payload = response.json()
        detail = payload.get("error") or payload.get("message") or json.dumps(payload)
    except Exception:
        detail = response.text
    raise OpenRouterError(f"OpenRouter request failed ({response.status_code}): {detail}") from exc


async def request_chat_completion(
    *,
    model: str,
    messages: List[Dict[str, str]],
    system: Optional[str] = None,
    api_key: Optional[str] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    base_url: str = OpenRouterBaseURL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: Optional[float] = None,
    tool_choice: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Request a chat completion and return the raw JSON payload.

    `tool_choice` forces a call to one named tool, which is how a caller gets output in a
    fixed shape.
    """

    payload: Dict[str, object] = {
        "model": model,
        "messages": _build_messages(messages, system),
        "stream": False,
        "max_tokens": max_tokens,
    }
    if tools:
        payload["tools"] = tools
    if tool_choice:
        payload["tool_choice"] = tool_choice
    if temperature is not None:
        payload["temperature"] = temperature

    url = f"{base_url.rstrip('/')}/chat/completions"

    # A dropped connection, a timeout, a rate limit or a server error is retried; anything
    # else (a bad request, no credit) is not going to change on a second try.
    last_error: Optional[Exception] = None
    async with httpx.AsyncClient() as client:
        for attempt in range(MAX_ATTEMPTS):
            if attempt:
                await asyncio.sleep(2 ** (attempt - 1))
            try:
                response = await client.post(url, headers=_headers(api_key=api_key), json=payload, timeout=60.0)
            except httpx.HTTPError as exc:
                last_error = OpenRouterError(f"OpenRouter request failed: {exc}")
                continue
            if response.status_code in RETRY_STATUS:
                last_error = OpenRouterError(f"OpenRouter request failed ({response.status_code})")
                continue
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                _handle_response_error(exc)
            return response.json()

    raise last_error or OpenRouterError("OpenRouter request failed: unknown error")


__all__ = ["OpenRouterError", "request_chat_completion", "OpenRouterBaseURL"]
