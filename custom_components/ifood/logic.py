"""Lógica pura sobre os pedidos (sem Home Assistant), testável isolada."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
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
    week = [o for o in paid if (parse_dt(o.get("createdAt")) or now) > now - timedelta(days=7)]
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
        "gasto_7d": spend(week),
        "pedidos_7d": len(week),
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


# ---------- cupons ----------

def voucher_value(v: dict[str, Any]) -> float | None:
    """Desconto máximo em reais. FIXED vem em centavos; PERCENT usa o teto (maxCredit, em reais)."""
    effects = (v.get("campaign") or {}).get("effects") or []
    if not effects:
        return None
    e = effects[0]
    if e.get("type") == "FIXED" and isinstance(e.get("value"), (int, float)):
        return round(e["value"] / 100, 2)
    if isinstance(e.get("maxCredit"), (int, float)) and e["maxCredit"] > 0:
        return round(float(e["maxCredit"]), 2)
    return None


def voucher_is_club(v: dict[str, Any]) -> bool:
    """Cupom do Clube iFood."""
    code = str((v.get("campaign") or {}).get("code") or "")
    return code.startswith("CLUBE") or (v.get("metadata") or {}).get("club") == "true"


VERTICAL_PT = {
    "RESTAURANT": "Restaurantes",
    "MARKET": "Mercados",
    "PHARMACY": "Farmácias",
    "BEVERAGE": "Bebidas",
    "PET": "Pet",
    "SHOP": "Lojas",
    "WHOLESALE": "Atacado",
}


def voucher_expiry(v: dict[str, Any]) -> datetime | None:
    """Vencimento real. A API devolve muitos cupons com `expiresAt` = agora + ~1 h, com
    fração de segundo (ex.: 18:30:20.530254073Z), que anda a cada consulta: é prazo
    deslizante, não vencimento. Vencimento real vem redondo (ex.: 02:59:59Z)."""
    raw = str(v.get("expiresAt") or "")
    if not raw or "." in raw:
        return None
    return parse_dt(raw)


def voucher_summary(v: dict[str, Any]) -> dict[str, Any]:
    """Resumo pt-BR de um cupom."""
    c = v.get("campaign") or {}
    return {
        "id": v.get("id"),
        "descricao": c.get("promoDescription"),
        "valor_max": voucher_value(v),
        "categoria": VERTICAL_PT.get(c.get("vertical"), c.get("vertical")),
        "vence_em": exp.isoformat() if (exp := voucher_expiry(v)) else None,
        "clube": voucher_is_club(v),
        "regras": c.get("promoTerms") or [],
    }


def vouchers_available(vouchers: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    """Disponíveis e não vencidos, do que vence primeiro ao último."""
    out = []
    for v in vouchers:
        exp = voucher_expiry(v)
        if v.get("status") == "AVAILABLE" and (exp is None or exp > now):
            out.append(v)
    # Com prazo fixo primeiro (do que vence antes), depois os sem prazo.
    return sorted(out, key=lambda v: (voucher_expiry(v) is None, voucher_expiry(v) or now))


def voucher_stats(vouchers: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    """Números da carteira de cupons."""
    av = vouchers_available(vouchers, now)
    fixed = [v for v in av if voucher_expiry(v)]
    soon = [v for v in fixed if voucher_expiry(v) < now + timedelta(days=7)]
    food = [v for v in av if (v.get("campaign") or {}).get("vertical") == "RESTAURANT"]
    best = max(food, key=lambda v: voucher_value(v) or 0, default=None)
    by_cat: Counter[str] = Counter(voucher_summary(v)["categoria"] or "Outros" for v in av)
    end_of_day = now.astimezone(now.tzinfo).replace(hour=23, minute=59, second=59)
    food_today = [v for v in food if voucher_expiry(v) and voucher_expiry(v) <= end_of_day]
    return {
        "restaurante_hoje": [voucher_summary(v) for v in food_today],
        "disponiveis": len(av),
        "vencendo_7d": len(soon),
        "clube": sum(1 for v in av if voucher_is_club(v)),
        "proximo": voucher_summary(fixed[0]) if fixed else None,
        "sem_prazo_fixo": len(av) - len(fixed),
        "maior": voucher_summary(best) if best else None,
        "por_categoria": dict(by_cat.most_common()),
    }


# ---------- Clube ----------

def club_info(me: dict[str, Any]) -> dict[str, Any]:
    """Lê as tags internas `chave/valor` do Clube. Estimativa: não é uma API do Clube."""
    tags = ((me or {}).get("club") or {}).get("tags") or []
    kv: dict[str, str] = {}
    flags: set[str] = set()
    for t in tags:
        if "/" in t:
            k, _, val = t.partition("/")
            kv.setdefault(k, val)
        else:
            flags.add(t)
    plan = kv.get("club_lifecycle_string_plan")
    return {
        "ativo": plan == "signed" or "is_mub_club" in flags,
        "situacao": plan,
        "plano": kv.get("club_plan_tier"),
        "modalidade": kv.get("club_plan_modality"),
        "status": kv.get("status_clube"),
        "pedidos_com_clube": kv.get("lifetime_club_orders"),
        "uso_do_beneficio": kv.get("active_club_consumed"),
        "meses_assinante": kv.get("months_with_club_subscriptions"),
        "pedidos_por_semana": kv.get("freq_ifood_weekly"),
        "pedidos_por_mes": kv.get("freq_fd_monthly"),
    }


# ---------- lojas ----------

def top_merchants(orders: list[dict[str, Any]], n: int = 3) -> list[dict[str, Any]]:
    """Lojas mais pedidas (concluídos), com o último endereço de entrega usado nelas."""
    count: Counter[str] = Counter()
    info: dict[str, dict[str, Any]] = {}
    for o in orders:
        m = o.get("merchant") or {}
        if not is_paid(o) or not m.get("id"):
            continue
        count[m["id"]] += 1
        info.setdefault(m["id"], {"id": m["id"], "name": m.get("name"), "logo": m.get("logo")})
    return [info[mid] for mid, _ in count.most_common(n)]


def usual_item(orders: list[dict[str, Any]], merchant_id: str) -> dict[str, Any] | None:
    """Item mais pedido na loja e o último preço pago (em reais)."""
    count: Counter[str] = Counter()
    last: dict[str, dict[str, Any]] = {}
    for o in orders:  # mais novo primeiro
        if not is_paid(o) or (o.get("merchant") or {}).get("id") != merchant_id:
            continue
        for i in (o.get("bag") or {}).get("items") or []:
            iid = i.get("id")
            if not iid:
                continue
            count[iid] += i.get("quantity", 1)
            last.setdefault(iid, {"id": iid, "nome": " ".join(str(i.get("name", "")).split()),
                                  "ultimo_preco": money(i.get("unitPrice")), "pedido_em": o.get("createdAt")})
    if not count:
        return None
    iid, n = count.most_common(1)[0]
    return {**last[iid], "vezes": n}


DAY_PT = {"MONDAY": "seg", "TUESDAY": "ter", "WEDNESDAY": "qua", "THURSDAY": "qui",
          "FRIDAY": "sex", "SATURDAY": "sáb", "SUNDAY": "dom"}


def shifts_text(shifts: list[dict[str, Any]]) -> dict[str, str]:
    """{'seg': '10:30–14:30', ...}."""
    out: dict[str, list[str]] = {}
    for s in shifts or []:
        start = str(s.get("start") or "")[:5]
        dur = s.get("duration")
        if not start or not isinstance(dur, (int, float)):
            continue
        h, m = map(int, start.split(":"))
        end_min = h * 60 + m + int(dur)
        end = f"{(end_min // 60) % 24:02d}:{end_min % 60:02d}"
        out.setdefault(DAY_PT.get(s.get("dayOfWeek"), s.get("dayOfWeek")), []).append(f"{start}–{end}")
    return {d: ", ".join(v) for d, v in out.items()}


def last_delivery_coords(orders: list[dict[str, Any]]) -> tuple[float, float] | None:
    """Coordenadas da última entrega: o endereço "favorito" da conta pode estar em outra cidade."""
    for o in orders:
        c = ((o.get("delivery") or {}).get("address") or {}).get("coordinates") or {}
        if isinstance(c.get("latitude"), (int, float)) and isinstance(c.get("longitude"), (int, float)):
            return c["latitude"], c["longitude"]
    return None
