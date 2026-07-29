"""Sensor platform for Perioder.

Read-only, computed on demand from stored data + today's date - nothing is
polled. Entities refresh when storage changes (a service call) and on a
periodic tick registered in __init__.py, to catch the plain passage of time
(e.g. midnight rolling the cycle day over) without any user action.
Settings (cycle_length, period_duration, ...) come from the config entry
via settings.get_settings(), not from the runtime Store - see storage.py.
"""
from __future__ import annotations

from datetime import date, datetime, time

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from . import cycle_math as cm
from . import pill_math as pm
from .const import DOMAIN, SYMPTOMS
from .settings import get_settings, get_supporters
from .storage import PerioderData


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Perioder sensors for one cycle owner."""
    data: PerioderData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            CycleDaySensor(entry, data),
            PhaseSensor(entry, data),
            FertilitySensor(entry, data),
            NextPeriodSensor(entry, data),
            ContraceptionStatusSensor(entry, data),
            PackDaysRemainingSensor(entry, data),
            LastSymptomSensor(entry, data),
            SupportersSensor(entry, data),
        ]
    )


class _PerioderSensorBase(SensorEntity):
    """Shared plumbing: device grouping per cycle owner + storage listener."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, data: PerioderData, key: str) -> None:
        self._entry = entry
        self._data = data
        self._attr_translation_key = key
        self.entity_id = f"sensor.{slugify(entry.title)}_{key}"
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Perioder",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._data.add_listener(self._handle_update))

    def _handle_update(self) -> None:
        self.async_write_ha_state()

    @property
    def _last_start(self) -> date | None:
        return self._data.last_period_start


class CycleDaySensor(_PerioderSensorBase):
    """Current 1-based day of the cycle."""

    _attr_native_unit_of_measurement = "d"

    def __init__(self, entry: ConfigEntry, data: PerioderData) -> None:
        super().__init__(entry, data, "cycle_day")

    @property
    def native_value(self) -> int | None:
        last_start = self._last_start
        if last_start is None:
            return None
        return cm.cycle_day(last_start, date.today())

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        if self._last_start is None:
            return {"status": "no data - call perioder.log_period_start"}
        return {}


class PhaseSensor(_PerioderSensorBase):
    """Current cycle phase: menstruation / follicular / ovulation / luteal."""

    _attr_device_class = "enum"
    _attr_options = ["menstruation", "follicular", "ovulation", "luteal"]

    def __init__(self, entry: ConfigEntry, data: PerioderData) -> None:
        super().__init__(entry, data, "phase")

    @property
    def native_value(self) -> str | None:
        last_start = self._last_start
        if last_start is None:
            return None
        settings = get_settings(self._entry)
        day = cm.cycle_day(last_start, date.today())
        return cm.phase(day, settings["cycle_length"], settings["period_duration"])


class FertilitySensor(_PerioderSensorBase):
    """Current fertility level: fertile / low / safer."""

    _attr_device_class = "enum"
    _attr_options = ["fertile", "low", "safer"]

    def __init__(self, entry: ConfigEntry, data: PerioderData) -> None:
        super().__init__(entry, data, "fertility")

    @property
    def native_value(self) -> str | None:
        last_start = self._last_start
        if last_start is None:
            return None
        settings = get_settings(self._entry)
        day = cm.cycle_day(last_start, date.today())
        return cm.fertility(day, settings["cycle_length"])


class NextPeriodSensor(_PerioderSensorBase):
    """Days until the next predicted period."""

    _attr_native_unit_of_measurement = "d"

    def __init__(self, entry: ConfigEntry, data: PerioderData) -> None:
        super().__init__(entry, data, "next_period")

    @property
    def native_value(self) -> int | None:
        last_start = self._last_start
        if last_start is None:
            return None
        settings = get_settings(self._entry)
        return cm.days_until_next_period(last_start, settings["cycle_length"], date.today())


class ContraceptionStatusSensor(_PerioderSensorBase):
    """Today's contraception status: inactive / paused / pending / taken / missed."""

    _attr_device_class = "enum"
    _attr_options = ["inactive", "paused", "pending", "taken", "missed"]

    def __init__(self, entry: ConfigEntry, data: PerioderData) -> None:
        super().__init__(entry, data, "contraception_status")

    @property
    def native_value(self) -> str:
        settings = get_settings(self._entry)
        contraception = self._data.contraception
        reminder_time = time.fromisoformat(settings["reminder_time"])
        return pm.pill_status(
            active=contraception["active"],
            pack_start_date=(
                date.fromisoformat(contraception["pack_start_date"])
                if contraception["pack_start_date"]
                else None
            ),
            today=date.today(),
            pack_size=settings["pack_size"],
            pause_days=settings["pause_days"],
            pill_log=contraception["pill_log"],
            now=datetime.now(),
            reminder_time=reminder_time,
            grace_minutes=settings["escalation_grace_minutes"],
        )

    @property
    def extra_state_attributes(self) -> dict[str, str | int | None]:
        settings = get_settings(self._entry)
        today_entry = self._data.contraception["pill_log"].get(date.today().isoformat())
        if not today_entry or not today_entry.get("logged_at"):
            return {}
        logged_at = datetime.fromisoformat(today_entry["logged_at"])
        reminder_time = time.fromisoformat(settings["reminder_time"])
        return {
            "logged_at": today_entry["logged_at"],
            "delay_minutes": pm.delay_minutes(logged_at, date.today(), reminder_time),
        }


class PackDaysRemainingSensor(_PerioderSensorBase):
    """Days left in the current pack's active-pill part (0 on the last pill day)."""

    _attr_native_unit_of_measurement = "d"

    def __init__(self, entry: ConfigEntry, data: PerioderData) -> None:
        super().__init__(entry, data, "pack_days_remaining")

    @property
    def native_value(self) -> int | None:
        settings = get_settings(self._entry)
        contraception = self._data.contraception
        if not contraception["active"] or not contraception["pack_start_date"]:
            return None
        pack_start = date.fromisoformat(contraception["pack_start_date"])
        day = pm.day_in_pack(pack_start, date.today(), settings["pack_size"], settings["pause_days"])
        return pm.days_until_pack_ends(day, settings["pack_size"])


class LastSymptomSensor(_PerioderSensorBase):
    """Which symptom (see const.SYMPTOMS) was logged most recently, and when."""

    _attr_device_class = "enum"
    _attr_options = list(SYMPTOMS)

    def __init__(self, entry: ConfigEntry, data: PerioderData) -> None:
        super().__init__(entry, data, "last_symptom")

    @property
    def native_value(self) -> str | None:
        symptoms = self._data.symptoms
        if not symptoms:
            return None
        return max(symptoms, key=lambda symptom: symptoms[symptom])

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        symptoms = self._data.symptoms
        if not symptoms:
            return {}
        last_symptom = max(symptoms, key=lambda symptom: symptoms[symptom])
        return {"logged_at": symptoms[last_symptom], "log_entry_count": len(self._data.symptom_log)}


class SupportersSensor(_PerioderSensorBase):
    """How many supporters are configured, with their subscriptions as attributes.

    Exists so a dashboard markdown card can show a "supporters overview"
    (ANALYZA-A-ROADMAP.md section 2.9) via `state_attr(...)`, since supporters
    themselves aren't Home Assistant entities - they're config entry options
    (see settings.py).
    """

    _attr_native_unit_of_measurement = "supporters"

    def __init__(self, entry: ConfigEntry, data: PerioderData) -> None:
        super().__init__(entry, data, "supporters")

    @property
    def native_value(self) -> int:
        return len(get_supporters(self._entry))

    @property
    def extra_state_attributes(self) -> dict[str, list[dict[str, str]]]:
        return {
            "supporters": [
                {
                    "device_id": supporter["device_id"],
                    "categories": ", ".join(supporter.get("categories", [])) or "none",
                    "detail_level": supporter.get("detail_level", "general"),
                }
                for supporter in get_supporters(self._entry)
            ]
        }
