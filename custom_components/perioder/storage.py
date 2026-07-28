"""Storage layer for Perioder - runtime state only.

Deliberately does NOT hold settings or supporters: those are "declarative
config" the admin sets via Config/Options Flow and belong in the config
entry's data/options (see settings.py), which Home Assistant already
persists and which OptionsFlowWithReload keeps in sync automatically.

This Store instead holds things that change through services/automations
between config changes: the last period start date, a manual PMS override,
contraception pack state, and symptom history. One Store per config entry
(one cycle owner), isolated by entry_id.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, TypedDict, cast

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY_PREFIX, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)


class ContraceptionState(TypedDict):
    """Current contraception pack state."""

    active: bool
    pack_start_date: str | None
    pill_log: dict[str, str]  # date_str -> "taken" | "missed"


class PerioderStorageData(TypedDict):
    version: int
    last_period_start: str | None
    pms_override: bool | None
    contraception: ContraceptionState
    symptoms: dict[str, str]  # symptom -> iso timestamp of the most recent log
    symptom_log: list[dict[str, str]]  # full history: [{"symptom", "logged_at"}]


def _default_contraception() -> ContraceptionState:
    return {"active": False, "pack_start_date": None, "pill_log": {}}


def _default_data() -> PerioderStorageData:
    return {
        "version": STORAGE_VERSION,
        "last_period_start": None,
        "pms_override": None,
        "contraception": _default_contraception(),
        "symptoms": {},
        "symptom_log": [],
    }


class PerioderData:
    """Manages persisted runtime data for a single Perioder config entry."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self.hass = hass
        self.store: Store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY_PREFIX}_{entry_id}")
        self.data: PerioderStorageData | None = None
        self._listeners: list[Any] = []

    async def async_load(self) -> None:
        """Load data from storage, backfilling any keys missing from an older schema."""
        stored = await self.store.async_load()
        if stored is None:
            self.data = _default_data()
            await self.async_save()
            return

        data = cast(PerioderStorageData, stored)
        defaults = _default_data()
        for key, value in defaults.items():
            data.setdefault(key, value)
        for key, value in defaults["contraception"].items():
            data["contraception"].setdefault(key, value)
        self.data = data

    async def async_save(self) -> None:
        if self.data is not None:
            await self.store.async_save(self.data)
            self._notify_listeners()

    def add_listener(self, listener: Any) -> Any:
        """Register a callback to run whenever stored data changes. Returns an unsubscribe function."""
        self._listeners.append(listener)

        def remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return remove

    def _notify_listeners(self) -> None:
        for listener in self._listeners:
            listener()

    def request_refresh(self) -> None:
        """Ask all entities bound to this entry to recompute now, without changing data.

        Used for the periodic tick in __init__.py so time-only changes (e.g. the
        cycle day rolling over at midnight) show up without waiting for the next
        service call.
        """
        self._notify_listeners()

    # -- cycle ----------------------------------------------------------

    @property
    def last_period_start(self) -> date | None:
        if self.data and self.data["last_period_start"]:
            return date.fromisoformat(self.data["last_period_start"])
        return None

    async def async_set_last_period_start(self, value: date) -> None:
        if self.data:
            self.data["last_period_start"] = value.isoformat()
            await self.async_save()

    @property
    def pms_override(self) -> bool | None:
        return self.data.get("pms_override") if self.data else None

    async def async_set_pms_override(self, value: bool | None) -> None:
        if self.data:
            self.data["pms_override"] = value
            await self.async_save()

    # -- contraception ------------------------------------------------------

    @property
    def contraception(self) -> ContraceptionState:
        return self.data["contraception"] if self.data else _default_contraception()

    async def async_set_contraception_active(self, active: bool) -> None:
        if self.data:
            self.data["contraception"]["active"] = active
            await self.async_save()

    async def async_start_new_pack(self, start_date: date) -> None:
        if not self.data:
            return
        self.data["contraception"]["pack_start_date"] = start_date.isoformat()
        self.data["contraception"]["active"] = True
        await self.async_save()

    async def async_log_pill_taken(self, log_date: date) -> None:
        if self.data:
            self.data["contraception"]["pill_log"][log_date.isoformat()] = "taken"
            await self.async_save()

    async def async_log_pill_missed(self, log_date: date) -> None:
        if self.data:
            self.data["contraception"]["pill_log"][log_date.isoformat()] = "missed"
            await self.async_save()

    # -- symptoms -----------------------------------------------------------

    @property
    def symptoms(self) -> dict[str, str]:
        return self.data.get("symptoms", {}) if self.data else {}

    async def async_log_symptom(self, symptom: str) -> None:
        if self.data:
            now = datetime.now().isoformat()
            self.data["symptoms"][symptom] = now
            self.data.setdefault("symptom_log", []).append({"symptom": symptom, "logged_at": now})
            await self.async_save()
