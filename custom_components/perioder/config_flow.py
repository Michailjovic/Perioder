"""Config and options flow for Perioder.

Config flow: one-time setup of a new cycle owner (basic settings only).
Options flow: edit those settings later, plus manage supporters - who gets
notified about what, and in how much detail. Options Flow is only reachable
by a Home Assistant administrator, which is a deliberate choice here (see
the project's ANALYZA-A-ROADMAP.md, section 2.5): the admin decides who
sees what, there is no separate consent step from the cycle owner.

Uses `OptionsFlowWithReload` (current HA API, no self.config_entry
assignment in __init__ - the base class provides that property once the
flow is created; see developers.home-assistant.io/docs/core/integration/options_flow).
Editing settings or supporters reloads the entry, so sensors always read
fresh values straight from entry.options (see settings.py).
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import OptionsFlowWithReload
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_CYCLE_LENGTH,
    CONF_GOAL,
    CONF_NAME,
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
    DETAIL_GENERAL,
    DETAIL_LEVELS,
    DOMAIN,
    GOALS,
    REGIMEN_PACK_DEFAULTS,
    REGIMEN_TYPES,
    SUPPORTER_CATEGORIES,
)

_LOGGER = logging.getLogger(__name__)


def _settings_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Schema shared by the initial setup step and the options settings step."""
    return vol.Schema(
        {
            vol.Required(CONF_CYCLE_LENGTH, default=defaults[CONF_CYCLE_LENGTH]): vol.All(
                vol.Coerce(int), vol.Range(min=15, max=60)
            ),
            vol.Required(CONF_PERIOD_DURATION, default=defaults[CONF_PERIOD_DURATION]): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=14)
            ),
            vol.Required(CONF_GOAL, default=defaults[CONF_GOAL]): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=GOALS,
                    translation_key="goal",
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(CONF_PMS_WINDOW_DAYS, default=defaults[CONF_PMS_WINDOW_DAYS]): vol.All(
                vol.Coerce(int), vol.Range(min=0, max=10)
            ),
            vol.Required(CONF_REGIMEN_TYPE, default=defaults[CONF_REGIMEN_TYPE]): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=REGIMEN_TYPES,
                    translation_key="regimen_type",
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(CONF_PACK_SIZE, default=defaults[CONF_PACK_SIZE]): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=90)
            ),
            vol.Optional(CONF_PAUSE_DAYS, default=defaults[CONF_PAUSE_DAYS]): vol.All(
                vol.Coerce(int), vol.Range(min=0, max=30)
            ),
            vol.Required(CONF_REMINDER_TIME, default=defaults[CONF_REMINDER_TIME]): selector.TimeSelector(),
        }
    )


def _supporter_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required("device_id"): selector.DeviceSelector(
                selector.DeviceSelectorConfig(integration="mobile_app")
            ),
            vol.Required("categories", default=[]): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=SUPPORTER_CATEGORIES,
                    translation_key="supporter_category",
                    multiple=True,
                    mode=selector.SelectSelectorMode.LIST,
                )
            ),
            vol.Required("detail_level", default=DETAIL_GENERAL): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=DETAIL_LEVELS,
                    translation_key="detail_level",
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        }
    )


class PerioderConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle initial setup - one config entry per cycle owner."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            if user_input[CONF_CYCLE_LENGTH] <= user_input[CONF_PERIOD_DURATION]:
                errors["base"] = "invalid_length"
            else:
                name = user_input.pop(CONF_NAME)
                return self.async_create_entry(title=name, data=user_input)

        # First-time setup has no config entry yet to read defaults from,
        # so build the defaults dict straight from const.py.
        pack_size, pause_days = REGIMEN_PACK_DEFAULTS[DEFAULT_REGIMEN_TYPE]
        defaults = {
            CONF_CYCLE_LENGTH: DEFAULT_CYCLE_LENGTH,
            CONF_PERIOD_DURATION: DEFAULT_PERIOD_DURATION,
            CONF_GOAL: DEFAULT_GOAL,
            CONF_PMS_WINDOW_DAYS: DEFAULT_PMS_WINDOW_DAYS,
            CONF_REGIMEN_TYPE: DEFAULT_REGIMEN_TYPE,
            CONF_PACK_SIZE: pack_size,
            CONF_PAUSE_DAYS: pause_days,
            CONF_REMINDER_TIME: DEFAULT_REMINDER_TIME,
        }

        schema = vol.Schema({vol.Required(CONF_NAME): str}).extend(_settings_schema(defaults).schema)
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        return PerioderOptionsFlow()


class PerioderOptionsFlow(OptionsFlowWithReload):
    """Manage settings and supporters for an existing cycle owner.

    Only reachable by a Home Assistant administrator (Settings > Devices &
    Services), which is what makes the admin the one who decides supporter
    access - the platform already gates this, we don't add anything extra.

    `self.config_entry` is provided automatically by the base class once
    the flow is instantiated - it must not be set explicitly here (doing so
    is a hard error on current Home Assistant versions).
    """

    def _ensure_working_copy(self) -> None:
        if not hasattr(self, "_options"):
            self._options: dict[str, Any] = dict(self.config_entry.options) or dict(
                self.config_entry.data
            )
            self._options.setdefault("supporters", [])

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        self._ensure_working_copy()
        return self.async_show_menu(step_id="init", menu_options=["settings", "supporters"])

    async def async_step_settings(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        self._ensure_working_copy()
        errors: dict[str, str] = {}
        # self._options already has every settings key, seeded from
        # entry.options/entry.data in _ensure_working_copy(), plus any
        # edits made earlier in this same flow.
        defaults = self._options

        if user_input is not None:
            if user_input[CONF_CYCLE_LENGTH] <= user_input[CONF_PERIOD_DURATION]:
                errors["base"] = "invalid_length"
            else:
                self._options.update(user_input)
                return await self.async_step_init()

        return self.async_show_form(step_id="settings", data_schema=_settings_schema(defaults), errors=errors)

    async def async_step_supporters(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        self._ensure_working_copy()
        supporters = self._options.get("supporters", [])
        menu_options = ["add_supporter"]
        if supporters:
            menu_options.append("remove_supporter")
        menu_options.append("finish")
        return self.async_show_menu(step_id="supporters", menu_options=menu_options)

    async def async_step_add_supporter(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        self._ensure_working_copy()
        if user_input is not None:
            supporter = {
                "id": uuid.uuid4().hex,
                "device_id": user_input["device_id"],
                "categories": user_input["categories"],
                "detail_level": user_input["detail_level"],
            }
            self._options.setdefault("supporters", []).append(supporter)
            return await self.async_step_supporters()

        return self.async_show_form(step_id="add_supporter", data_schema=_supporter_schema())

    async def async_step_remove_supporter(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        self._ensure_working_copy()
        supporters = self._options.get("supporters", [])

        if user_input is not None:
            remove_id = user_input["supporter_id"]
            self._options["supporters"] = [s for s in supporters if s["id"] != remove_id]
            return await self.async_step_supporters()

        options = [
            selector.SelectOptionDict(
                value=s["id"], label=f"{s['device_id']} ({', '.join(s['categories']) or 'no categories'})"
            )
            for s in supporters
        ]
        schema = vol.Schema(
            {
                vol.Required("supporter_id"): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=options, mode=selector.SelectSelectorMode.DROPDOWN)
                )
            }
        )
        return self.async_show_form(step_id="remove_supporter", data_schema=schema)

    async def async_step_finish(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        self._ensure_working_copy()
        return self.async_create_entry(data=self._options)
