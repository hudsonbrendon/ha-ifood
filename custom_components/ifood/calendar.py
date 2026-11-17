"""Calendário com o histórico de pedidos."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import logic
from .data import IfoodConfigEntry
from .entity import IfoodEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: IfoodConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Cria o calendário."""
    async_add_entities([IfoodOrdersCalendar(entry.runtime_data)])


class IfoodOrdersCalendar(IfoodEntity, CalendarEntity):
    """Um evento por pedido, do pedido até a entrega."""

    _attr_name = "Pedidos"
    _attr_icon = "mdi:food"

    def __init__(self, coordinator) -> None:
        """Inicializa."""
        super().__init__(coordinator, "calendario_pedidos")

    def _events(self) -> list[CalendarEvent]:
        events = []
        for order in self.coordinator.data["orders"]:
            start = logic.parse_dt(order.get("createdAt"))
            if not start:
                continue
            end = logic.parse_dt(order.get("closedAt")) or logic.parse_dt(
                (order.get("delivery") or {}).get("expectedDeliveryTime")
            )
            if not end or end <= start:
                end = start + timedelta(hours=1)
            s = logic.summary(order)
            total = f"R$ {s['total']:.2f}".replace(".", ",") if s["total"] is not None else ""
            events.append(
                CalendarEvent(
                    start=start,
                    end=end,
                    summary=f"iFood: {s['restaurante']}",
                    description="\n".join([f"{s['status']} · {total}", *s["itens"]]),
                    uid=f"ifood-{order['id']}",
                )
            )
        return events

    @property
    def event(self) -> CalendarEvent | None:
        """Pedido aberto ou o mais recente."""
        events = self._events()
        return events[0] if events else None

    async def async_get_events(self, hass: HomeAssistant, start_date: datetime, end_date: datetime) -> list[CalendarEvent]:
        """Eventos no intervalo."""
        return [e for e in self._events() if e.end > start_date and e.start < end_date]
