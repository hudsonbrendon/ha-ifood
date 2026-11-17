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
    EVENT_NEW_VOUCHER,
    EVENT_ORDER_UPDATED,
    EXTRAS_REFRESH_SECONDS,
    HISTORY_REFRESH_SECONDS,
    IDLE_SCAN_INTERVAL_SECONDS,
    LOGGER,
    MERCHANT_REFRESH_SECONDS,
    SILENT_EVENTS,
    TOP_MERCHANTS,
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
        self._extras: dict[str, Any] = {"vouchers": [], "me": {}, "wallet": [], "stores": {}}
        self._extras_at = 0.0
        self._live_at = 0.0
        self._seen_vouchers: set[str] | None = None

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
        await self._fetch_extras(orders)
        self._primed = True
        return {
            "account": self._account,
            "addresses": self._addresses,
            "orders": orders,
            "active": active,
            "details": details,
            **self._extras,
        }

    async def _safe(self, coro: Any, default: Any) -> Any:
        """Extras não derrubam o update: erro (exceto auth) mantém o valor anterior."""
        try:
            return await coro
        except IfoodApiAuthenticationError:
            raise
        except IfoodApiError as err:
            LOGGER.debug("extra indisponível: %s", err)
            return default

    async def _fetch_extras(self, orders: list[dict[str, Any]]) -> None:
        """Cupons/Clube/carteira/lojas: hora em hora; loja ao vivo: 10 min."""
        coords = logic.last_delivery_coords(orders)
        now = time.monotonic()
        ex = self._extras
        tops = logic.top_merchants(orders, TOP_MERCHANTS)
        if now - self._extras_at > EXTRAS_REFRESH_SECONDS or not self._extras_at:
            self._extras_at = now
            if coords:
                ex["vouchers"] = await self._safe(self.client.async_get_vouchers(*coords), ex["vouchers"])
                self._fire_new_vouchers(ex["vouchers"])
            ex["me"] = await self._safe(self.client.async_get_me(), ex["me"])
            ex["wallet"] = await self._safe(self.client.async_get_wallet_accounts(), ex["wallet"])
            for m in tops:
                st = ex["stores"].setdefault(m["id"], {"info": m})
                st["extra"] = await self._safe(self.client.async_get_merchant_extra(m["id"]), st.get("extra"))
                st["items"] = await self._safe(self.client.async_get_my_items(m["id"]), st.get("items") or [])
                st["reviews"] = await self._safe(
                    self.client.async_get_review_averages(m["id"]), st.get("reviews") or []
                )
        if coords and (now - self._live_at > MERCHANT_REFRESH_SECONDS or not self._live_at):
            self._live_at = now
            for m in tops:
                st = ex["stores"].setdefault(m["id"], {"info": m})
                st["live"] = await self._safe(self.client.async_get_merchant(m["id"], *coords), st.get("live"))

    def _fire_new_vouchers(self, vouchers: list[dict[str, Any]]) -> None:
        ids = {v["id"] for v in vouchers if v.get("id")}
        if self._seen_vouchers is not None:
            for v in vouchers:
                if v.get("id") not in self._seen_vouchers and v.get("status") == "AVAILABLE":
                    self.hass.bus.async_fire(EVENT_NEW_VOUCHER, logic.voucher_summary(v))
        if ids:  # lista vazia (erro) não zera o que já foi visto
            self._seen_vouchers = (self._seen_vouchers or set()) | ids

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
