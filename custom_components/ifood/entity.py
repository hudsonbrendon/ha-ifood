"""Entidade base do iFood."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import IfoodDataUpdateCoordinator


class IfoodEntity(CoordinatorEntity[IfoodDataUpdateCoordinator]):
    """Base: dispositivo "iFood" (conta) ou "iFood <loja>" (uma das lojas mais pedidas)."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: IfoodDataUpdateCoordinator, key: str, store: dict[str, Any] | None = None
    ) -> None:
        """Inicializa a entidade."""
        super().__init__(coordinator)
        account = coordinator.config_entry.unique_id
        self.store_id = store["id"] if store else None
        if store:
            self._attr_unique_id = f"{account}_{store['id']}_{key}"
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, f"{account}_{store['id']}")},
                manufacturer="iFood",
                model="Restaurante",
                name=f"iFood {store['name']}",
                entry_type=DeviceEntryType.SERVICE,
            )
        else:
            self._attr_unique_id = f"{account}_{key}"
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, str(account))},
                manufacturer="iFood",
                model="Conta",
                name="iFood",
                entry_type=DeviceEntryType.SERVICE,
                configuration_url="https://www.ifood.com.br/pedidos",
            )

    @property
    def store(self) -> dict[str, Any]:
        """Dados da loja desta entidade."""
        return (self.coordinator.data.get("stores") or {}).get(self.store_id) or {}
