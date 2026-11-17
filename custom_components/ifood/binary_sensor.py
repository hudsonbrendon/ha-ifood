"""Binary sensor: tem pedido aberto agora."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .data import IfoodConfigEntry
from .entity import IfoodEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: IfoodConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Cria o binary sensor."""
    async_add_entities([IfoodOrderOpen(entry.runtime_data)])


class IfoodOrderOpen(IfoodEntity, BinarySensorEntity):
    """Ligado enquanto houver pedido não concluído/recusado/cancelado."""

    _attr_name = "Pedido aberto"
    _attr_icon = "mdi:moped"

    def __init__(self, coordinator) -> None:
        """Inicializa."""
        super().__init__(coordinator, "pedido_aberto")

    @property
    def is_on(self) -> bool:
        """Há pedido aberto."""
        return bool(self.coordinator.data["active"])
