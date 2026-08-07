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


class PillLogEntry(TypedDict):
    status: str  # "taken" | "missed"
    logged_at: str | None  # full isoformat datetime of the confirmation, if known


class ContraceptionState(TypedDict):
    """Current contraception pack state."""

    active: bool
    pack_start_date: str | None
    pill_log: dict[str, PillLogEntry]  # date_str -> {"status", "logged_at"}


class NotificationState(TypedDict):
    """Runtime state for the M4 notification engine (__init__.py's tick + notifications.py).

    Not settings (those live in the config entry, see settings.py) - this is
    "where things stand right now" bookkeeping so the periodic tick knows
    what it has already sent today and doesn't repeat/spam.
    """

    paused: bool  # perioder.pause_notifications / switch.pause_notifications
    last_reminder_date: str | None  # date the initial daily reminder was last sent
    escalation_count: int  # escalations sent so far for the current missed dose
    last_escalation_at: str | None  # isoformat datetime of the last escalation sent
    restock_notified_for: str | None  # start date of the pack+pause cycle already notified about restock
    low_stock_notified: bool  # already warned about pills_in_stock being low (v0.8.0)
    snoozed_until: str | None  # isoformat datetime; reminder/escalation muted until then (v0.8.0)


class PerioderStorageData(TypedDict):
    version: int
    last_period_start: str | None
    last_period_end: str | None  # real, logged end of the current/most recent period (v0.9.0)
    pms_override: bool | None
    contraception: ContraceptionState
    symptoms: dict[str, str]  # symptom -> iso timestamp of the most recent log
    symptom_log: list[dict[str, str]]  # full history: [{"symptom", "logged_at"}]
    notifications: NotificationState
    pills_in_stock: int  # physical tablets at home right now (v0.8.0)


def _default_contraception() -> ContraceptionState:
    return {"active": False, "pack_start_date": None, "pill_log": {}}


def _default_notifications() -> NotificationState:
    return {
        "paused": False,
        "last_reminder_date": None,
        "escalation_count": 0,
        "last_escalation_at": None,
        "restock_notified_for": None,
        "low_stock_notified": False,
        "snoozed_until": None,
    }


def _default_data() -> PerioderStorageData:
    return {
        "version": STORAGE_VERSION,
        "last_period_start": None,
        "last_period_end": None,
        "pms_override": None,
        "contraception": _default_contraception(),
        "symptoms": {},
        "symptom_log": [],
        "notifications": _default_notifications(),
        "pills_in_stock": 0,
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
        for key, value in defaults["notifications"].items():
            data["notifications"].setdefault(key, value)

        # v0.2.0 stored pill_log values as a plain "taken"/"missed" string;
        # v0.3.0 needs the confirmation time too (to show delay vs.
        # reminder_time in the calendar), so normalize old entries in place.
        pill_log = data["contraception"]["pill_log"]
        for log_date, entry in list(pill_log.items()):
            if isinstance(entry, str):
                pill_log[log_date] = {"status": entry, "logged_at": None}

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
        """Log a new period start - and with it, a new cycle.

        Resets `pms_override` back to automatic (`None`): the override is
        documented as being *per cycle* (ANALYZA-A-ROADMAP.md section 2.2 -
        "protože to nemusí platit každý měsíc stejně"), so carrying last
        cycle's manual on/off across into a brand new one would silently
        contradict that. Found while reviewing PMS-override-across-cycles
        as an M7 edge case - this was a real gap, not a hypothetical one.

        Also resets `last_period_end` (v0.9.0) - the confirmed end date is
        just as much a per-cycle fact as the override, so a new period
        starting means last cycle's confirmed end no longer applies to
        anything going forward.
        """
        if self.data:
            self.data["last_period_start"] = value.isoformat()
            self.data["last_period_end"] = None
            self.data["pms_override"] = None
            await self.async_save()

    @property
    def last_period_end(self) -> date | None:
        if self.data and self.data.get("last_period_end"):
            return date.fromisoformat(self.data["last_period_end"])
        return None

    async def async_set_last_period_end(self, value: date) -> None:
        """Log the real (confirmed) end date of the current/most recent
        period - the last day bleeding was actually present, inclusive.
        Lets the calendar show the real span instead of just the
        `period_duration` estimate for that one cycle (v0.9.0).
        """
        if self.data:
            self.data["last_period_end"] = value.isoformat()
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
        """Confirm a dose taken - and, the first time for this date, take one
        tablet off `pills_in_stock` (v0.8.0). Re-confirming the same date
        (e.g. a double tap) does not decrement a second time; a date that was
        previously "missed" and now gets confirmed still decrements once,
        since that tablet genuinely was taken from stock.
        """
        if not self.data:
            return
        log_key = log_date.isoformat()
        previous = self.data["contraception"]["pill_log"].get(log_key)
        already_taken = previous is not None and previous["status"] == "taken"
        self.data["contraception"]["pill_log"][log_key] = {
            "status": "taken",
            "logged_at": datetime.now().isoformat(),
        }
        if not already_taken:
            self.data["pills_in_stock"] = max(0, self.data.get("pills_in_stock", 0) - 1)
        await self.async_save()

    async def async_log_pill_missed(self, log_date: date) -> None:
        if self.data:
            self.data["contraception"]["pill_log"][log_date.isoformat()] = {
                "status": "missed",
                "logged_at": datetime.now().isoformat(),
            }
            await self.async_save()

    # -- pill stock (v0.8.0) --------------------------------------------------

    @property
    def pills_in_stock(self) -> int:
        return self.data.get("pills_in_stock", 0) if self.data else 0

    async def async_set_pills_in_stock(self, value: int) -> None:
        """Set the physical pill count directly (restocking after a purchase,
        or correcting drift). Re-arms the low-stock warning: whatever the new
        count is, the admin just deliberately confirmed it, so it's fair to
        warn again later if it drops back below the threshold.
        """
        if self.data:
            self.data["pills_in_stock"] = max(0, value)
            self.data["notifications"]["low_stock_notified"] = False
            await self.async_save()

    # -- symptoms -----------------------------------------------------------

    @property
    def symptoms(self) -> dict[str, str]:
        return self.data.get("symptoms", {}) if self.data else {}

    @property
    def symptom_log(self) -> list[dict[str, str]]:
        """Full symptom history: [{"symptom", "logged_at"}, ...], oldest first."""
        return self.data.get("symptom_log", []) if self.data else []

    async def async_log_symptom(self, symptom: str) -> None:
        if self.data:
            now = datetime.now().isoformat()
            self.data["symptoms"][symptom] = now
            self.data.setdefault("symptom_log", []).append({"symptom": symptom, "logged_at": now})
            await self.async_save()

    # -- notifications (M4) --------------------------------------------------

    @property
    def notifications(self) -> NotificationState:
        return self.data["notifications"] if self.data else _default_notifications()

    async def async_set_notifications_paused(self, paused: bool) -> None:
        if self.data:
            self.data["notifications"]["paused"] = paused
            await self.async_save()

    async def async_mark_reminder_sent(self, log_date: date) -> None:
        """Record that today's initial reminder went out, resetting escalation
        counters and any leftover snooze from a previous day (v0.8.0) - a
        snooze is only meant to delay *today's* nag, not bleed into tomorrow.
        """
        if self.data:
            self.data["notifications"]["last_reminder_date"] = log_date.isoformat()
            self.data["notifications"]["escalation_count"] = 0
            self.data["notifications"]["last_escalation_at"] = None
            self.data["notifications"]["snoozed_until"] = None
            await self.async_save()

    async def async_mark_escalation_sent(self, when: datetime) -> None:
        if self.data:
            self.data["notifications"]["escalation_count"] += 1
            self.data["notifications"]["last_escalation_at"] = when.isoformat()
            await self.async_save()

    async def async_mark_restock_notified(self, cycle_start_date: str) -> None:
        """Record that the restock notice went out for the pack+pause cycle
        starting on `cycle_start_date` (see `pill_math.current_pack_start()`
        - NOT the stored `contraception.pack_start_date`, which never
        changes once set and would only ever dedupe the very first pack).
        """
        if self.data:
            self.data["notifications"]["restock_notified_for"] = cycle_start_date
            await self.async_save()

    async def async_mark_low_stock_notified(self) -> None:
        if self.data:
            self.data["notifications"]["low_stock_notified"] = True
            await self.async_save()

    async def async_snooze(self, until: datetime) -> None:
        """Postpone the reminder/escalation nag until `until` (v0.8.0) -
        triggered by tapping "Odložit" on the push notification itself.
        Does not touch escalation_count/pill_log: it's a pure delay, not a
        confirmation.
        """
        if self.data:
            self.data["notifications"]["snoozed_until"] = until.isoformat()
            await self.async_save()
