"""Constants for the Hermes Agent conversation integration."""

from __future__ import annotations

import logging

DOMAIN = "hermes_agent_conversation"
LOGGER = logging.getLogger(__package__)

CONF_BASE_URL = "base_url"
CONF_API_KEY = "api_key"
CONF_MODEL = "model"
CONF_PROMPT = "prompt"
CONF_PREFER_LOCAL = "prefer_local"
CONF_REQUEST_TIMEOUT = "request_timeout"
CONF_ENABLE_SESSION_CONTINUITY = "enable_session_continuity"
CONF_SESSION_RESUME_TIMEOUT = "session_resume_timeout"

DEFAULT_NAME = "Hermes Agent Conversation"
DEFAULT_BASE_URL = "http://127.0.0.1:8642/v1"
DEFAULT_MODEL = "hermes-agent"
DEFAULT_REQUEST_TIMEOUT = 90
DEFAULT_PREFER_LOCAL = True
DEFAULT_ENABLE_SESSION_CONTINUITY = True
DEFAULT_SESSION_RESUME_TIMEOUT = 300

SESSION_PREFIX = "ha-assist"


def normalize_base_url(base_url: str) -> str:
    """Normalize a Hermes API server URL to its /v1 base path."""
    url = (base_url or DEFAULT_BASE_URL).strip().rstrip("/")
    if not url.endswith("/v1"):
        if url.endswith("/v1/"):
            url = url[:-1]
        elif url.endswith("/chat/completions"):
            url = url[: -len("/chat/completions")]
        elif url.endswith("/v1/chat/completions"):
            url = url[: -len("/chat/completions")]
        elif url.endswith("/health"):
            url = url[: -len("/health")] + "/v1"
        else:
            url = f"{url}/v1"
    return url
