"""Reading Perioder settings and supporters from a config entry.

Settings (cycle length, goal, contraception regimen, reminder time, ...) and
the supporters list are "declarative config" set by an administrator via
Config Flow / Options Flow - the same values shown in Settings > Devices &
Services > Perioder > Configure. They live in the config entry's data/options,
not in the runtime Store (see storage.py). `entry.options` wins once
anything has been changed via Options Flow; `entry.data` (from the initial
setup) is the fallback before that.
"""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry

from .const import (
    CONF_CYCLE_LENGTH,
    CONF_GOAL,
    CONF_PACK_SIZE,
    CONF_PAUSE_DAYS,
    CONF_PERIOD_DURATION,
    CONF_PMS_WINDOW_DAYS,
    CONF_REGIMEN_TYPE,
    CONF_REMINDER_TIME,
    DEFAULT_CYCLE_LENGTH,
    DEFAULT_GOAL,
    DEFAULT_PERIOD_DURATION,
    DEFAULT_PMS_WINDOW_DAYS,
    DEFAULT_REGIMEN_TYPE,
    DEFAULT_REMINDER_TIME,
    REGIMEN_PACK_DEFAULTS,
)


def get_settings(entry: ConfigEntry) -> dict[str, Any]:
    """Return the effective settings for a cycle owner's config entry."""

    def _get(key: str, default: Any) -> Any:
        return entry.options.get(key, entry.data.get(key, default))

    default_pack_size, default_pause_days = REGIMEN_PACK_DEFAULTS[DEFAULT_REGIMEN_TYPE]
    return {
        CONF_CYCLE_LENGTH: _get(CONF_CYCLE_LENGTH, DEFAULT_CYCLE_LENGTH),
        CONF_PERIOD_DURATION: _get(CONF_PERIOD_DURATION, DEFAULT_PERIOD_DURATION),
        CONF_GOAL: _get(CONF_GOAL, DEFAULT_GOAL),
        CONF_PMS_WINDOW_DAYS: _get(CONF_PMS_WINDOW_DAYS, DEFAULT_PMS_WINDOW_DAYS),
        CONF_REGIMEN_TYPE: _get(CONF_REGIMEN_TYPE, DEFAULT_REGIMEN_TYPE),
        CONF_PACK_SIZE: _get(CONF_PACK_SIZE, default_pack_size),
        CONF_PAUSE_DAYS: _get(CONF_PAUSE_DAYS, default_pause_days),
        CONF_REMINDER_TIME: _get(CONF_REMINDER_TIME, DEFAULT_REMINDER_TIME),
    }


def get_supporters(entry: ConfigEntry) -> list[dict[str, Any]]:
    """Return the supporters configured for a cycle owner's config entry."""
    return entry.options.get("supporters", entry.data.get("supporters", []))
