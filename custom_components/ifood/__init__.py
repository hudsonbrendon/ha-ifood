"""Integração iFood para Home Assistant: pedidos, status e histórico."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import IfoodApiClient
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_DEVICE_ID,
    CONF_PAYMENT_SECRET,
    CONF_REFRESH_TOKEN,
)
from .coordinator import IfoodDataUpdateCoordinator
from .data import IfoodConfigEntry

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.CALENDAR]


async def async_setup_entry(hass: HomeAssistant, entry: IfoodConfigEntry) -> bool:
    """Configura a partir do config entry."""
    client = IfoodApiClient(
        session=async_get_clientsession(hass),
        refresh_token=entry.data[CONF_REFRESH_TOKEN],
        device_id=entry.data[CONF_DEVICE_ID],
        access_token=entry.data.get(CONF_ACCESS_TOKEN),
        payment_secret=entry.data.get(CONF_PAYMENT_SECRET),
    )
    coordinator = IfoodDataUpdateCoordinator(hass, client)
    entry.runtime_data = coordinator
    await coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: IfoodConfigEntry) -> bool:
    """Descarrega o config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
