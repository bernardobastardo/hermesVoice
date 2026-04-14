"""Hermes Agent Conversation integration."""

from __future__ import annotations

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .const import CONF_API_KEY, CONF_BASE_URL, DOMAIN, LOGGER, normalize_base_url

PLATFORMS = (Platform.CONVERSATION,)
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

HermesConversationConfigEntry = ConfigEntry[aiohttp.ClientSession]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up Hermes Agent Conversation from YAML."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: HermesConversationConfigEntry) -> bool:
    """Set up Hermes Agent Conversation from a config entry."""
    session = async_get_clientsession(hass)
    base_url = normalize_base_url(entry.data[CONF_BASE_URL])
    headers: dict[str, str] = {"Content-Type": "application/json"}
    api_key = entry.data.get(CONF_API_KEY)
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    health_urls = [f"{base_url}/health", f"{base_url.removesuffix('/v1')}/health"]

    try:
        last_status = None
        for health_url in health_urls:
            async with session.get(
                health_url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                last_status = resp.status
                if resp.status in (200, 404):
                    entry.runtime_data = session
                    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
                    entry.async_on_unload(entry.add_update_listener(async_update_options))
                    return True
        raise ConfigEntryNotReady(
            f"Cannot reach Hermes API server: HTTP {last_status}"
        )
    except aiohttp.ClientError as err:
        raise ConfigEntryNotReady(
            f"Cannot connect to Hermes API server at {base_url}"
        ) from err


async def async_unload_entry(hass: HomeAssistant, entry: HermesConversationConfigEntry) -> bool:
    """Unload Hermes Agent Conversation."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_update_options(hass: HomeAssistant, entry: HermesConversationConfigEntry) -> None:
    """Reload the config entry when options change."""
    LOGGER.debug("Reloading Hermes Agent Conversation entry %s after options update", entry.entry_id)
    await hass.config_entries.async_reload(entry.entry_id)
