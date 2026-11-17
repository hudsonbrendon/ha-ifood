"""Renovação do token: `uv run --with aiohttp python -I tests/test_refresh.py`."""

from __future__ import annotations

import asyncio
import base64
import importlib.util
import json
import os
import time

spec = importlib.util.spec_from_file_location(
    "api", os.path.join(os.path.dirname(__file__), "..", "custom_components", "ifood", "api.py")
)
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


def jwt(exp: float) -> str:
    body = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return f"h.{body}.s"


def client(access_exp: float, responses: list) -> api.IfoodApiClient:
    c = api.IfoodApiClient(session=None, refresh_token="r0", device_id="d", access_token=jwt(access_exp))
    calls = []

    async def raw(method, path, params=None, json_body=None, auth=True):
        calls.append(path)
        r = responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    c._raw = raw
    c.calls = calls
    return c


async def main() -> None:
    now = time.time()
    # Longe do exp: não chama o refresh.
    c = client(now + 7200, [])
    assert await c.async_refresh() is False and c.calls == []

    # Perto do exp: renova e guarda o refresh girado.
    new = jwt(now + 7200)
    c = client(now + 600, [{"access_token": new, "refresh_token": "r1"}])
    assert await c.async_refresh() is True and c.access_token == new and c.refresh_token == "r1"

    # 429 com access ainda valendo: segue com o atual.
    c = client(now + 600, [api.IfoodApiRateLimitError("429")])
    old = c.access_token
    assert await c.async_refresh() is False and c.access_token == old

    # 429 com access vencido: erro (vira UpdateFailed, tenta no próximo ciclo).
    c = client(now - 60, [api.IfoodApiRateLimitError("429")])
    try:
        await c.async_refresh()
        raise AssertionError("devia falhar")
    except api.IfoodApiRateLimitError:
        pass

    # Refresh revogado: erro de auth (vira reauth no HA).
    c = client(now - 60, [api.IfoodApiAuthenticationError("401")])
    try:
        await c.async_refresh()
        raise AssertionError("devia falhar")
    except api.IfoodApiAuthenticationError:
        pass
    print("ok")


async def test_refresh() -> None:
    await main()


if __name__ == "__main__":
    asyncio.run(main())
