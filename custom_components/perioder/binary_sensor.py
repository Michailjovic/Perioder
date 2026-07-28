"""Binary sensor platform for Perioder.

`pms_active` exists here for every cycle owner like any other entity - the
"supporters only, never the owner's own dashboard" rule from the project's
ANALYZA-A-ROADMAP.md (section 2.2/2.9) is a *dashboard/notification*
convention, not an entity-visibility restriction. The entity itself is
always available (e.g. for the admin to verify in Developer Tools); it's
simply left off the example owner-facing dashboard card.
"""
from __future__ import annotations

from datetime import date

from homeassistant.components.binary_sensor import BinarySensorEntity
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
    """Set up Perioder binary sensors for one cycle owner."""
    data: PerioderData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            PeriodActiveBinarySensor(entry, data),
            PmsActiveBinarySensor(entry, data),
        ]
    )


class _PerioderBinarySensorBase(BinarySensorEntity):
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


class PeriodActiveBinarySensor(_PerioderBinarySensorBase):
    """On while the period itself is ongoing."""

    def __init__(self, entry: ConfigEntry, data: PerioderData) -> None:
        super().__init__(entry, data, "period_active")

    @property
    def is_on(self) -> bool | None:
        last_start = self._last_start
        if last_start is None:
            return None
        settings = self._data.settings
        day = cm.cycle_day(last_start, date.today())
        return cm.is_period_active(day, settings["period_duration"])


class PmsActiveBinarySensor(_PerioderBinarySensorBase):
    """On during the PMS window, honoring a manual per-cycle override."""

    def __init__(self, entry: ConfigEntry, data: PerioderData) -> None:
        super().__init__(entry, data, "pms_active")

    @property
    def is_on(self) -> bool | None:
        last_start = self._last_start
        if last_start is None:
            return None
        settings = self._data.settings
        today = date.today()
        next_start = cm.next_period_date(last_start, settings["cycle_length"], today)
        return cm.is_pms_active(
            today, next_start, settings["pms_window_days"], override=self._data.pms_override
        )

    @property
    def extra_state_attributes(self) -> dict[str, bool | None]:
        return {"manual_override": self._data.pms_override}
