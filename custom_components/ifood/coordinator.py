"""Coordinator do iFood: histórico, pedido em andamento e eventos de status."""

from __future__ import annotations

import time
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from . import logic
from .api import IfoodApiAuthenticationError, IfoodApiError
from .const import (
    ACTIVE_SCAN_INTERVAL_SECONDS,
    CONF_ACCESS_TOKEN,
    CONF_REFRESH_TOKEN,
    DOMAIN,
    EVENT_ORDER_UPDATED,
    HISTORY_REFRESH_SECONDS,
    IDLE_SCAN_INTERVAL_SECONDS,
    LOGGER,
    SILENT_EVENTS,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .api import IfoodApiClient
    from .data import IfoodConfigEntry


class IfoodDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polling adaptativo: 30 s com pedido aberto, 10 min sem."""

    config_entry: IfoodConfigEntry

    def __init__(self, hass: HomeAssistant, client: IfoodApiClient) -> None:
        """Inicializa o coordinator."""
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=IDLE_SCAN_INTERVAL_SECONDS),
        )
        self.client = client
        self._history: dict[str, dict[str, Any]] = {}
        self._history_at = 0.0
        self._account: dict[str, Any] = {}
        self._addresses: list[dict[str, Any]] = []
        self._seen_events: set[str] = set()
        self._last_status: dict[str, str] = {}
        self._active_ids: set[str] = set()
        self._primed = False

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            data = await self._fetch()
        except IfoodApiAuthenticationError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except IfoodApiError as err:
            raise UpdateFailed(str(err)) from err
        finally:
            self._persist_tokens()
        self.update_interval = timedelta(
            seconds=ACTIVE_SCAN_INTERVAL_SECONDS if data["active"] else IDLE_SCAN_INTERVAL_SECONDS
        )
        return data

    def _persist_tokens(self) -> None:
        """O refresh token pode girar: guarda o novo para sobreviver a restart."""
        entry = self.config_entry
        new = {CONF_REFRESH_TOKEN: self.client.refresh_token, CONF_ACCESS_TOKEN: self.client.access_token}
        if any(entry.data.get(k) != v for k, v in new.items()):
            self.hass.config_entries.async_update_entry(entry, data={**entry.data, **new})

    async def _fetch(self) -> dict[str, Any]:
        recent = await self.client.async_get_orders(0, 10)
        recent_ids = {o["id"] for o in recent if o.get("id")}
        just_closed = {i for i in self._active_ids if i in recent_ids and not logic.is_active(next(o for o in recent if o["id"] == i))}

        if not self._history or just_closed or time.monotonic() - self._history_at > HISTORY_REFRESH_SECONDS:
            self._history = {o["id"]: o for o in await self.client.async_get_all_orders() if o.get("id")}
            self._history_at = time.monotonic()
            self._account = await self.client.async_get_account()
            try:
                self._addresses = await self.client.async_get_addresses()
            except IfoodApiError as err:
                LOGGER.debug("endereços indisponíveis: %s", err)
        self._history.update({o["id"]: o for o in recent if o.get("id")})

        orders = sorted(self._history.values(), key=lambda o: o.get("createdAt") or "", reverse=True)
        active = [o for o in orders if logic.is_active(o)]
        details: dict[str, dict[str, Any]] = {}
        for order in active + [self._history[i] for i in just_closed if i in self._history]:
            oid = order["id"]
            events: list[dict[str, Any]] = []
            tracking = None
            try:
                events = await self.client.async_get_order_events(oid)
                if logic.is_active(order):
                    tracking = await self.client.async_get_order_tracking(oid)
            except IfoodApiAuthenticationError:
                raise
            except IfoodApiError as err:
                LOGGER.debug("eventos/rastreio de %s indisponíveis: %s", oid, err)
            details[oid] = {"events": events, "tracking": tracking}
            self._fire_events(order, events)

        # Fallback quando /events falha: muda o lastStatus, notifica igual.
        for order in orders[:10]:
            self._fire_status_change(order)

        self._active_ids = {o["id"] for o in active}
        self._primed = True
        return {
            "account": self._account,
            "addresses": self._addresses,
            "orders": orders,
            "active": active,
            "details": details,
        }

    def _fire(self, order: dict[str, Any], code: str, when: str | None, meta: dict[str, Any] | None) -> None:
        if not self._primed:
            return  # primeira carga: não notifica o passado
        s = logic.summary(order)
        self.hass.bus.async_fire(
            EVENT_ORDER_UPDATED,
            {
                **{k: s[k] for k in ("id", "numero", "restaurante", "total", "previsao_entrega", "codigo_entrega", "itens")},
                "evento": code,
                "descricao": logic.status_pt(code),
                "momento": when,
                "status_pedido": s["status"],
                "metadados": {k: v for k, v in (meta or {}).items() if k != "deliveryOperation" and k != "source"},
            },
        )

    def _fire_events(self, order: dict[str, Any], events: list[dict[str, Any]]) -> None:
        for ev in events:
            eid = ev.get("eventId")
            if not eid or eid in self._seen_events:
                continue
            self._seen_events.add(eid)
            if ev.get("value") in SILENT_EVENTS:
                continue
            self._fire(order, ev.get("value", ""), ev.get("timestamp"), ev.get("metadata"))
            # Evento com o mesmo nome do lastStatus já cobre o fallback.
            self._last_status[order["id"]] = order.get("lastStatus", "")

    def _fire_status_change(self, order: dict[str, Any]) -> None:
        oid, status = order.get("id"), order.get("lastStatus")
        if not oid or not status:
            return
        old = self._last_status.get(oid)
        self._last_status[oid] = status
        if self._primed and old is not None and old != status:
            self._fire(order, status, order.get("updatedAt"), None)
        elif self._primed and old is None and logic.is_active(order):
            self._fire(order, status, order.get("createdAt"), None)  # pedido novo
