"""Lógica pura sobre os pedidos (sem Home Assistant), testável isolada."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from .const import FINAL_STATUSES, LOGO_URL, STATUS_PT


def money(value: Any) -> float | None:
    """Centavos -> reais."""
    return round(value / 100, 2) if isinstance(value, (int, float)) else None


def parse_dt(value: Any) -> datetime | None:
    """ISO 8601 com fuso (o iFood manda -03:00)."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def status_pt(status: str | None) -> str | None:
    """Status em português; desconhecido volta cru para não sumir."""
    return STATUS_PT.get(status, status) if status else None


def is_active(order: dict[str, Any]) -> bool:
    """Pedido ainda aberto."""
    return order.get("lastStatus") not in FINAL_STATUSES


def is_paid(order: dict[str, Any]) -> bool:
    """Pedido que de fato custou dinheiro (recusado/cancelado não conta)."""
    return order.get("lastStatus") == "CONCLUDED"


def total(order: dict[str, Any]) -> float | None:
    """Valor pago (com descontos)."""
    paid = (order.get("payments") or {}).get("total", {}).get("value")
    if paid is None:
        paid = ((order.get("bag") or {}).get("total") or {}).get("valueWithDiscount")
    return money(paid)


def discount(order: dict[str, Any]) -> float:
    """Quanto cupom/clube abateu."""
    benefits = [b.get("value") for b in (order.get("bag") or {}).get("benefits") or []]
    if any(isinstance(v, (int, float)) for v in benefits):
        return round(sum(v for v in benefits if isinstance(v, (int, float))) / 100, 2)
    # Sem lista de benefícios: diferença dos totais (inclui taxa de serviço, aproximado).
    t = (order.get("bag") or {}).get("total") or {}
    full, paid = t.get("value"), t.get("valueWithDiscount")
    if isinstance(full, (int, float)) and isinstance(paid, (int, float)):
        return round(max(full - paid, 0) / 100, 2)
    return 0.0


def items_text(order: dict[str, Any]) -> list[str]:
    """['1x Quentinha - 2 Proteínas', ...]."""
    return [
        f"{i.get('quantity', 1)}x {' '.join(str(i.get('name', '')).split())}"
        for i in (order.get("bag") or {}).get("items") or []
    ]


def delivery_code(order: dict[str, Any]) -> str | None:
    """Código que o entregador pede na porta."""
    for c in order.get("verificationCodes") or []:
        if c.get("name") == "DELIVERY_CODE" and c.get("value"):
            return str(c["value"])
    return None


def payment_text(order: dict[str, Any]) -> str | None:
    """'Apple Pay (Mastercard)', 'Pix', ..."""
    methods = (order.get("payments") or {}).get("methods") or []
    if not methods:
        return None
    m = methods[0]
    wallet = (m.get("digitalWallet") or {}).get("description")
    brand = (m.get("brand") or {}).get("description")
    base = wallet or (m.get("method") or {}).get("description")
    return f"{base} ({brand})" if base and brand and brand != base else base or brand


def summary(order: dict[str, Any]) -> dict[str, Any]:
    """Resumo pt-BR de um pedido para atributos e eventos."""
    merchant = order.get("merchant") or {}
    delivery = order.get("delivery") or {}
    eta = delivery.get("estimatedTimeOfArrival") or {}
    bag = order.get("bag") or {}
    logo = merchant.get("logo")
    return {
        "id": order.get("id"),
        "numero": order.get("orderNumber") or order.get("shortId"),
        "status": status_pt(order.get("lastStatus")),
        "status_codigo": order.get("lastStatus"),
        "restaurante": merchant.get("name"),
        "restaurante_id": merchant.get("id"),
        "logo": LOGO_URL.format(logo) if logo else None,
        "tipo": (order.get("details") or {}).get("mode"),
        "agendado": (order.get("details") or {}).get("scheduled"),
        "criado_em": order.get("createdAt"),
        "fechado_em": order.get("closedAt"),
        "previsao_entrega": eta.get("deliversAt") or delivery.get("expectedDeliveryTime"),
        "previsao_entrega_ate": eta.get("deliversEndAt") or delivery.get("expectedDeliveryTimeEnd"),
        "codigo_entrega": delivery_code(order),
        "itens": items_text(order),
        "subtotal": money((bag.get("subTotal") or {}).get("valueWithDiscount")),
        "taxa_entrega": money((bag.get("deliveryFee") or {}).get("valueWithDiscount")),
        "desconto": discount(order),
        "total": total(order),
        "pagamento": payment_text(order),
        "entrega_por": (
            ((order.get("deliveryOperation") or {}).get("executions") or [{}])[0]
            .get("deliveryParameters", {})
            .get("logisticProvider")
        ),
    }


def stats(orders: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    """Números do histórico. `now` com fuso, para comparar mês/ano locais."""
    paid = [o for o in orders if is_paid(o)]

    def in_period(o: dict[str, Any], year: bool) -> bool:
        dt = parse_dt(o.get("createdAt"))
        if not dt:
            return False
        dt = dt.astimezone(now.tzinfo)
        return dt.year == now.year and (year or dt.month == now.month)

    month = [o for o in paid if in_period(o, False)]
    year = [o for o in paid if in_period(o, True)]

    def spend(lst: list[dict[str, Any]]) -> float:
        return round(sum(total(o) or 0 for o in lst), 2)

    merchants = Counter((o.get("merchant") or {}).get("name") for o in paid if o.get("merchant"))
    top = merchants.most_common(5)
    return {
        "total_pedidos": len(paid),
        "pedidos_recusados": sum(1 for o in orders if o.get("lastStatus") in ("DECLINED", "CANCELLED")),
        "gasto_total": spend(paid),
        "gasto_mes": spend(month),
        "pedidos_mes": len(month),
        "gasto_ano": spend(year),
        "pedidos_ano": len(year),
        "ticket_medio": round(spend(paid) / len(paid), 2) if paid else None,
        "economia_mes": round(sum(discount(o) for o in month), 2),
        "economia_total": round(sum(discount(o) for o in paid), 2),
        "taxa_entrega_mes": round(sum(money((o.get("bag") or {}).get("deliveryFee", {}).get("valueWithDiscount")) or 0 for o in month), 2),
        "restaurante_favorito": top[0][0] if top else None,
        "top_restaurantes": {name: n for name, n in top},
        "primeiro_pedido": paid[-1].get("createdAt") if paid else None,
    }
