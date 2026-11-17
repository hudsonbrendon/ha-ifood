"""Config flow do iFood: refresh token + device id da sessão do site.

O login do iFood (OTP por SMS/WhatsApp/e-mail) pode cair em desafio de
segurança (selfie, captcha); por isso a integração parte da sessão já logada
no navegador: cookies `aRefreshToken` e `aDeviceId` de www.ifood.com.br.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    IfoodApiAuthenticationError,
    IfoodApiClient,
    IfoodApiCommunicationError,
    IfoodApiError,
    IfoodApiRateLimitError,
)
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_DEVICE_ID,
    CONF_PAYMENT_SECRET,
    CONF_REFRESH_TOKEN,
    DOMAIN,
)

SCHEMA = vol.Schema(
    {
        vol.Required(CONF_REFRESH_TOKEN): str,
        vol.Required(CONF_DEVICE_ID): str,
        vol.Optional(CONF_ACCESS_TOKEN): str,
        vol.Optional(CONF_PAYMENT_SECRET): str,
    }
)


PLACEHOLDERS = {"url": "www.ifood.com.br"}


class IfoodConfigFlow(ConfigFlow, domain=DOMAIN):
    """Fluxo via UI."""

    VERSION = 1

    async def _validate(self, user_input: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, str]]:
        client = IfoodApiClient(
            session=async_get_clientsession(self.hass),
            refresh_token=user_input[CONF_REFRESH_TOKEN].strip(),
            device_id=user_input[CONF_DEVICE_ID].strip(),
            access_token=(user_input.get(CONF_ACCESS_TOKEN) or "").strip() or None,
            payment_secret=(user_input.get(CONF_PAYMENT_SECRET) or "").strip() or None,
        )
        try:
            account = await client.async_get_account()
        except IfoodApiAuthenticationError:
            return None, {"base": "invalid_auth"}
        except IfoodApiRateLimitError:
            return None, {"base": "rate_limited"}
        except IfoodApiCommunicationError:
            return None, {"base": "cannot_connect"}
        except IfoodApiError:
            return None, {"base": "unknown"}
        if not account.get("id"):
            return None, {"base": "invalid_auth"}
        return {
            "account": account,
            "data": {
                CONF_REFRESH_TOKEN: client.refresh_token,
                CONF_ACCESS_TOKEN: client.access_token,
                CONF_DEVICE_ID: client.device_id,
                CONF_PAYMENT_SECRET: client.payment_secret,
            },
        }, {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Passo único: tokens da sessão do site."""
        errors: dict[str, str] = {}
        if user_input is not None:
            result, errors = await self._validate(user_input)
            if result:
                await self.async_set_unique_id(result["account"]["id"])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=result["account"].get("name") or "iFood", data=result["data"]
                )
        return self.async_show_form(
            step_id="user", data_schema=SCHEMA, errors=errors, description_placeholders=PLACEHOLDERS
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Sessão expirou."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Pede tokens novos."""
        errors: dict[str, str] = {}
        if user_input is not None:
            result, errors = await self._validate(user_input)
            if result:
                await self.async_set_unique_id(result["account"]["id"])
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(), data_updates=result["data"]
                )
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=SCHEMA, errors=errors, description_placeholders=PLACEHOLDERS
        )
