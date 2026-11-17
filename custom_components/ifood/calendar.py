"""Calendário com o histórico de pedidos."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import logic
from .data import IfoodConfigEntry
from .entity import IfoodEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: IfoodConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Cria o calendário."""
    async_add_entities([IfoodOrdersCalendar(entry.runtime_data), IfoodVouchersCalendar(entry.runtime_data)])


class IfoodOrdersCalendar(IfoodEntity, CalendarEntity):
    """Um evento por pedido, do pedido até a entrega."""

    _attr_name = "Pedidos"
    _attr_icon = "mdi:food"

    def __init__(self, coordinator) -> None:
        """Inicializa."""
        super().__init__(coordinator, "calendario_pedidos")

    def _events(self) -> list[CalendarEvent]:
        # Recalcula só quando o coordinator troca os dados (HA lê `event` várias vezes).
        if getattr(self, "_cache_for", None) is not self.coordinator.data:
            self._cache = self._build()
            self._cache_for = self.coordinator.data
        return self._cache

    def _build(self) -> list[CalendarEvent]:
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

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Eventos no intervalo."""
        return [e for e in self._events() if e.end > start_date and e.start < end_date]


class IfoodVouchersCalendar(IfoodEntity, CalendarEntity):
    """Vencimento de cada cupom disponível (evento de 1 h terminando no vencimento)."""

    _attr_name = "Cupons"
    _attr_icon = "mdi:ticket-percent"

    def __init__(self, coordinator) -> None:
        """Inicializa."""
        super().__init__(coordinator, "calendario_cupons")

    def _events(self) -> list[CalendarEvent]:
        # Recalcula só quando o coordinator troca os dados (HA lê `event` várias vezes).
        if getattr(self, "_cache_for", None) is not self.coordinator.data:
            self._cache = self._build()
            self._cache_for = self.coordinator.data
        return self._cache

    def _build(self) -> list[CalendarEvent]:
        events = []
        for v in logic.vouchers_available(self.coordinator.data.get("vouchers") or [], dt_util.utcnow()):
            s = logic.voucher_summary(v)
            end = logic.parse_dt(s["vence_em"])
            if not end:
                continue
            val = f" (até R$ {s['valor_max']:.2f})".replace(".", ",") if s["valor_max"] is not None else ""
            events.append(
                CalendarEvent(
                    start=end - timedelta(hours=1),
                    end=end,
                    summary=f"Cupom vence: {s['descricao']}{val}",
                    description="\n".join([s["categoria"] or "", *s["regras"]]),
                    uid=f"ifood-cupom-{v.get('id')}",
                )
            )
        return events

    @property
    def event(self) -> CalendarEvent | None:
        """Próximo vencimento."""
        events = self._events()
        return events[0] if events else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Eventos no intervalo."""
        return [e for e in self._events() if e.end > start_date and e.start < end_date]
