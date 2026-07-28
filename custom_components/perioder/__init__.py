"""The Perioder integration.

v0.1.0 adds just enough on top of the M1 foundation to be testable end to
end: read-only cycle sensors, a way to feed in test data
(`perioder.log_period_start`), and a way to poke the PMS window for testing
(`perioder.set_pms_override`). Contraception logic, the calendar, symptoms,
and the supporter notification engine are not in yet - see CHANGELOG.md.

Settings and supporters live in the config entry (data/options) and are
handled by config_flow.py + settings.py; this module only owns the runtime
Store (storage.py) for cycle/contraception/symptom state. Because the
options flow uses `OptionsFlowWithReload`, editing settings or supporters
reloads the entry automatically - there is no manual update listener here.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv, selector
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN
from .storage import PerioderData

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

SERVICE_LOG_PERIOD_START = "log_period_start"
SERVICE_SET_PMS_OVERRIDE = "set_pms_override"

_PMS_OVERRIDE_VALUES = {"auto": None, "active": True, "inactive": False}

_ENTRY_TARGET_SCHEMA = {
    vol.Required("config_entry_id"): selector.ConfigEntrySelector(
        selector.ConfigEntrySelectorConfig(integration=DOMAIN)
    ),
}

REFRESH_INTERVAL = timedelta(minutes=15)


def _get_entry_data(hass: HomeAssistant, config_entry_id: str) -> PerioderData:
    """Resolve a config_entry_id from a service call to its PerioderData."""
    entry = hass.config_entries.async_get_entry(config_entry_id)
    if entry is None or entry.entry_id not in hass.data.get(DOMAIN, {}):
        raise ValueError(f"Unknown Perioder cycle owner: {config_entry_id}")
    return hass.data[DOMAIN][entry.entry_id]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Perioder from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    data = PerioderData(hass, entry.entry_id)
    await data.async_load()
    hass.data[DOMAIN][entry.entry_id] = data

    entry.async_on_unload(
        async_track_time_interval(hass, lambda now, d=data: d.request_refresh(), REFRESH_INTERVAL)
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _async_register_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    if not hass.data.get(DOMAIN):
        hass.services.async_remove(DOMAIN, SERVICE_LOG_PERIOD_START)
        hass.services.async_remove(DOMAIN, SERVICE_SET_PMS_OVERRIDE)

    return unload_ok


def _async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_LOG_PERIOD_START):
        return

    async def handle_log_period_start(call: ServiceCall) -> None:
        log_date = call.data.get("date", date.today())
        if log_date > date.today():
            raise ValueError("Cannot log a period start in the future")
        data = _get_entry_data(hass, call.data["config_entry_id"])
        await data.async_set_last_period_start(log_date)

    hass.services.async_register(
        DOMAIN,
        SERVICE_LOG_PERIOD_START,
        handle_log_period_start,
        schema=vol.Schema({**_ENTRY_TARGET_SCHEMA, vol.Optional("date"): cv.date}),
    )

    async def handle_set_pms_override(call: ServiceCall) -> None:
        data = _get_entry_data(hass, call.data["config_entry_id"])
        await data.async_set_pms_override(_PMS_OVERRIDE_VALUES[call.data["value"]])

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_PMS_OVERRIDE,
        handle_set_pms_override,
        schema=vol.Schema(
            {**_ENTRY_TARGET_SCHEMA, vol.Required("value"): vol.In(_PMS_OVERRIDE_VALUES)}
        ),
    )
