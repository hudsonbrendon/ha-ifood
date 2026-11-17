"""Sensores do iFood."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import logic
from .data import IfoodConfigEntry
from .entity import IfoodEntity

BRL = "R$"


def _stats(d: dict[str, Any]) -> dict[str, Any]:
    return logic.stats(d["orders"], dt_util.now())


def _active(d: dict[str, Any]) -> dict[str, Any] | None:
    return d["active"][0] if d["active"] else None


def _last(d: dict[str, Any]) -> dict[str, Any] | None:
    return d["orders"][0] if d["orders"] else None


def _timeline(d: dict[str, Any], order: dict[str, Any]) -> list[str]:
    out = []
    for ev in (d["details"].get(order["id"]) or {}).get("events") or []:
        dt = logic.parse_dt(ev.get("timestamp"))
        hora = dt_util.as_local(dt).strftime("%H:%M") if dt else "--:--"
        out.append(f"{hora} {logic.status_pt(ev.get('value'))}")
    return out


def _active_attrs(d: dict[str, Any]) -> dict[str, Any]:
    order = _active(d)
    if not order:
        return {"pedidos_em_andamento": 0}
    return {
        **logic.summary(order),
        "pedidos_em_andamento": len(d["active"]),
        "linha_do_tempo": _timeline(d, order),
        "rastreio": (d["details"].get(order["id"]) or {}).get("tracking"),
    }


def _dt(value: Any):
    dt = logic.parse_dt(value)
    return dt_util.as_utc(dt) if dt else None


@dataclass(frozen=True, kw_only=True)
class IfoodSensorDescription(SensorEntityDescription):
    """Sensor com função de valor e de atributos."""

    value_fn: Callable[[dict[str, Any]], Any]
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


def _money_sensor(key: str, name: str, icon: str = "mdi:cash") -> IfoodSensorDescription:
    return IfoodSensorDescription(
        key=key,
        name=name,
        icon=icon,
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=BRL,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        value_fn=lambda d: _stats(d)[key],
    )


def _count_sensor(key: str, name: str, icon: str = "mdi:shopping") -> IfoodSensorDescription:
    return IfoodSensorDescription(
        key=key,
        name=name,
        icon=icon,
        native_unit_of_measurement="pedidos",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda d: _stats(d)[key],
    )


SENSORS: tuple[IfoodSensorDescription, ...] = (
    IfoodSensorDescription(
        key="pedido_em_andamento",
        name="Pedido em andamento",
        icon="mdi:moped",
        value_fn=lambda d: logic.status_pt(_active(d)["lastStatus"]) if _active(d) else "Nenhum",
        attrs_fn=_active_attrs,
    ),
    IfoodSensorDescription(
        key="previsao_entrega",
        name="Previsão de entrega",
        icon="mdi:clock-fast",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: _dt(logic.summary(_active(d))["previsao_entrega"]) if _active(d) else None,
        attrs_fn=lambda d: {"ate": logic.summary(_active(d))["previsao_entrega_ate"]} if _active(d) else {},
    ),
    IfoodSensorDescription(
        key="codigo_entrega",
        name="Código de entrega",
        icon="mdi:numeric",
        value_fn=lambda d: logic.delivery_code(_active(d)) if _active(d) else None,
    ),
    IfoodSensorDescription(
        key="ultimo_pedido",
        name="Último pedido",
        icon="mdi:food",
        value_fn=lambda d: (_last(d).get("merchant") or {}).get("name") if _last(d) else None,
        attrs_fn=lambda d: logic.summary(_last(d)) if _last(d) else {},
    ),
    IfoodSensorDescription(
        key="ultimo_pedido_data",
        name="Data do último pedido",
        icon="mdi:calendar-clock",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: _dt(_last(d).get("createdAt")) if _last(d) else None,
    ),
    IfoodSensorDescription(
        key="ultimo_pedido_valor",
        name="Valor do último pedido",
        icon="mdi:cash",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=BRL,
        suggested_display_precision=2,
        value_fn=lambda d: logic.total(_last(d)) if _last(d) else None,
    ),
    _money_sensor("gasto_mes", "Gasto no mês"),
    _count_sensor("pedidos_mes", "Pedidos no mês"),
    _money_sensor("gasto_ano", "Gasto no ano"),
    _count_sensor("pedidos_ano", "Pedidos no ano"),
    _money_sensor("gasto_total", "Gasto total"),
    _count_sensor("total_pedidos", "Total de pedidos"),
    _count_sensor("pedidos_recusados", "Pedidos recusados", "mdi:cancel"),
    _money_sensor("economia_mes", "Economia no mês", "mdi:ticket-percent"),
    _money_sensor("economia_total", "Economia total", "mdi:ticket-percent"),
    _money_sensor("taxa_entrega_mes", "Taxas de entrega no mês", "mdi:truck-delivery"),
    IfoodSensorDescription(
        key="ticket_medio",
        name="Ticket médio",
        icon="mdi:cash-multiple",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=BRL,
        suggested_display_precision=2,
        value_fn=lambda d: _stats(d)["ticket_medio"],
    ),
    IfoodSensorDescription(
        key="restaurante_favorito",
        name="Restaurante favorito",
        icon="mdi:heart",
        value_fn=lambda d: _stats(d)["restaurante_favorito"],
        attrs_fn=lambda d: {"mais_pedidos": _stats(d)["top_restaurantes"]},
    ),
    IfoodSensorDescription(
        key="cliente_desde",
        name="Cliente desde",
        icon="mdi:account-clock",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: _dt(d["account"].get("registration_date")),
        attrs_fn=lambda d: {
            "nome": d["account"].get("name"),
            "enderecos": [
                ", ".join(
                    str(p)
                    for p in (a.get("streetName"), a.get("streetNumber"), a.get("neighborhood"), a.get("city"))
                    if p
                )
                for a in d.get("addresses") or []
            ],
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: IfoodConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Cria os sensores."""
    async_add_entities(IfoodSensor(entry.runtime_data, desc) for desc in SENSORS)


class IfoodSensor(IfoodEntity, SensorEntity):
    """Sensor genérico guiado pela descrição."""

    entity_description: IfoodSensorDescription

    def __init__(self, coordinator, description: IfoodSensorDescription) -> None:
        """Inicializa."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        """Valor atual."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Atributos extras."""
        fn = self.entity_description.attrs_fn
        return fn(self.coordinator.data) if fn else None
