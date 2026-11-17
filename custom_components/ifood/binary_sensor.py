"""Binary sensors: pedido aberto, Clube ativo e loja aberta."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import logic
from .const import TOP_MERCHANTS
from .data import IfoodConfigEntry
from .entity import IfoodEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: IfoodConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Cria os binary sensors."""
    c = entry.runtime_data
    entities: list[BinarySensorEntity] = [IfoodOrderOpen(c), IfoodClub(c)]
    entities += [IfoodStoreOpen(c, s) for s in logic.top_merchants(c.data["orders"], TOP_MERCHANTS)]
    async_add_entities(entities)


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


class IfoodClub(IfoodEntity, BinarySensorEntity):
    """Assinatura do Clube iFood, lida das tags internas da conta (estimativa)."""

    _attr_name = "Clube iFood"
    _attr_icon = "mdi:crown"

    def __init__(self, coordinator) -> None:
        """Inicializa."""
        super().__init__(coordinator, "clube_ativo")

    @property
    def is_on(self) -> bool | None:
        """Assinante."""
        me = self.coordinator.data.get("me")
        return logic.club_info(me)["ativo"] if me else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Detalhes."""
        return {**logic.club_info(self.coordinator.data.get("me") or {}), "fonte": "tags internas do iFood (estimado)"}


class IfoodStoreOpen(IfoodEntity, BinarySensorEntity):
    """Loja aceitando pedido agora."""

    _attr_name = "Aberto"
    _attr_icon = "mdi:storefront"

    def __init__(self, coordinator, store: dict[str, Any]) -> None:
        """Inicializa."""
        super().__init__(coordinator, "aberto", store)

    @property
    def is_on(self) -> bool | None:
        """Aberta."""
        live = self.store.get("live")
        return bool(live.get("available")) if live else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Horários e agendamento."""
        live = self.store.get("live") or {}
        return {
            "horarios": logic.shifts_text((self.store.get("extra") or {}).get("shifts") or []),
            "aceita_agendamento": live.get("availableForScheduling"),
            "abre_em_breve": live.get("availableOrHasSlotsShortly"),
        }
