"""Config flow for Hermes Agent Conversation."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TemplateSelector,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_ENABLE_SESSION_CONTINUITY,
    CONF_MODEL,
    CONF_PREFER_LOCAL,
    CONF_PROMPT,
    CONF_REQUEST_TIMEOUT,
    DEFAULT_BASE_URL,
    DEFAULT_ENABLE_SESSION_CONTINUITY,
    DEFAULT_MODEL,
    DEFAULT_NAME,
    DEFAULT_PREFER_LOCAL,
    DEFAULT_REQUEST_TIMEOUT,
    DOMAIN,
    normalize_base_url,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_BASE_URL, default=DEFAULT_BASE_URL): TextSelector(
            TextSelectorConfig(type=TextSelectorType.URL)
        ),
        vol.Required(CONF_API_KEY): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
        vol.Optional(CONF_MODEL, default=DEFAULT_MODEL): str,
    }
)


def _options_schema(config_entry: ConfigEntry) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(CONF_PROMPT): TemplateSelector(),
            vol.Optional(
                CONF_MODEL,
                default=config_entry.options.get(
                    CONF_MODEL,
                    config_entry.data.get(CONF_MODEL, DEFAULT_MODEL),
                ),
            ): str,
            vol.Optional(
                CONF_PREFER_LOCAL,
                default=config_entry.options.get(CONF_PREFER_LOCAL, DEFAULT_PREFER_LOCAL),
            ): BooleanSelector(),
            vol.Optional(
                CONF_ENABLE_SESSION_CONTINUITY,
                default=config_entry.options.get(
                    CONF_ENABLE_SESSION_CONTINUITY,
                    DEFAULT_ENABLE_SESSION_CONTINUITY,
                ),
            ): BooleanSelector(),
            vol.Optional(
                CONF_REQUEST_TIMEOUT,
                default=config_entry.options.get(
                    CONF_REQUEST_TIMEOUT,
                    DEFAULT_REQUEST_TIMEOUT,
                ),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=15,
                    max=300,
                    mode=NumberSelectorMode.BOX,
                    step=5,
                )
            ),
        }
    )


async def validate_input(data: dict[str, Any], session) -> dict[str, str]:
    """Validate user input by calling Hermes chat completions."""
    base_url = normalize_base_url(data[CONF_BASE_URL])
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {data[CONF_API_KEY]}",
    }
    payload = {
        "model": data.get(CONF_MODEL, DEFAULT_MODEL),
        "messages": [{"role": "user", "content": "Reply with only the word pong."}],
        "max_tokens": 8,
        "stream": False,
    }

    try:
        async with session.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status == 401:
                raise InvalidAuth
            if resp.status >= 400:
                text = await resp.text()
                _LOGGER.error("Hermes API server returned %s: %s", resp.status, text)
                raise CannotConnect
    except aiohttp.ClientError as err:
        _LOGGER.error("Cannot connect to Hermes API server: %s", err)
        raise CannotConnect from err

    return {"title": DEFAULT_NAME}


class HermesAgentConversationConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Hermes Agent Conversation."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            normalized_url = normalize_base_url(user_input[CONF_BASE_URL])
            user_input = {**user_input, CONF_BASE_URL: normalized_url}
            await self.async_set_unique_id(normalized_url)
            self._abort_if_unique_id_configured()

            try:
                info = await validate_input(
                    user_input, async_get_clientsession(self.hass)
                )
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception during Hermes validation")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, user_input
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> "HermesAgentConversationOptionsFlowHandler":
        """Return the options flow for this config entry."""
        return HermesAgentConversationOptionsFlowHandler(config_entry)


class HermesAgentConversationOptionsFlowHandler(OptionsFlow):
    """Handle Hermes Agent Conversation options."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                _options_schema(self.config_entry),
                {
                    CONF_PROMPT: self.config_entry.options.get(CONF_PROMPT),
                    CONF_MODEL: self.config_entry.options.get(
                        CONF_MODEL,
                        self.config_entry.data.get(CONF_MODEL, DEFAULT_MODEL),
                    ),
                    CONF_PREFER_LOCAL: self.config_entry.options.get(
                        CONF_PREFER_LOCAL,
                        DEFAULT_PREFER_LOCAL,
                    ),
                    CONF_ENABLE_SESSION_CONTINUITY: self.config_entry.options.get(
                        CONF_ENABLE_SESSION_CONTINUITY,
                        DEFAULT_ENABLE_SESSION_CONTINUITY,
                    ),
                    CONF_REQUEST_TIMEOUT: self.config_entry.options.get(
                        CONF_REQUEST_TIMEOUT,
                        DEFAULT_REQUEST_TIMEOUT,
                    ),
                },
            ),
        )


class CannotConnect(Exception):
    """Raised when the integration cannot connect to Hermes."""


class InvalidAuth(Exception):
    """Raised when the provided API key is invalid."""
