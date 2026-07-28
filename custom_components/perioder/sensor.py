"""Sensor platform for Perioder.

Read-only, computed on demand from stored data + today's date - nothing is
polled. Entities refresh when storage changes (a service call) and on a
periodic tick registered in __init__.py, to catch the plain passage of time
(e.g. midnight rolling the cycle day over) without any user action.
"""
from __future__ import annotations

from datetime import date

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import cycle_math as cm
from .const import DOMAIN
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
        settings = self._data.settings
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
        settings = self._data.settings
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
        settings = self._data.settings
        return cm.days_until_next_period(last_start, settings["cycle_length"], date.today())
