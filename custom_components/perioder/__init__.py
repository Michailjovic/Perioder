"""The Perioder integration.

v0.1.x covered the cycle/fertility/PMS foundation: read-only cycle sensors,
a settable `date` entity to log/backdate the period start, and a `select`
entity for the PMS override. v0.2.0 (M2) added the contraception core:
pack-day status, a "Confirm pill taken" button, and the matching services.
v0.3.0 (M3) closed out the cycle/fertility milestone: a `calendar` entity
predicting periods/fertile windows/pack-pauses and showing logged pill
confirmations (with delay vs. the reminder time), plus `update_settings` for
editing settings outside of Options Flow (automations/voice/NFC).

v0.4.0 (M4) adds the notification engine: the daily contraception
reminder + escalation to the cycle owner's own device (`owner_notify_device`),
a missed-dose notification to supporters subscribed to that category (with a
fertility-window heads-up folded in), a one-shot "pack running low" notice,
and `pause_notifications` (service + `switch.pause_notifications`) to mute
all of it without losing data. Scope note: only `missed_dose` and
`contraception_restock` are wired up to actually fire in this release -
`pms`/`period`/`fertility` as *transition-triggered* supporter notifications
(vs. today's fertility-window mention folded into the missed-dose message)
are intentionally left for a follow-up, see CHANGELOG.md and
ANALYZA-A-ROADMAP.md.

v0.8.0 adds a real pill-stock count (`number.*_pills_in_stock`, auto-decremented
per confirmed dose, see storage.py) with its own low-stock warning - separate
from the existing pack-days-remaining check, which is about the *current
pack* running out, not the physical supply at home - plus actionable buttons
("Vzal(a) jsem" / "Odložit") on the owner's reminder/escalation notifications,
handled here via a shared `mobile_app_notification_action` event listener.

Settings and supporters live in the config entry (data/options) and are
handled by config_flow.py + settings.py; this module only owns the runtime
Store (storage.py) for cycle/contraception/symptom state. Because the
options flow uses `OptionsFlowWithReload`, editing settings or supporters
reloads the entry automatically - there is no manual update listener here.
"""
from __future__ import annotations

import csv
import logging
from datetime import date, datetime, time, timedelta
from pathlib import Path

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import Event, HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv, selector
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import slugify

from . import cycle_math as cm
from . import notifications
from . import pill_math as pm
from .const import (
    ACTION_CONFIRM_PILL_PREFIX,
    ACTION_POSTPONE_PILL_PREFIX,
    CATEGORY_CONTRACEPTION_RESTOCK,
    CATEGORY_MISSED_DOSE,
    CONF_CYCLE_LENGTH,
    CONF_ESCALATION_GRACE_MINUTES,
    CONF_ESCALATION_MAX_COUNT,
    CONF_ESCALATION_REPEAT_MINUTES,
    CONF_GOAL,
    CONF_LOW_STOCK_THRESHOLD,
    CONF_OWNER_NOTIFY_DEVICE,
    CONF_PACK_SIZE,
    CONF_PAUSE_DAYS,
    CONF_PERIOD_DURATION,
    CONF_PMS_WINDOW_DAYS,
    CONF_REGIMEN_TYPE,
    CONF_REMINDER_TIME,
    CONF_RESTOCK_DAYS_BEFORE,
    CONF_SHARED_CALENDAR_CATEGORIES,
    DOMAIN,
    EVENT_MOBILE_APP_NOTIFICATION_ACTION,
    FERTILITY_FERTILE,
    GOALS,
    REGIMEN_TYPES,
    SHARED_CALENDAR_CATEGORIES,
    SYMPTOMS,
)
from .settings import get_settings
from .storage import PerioderData

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.DATE,
    Platform.SELECT,
    Platform.BUTTON,
    Platform.CALENDAR,
    Platform.SWITCH,
    Platform.NUMBER,
]

SERVICE_LOG_PERIOD_START = "log_period_start"
SERVICE_SET_PMS_OVERRIDE = "set_pms_override"
SERVICE_LOG_PILL_TAKEN = "log_pill_taken"
SERVICE_START_NEW_PACK = "start_new_pack"
SERVICE_SET_CONTRACEPTION_ACTIVE = "set_contraception_active"
SERVICE_UPDATE_SETTINGS = "update_settings"
SERVICE_PAUSE_NOTIFICATIONS = "pause_notifications"
SERVICE_LOG_SYMPTOM = "log_symptom"
SERVICE_EXPORT_SYMPTOM_LOG = "export_symptom_log"
SERVICE_SET_PILLS_IN_STOCK = "set_pills_in_stock"

_PMS_OVERRIDE_VALUES = {"auto": None, "active": True, "inactive": False}
_ALL_SERVICES = (
    SERVICE_LOG_PERIOD_START,
    SERVICE_SET_PMS_OVERRIDE,
    SERVICE_LOG_PILL_TAKEN,
    SERVICE_START_NEW_PACK,
    SERVICE_SET_CONTRACEPTION_ACTIVE,
    SERVICE_UPDATE_SETTINGS,
    SERVICE_PAUSE_NOTIFICATIONS,
    SERVICE_LOG_SYMPTOM,
    SERVICE_EXPORT_SYMPTOM_LOG,
    SERVICE_SET_PILLS_IN_STOCK,
)

_ENTRY_TARGET_SCHEMA = {
    vol.Required("config_entry_id"): selector.ConfigEntrySelector(
        selector.ConfigEntrySelectorConfig(integration=DOMAIN)
    ),
}

REFRESH_INTERVAL = timedelta(minutes=15)

# Key under which the shared (not per-entry) mobile_app_notification_action
# listener's unsubscribe callable is stashed in hass.data - registered once
# on the first config entry's setup, removed once the last one unloads, same
# lifecycle as _ALL_SERVICES below.
_ACTION_LISTENER_KEY = f"{DOMAIN}_action_listener"


def _get_entry_data(hass: HomeAssistant, config_entry_id: str) -> PerioderData:
    """Resolve a config_entry_id from a service call to its PerioderData."""
    entry = hass.config_entries.async_get_entry(config_entry_id)
    if entry is None or entry.entry_id not in hass.data.get(DOMAIN, {}):
        raise ValueError(f"Unknown Perioder cycle owner: {config_entry_id}")
    return hass.data[DOMAIN][entry.entry_id]


def _get_entry(hass: HomeAssistant, config_entry_id: str) -> ConfigEntry:
    """Resolve a config_entry_id from a service call to its ConfigEntry."""
    entry = hass.config_entries.async_get_entry(config_entry_id)
    if entry is None or entry.entry_id not in hass.data.get(DOMAIN, {}):
        raise ValueError(f"Unknown Perioder cycle owner: {config_entry_id}")
    return entry


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Perioder from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    data = PerioderData(hass, entry.entry_id)
    await data.async_load()
    hass.data[DOMAIN][entry.entry_id] = data

    async def _async_tick(now, hass=hass, entry=entry, data=data) -> None:
        data.request_refresh()
        await _async_check_contraception_notifications(hass, entry, data)

    entry.async_on_unload(async_track_time_interval(hass, _async_tick, REFRESH_INTERVAL))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _async_register_services(hass)

    if _ACTION_LISTENER_KEY not in hass.data:
        hass.data[_ACTION_LISTENER_KEY] = hass.bus.async_listen(
            EVENT_MOBILE_APP_NOTIFICATION_ACTION,
            lambda event: hass.async_create_task(_async_handle_notification_action(hass, event)),
        )

    return True


async def _async_handle_notification_action(hass: HomeAssistant, event: Event) -> None:
    """React to a tap on the reminder/escalation notification's action buttons.

    Registered once for the whole integration (not per config entry), since
    the `mobile_app_notification_action` event carries no config_entry_id -
    only the action identifier, which is why `notifications.pill_actions()`
    suffixes it with the entry_id in the first place.
    """
    action = event.data.get("action") or ""

    if action.startswith(ACTION_CONFIRM_PILL_PREFIX):
        entry_id = action[len(ACTION_CONFIRM_PILL_PREFIX):]
        data = hass.data.get(DOMAIN, {}).get(entry_id)
        if data is None:
            return  # entry removed since the notification was sent
        await data.async_log_pill_taken(date.today())
        return

    if action.startswith(ACTION_POSTPONE_PILL_PREFIX):
        entry_id = action[len(ACTION_POSTPONE_PILL_PREFIX):]
        data = hass.data.get(DOMAIN, {}).get(entry_id)
        entry = hass.config_entries.async_get_entry(entry_id)
        if data is None or entry is None:
            return
        settings = get_settings(entry)
        until = datetime.now() + timedelta(minutes=settings[CONF_ESCALATION_REPEAT_MINUTES])
        await data.async_snooze(until)


async def _async_check_contraception_notifications(
    hass: HomeAssistant, entry: ConfigEntry, data: PerioderData
) -> None:
    """Daily reminder + escalation to the owner, missed-dose alert to supporters, pack restock notice.

    Runs on every REFRESH_INTERVAL tick (15 min) rather than at exact times -
    fine for a daily reminder, but it does mean `escalation_repeat_minutes`
    shorter than ~15 min has no extra effect (capped at tick granularity).
    """
    contraception = data.contraception
    if not contraception["active"] or not contraception["pack_start_date"]:
        return

    notif_state = data.notifications
    settings = get_settings(entry)
    today = date.today()
    now = datetime.now()
    reminder_time = time.fromisoformat(settings[CONF_REMINDER_TIME])
    pack_start = date.fromisoformat(contraception["pack_start_date"])

    # -- pack running low (once per pack) --------------------------------
    day = pm.day_in_pack(pack_start, today, settings[CONF_PACK_SIZE], settings[CONF_PAUSE_DAYS])
    days_left = pm.days_until_pack_ends(day, settings[CONF_PACK_SIZE])
    if (
        not notif_state["paused"]
        and pm.is_pill_day(day, settings[CONF_PACK_SIZE])
        and days_left <= settings[CONF_RESTOCK_DAYS_BEFORE]
        and notif_state["restock_notified_for"] != contraception["pack_start_date"]
    ):
        await notifications.async_notify_supporters(
            hass,
            entry,
            CATEGORY_CONTRACEPTION_RESTOCK,
            title="Perioder",
            general_message="Antikoncepční balení brzy dojde.",
            detailed_message=f"Antikoncepční balení brzy dojde - zbývá {days_left} dní aktivních tablet.",
        )
        await data.async_mark_restock_notified(contraception["pack_start_date"])

    # -- physical stock low, once until restocked (v0.8.0) -----------------
    # Separate signal from the pack-days-remaining check above: that one is
    # about the *current pack* (its active days are running out); this one
    # is about the real count in number.*_pills_in_stock (is there actually a
    # next pack at home, or is it time to buy more).
    if (
        not notif_state["paused"]
        and data.pills_in_stock <= settings[CONF_LOW_STOCK_THRESHOLD]
        and not notif_state["low_stock_notified"]
    ):
        await notifications.async_notify_owner(
            hass,
            entry,
            "💊 Dochází zásoba",
            f"Doma zbývá jen {data.pills_in_stock} tablet(y) antikoncepce - je čas dokoupit.",
        )
        await notifications.async_notify_supporters(
            hass,
            entry,
            CATEGORY_CONTRACEPTION_RESTOCK,
            title="Perioder",
            general_message="Dochází zásoba antikoncepčních tablet doma.",
            detailed_message=f"Doma zbývá jen {data.pills_in_stock} tablet(y) antikoncepce.",
        )
        await data.async_mark_low_stock_notified()

    # -- daily reminder / escalation / missed-dose alert -------------------
    if not pm.is_pill_day(day, settings[CONF_PACK_SIZE]):
        return  # pause day, nothing to remind about today
    logged_today = contraception["pill_log"].get(today.isoformat())
    if logged_today is not None and logged_today["status"] == "taken":
        return  # confirmed taken - nothing left to do today
    # A "missed" entry does NOT stop here - escalation keeps nagging the
    # owner (up to escalation_max_count) even after the day's status has
    # flipped to "missed"; only an actual "taken" confirmation ends it.
    if now < datetime.combine(today, reminder_time):
        return  # not reminder time yet
    if notif_state["paused"]:
        return

    snoozed_until = notif_state.get("snoozed_until")
    if snoozed_until and now < datetime.fromisoformat(snoozed_until):
        return  # postponed via the notification's "Odložit" action

    pill_action_data = {"actions": notifications.pill_actions(entry.entry_id)}

    if notif_state["last_reminder_date"] != today.isoformat():
        await notifications.async_notify_owner(
            hass,
            entry,
            "💊 Čas na prášek",
            "Nezapomeň dnes vzít antikoncepci.",
            data=pill_action_data,
        )
        await data.async_mark_reminder_sent(today)
        return

    grace_end = datetime.combine(today, reminder_time) + timedelta(
        minutes=settings[CONF_ESCALATION_GRACE_MINUTES]
    )
    if now < grace_end:
        return  # still within the grace period, not "missed" yet

    if notif_state["escalation_count"] == 0:
        # first time crossing into "missed" today - this is the moment the
        # sensor's status also flips to "missed" (same grace period), so
        # persist it and tell everyone who's subscribed.
        await data.async_log_pill_missed(today)

        fertility_note = ""
        last_start = data.last_period_start
        if last_start is not None:
            cycle_day = cm.cycle_day(last_start, today)
            if cm.fertility(cycle_day, settings[CONF_CYCLE_LENGTH]) == FERTILITY_FERTILE:
                fertility_note = " Dnes je navíc plodné okno - zvaž zálohovou ochranu."

        await notifications.async_notify_owner(
            hass,
            entry,
            "⚠️ Antikoncepce nepotvrzena",
            f"Dnešní dávka nebyla potvrzena.{fertility_note}",
            data=pill_action_data,
        )
        await notifications.async_notify_supporters(
            hass,
            entry,
            CATEGORY_MISSED_DOSE,
            title="Perioder",
            general_message="Vynechaná dávka antikoncepce.",
            detailed_message=f"Dnešní dávka antikoncepce nebyla potvrzena.{fertility_note}",
        )
        await data.async_mark_escalation_sent(now)
        return

    if notif_state["escalation_count"] >= settings[CONF_ESCALATION_MAX_COUNT]:
        return

    last_escalation_at = notif_state["last_escalation_at"]
    last_escalation_dt = datetime.fromisoformat(last_escalation_at) if last_escalation_at else grace_end
    minutes_since = (now - last_escalation_dt).total_seconds() / 60
    if minutes_since >= settings[CONF_ESCALATION_REPEAT_MINUTES]:
        await notifications.async_notify_owner(
            hass,
            entry,
            "⚠️ Stále nepotvrzeno",
            "Připomínka: dnešní dávka antikoncepce pořád není potvrzená.",
            data=pill_action_data,
        )
        await data.async_mark_escalation_sent(now)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    if not hass.data.get(DOMAIN):
        for service in _ALL_SERVICES:
            hass.services.async_remove(DOMAIN, service)
        unsub = hass.data.pop(_ACTION_LISTENER_KEY, None)
        if unsub is not None:
            unsub()

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

    async def handle_log_pill_taken(call: ServiceCall) -> None:
        log_date = call.data.get("date", date.today())
        if log_date > date.today():
            raise ValueError("Cannot log a dose taken in the future")
        data = _get_entry_data(hass, call.data["config_entry_id"])
        await data.async_log_pill_taken(log_date)

    hass.services.async_register(
        DOMAIN,
        SERVICE_LOG_PILL_TAKEN,
        handle_log_pill_taken,
        schema=vol.Schema({**_ENTRY_TARGET_SCHEMA, vol.Optional("date"): cv.date}),
    )

    async def handle_start_new_pack(call: ServiceCall) -> None:
        start_date = call.data.get("date", date.today())
        if start_date > date.today():
            raise ValueError("Cannot start a pack in the future")
        data = _get_entry_data(hass, call.data["config_entry_id"])
        await data.async_start_new_pack(start_date)

    hass.services.async_register(
        DOMAIN,
        SERVICE_START_NEW_PACK,
        handle_start_new_pack,
        schema=vol.Schema({**_ENTRY_TARGET_SCHEMA, vol.Optional("date"): cv.date}),
    )

    async def handle_set_contraception_active(call: ServiceCall) -> None:
        data = _get_entry_data(hass, call.data["config_entry_id"])
        await data.async_set_contraception_active(call.data["active"])

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_CONTRACEPTION_ACTIVE,
        handle_set_contraception_active,
        schema=vol.Schema({**_ENTRY_TARGET_SCHEMA, vol.Required("active"): cv.boolean}),
    )

    async def handle_update_settings(call: ServiceCall) -> None:
        entry = _get_entry(hass, call.data["config_entry_id"])
        updates = {}
        for key, value in call.data.items():
            if key == "config_entry_id" or value is None:
                continue
            # cv.time validates the input but yields a datetime.time object;
            # settings.py/pill_math.py/calendar.py all expect an isoformat
            # string here (same shape TimeSelector produces in Config/Options
            # Flow), and a bare time object isn't JSON-serializable for the
            # config entry store anyway.
            if key == CONF_REMINDER_TIME:
                value = value.isoformat()
            updates[key] = value
        if not updates:
            return
        merged = {**get_settings(entry), **updates}
        if merged[CONF_CYCLE_LENGTH] <= merged[CONF_PERIOD_DURATION]:
            raise ValueError("Cycle length must be longer than period duration")
        base = dict(entry.options) if entry.options else dict(entry.data)
        base.update(updates)
        hass.config_entries.async_update_entry(entry, options=base)

    hass.services.async_register(
        DOMAIN,
        SERVICE_UPDATE_SETTINGS,
        handle_update_settings,
        schema=vol.Schema(
            {
                **_ENTRY_TARGET_SCHEMA,
                vol.Optional(CONF_CYCLE_LENGTH): vol.All(vol.Coerce(int), vol.Range(min=15, max=60)),
                vol.Optional(CONF_PERIOD_DURATION): vol.All(vol.Coerce(int), vol.Range(min=1, max=14)),
                vol.Optional(CONF_GOAL): vol.In(GOALS),
                vol.Optional(CONF_PMS_WINDOW_DAYS): vol.All(vol.Coerce(int), vol.Range(min=0, max=10)),
                vol.Optional(CONF_REGIMEN_TYPE): vol.In(REGIMEN_TYPES),
                vol.Optional(CONF_PACK_SIZE): vol.All(vol.Coerce(int), vol.Range(min=1, max=90)),
                vol.Optional(CONF_PAUSE_DAYS): vol.All(vol.Coerce(int), vol.Range(min=0, max=30)),
                vol.Optional(CONF_REMINDER_TIME): cv.time,
                vol.Optional(CONF_OWNER_NOTIFY_DEVICE): selector.DeviceSelector(
                    selector.DeviceSelectorConfig(integration="mobile_app")
                ),
                vol.Optional(CONF_ESCALATION_GRACE_MINUTES): vol.All(
                    vol.Coerce(int), vol.Range(min=5, max=360)
                ),
                vol.Optional(CONF_ESCALATION_REPEAT_MINUTES): vol.All(
                    vol.Coerce(int), vol.Range(min=15, max=360)
                ),
                vol.Optional(CONF_ESCALATION_MAX_COUNT): vol.All(vol.Coerce(int), vol.Range(min=0, max=20)),
                vol.Optional(CONF_RESTOCK_DAYS_BEFORE): vol.All(vol.Coerce(int), vol.Range(min=0, max=14)),
                vol.Optional(CONF_SHARED_CALENDAR_CATEGORIES): [vol.In(SHARED_CALENDAR_CATEGORIES)],
                vol.Optional(CONF_LOW_STOCK_THRESHOLD): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
            }
        ),
    )

    async def handle_pause_notifications(call: ServiceCall) -> None:
        data = _get_entry_data(hass, call.data["config_entry_id"])
        await data.async_set_notifications_paused(call.data["paused"])

    hass.services.async_register(
        DOMAIN,
        SERVICE_PAUSE_NOTIFICATIONS,
        handle_pause_notifications,
        schema=vol.Schema({**_ENTRY_TARGET_SCHEMA, vol.Required("paused"): cv.boolean}),
    )

    async def handle_log_symptom(call: ServiceCall) -> None:
        data = _get_entry_data(hass, call.data["config_entry_id"])
        await data.async_log_symptom(call.data["symptom"])

    hass.services.async_register(
        DOMAIN,
        SERVICE_LOG_SYMPTOM,
        handle_log_symptom,
        schema=vol.Schema({**_ENTRY_TARGET_SCHEMA, vol.Required("symptom"): vol.In(SYMPTOMS)}),
    )

    async def handle_export_symptom_log(call: ServiceCall) -> None:
        entry = _get_entry(hass, call.data["config_entry_id"])
        data = _get_entry_data(hass, call.data["config_entry_id"])
        rows = data.symptom_log
        filename = call.data.get("filename") or f"perioder_{slugify(entry.title)}_symptoms.csv"
        if not filename.endswith(".csv"):
            filename += ".csv"

        def _write_csv() -> None:
            www_dir = Path(hass.config.path("www"))
            www_dir.mkdir(parents=True, exist_ok=True)
            with (www_dir / filename).open("w", newline="", encoding="utf-8") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=["symptom", "logged_at"])
                writer.writeheader()
                writer.writerows(rows)

        await hass.async_add_executor_job(_write_csv)
        await hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "title": "Perioder - export symptomů",
                "message": f"Export hotový: `/local/{filename}` ({len(rows)} záznamů).",
                "notification_id": f"perioder_export_{entry.entry_id}",
            },
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_EXPORT_SYMPTOM_LOG,
        handle_export_symptom_log,
        schema=vol.Schema({**_ENTRY_TARGET_SCHEMA, vol.Optional("filename"): cv.string}),
    )

    async def handle_set_pills_in_stock(call: ServiceCall) -> None:
        data = _get_entry_data(hass, call.data["config_entry_id"])
        await data.async_set_pills_in_stock(call.data["value"])

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_PILLS_IN_STOCK,
        handle_set_pills_in_stock,
        schema=vol.Schema(
            {**_ENTRY_TARGET_SCHEMA, vol.Required("value"): vol.All(vol.Coerce(int), vol.Range(min=0, max=500))}
        ),
    )
