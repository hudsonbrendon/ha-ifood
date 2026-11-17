"""Checagem da lógica pura (sem HA): `python3 -I tests/test_logic.py`.

Carrega logic.py/const.py como pacote solto (sem rodar o __init__ que importa o HA).
Dados sintéticos no formato real de GET /v4/customers/me/orders.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types
from datetime import datetime
from zoneinfo import ZoneInfo

PKG = os.path.join(os.path.dirname(__file__), "..", "custom_components", "ifood")
pkg = types.ModuleType("ifood")
pkg.__path__ = [PKG]
sys.modules["ifood"] = pkg
for name in ("const", "logic"):
    spec = importlib.util.spec_from_file_location(f"ifood.{name}", os.path.join(PKG, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"ifood.{name}"] = mod
    spec.loader.exec_module(mod)
logic = sys.modules["ifood.logic"]

TZ = ZoneInfo("America/Fortaleza")


def order(oid, created, status="CONCLUDED", merchant="Pizzaria", paid=3197, full=3798, fee=999):
    return {
        "id": oid,
        "orderNumber": oid[-4:],
        "createdAt": created,
        "closedAt": created,
        "lastStatus": status,
        "details": {"mode": "DELIVERY", "scheduled": False},
        "merchant": {"id": "m-" + merchant, "name": merchant, "logo": "x/y.png"},
        "payments": {
            "methods": [
                {
                    "method": {"name": "DIGITAL_WALLET", "description": "Carteira digital"},
                    "brand": {"description": "Mastercard"},
                    "digitalWallet": {"description": "Apple Pay"},
                }
            ],
            "total": {"currency": "BRL", "value": paid},
        },
        "bag": {
            "items": [{"name": "Quentinha  - 2 Proteínas", "quantity": 1}],
            "subTotal": {"value": 2799, "valueWithDiscount": 2799},
            "deliveryFee": {"value": fee, "valueWithDiscount": fee},
            "total": {"value": full, "valueWithDiscount": paid},
        },
        "verificationCodes": [{"name": "DELIVERY_CODE", "value": "7004"}],
        "delivery": {"estimatedTimeOfArrival": {"deliversAt": created, "deliversEndAt": created}},
    }


def main() -> None:
    orders = [
        order("o-0005", "2026-11-17T12:13:09-03:00", status="DISPATCHED"),
        order("o-0004", "2026-11-10T20:00:00-03:00", merchant="Churrascaria"),
        order("o-0003", "2026-11-01T00:30:00-03:00", merchant="Churrascaria"),
        order("o-0002", "2026-10-31T23:59:00-03:00", status="DECLINED"),
        order("o-0001", "2025-12-20T19:00:00-03:00", merchant="Sushi", paid=10000, full=10000),
    ]
    now = datetime(2026, 11, 17, 15, 0, tzinfo=TZ)
    s = logic.stats(orders, now)
    # Aberto (DISPATCHED) e recusado não entram em gasto.
    assert s["total_pedidos"] == 3, s
    assert s["pedidos_mes"] == 2 and s["gasto_mes"] == 63.94, s
    assert s["pedidos_ano"] == 2 and s["gasto_ano"] == 63.94, s
    assert s["gasto_total"] == 163.94, s
    assert s["pedidos_recusados"] == 1, s
    assert s["economia_mes"] == 12.02 and s["taxa_entrega_mes"] == 19.98, s
    assert s["restaurante_favorito"] == "Churrascaria", s
    assert s["ticket_medio"] == 54.65, s
    assert s["primeiro_pedido"] == "2025-12-20T19:00:00-03:00", s

    assert logic.is_active(orders[0]) and not logic.is_active(orders[3])
    sm = logic.summary(orders[0])
    assert sm["status"] == "Saiu para entrega", sm
    assert sm["codigo_entrega"] == "7004", sm
    assert sm["itens"] == ["1x Quentinha - 2 Proteínas"], sm
    assert sm["pagamento"] == "Apple Pay (Mastercard)", sm
    assert sm["total"] == 31.97 and sm["desconto"] == 6.01, sm
    assert logic.status_pt("NOVO_STATUS_X") == "NOVO_STATUS_X"
    print("ok")


if __name__ == "__main__":
    main()
