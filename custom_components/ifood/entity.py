"""Entidade base do iFood."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import IfoodDataUpdateCoordinator


class IfoodEntity(CoordinatorEntity[IfoodDataUpdateCoordinator]):
    """Base: um dispositivo "iFood" por conta."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: IfoodDataUpdateCoordinator, key: str) -> None:
        """Inicializa a entidade."""
        super().__init__(coordinator)
        account = coordinator.config_entry.unique_id
        self._attr_unique_id = f"{account}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(account))},
            manufacturer="iFood",
            model="Conta",
            name="iFood",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://www.ifood.com.br/pedidos",
        )
