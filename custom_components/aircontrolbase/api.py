"""Cliente HTTP async para AirControlBase (CCM21)."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aiohttp

from .const import (
    BASE_URL,
    CODE_SESSION_EXPIRED,
    DEFAULT_TIMEOUT,
    EP_CONTROL,
    EP_CONTROL_LOG,
    EP_DEVICE_LOG,
    EP_GET_DETAILS,
    EP_LOGIN,
    EP_LOGIN_LOG,
    EP_SCHEDULE_ALL,
    EP_SCHEDULE_UPDATE,
)

_LOGGER = logging.getLogger(__name__)


class AirControlBaseError(Exception):
    """Erro genérico do AirControlBase."""


class AuthError(AirControlBaseError):
    """Falha de autenticação (credenciais inválidas ou usuário sem userId)."""


class SessionExpired(AirControlBaseError):
    """Sessão expirou (code 40018) — interno, usado pra trigger re-login."""


class AirControlBaseClient:
    """Cliente da web API do AirControlBase.

    Mantém um ClientSession próprio (com cookie jar) para guardar o JSESSIONID.
    Em qualquer 40018 faz re-login automático e retenta UMA vez.
    """

    def __init__(self, account: str, password: str, user_id: str | None = None) -> None:
        self._account = account
        self._password = password
        self._user_id = user_id
        self._session: aiohttp.ClientSession | None = None
        self._lock = asyncio.Lock()
        self._logged_in = False

    # ── ciclo de vida ─────────────────────────────────────────────────────────

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            jar = aiohttp.CookieJar(unsafe=True)
            timeout = aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT)
            self._session = aiohttp.ClientSession(cookie_jar=jar, timeout=timeout)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None
        self._logged_in = False

    @property
    def user_id(self) -> str | None:
        return self._user_id

    # ── auth ──────────────────────────────────────────────────────────────────

    async def login(self) -> dict[str, Any]:
        """Faz login. Salva cookies no jar. Tenta extrair userId da resposta."""
        session = await self._ensure_session()
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": BASE_URL,
            "Referer": f"{BASE_URL}/login.html",
        }
        data = {
            "account": self._account,
            "password": self._password,
            "from": "web",
        }
        async with session.post(BASE_URL + EP_LOGIN, headers=headers, data=data) as resp:
            text = await resp.text()
            if resp.status != 200:
                raise AuthError(f"Login HTTP {resp.status}: {text[:200]}")
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as err:
                raise AuthError(f"Login resposta não-JSON: {text[:200]}") from err

        if not isinstance(payload, dict):
            raise AuthError(f"Login resposta inesperada: {payload!r}")

        _LOGGER.debug("Login raw payload: %s", payload)

        code = payload.get("code")
        if code is not None and str(code) not in ("0", "200"):
            raise AuthError(
                f"Login falhou: code={code} msg={payload.get('msg') or payload.get('message')}"
            )

        # tenta achar o userId na resposta — caminhos comuns
        result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        data_field = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        extracted = (
            payload.get("userId")
            or payload.get("uid")
            or payload.get("user_id")
            or result.get("userId")
            or result.get("uid")
            or result.get("id")
            or data_field.get("userId")
            or data_field.get("uid")
            or data_field.get("id")
        )
        if extracted:
            self._user_id = str(extracted)

        if not self._user_id:
            raise AuthError(
                "Login OK mas userId não encontrado na resposta — informe manualmente."
            )

        self._logged_in = True
        return payload

    # ── helper de POST com retry em sessão expirada ───────────────────────────

    async def _post(self, endpoint: str, data: dict[str, str], referer: str = "") -> dict[str, Any]:
        """POST form-urlencoded. Em code=40018 faz re-login + retry 1x."""
        async with self._lock:
            if not self._logged_in:
                await self.login()

        for attempt in (1, 2):
            session = await self._ensure_session()
            headers = {
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Requested-With": "XMLHttpRequest",
                "Origin": BASE_URL,
                "Referer": referer or f"{BASE_URL}/devicecontrol.html",
            }
            async with session.post(BASE_URL + endpoint, headers=headers, data=data) as resp:
                text = await resp.text()
                if resp.status != 200:
                    raise AirControlBaseError(
                        f"POST {endpoint} HTTP {resp.status}: {text[:200]}"
                    )
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError as err:
                    raise AirControlBaseError(
                        f"POST {endpoint} resposta não-JSON: {text[:200]}"
                    ) from err

            if isinstance(payload, dict) and payload.get("code") == CODE_SESSION_EXPIRED:
                if attempt == 2:
                    raise SessionExpired("Sessão expirada após re-login")
                _LOGGER.debug("Sessão expirada em %s — refazendo login", endpoint)
                async with self._lock:
                    self._logged_in = False
                    await self.login()
                continue

            return payload

        raise AirControlBaseError(f"POST {endpoint}: falha após retry")

    # ── endpoints públicos ────────────────────────────────────────────────────

    async def get_details(self) -> dict[str, Any]:
        """Estado de todos os ACs agrupados por área + deviceCase (resumo)."""
        return await self._post(EP_GET_DETAILS, {"userId": self._user_id or ""})

    async def control_device(
        self,
        *,
        device_id: int | str,
        current: dict[str, Any],
        changes: dict[str, Any],
    ) -> dict[str, Any]:
        """Envia comando ao device. `current` é o estado espelhado completo,
        `changes` é só o que mudou (operation)."""
        control = {
            "id": int(device_id),
            "power": current.get("power", "n"),
            "mode": current.get("mode", "cool"),
            "setTemp": int(current.get("setTemp", 24)),
            "wind": current.get("wind", "auto"),
            "swing": current.get("swing", "n"),
            "lock": current.get("lock", ""),
            "factTemp": int(current.get("factTemp", 0)),
            "modeLockValue": current.get("modeLockValue", ""),
            "coolLockValue": current.get("coolLockValue", ""),
            "heatLockValue": current.get("heatLockValue", ""),
            "windLockValue": current.get("windLockValue", ""),
            "unlock": current.get("unlock", "mode,cool,heat,wind,remote"),
        }
        control.update(changes)
        data = {
            "userId": self._user_id or "",
            "control": json.dumps(control, separators=(",", ":")),
            "operation": json.dumps(changes, separators=(",", ":")),
            "type": "control",
        }
        return await self._post(EP_CONTROL, data)

    async def get_control_log(self, device_id: int | str, page: int = 1, page_size: int = 10) -> dict[str, Any]:
        return await self._post(
            EP_CONTROL_LOG,
            {
                "pageSize": str(page_size),
                "pageNumber": str(page),
                "userId": self._user_id or "",
                "did": str(device_id),
            },
            referer=f"{BASE_URL}/deviceControlRecord.html",
        )

    async def get_device_log(self, log_type: str = "r", page: int = 1, page_size: int = 10) -> dict[str, Any]:
        """log_type: 'r' = operação remota, 'm' = manutenção/erro."""
        return await self._post(
            EP_DEVICE_LOG,
            {
                "pageSize": str(page_size),
                "pageNumber": str(page),
                "userId": self._user_id or "",
                "type": log_type,
            },
            referer=f"{BASE_URL}/deviceLogRecord.html",
        )

    async def get_login_log(self, log_type: str = "web", page: int = 1, page_size: int = 10) -> dict[str, Any]:
        """log_type: 'web' ou 'app'."""
        return await self._post(
            EP_LOGIN_LOG,
            {
                "pageSize": str(page_size),
                "pageNumber": str(page),
                "userId": self._user_id or "",
                "logType": log_type,
            },
            referer=f"{BASE_URL}/logRecord.html",
        )

    async def get_schedules(self) -> dict[str, Any]:
        return await self._post(
            EP_SCHEDULE_ALL,
            {"userId": self._user_id or ""},
            referer=f"{BASE_URL}/bookingControl.html",
        )

    async def update_schedule(
        self,
        *,
        schedule_id: str | int | None,
        control: dict[str, Any],
        timer: str,
        weeks: list[int],
        objs: list[dict[str, Any]],
        cycle: bool = True,
        power: str = "y",
    ) -> dict[str, Any]:
        """Cria (sid vazio) ou atualiza (sid existente) um agendamento.

        Args:
            schedule_id: sid do agendamento (None/vazio para criar novo).
            control: dict tipo {"mode":"dry","temp":"25","wind":"low","power":"y"}.
            timer: "HH:MM".
            weeks: lista de dias (1=segunda ... 7=domingo).
            objs: lista de áreas, cada uma {"aname","aid","devices":[{"deviceName","deviceId"}]}.
            cycle: se repete.
            power: "y" ou "n".
        """
        data = {
            "control": json.dumps(control, separators=(",", ":")),
            "cycle": "y" if cycle else "n",
            "timer": timer,
            "weeks": json.dumps(weeks, separators=(",", ":")),
            "userId": self._user_id or "",
            "objs": json.dumps(objs, separators=(",", ":")),
            "power": power,
        }
        if schedule_id is not None and str(schedule_id) != "":
            data["sid"] = str(schedule_id)
        return await self._post(
            EP_SCHEDULE_UPDATE,
            data,
            referer=f"{BASE_URL}/bookingControl.html",
        )
