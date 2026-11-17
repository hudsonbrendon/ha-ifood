"""Cliente da API de consumidor do iFood (a mesma que o site usa).

O site chama `www.ifood.com.br/site-api/`, que fica atrás de Cloudflare e
PerimeterX. O host de origem `marketplace.ifood.com.br` responde as mesmas rotas
sem desafio, só com o Bearer. Ver REVERSE_ENGINEERING.md.
"""

from __future__ import annotations

import asyncio
import base64
import json
import time
from typing import Any

import aiohttp

BASE_URL = "https://marketplace.ifood.com.br"
# Cupons e loja ao vivo: o site-api roteia para cá (marketplace devolve 404).
CW_URL = "https://cw-marketplace.ifood.com.br"
# Carteira/cartões: exige X-Ifood-Device-Payment-Secret (cookie x-ifood-device-payment-<hash>).
PAYMENT_URL = "https://payment.ifood.com.br"
APP_VERSION = "9.182.2"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36"
)
# Renova o access token (~2 h de vida) quando faltar menos que isso (3 ciclos de 10 min, por causa do 429).
REFRESH_MARGIN_SECONDS = 1800


class IfoodApiError(Exception):
    """Erro genérico da API."""


class IfoodApiCommunicationError(IfoodApiError):
    """Falha de rede ou timeout."""


class IfoodApiAuthenticationError(IfoodApiError):
    """Refresh token inválido ou revogado: precisa logar de novo."""


class IfoodApiRateLimitError(IfoodApiError):
    """O gateway devolveu 429."""


def token_expiry(token: str | None) -> float:
    """`exp` do JWT (sem validar assinatura); 0 se ilegível."""
    if not token:
        return 0
    try:
        payload = token.split(".")[1]
        return float(json.loads(base64.urlsafe_b64decode(payload + "=="))["exp"])
    except (IndexError, KeyError, ValueError, TypeError):
        return 0


class IfoodApiClient:
    """Guarda access/refresh token e renova só quando precisa (o refresh tem rate limit)."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        refresh_token: str,
        device_id: str,
        access_token: str | None = None,
        payment_secret: str | None = None,
    ) -> None:
        """Inicializa o cliente."""
        self._session = session
        self.refresh_token = refresh_token
        self.access_token = access_token
        self.device_id = device_id
        self.payment_secret = payment_secret
        self._lock = asyncio.Lock()

    def _headers(self, auth: bool = True) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "platform": "Desktop",
            "app_version": APP_VERSION,
            "country": "br",
            "X-Ifood-Device-Id": self.device_id,
        }
        if auth and self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    async def async_refresh(self, force: bool = False) -> bool:
        """Renova o access token. Devolve True se os tokens mudaram."""
        async with self._lock:
            if not force and token_expiry(self.access_token) - time.time() > REFRESH_MARGIN_SECONDS:
                return False
            try:
                data = await self._raw(
                    "POST",
                    "/v2/access_tokens",
                    json_body={"refresh_token": self.refresh_token},
                    auth=False,
                )
            except IfoodApiRateLimitError:
                # Rate limit (~20 min): se o access atual ainda vale, segue com ele e tenta no próximo ciclo.
                if not force and token_expiry(self.access_token) > time.time() + 30:
                    return False
                raise
            if not isinstance(data, dict) or not data.get("access_token"):
                raise IfoodApiAuthenticationError("resposta sem access_token")
            self.access_token = data["access_token"]
            self.refresh_token = data.get("refresh_token") or self.refresh_token
            return True

    async def _raw(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        auth: bool = True,
        base: str = BASE_URL,
        headers: dict[str, str] | None = None,
    ) -> Any:
        try:
            async with self._session.request(
                method,
                base + path,
                params=params,
                json=json_body,
                headers={**self._headers(auth), **(headers or {})},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status in (401, 403):
                    raise IfoodApiAuthenticationError(f"{resp.status} em {path}")
                if resp.status == 429:
                    raise IfoodApiRateLimitError(f"429 em {path}")
                if resp.status == 404:
                    return None
                if resp.status >= 400:
                    raise IfoodApiError(f"{resp.status} em {path}: {(await resp.text())[:200]}")
                if resp.status == 204:
                    return None
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise IfoodApiCommunicationError(str(err)) from err

    async def _get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        base: str = BASE_URL,
        headers: dict[str, str] | None = None,
    ) -> Any:
        await self.async_refresh()
        try:
            return await self._raw("GET", path, params, base=base, headers=headers)
        except IfoodApiAuthenticationError:
            # Access token revogado antes do exp: uma tentativa de renovar.
            await self.async_refresh(force=True)
            return await self._raw("GET", path, params, base=base, headers=headers)

    async def async_get_account(self) -> dict[str, Any]:
        """Dados da conta (nome, e-mail, telefone, cadastro)."""
        return await self._get("/v1/customers/me/account") or {}

    async def async_get_orders(self, page: int = 0, size: int = 20) -> list[dict[str, Any]]:
        """Pedidos do mais novo para o mais velho."""
        return await self._get("/v4/customers/me/orders", {"page": page, "size": size}) or []

    async def async_get_all_orders(self, max_pages: int = 50) -> list[dict[str, Any]]:
        """Todas as páginas do histórico."""
        orders: list[dict[str, Any]] = []
        for page in range(max_pages):
            batch = await self.async_get_orders(page, 20)
            orders.extend(batch)
            if len(batch) < 20:
                break
        return orders

    async def async_get_order_events(self, order_id: str) -> list[dict[str, Any]]:
        """Linha do tempo do pedido (CREATED, CONFIRMED, DISPATCHED, ...)."""
        return await self._get(f"/v1/customers/me/orders/{order_id}/events") or []

    async def async_get_order_tracking(self, order_id: str) -> dict[str, Any] | None:
        """Rastreio do entregador. 404 (None) quando a entrega é da própria loja."""
        return await self._get(f"/v1/customers/me/orders/{order_id}/tracking")

    async def async_get_addresses(self) -> list[dict[str, Any]]:
        """Endereços salvos."""
        return await self._get("/v1/customers/me/addresses") or []

    async def async_get_me(self) -> dict[str, Any]:
        """Conta + `club.tags` (segmentação interna; única pista do Clube no site)."""
        return await self._get("/v1/customers/me") or {}

    async def async_get_vouchers(self, lat: float, lon: float) -> list[dict[str, Any]]:
        """Carteira de cupons."""
        data = await self._get(
            "/v3/customers/me/wallet/benefits",
            {"lat": lat, "lon": lon, "distanceInKm": 10},
            base=CW_URL,
            headers={"X-ZoneId": "America/Sao_Paulo"},
        )
        return (data or {}).get("vouchers") or []

    async def async_get_merchant(self, merchant_id: str, lat: float, lon: float) -> dict[str, Any] | None:
        """Loja ao vivo: aberta, tempo/taxa de entrega, distância, nota."""
        return await self._get(
            f"/v2/merchants/{merchant_id}",
            {"latitude": lat, "longitude": lon, "channel": "IFOOD"},
            base=CW_URL,
        )

    async def async_get_merchant_extra(self, merchant_id: str) -> dict[str, Any] | None:
        """Horários (`shifts`), total de avaliações, categorias."""
        return await self._get(f"/v1/merchants/{merchant_id}/extra")

    async def async_get_my_items(self, merchant_id: str) -> list[dict[str, Any]]:
        """Itens que você já pediu na loja, com o preço de hoje (em reais)."""
        return await self._get(f"/v1/customers/me/merchants/{merchant_id}/items") or []

    async def async_get_review_averages(self, merchant_id: str) -> list[dict[str, Any]]:
        """Médias de avaliação por critério."""
        data = await self._get(
            "/v1/review/evaluations",
            {"filterJson": json.dumps({"restaurantUuid": merchant_id, "page": 1, "pageSize": 1, "visible": True})},
        )
        return ((data or {}).get("data") or {}).get("evaluationsAverages") or []

    async def async_get_wallet_accounts(self) -> list[dict[str, Any]]:
        """Saldo da conta iFood. Sem o segredo de pagamento, nada."""
        if not self.payment_secret:
            return []
        return (
            await self._get(
                "/v1/customers/me/wallet-accounts",
                base=PAYMENT_URL,
                headers={"X-Ifood-Device-Payment-Secret": self.payment_secret},
            )
            or []
        )
