"""Conversation support for Hermes Agent through the API server."""

from __future__ import annotations

import json
import re
from collections.abc import AsyncGenerator
from typing import Literal

import aiohttp

from homeassistant.components import conversation
from homeassistant.components.conversation import (
    ChatLog,
    ConversationEntity,
    ConversationInput,
    ConversationResult,
    get_agent_manager,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import MATCH_ALL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, intent
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_ENABLE_SESSION_CONTINUITY,
    CONF_MODEL,
    CONF_PREFER_LOCAL,
    CONF_PROMPT,
    CONF_REQUEST_TIMEOUT,
    DEFAULT_ENABLE_SESSION_CONTINUITY,
    DEFAULT_MODEL,
    DEFAULT_NAME,
    DEFAULT_PREFER_LOCAL,
    DEFAULT_REQUEST_TIMEOUT,
    DOMAIN,
    LOGGER,
    SESSION_PREFIX,
    normalize_base_url,
)

_RE_THINK_BLOCK = re.compile(r"<think[\s\S]*?</think>", re.IGNORECASE)
_RE_THINK_OPEN = re.compile(r"</?think[^>]*>?", re.IGNORECASE)
_RE_FINAL_TAG = re.compile(r"</?final[^>]*>?", re.IGNORECASE)
_RE_THOUGHT_TAG = re.compile(r"</?thought[^>]*>?", re.IGNORECASE)
_RE_MD_BOLD = re.compile(r"\*\*(.+?)\*\*")
_RE_MD_ITALIC = re.compile(r"\*(.+?)\*")
_RE_MD_CODE = re.compile(r"`([^`]+)`")
_RE_MD_HEADING = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_RE_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_RE_MD_BULLET = re.compile(r"^\s*[-*+]\s+", re.MULTILINE)
_RE_MD_NUMBERED = re.compile(r"^\s*\d+\.\s+", re.MULTILINE)
_RE_MULTI_SPACE = re.compile(r"  +")
_RE_MULTI_NEWLINE = re.compile(r"\n{3,}")

_DEFAULT_PROMPT = (
    "You are responding through Home Assistant Assist. "
    "Keep replies brief, natural, and suitable for speech. "
    "Do not use markdown, code fences, XML-style thought tags, or long bullet lists unless explicitly asked."
)


def sanitize_for_tts(text: str) -> str:
    """Strip reasoning tags and markdown artifacts from model output."""
    if not text:
        return text
    text = _RE_THINK_BLOCK.sub("", text)
    text = _RE_THINK_OPEN.sub("", text)
    text = _RE_FINAL_TAG.sub("", text)
    text = _RE_THOUGHT_TAG.sub("", text)
    text = _RE_MD_BOLD.sub(r"\1", text)
    text = _RE_MD_ITALIC.sub(r"\1", text)
    text = _RE_MD_CODE.sub(r"\1", text)
    text = _RE_MD_HEADING.sub("", text)
    text = _RE_MD_LINK.sub(r"\1", text)
    text = _RE_MD_BULLET.sub("", text)
    text = _RE_MD_NUMBERED.sub("", text)
    text = re.sub(r"<[^>]*>", "", text)
    text = text.replace("<", "").replace(">", "")
    text = _RE_MULTI_SPACE.sub(" ", text)
    text = _RE_MULTI_NEWLINE.sub("\n", text)
    return text.strip()


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up conversation entities."""
    async_add_entities([HermesConversationEntity(config_entry, hass)])


async def _transform_stream(
    resp: aiohttp.ClientResponse,
) -> AsyncGenerator[conversation.AssistantContentDeltaDict]:
    """Parse SSE from Hermes chat completions and yield HA deltas."""
    yield {"role": "assistant"}
    buffer = ""
    current_event = "message"
    data_lines: list[str] = []

    async for chunk in resp.content.iter_any():
        buffer += chunk.decode("utf-8", errors="ignore")
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            line = line.rstrip("\r")

            if not line.strip():
                if data_lines:
                    data_str = "\n".join(data_lines).strip()
                    data_lines = []
                    event_name = current_event
                    current_event = "message"

                    if data_str == "[DONE]":
                        return
                    if event_name == "hermes.tool.progress":
                        continue

                    try:
                        payload = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    choices = payload.get("choices") or []
                    if not choices:
                        continue

                    choice = choices[0]
                    delta = choice.get("delta") or {}
                    content = delta.get("content")
                    if content:
                        cleaned = sanitize_for_tts(content)
                        if cleaned:
                            yield {"content": cleaned}
                    if choice.get("finish_reason") == "stop":
                        return
                continue

            if line.startswith(":"):
                continue
            if line.startswith("event:"):
                current_event = line[6:].strip() or "message"
                continue
            if line.startswith("data:"):
                data_lines.append(line[5:].strip())


class HermesConversationEntity(ConversationEntity):
    """Hermes-backed conversation agent for Home Assistant Assist."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_supports_streaming = True

    def __init__(self, entry: ConfigEntry, hass: HomeAssistant) -> None:
        self.entry = entry
        self._hass = hass
        self._attr_unique_id = entry.entry_id
        self._attr_device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title or DEFAULT_NAME,
            manufacturer="Hermes Agent",
            model="API Server",
            entry_type=dr.DeviceEntryType.SERVICE,
        )

        api_key = entry.data.get(CONF_API_KEY)
        self._auth_headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            self._auth_headers["Authorization"] = f"Bearer {api_key}"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        conversation.async_set_agent(self.hass, self.entry, self)

    async def async_will_remove_from_hass(self) -> None:
        conversation.async_unset_agent(self.hass, self.entry)
        await super().async_will_remove_from_hass()

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        return MATCH_ALL

    @property
    def _base_url(self) -> str:
        return normalize_base_url(self.entry.data[CONF_BASE_URL])

    @property
    def _model(self) -> str:
        return self.entry.options.get(
            CONF_MODEL, self.entry.data.get(CONF_MODEL, DEFAULT_MODEL)
        )

    @property
    def _prefer_local(self) -> bool:
        return self.entry.options.get(CONF_PREFER_LOCAL, DEFAULT_PREFER_LOCAL)

    @property
    def _request_timeout(self) -> int:
        return int(
            self.entry.options.get(CONF_REQUEST_TIMEOUT, DEFAULT_REQUEST_TIMEOUT)
        )

    @property
    def _enable_session_continuity(self) -> bool:
        return self.entry.options.get(
            CONF_ENABLE_SESSION_CONTINUITY,
            DEFAULT_ENABLE_SESSION_CONTINUITY,
        )

    @property
    def _headers(self) -> dict[str, str]:
        return dict(self._auth_headers)

    def _get_session_id(self, conversation_id: str | None) -> str | None:
        if not conversation_id or not self._enable_session_continuity:
            return None
        return f"{SESSION_PREFIX}:{conversation_id}"

    async def _try_local_intent(
        self, user_input: ConversationInput, chat_log: ChatLog
    ) -> tuple[ConversationResult | None, dict | None]:
        """Try local Home Assistant intent handling before Hermes fallback."""
        try:
            agent_manager = get_agent_manager(self.hass)
            default_agent = agent_manager.default_agent

            if default_agent is None:
                LOGGER.debug("No default HA conversation agent available for local processing")
                return None, None

            if default_agent is self:
                LOGGER.debug("Default HA conversation agent is Hermes itself; skipping local fallback")
                return None, {"local_intent_error": "recursive_default_agent"}

            conv_result = await default_agent._async_handle_message(user_input, chat_log)
            response = conv_result.response

            if response.response_type == intent.IntentResponseType.ERROR:
                error_context: dict[str, str] = {
                    "local_intent_error": str(response.error_code or "unknown")
                }
                if response.speech:
                    speech = response.speech.get("plain", {}).get("speech", "")
                    if speech:
                        error_context["error_message"] = speech
                return None, error_context

            has_speech = bool(
                response.speech and response.speech.get("plain", {}).get("speech")
            )
            if not has_speech and response.response_type != intent.IntentResponseType.ACTION_DONE:
                return None, {
                    "local_intent_error": "no_intent_match",
                    "original_text": user_input.text,
                }

            return conv_result, None
        except Exception as err:  # pragma: no cover - defensive HA runtime guard
            LOGGER.debug("Local intent processing failed: %s", err)
            return None, {"local_intent_error": "local_processing_exception"}

    async def _async_handle_message(
        self, user_input: ConversationInput, chat_log: ChatLog
    ) -> ConversationResult:
        local_error_context = None

        if self._prefer_local:
            local_result, local_error_context = await self._try_local_intent(
                user_input, chat_log
            )
            if local_result is not None:
                return local_result

        return await self._async_handle_hermes(
            user_input, chat_log, local_error_context=local_error_context
        )

    async def _async_handle_hermes(
        self,
        user_input: ConversationInput,
        chat_log: ChatLog,
        local_error_context: dict | None = None,
    ) -> ConversationResult:
        """Send the request to Hermes via the OpenAI-compatible API server."""
        session = async_get_clientsession(self.hass)
        prompt = self.entry.options.get(CONF_PROMPT)
        system_prompt = f"{_DEFAULT_PROMPT}\n\n{prompt.strip()}" if prompt else _DEFAULT_PROMPT

        user_message = user_input.text
        if local_error_context:
            user_message = (
                f"{user_input.text}\n\n"
                f"[Home Assistant local intent context: {json.dumps(local_error_context)}]"
            )

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "stream": True,
        }

        headers = self._headers
        session_id = self._get_session_id(user_input.conversation_id)
        if session_id:
            headers["X-Hermes-Session-Id"] = session_id

        url = f"{self._base_url}/chat/completions"
        timeout = aiohttp.ClientTimeout(
            total=self._request_timeout,
            sock_connect=10,
            sock_read=self._request_timeout,
        )

        try:
            resp = await session.post(url, json=payload, headers=headers, timeout=timeout)
        except aiohttp.ClientError as err:
            LOGGER.error("Connection error to Hermes API server: %s", err)
            return conversation.async_get_result_from_chat_log(user_input, chat_log)

        try:
            if resp.status >= 400:
                text = await resp.text()
                LOGGER.error("Hermes API server error %s: %s", resp.status, text)
                return conversation.async_get_result_from_chat_log(user_input, chat_log)

            async for _content in chat_log.async_add_delta_content_stream(
                user_input.agent_id, _transform_stream(resp)
            ):
                pass
        except Exception as err:  # pragma: no cover - defensive HA runtime guard
            LOGGER.error("Error while streaming response from Hermes: %s", err)
            return conversation.async_get_result_from_chat_log(user_input, chat_log)
        finally:
            resp.release()

        return conversation.async_get_result_from_chat_log(user_input, chat_log)
