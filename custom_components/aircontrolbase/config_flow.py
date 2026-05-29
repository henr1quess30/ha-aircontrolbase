"""Config flow do AirControlBase."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .api import AirControlBaseClient, AuthError
from .const import CONF_ACCOUNT, CONF_PASSWORD, CONF_USER_ID, DOMAIN

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ACCOUNT): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

STEP_USER_ID_SCHEMA = vol.Schema({vol.Required(CONF_USER_ID): str})


class AirControlBaseConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Fluxo de configuração via UI."""

    VERSION = 1

    def __init__(self) -> None:
        self._account: str | None = None
        self._password: str | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._account = user_input[CONF_ACCOUNT]
            self._password = user_input[CONF_PASSWORD]

            await self.async_set_unique_id(self._account.lower())
            self._abort_if_unique_id_configured()

            client = AirControlBaseClient(self._account, self._password)
            try:
                await client.login()
            except AuthError as err:
                msg = str(err).lower()
                if "userid não encontrado" in msg or "userid nao encontrado" in msg:
                    await client.close()
                    return await self.async_step_userid()
                errors["base"] = "invalid_auth"
            except Exception:  # noqa: BLE001
                errors["base"] = "cannot_connect"
            else:
                user_id = client.user_id
                await client.close()
                return self.async_create_entry(
                    title=self._account,
                    data={
                        CONF_ACCOUNT: self._account,
                        CONF_PASSWORD: self._password,
                        CONF_USER_ID: user_id,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )

    async def async_step_userid(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Fallback: pedir userId manualmente se não vier no login."""
        errors: dict[str, str] = {}
        if user_input is not None:
            user_id = user_input[CONF_USER_ID].strip()
            client = AirControlBaseClient(self._account or "", self._password or "", user_id)
            try:
                await client.login()
                await client.get_details()
            except AuthError:
                errors["base"] = "invalid_user_id"
            except Exception:  # noqa: BLE001
                errors["base"] = "cannot_connect"
            else:
                await client.close()
                return self.async_create_entry(
                    title=self._account or user_id,
                    data={
                        CONF_ACCOUNT: self._account,
                        CONF_PASSWORD: self._password,
                        CONF_USER_ID: user_id,
                    },
                )

        return self.async_show_form(
            step_id="userid",
            data_schema=STEP_USER_ID_SCHEMA,
            errors=errors,
            description_placeholders={"account": self._account or ""},
        )
