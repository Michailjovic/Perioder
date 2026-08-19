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
all of it without losing data. Scope note (closed in v0.9.29, see below):
only `missed_dose` and `contraception_restock` were wired up to actually
fire in the original M4 release - `pms`/`period`/`fertility` as
*transition-triggered* supporter notifications (vs. the fertility-window
mention folded into the missed-dose message) were intentionally left for a
follow-up.

v0.9.29 closes that scope note: `_async_check_cycle_notifications()` fires
three more one-shot-per-cycle supporter notifications - a "blížící se
perioda" heads-up (`period_heads_up_days` before the predicted start,
CATEGORY_PERIOD), and "just started" notices for the PMS window
(CATEGORY_PMS) and the fertile window (CATEGORY_FERTILITY). Deliberately
independent of `contraception.active` (unlike the contraception check
below) - the cycle itself is tracked regardless of contraception -  but
still respects `pause_notifications`, same as everything else here.

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

v0.9.30 adds `async_setup()` (below), which registers a bundled custom
Lovelace card (`perioder-calendar-card`, see `frontend/`) as a frontend
resource - a month-grid calendar with fixed per-category colors and an
always-visible pill-taken badge, replacing the built-in `type: calendar`
card's two unfixable limitations (auto-assigned colors, and a single-day
event losing to "+n more" behind multi-day blocks). See
CALENDAR-CARD-ADR.md for the full design history.
"""
from __future__ import annotations

import csv
import logging
# `date` and `time` are aliased to `dt_date`/`dt_time` here - NOT cosmetic,
# do not "clean up" back to bare `date`/`time`. This package also has
# `date.py` and `time.py` submodules (the Platform.DATE / Platform.TIME
# entity files). The moment `hass.config_entries.async_forward_entry_setups()`
# imports either, Python's import machinery binds that submodule as the
# matching attribute on *this* package/module - silently overwriting
# whatever `from datetime import date`/`from datetime import time` bound
# here at import time. Every bare `date.today()`/`date.fromisoformat()` (or
# `time.fromisoformat()`/`time.min`) call after that point then breaks with
# `AttributeError: module '...perioder.date' has no attribute 'today'` (hit
# live 2026-08-07 for `date`, via start_new_pack; hit again live 2026-08-09
# for `time`, once Platform.TIME/`time.py` were added in v0.9.19 - same bug,
# same fix, just never applied to `time` until now since it didn't exist
# yet). Aliasing sidesteps it entirely since nothing here ever reads either
# clobbered name.
from datetime import date as dt_date, datetime, time as dt_time, timedelta
from pathlib import Path

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import (
    EVENT_HOMEASSISTANT_STARTED,
    CoreState,
    Event,
    HomeAssistant,
    ServiceCall,
    callback,
)
from homeassistant.helpers import config_validation as cv, selector
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import slugify

from . import cycle_math as cm
from . import notifications
from . import pill_math as pm
from .frontend import JSModuleRegistration
from .const import (
    ACTION_CONFIRM_PILL_PREFIX,
    ACTION_POSTPONE_PILL_PREFIX,
    CATEGORY_CONTRACEPTION_RESTOCK,
    CATEGORY_FERTILITY,
    CATEGORY_MISSED_DOSE,
    CATEGORY_PERIOD,
    CATEGORY_PMS,
    CONF_CYCLE_LENGTH,
    CONF_DEBUG_NOTIFICATIONS,
    CONF_ESCALATION_GRACE_MINUTES,
    CONF_ESCALATION_MAX_COUNT,
    CONF_ESCALATION_REPEAT_MINUTES,
    CONF_GOAL,
    CONF_LOW_STOCK_THRESHOLD,
    CONF_NOTIFICATION_INTENSITY,
    CONF_OWNER_NOTIFY_DEVICE,
    CONF_PACK_SIZE,
    CONF_PAUSE_DAYS,
    CONF_PERIOD_DURATION,
    CONF_PERIOD_HEADS_UP_DAYS,
    CONF_PMS_WINDOW_DAYS,
    CONF_REGIMEN_TYPE,
    CONF_REMINDER_TIME,
    CONF_RESTOCK_DAYS_BEFORE,
    CONF_SHARED_CALENDAR_CATEGORIES,
    DOMAIN,
    EVENT_MOBILE_APP_NOTIFICATION_ACTION,
    FERTILITY_FERTILE,
    GOALS,
    NOTIFICATION_INTENSITIES,
    REGIMEN_TYPES,
    SHARED_CALENDAR_CATEGORIES,
    SYMPTOMS,
)
from .settings import get_settings
from .storage import PerioderData
from .time_util import local_now, local_today

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
    Platform.TIME,
]

SERVICE_LOG_PERIOD_START = "log_period_start"
SERVICE_LOG_PERIOD_END = "log_period_end"
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
    SERVICE_LOG_PERIOD_END,
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

_HEARTBEAT = timedelta(hours=6)
# v0.9.19: the notification engine no longer polls on a fixed interval at
# all (0.9.18's 1-minute `async_track_time_interval` was a stopgap, not the
# real fix). It now schedules exactly one `async_track_point_in_time` call
# for the next instant that actually matters - `reminder_time`, the grace
# deadline, the next escalation, or local midnight (for the plain cycle
# sensors, which need a nudge to roll over even with contraception
# untouched) - and reschedules itself from scratch every time it runs, from
# the fresh state left by that run. This is the difference between "roughly
# every N minutes" (which is what a human reads as "randomly a few minutes
# late") and firing at the literal configured second.
#
# v0.9.34: `_HEARTBEAT` used to be 5 minutes, justified as "the plain 'pack
# running low' / 'stock low' checks aren't otherwise time-anchored to
# anything". That reasoning didn't actually hold: the pack-running-low
# check only depends on today's date, already covered by the midnight
# candidate below; the stock-low check only changes on two explicit writes
# (a confirmed dose, or the admin retyping `number.*_pills_in_stock`) that
# now call `data.async_request_reschedule()` themselves (see number.py,
# button.py's `ConfirmPillTakenButton`, and `handle_set_pills_in_stock`
# below) - the same pattern switch.py/select.py/time.py already used for
# their own settings. With every write path wired to reschedule itself
# immediately, nothing left genuinely needs 5-minute polling; `_HEARTBEAT`
# is now purely a coarse safety net against a future write path that
# forgets to call `async_request_reschedule()` (self-healing, not routine
# operation - see `_async_run_and_reschedule()`'s own docstring). Michael
# asked for 6 hours as "bohatě stačí" for that role.
# See `_compute_next_check_at()` / `_async_run_and_reschedule()`.


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


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the bundled `perioder-calendar-card` frontend resource (v0.9.30).

    This is the integration-wide setup hook, called once per Home Assistant
    instance regardless of how many Perioder config entries (cycle owners)
    exist - deliberately NOT done in `async_setup_entry()` below, which runs
    once *per config entry* and would otherwise try to register the same
    Lovelace resource redundantly for every cycle owner. See
    CALENDAR-CARD-ADR.md for the full rationale and the reference this
    pattern is based on.

    Registration is deferred to `EVENT_HOMEASSISTANT_STARTED` on a fresh
    boot (Lovelace's own resource storage may not be ready any earlier -
    same "don't race other integrations' startup" reasoning as
    `_async_initial_run()` below) - but runs immediately if HA has already
    finished starting, which is the normal case for a config entry
    reload/first setup while HA is already running.
    """

    async def _register_frontend(_event: Event | None = None) -> None:
        await JSModuleRegistration(hass).async_register()

    if hass.state == CoreState.running:
        await _register_frontend()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _register_frontend)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Perioder from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    data = PerioderData(hass, entry.entry_id)
    await data.async_load()
    hass.data[DOMAIN][entry.entry_id] = data

    _schedule = {"cancel": None}  # holds the one live async_track_point_in_time unsub

    async def _async_run_and_reschedule(now=None, hass=hass, entry=entry, data=data) -> None:
        """Run one check, then arrange the next one for the next instant that
        actually matters (see `_HEARTBEAT` above) - not a fixed interval.

        Every check (both the reschedule-computation and, since v0.9.29,
        each of the two independent notification checks below) is wrapped
        in its own try/except: an unhandled exception here would otherwise
        silently kill the whole chain forever - the line that reschedules
        the *next* wake would simply never run, and nothing would tell you
        why the reminder just stopped coming entirely on some day. A bug in
        one check should cost at most one missed check (falls back to a
        plain `_HEARTBEAT` retry) and never take the *other*, unrelated
        check down with it - see CHANGELOG.md.
        """
        data.request_refresh()
        try:
            contraception_outcome = await _async_check_contraception_notifications(hass, entry, data)
        except Exception as err:  # noqa: BLE001 - must never kill the reschedule chain, see above
            _LOGGER.exception(
                "Perioder: contraception notification check failed for '%s' - will retry in %s",
                entry.title,
                _HEARTBEAT,
            )
            contraception_outcome = f"CHYBA při kontrole antikoncepce: {err} (detail v Nastavení > Systém > Logy)"
        try:
            cycle_outcome = await _async_check_cycle_notifications(hass, entry, data)
        except Exception as err:  # noqa: BLE001 - same reasoning, independent of the check above
            _LOGGER.exception(
                "Perioder: cycle notification check failed for '%s' - will retry in %s", entry.title, _HEARTBEAT
            )
            cycle_outcome = f"CHYBA při kontrole cyklu: {err} (detail v Nastavení > Systém > Logy)"
        outcome = f"{contraception_outcome} | {cycle_outcome}"
        try:
            next_at, next_reason = _compute_next_check_at(entry, data)
        except Exception as err:  # noqa: BLE001 - same reasoning
            _LOGGER.exception(
                "Perioder: could not compute next check time for '%s' - falling back to heartbeat",
                entry.title,
            )
            next_at = local_now() + _HEARTBEAT
            next_reason = f"záložní kontrola za {_HEARTBEAT} (CHYBA při plánování: {err})"
        _schedule["cancel"] = async_track_point_in_time(hass, _async_run_and_reschedule, next_at)
        await _async_update_debug_trace(hass, entry, data, outcome, next_at, next_reason)

    def _cancel_schedule() -> None:
        if _schedule["cancel"] is not None:
            _schedule["cancel"]()

    entry.async_on_unload(_cancel_schedule)
    data.async_request_reschedule = _async_run_and_reschedule

    async def _async_initial_run(_hass: HomeAssistant) -> None:
        # v0.9.26: NOT `await _async_run_and_reschedule()` directly here -
        # confirmed live 2026-08-09 that running the first check inline,
        # during Perioder's own async_setup_entry, races other integrations'
        # startup. Perioder has no formal dependency on `mobile_app` (nor
        # should it - it's optional), so on a full HA restart Perioder can
        # finish setting up, and this immediate first check can run, BEFORE
        # `mobile_app` has registered its `notify.mobile_app_*` services -
        # producing exactly the confusing "no legacy notify.mobile_app_*
        # service found for device ..." log even though the device is
        # configured correctly and the same lookup succeeds moments later
        # (e.g. pressing "Test notification" once HA has finished starting).
        # `async_at_started()` runs the callback once HA has fully started -
        # immediately, if it already has (the normal case: entry
        # reload/first setup while HA is already running) - so this only
        # actually delays anything on a full HA restart, which is exactly
        # the case that needs it.
        await _async_run_and_reschedule()

    entry.async_on_unload(async_at_started(hass, _async_initial_run))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _async_register_services(hass)

    if _ACTION_LISTENER_KEY not in hass.data:

        @callback
        def _handle_notification_action_event(event: Event) -> None:
            # Must be @callback (not a bare lambda/plain function): an
            # undecorated listener is dispatched by the event bus via
            # hass.async_add_executor_job (a worker thread), and calling
            # hass.async_create_task() from there trips the
            # "calls hass.async_create_task from a thread other than the
            # event loop" frame-helper warning. @callback tells HA this
            # listener is safe to run inline on the event loop instead.
            hass.async_create_task(_async_handle_notification_action(hass, event))

        hass.data[_ACTION_LISTENER_KEY] = hass.bus.async_listen(
            EVENT_MOBILE_APP_NOTIFICATION_ACTION,
            _handle_notification_action_event,
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
        await data.async_log_pill_taken(local_today())
        return

    if action.startswith(ACTION_POSTPONE_PILL_PREFIX):
        entry_id = action[len(ACTION_POSTPONE_PILL_PREFIX):]
        data = hass.data.get(DOMAIN, {}).get(entry_id)
        entry = hass.config_entries.async_get_entry(entry_id)
        if data is None or entry is None:
            return
        settings = get_settings(entry)
        until = local_now() + timedelta(minutes=settings[CONF_ESCALATION_REPEAT_MINUTES])
        await data.async_snooze(until)


def _next_local_midnight(now: datetime) -> datetime:
    """The start of the next local day - the plain cycle sensors (cycle_day,
    phase, next_period, ...) have nothing else to wake them up when
    contraception tracking is off/uninvolved, so this is always at least one
    of the candidates in `_compute_next_check_at()`.
    """
    return datetime.combine(now.date() + timedelta(days=1), dt_time.min)


def _compute_next_check_at(entry: ConfigEntry, data: PerioderData) -> tuple[datetime, str]:
    """The next instant `_async_check_contraception_notifications()` actually
    needs to run again - mirroring that function's own branching (reminder_time,
    a live snooze, the grace deadline, the next escalation) so the scheduled
    wake lines up with the literal configured moment instead of a fixed
    polling interval that may or may not happen to land nearby (see v0.9.19
    in CHANGELOG.md). Doesn't need to be byte-perfect: if it's ever off by a
    branch, the mismatched wake just re-runs the check a little early/late,
    finds nothing to do yet, and reschedules itself correctly from the fresh
    state it reads at that point - self-healing, never a missed or duplicate
    notification, see `_async_run_and_reschedule()` in `async_setup_entry()`.

    Returns `(when, why)` (v0.9.22) - `why` is a short Czech label for
    whichever candidate won, surfaced in the debug trace (see
    `_async_update_debug_trace()`) so it's visible *before* something goes
    wrong, not just after.
    """
    now = local_now()
    today = local_today()
    settings = get_settings(entry)
    notif_state = data.notifications
    candidates: list[tuple[datetime, str]] = [
        (now + _HEARTBEAT, "pravidelná kontrola (nejdéle za 6 h, jen záložní síť)"),
        (_next_local_midnight(now), "půlnoc (přechod na nový den)"),
    ]

    # -- cycle transition notifications (v0.9.29) - independent of
    # contraception, see _async_check_cycle_notifications() -------------
    last_start = data.last_period_start
    if last_start is not None and not notif_state["paused"]:
        cycle_length = settings[CONF_CYCLE_LENGTH]
        next_start = cm.next_period_date(last_start, cycle_length, today)
        next_start_key = next_start.isoformat()

        heads_up_days = settings[CONF_PERIOD_HEADS_UP_DAYS]
        if heads_up_days > 0 and notif_state.get("period_notified_for") != next_start_key:
            heads_up_at = datetime.combine(next_start - timedelta(days=heads_up_days), dt_time.min)
            candidates.append((heads_up_at, "blížící se perioda (upozornění podporovatelům)"))

        pms_days = settings[CONF_PMS_WINDOW_DAYS]
        if pms_days > 0 and notif_state.get("pms_notified_for") != next_start_key:
            pms_start, _pms_end = cm.pms_window(next_start, pms_days)
            candidates.append(
                (datetime.combine(pms_start, dt_time.min), "začátek PMS okna (upozornění podporovatelům)")
            )

        if notif_state.get("fertility_notified_for") != last_start.isoformat():
            fertile_start, _fertile_end = cm.fertile_window_dates(last_start, cycle_length)
            candidates.append(
                (
                    datetime.combine(fertile_start, dt_time.min),
                    "začátek plodného okna (upozornění podporovatelům)",
                )
            )

    contraception = data.contraception
    if contraception["active"] and contraception["pack_start_date"]:
        pack_start = dt_date.fromisoformat(contraception["pack_start_date"])
        day = pm.day_in_pack(pack_start, today, settings[CONF_PACK_SIZE], settings[CONF_PAUSE_DAYS])
        reminder_dt = datetime.combine(today, dt_time.fromisoformat(settings[CONF_REMINDER_TIME]))

        if not notif_state["paused"] and pm.is_pill_day(day, settings[CONF_PACK_SIZE]):
            logged_today = contraception["pill_log"].get(today.isoformat())
            already_taken = logged_today is not None and logged_today["status"] == "taken"

            if not already_taken:
                if notif_state["last_reminder_date"] != today.isoformat():
                    candidates.append((reminder_dt, f"denní připomínka ({reminder_dt.strftime('%H:%M')})"))
                else:
                    snoozed_until = notif_state.get("snoozed_until")
                    if snoozed_until and now < datetime.fromisoformat(snoozed_until):
                        candidates.append((datetime.fromisoformat(snoozed_until), "konec odložení (Odložit)"))
                    else:
                        grace_end = reminder_dt + timedelta(
                            minutes=settings[CONF_ESCALATION_GRACE_MINUTES]
                        )
                        if notif_state["escalation_count"] == 0:
                            candidates.append((grace_end, "konec grace periody -> 1. eskalace"))
                        elif notif_state["escalation_count"] < settings[CONF_ESCALATION_MAX_COUNT]:
                            last_escalation_at = notif_state["last_escalation_at"]
                            base = (
                                datetime.fromisoformat(last_escalation_at)
                                if last_escalation_at
                                else grace_end
                            )
                            next_num = notif_state["escalation_count"] + 1
                            candidates.append(
                                (
                                    base + timedelta(minutes=settings[CONF_ESCALATION_REPEAT_MINUTES]),
                                    f"eskalace #{next_num}",
                                )
                            )

    when, why = min(candidates, key=lambda c: c[0])
    return max(when, now + timedelta(seconds=1)), why


async def _async_update_debug_trace(
    hass: HomeAssistant,
    entry: ConfigEntry,
    data: PerioderData,
    outcome: str,
    next_at: datetime,
    next_reason: str,
) -> None:
    """Surface what the notification engine just did and what it's planning
    next (v0.9.22). The whole point is being able to answer "why didn't it
    fire" by looking at something in Home Assistant, not by pasting logs
    into a chat and waiting.

    - `data.debug_trace`: a plain dict, read by
      `sensor.*_notification_debug`'s attributes (see sensor.py) - a normal
      entity, browsable in Developer Tools > States or a dashboard card,
      keeps the last value until overwritten (no bell-icon clutter). Always
      kept up to date regardless of the toggle below - it's just an entity
      state, nothing to turn off.
    - A `persistent_notification` with a *fixed* `notification_id` per
      entry, so every run updates the same one in place instead of spamming
      the bell icon - the fastest way to check "what just happened" without
      hunting for an entity or turning on debug logging first. Gated by
      `debug_notifications_enabled` (v0.9.27, Options Flow > Edit settings,
      last field) - this is the one people actually asked to be able to
      switch off once things are working; if it's off and a notification
      from an earlier "on" period is still showing, it's dismissed here too
      instead of just left stale on the bell icon.

    Wrapped in its own try/except: a debug aid must never itself be the
    thing that breaks the actual notification engine.
    """
    checked_at = local_now()
    data.debug_trace = {
        "checked_at": checked_at.isoformat(timespec="seconds"),
        "outcome": outcome,
        "next_check_at": next_at.isoformat(timespec="seconds"),
        "next_check_reason": next_reason,
    }
    data.request_refresh()
    notification_id = f"perioder_debug_{entry.entry_id}"
    try:
        if get_settings(entry)[CONF_DEBUG_NOTIFICATIONS]:
            await hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "title": f"Perioder – {entry.title}: poslední kontrola",
                    "message": (
                        f"**{checked_at.strftime('%H:%M:%S')}**: {outcome}\n\n"
                        f"Další kontrola naplánována na **{next_at.strftime('%H:%M:%S')}** ({next_reason})."
                    ),
                    "notification_id": notification_id,
                },
            )
        else:
            await hass.services.async_call(
                "persistent_notification", "dismiss", {"notification_id": notification_id}
            )
    except Exception:  # noqa: BLE001 - see docstring
        _LOGGER.exception("Perioder: could not update debug persistent_notification for '%s'", entry.title)


async def _async_check_contraception_notifications(
    hass: HomeAssistant, entry: ConfigEntry, data: PerioderData
) -> str:
    """Daily reminder + escalation to the owner, missed-dose alert to supporters, pack restock notice.

    Called at the exact instants `_compute_next_check_at()` computes (v0.9.19)
    - `reminder_time`, the grace deadline, each escalation, or a live snooze -
    not on a fixed polling interval, so this fires right at the configured
    moment rather than merely "soon after" it.

    Returns a short, human-readable Czech summary of what this particular
    run did (or precisely why it did nothing) - v0.9.22, purely for the
    debug trace (`_async_update_debug_trace()`) so "why didn't it fire" is
    answerable by reading a notification/entity, not by guessing from code.
    """
    contraception = data.contraception
    if not contraception["active"] or not contraception["pack_start_date"]:
        return "sledování antikoncepce není aktivní (nebo nemá pack_start_date)"

    notif_state = data.notifications
    settings = get_settings(entry)
    today = local_today()
    now = local_now()
    reminder_time = dt_time.fromisoformat(settings[CONF_REMINDER_TIME])
    pack_start = dt_date.fromisoformat(contraception["pack_start_date"])

    side_notes: list[str] = []

    # -- pack running low (once per pack) --------------------------------
    day = pm.day_in_pack(pack_start, today, settings[CONF_PACK_SIZE], settings[CONF_PAUSE_DAYS])
    days_left = pm.days_until_pack_ends(day, settings[CONF_PACK_SIZE])
    # Dedup key is the *current* cycle's own start date, not the stored
    # pack_start_date - that one never changes once set (day_in_pack() wraps
    # to the next pack automatically via modulo, on purpose, so nothing has
    # to be re-pressed each cycle - see pill_math.py). Keying off the raw
    # pack_start_date meant this notification only ever fired once, for the
    # very first pack, and then silently never again for any later
    # automatic cycle.
    current_cycle_start = pm.current_pack_start(
        pack_start, today, settings[CONF_PACK_SIZE], settings[CONF_PAUSE_DAYS]
    ).isoformat()
    if (
        not notif_state["paused"]
        and pm.is_pill_day(day, settings[CONF_PACK_SIZE])
        and days_left <= settings[CONF_RESTOCK_DAYS_BEFORE]
        and notif_state["restock_notified_for"] != current_cycle_start
    ):
        await notifications.async_notify_supporters(
            hass,
            entry,
            CATEGORY_CONTRACEPTION_RESTOCK,
            title="Perioder",
            general_message="Antikoncepční balení brzy dojde.",
            detailed_message=f"Antikoncepční balení brzy dojde - zbývá {days_left} dní aktivních tablet.",
        )
        await data.async_mark_restock_notified(current_cycle_start)
        side_notes.append("odesláno upozornění na docházející balení")

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
        side_notes.append("odesláno upozornění na nízkou zásobu")

    prefix = (", ".join(side_notes) + "; ") if side_notes else ""

    # -- daily reminder / escalation / missed-dose alert -------------------
    if not pm.is_pill_day(day, settings[CONF_PACK_SIZE]):
        return prefix + "dnes je pauza balení, není co připomínat"
    logged_today = contraception["pill_log"].get(today.isoformat())
    if logged_today is not None and logged_today["status"] == "taken":
        return prefix + "dnešní dávka je už potvrzená jako vzatá"
    # A "missed" entry does NOT stop here - escalation keeps nagging the
    # owner (up to escalation_max_count) even after the day's status has
    # flipped to "missed"; only an actual "taken" confirmation ends it.
    if now < datetime.combine(today, reminder_time):
        return prefix + f"ještě není čas denní připomínky (nastaveno na {reminder_time.strftime('%H:%M')})"
    if notif_state["paused"]:
        return prefix + "notifikace jsou pozastavené (switch.*_pause_notifications je zapnutý)"

    # v0.9.20: merges in the configured push intensity (quiet/normal/urgent/
    # critical - see notifications.INTENSITY_DATA) alongside the actionable
    # buttons. Only the owner's reminder + escalation use this - not the
    # supporter or low-stock notifications, which stay at plain defaults.
    pill_action_data = {
        **notifications.intensity_data(settings[CONF_NOTIFICATION_INTENSITY]),
        "actions": notifications.pill_actions(entry.entry_id),
    }

    if notif_state["last_reminder_date"] != today.isoformat():
        # Always send *today's* initial reminder, even if snoozed_until is
        # still sitting in the future - a snooze ("Odložit") is only meant to
        # postpone the escalation nag after today's reminder already went
        # out, never block the next day's fresh one. Checking
        # last_reminder_date before the snooze check (v0.9.17) also self-heals
        # a snooze stuck in the future for any reason (a leftover value from
        # the pre-0.9.16 clock bug, an unusually long escalation_repeat_minutes,
        # ...) - previously that stale value permanently blocked every future
        # reminder, since only a successful send (async_mark_reminder_sent,
        # right below) ever clears it - a deadlock, since a blocked reminder
        # can never reach the call that would unblock it.
        await notifications.async_notify_owner(
            hass,
            entry,
            "💊 Čas na prášek",
            "Nezapomeň dnes vzít antikoncepci.",
            data=pill_action_data,
        )
        await data.async_mark_reminder_sent(today)
        return prefix + "odeslána denní připomínka ownerovi"

    # Only past this point (today's initial reminder already sent) does a
    # snooze apply - it postpones the escalation nag, not the daily reminder.
    snoozed_until = notif_state.get("snoozed_until")
    if snoozed_until and now < datetime.fromisoformat(snoozed_until):
        return prefix + f"odloženo přes 'Odložit' do {datetime.fromisoformat(snoozed_until).strftime('%H:%M')}"

    grace_end = datetime.combine(today, reminder_time) + timedelta(
        minutes=settings[CONF_ESCALATION_GRACE_MINUTES]
    )
    if now < grace_end:
        return prefix + f"připomínka odeslána, grace perioda běží do {grace_end.strftime('%H:%M')}"

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
        return prefix + "dávka označena jako vynechaná, odeslána 1. eskalace"

    if notif_state["escalation_count"] >= settings[CONF_ESCALATION_MAX_COUNT]:
        return prefix + f"dosažen max. počet eskalací ({settings[CONF_ESCALATION_MAX_COUNT]}), dál se nenaguje"

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
        return prefix + f"odeslána eskalace č. {notif_state['escalation_count'] + 1}"

    minutes_left = round(settings[CONF_ESCALATION_REPEAT_MINUTES] - minutes_since)
    return prefix + f"čekám na další eskalaci (za cca {minutes_left} min)"


async def _async_check_cycle_notifications(
    hass: HomeAssistant, entry: ConfigEntry, data: PerioderData
) -> str:
    """Transition-triggered supporter notifications for the menstrual cycle
    itself (v0.9.29) - closes the M4 scope note in this module's docstring.

    Three independent, once-per-cycle notices:
      - "blížící se perioda" (CATEGORY_PERIOD), `period_heads_up_days`
        before the predicted start;
      - PMS window just started (CATEGORY_PMS), the moment `today` reaches
        the automatic `pms_window` start (the manual PMS override is a
        display-only concept - see cycle_math.is_pms_active() - it doesn't
        have a "start date" of its own, so it's not consulted here);
      - fertile window just started (CATEGORY_FERTILITY).

    Deliberately does NOT gate on `contraception.active` (unlike
    `_async_check_contraception_notifications()`) - the cycle is tracked
    whether or not the owner is also on contraception (see const.GOALS).
    Still respects `notif_state["paused"]`, same as every other supporter
    notification (ANALYZA-A-ROADMAP.md section 2.8 - pause mutes *all* of
    them, not just the contraception ones).

    Each notice is a dedup-by-cycle one-shot - same `restock_notified_for`
    pattern as the contraception check (keyed to a value that moves forward
    every cycle on its own, so it fires again automatically next cycle
    without anything having to re-arm it by hand) - not a literal
    "yesterday vs. today" comparison, since this only actually runs at the
    exact instants `_compute_next_check_at()` schedules it for, not
    continuously; see that function for the matching candidates.

    Returns a short Czech summary for the debug trace, same convention as
    `_async_check_contraception_notifications()`.
    """
    last_start = data.last_period_start
    if last_start is None:
        return "cyklus zatím nemá zapsaný začátek periody, není co hlídat"

    notif_state = data.notifications
    if notif_state["paused"]:
        return "cyklus: notifikace jsou pozastavené"

    settings = get_settings(entry)
    today = local_today()
    cycle_length = settings[CONF_CYCLE_LENGTH]
    next_start = cm.next_period_date(last_start, cycle_length, today)
    next_start_key = next_start.isoformat()
    fertility_key = last_start.isoformat()

    sent: list[str] = []

    # -- blížící se perioda (N dní předem, 0 = vypnuto) ---------------------
    heads_up_days = settings[CONF_PERIOD_HEADS_UP_DAYS]
    if (
        heads_up_days > 0
        and notif_state.get("period_notified_for") != next_start_key
        and today >= next_start - timedelta(days=heads_up_days)
    ):
        days_left = (next_start - today).days
        await notifications.async_notify_supporters(
            hass,
            entry,
            CATEGORY_PERIOD,
            title="Perioder",
            general_message="Blíží se perioda.",
            detailed_message=f"Perioda se předpokládá za {days_left} dní ({next_start.strftime('%d.%m.')}).",
        )
        await data.async_mark_period_notified(next_start_key)
        sent.append("blížící se perioda")

    # -- start PMS okna (0 = vypnuto) -----------------------------------------
    pms_days = settings[CONF_PMS_WINDOW_DAYS]
    if pms_days > 0:
        pms_start, _pms_end = cm.pms_window(next_start, pms_days)
        if notif_state.get("pms_notified_for") != next_start_key and today >= pms_start:
            await notifications.async_notify_supporters(
                hass,
                entry,
                CATEGORY_PMS,
                title="Perioder",
                general_message="Začíná PMS okno - buď ohleduplný/á.",
                detailed_message=(
                    f"Začíná PMS okno ({pms_days} dní před predikovanou periodou "
                    f"{next_start.strftime('%d.%m.')})."
                ),
            )
            await data.async_mark_pms_notified(next_start_key)
            sent.append("start PMS okna")

    # -- start plodného okna --------------------------------------------------
    fertile_start, fertile_end = cm.fertile_window_dates(last_start, cycle_length)
    if notif_state.get("fertility_notified_for") != fertility_key and today >= fertile_start:
        await notifications.async_notify_supporters(
            hass,
            entry,
            CATEGORY_FERTILITY,
            title="Perioder",
            general_message="Začíná plodné okno.",
            detailed_message=f"Začíná plodné okno (do {fertile_end.strftime('%d.%m.')}).",
        )
        await data.async_mark_fertility_notified(fertility_key)
        sent.append("start plodného okna")

    if not sent:
        return "cyklus: nic nového k odeslání"
    return "cyklus: odesláno - " + ", ".join(sent)


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
        log_date = call.data.get("date", local_today())
        if log_date > local_today():
            raise ValueError("Cannot log a period start in the future")
        data = _get_entry_data(hass, call.data["config_entry_id"])
        await data.async_set_last_period_start(log_date)

    hass.services.async_register(
        DOMAIN,
        SERVICE_LOG_PERIOD_START,
        handle_log_period_start,
        schema=vol.Schema({**_ENTRY_TARGET_SCHEMA, vol.Optional("date"): cv.date}),
    )

    async def handle_log_period_end(call: ServiceCall) -> None:
        log_date = call.data["date"]
        if log_date > local_today():
            raise ValueError("Cannot log a period end in the future")
        data = _get_entry_data(hass, call.data["config_entry_id"])
        last_start = data.last_period_start
        if last_start is not None and log_date < last_start:
            raise ValueError("Period end cannot be before its logged start")
        await data.async_set_last_period_end(log_date)

    hass.services.async_register(
        DOMAIN,
        SERVICE_LOG_PERIOD_END,
        handle_log_period_end,
        schema=vol.Schema({**_ENTRY_TARGET_SCHEMA, vol.Required("date"): cv.date}),
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
        log_date = call.data.get("date", local_today())
        if log_date > local_today():
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
        start_date = call.data.get("date", local_today())
        if start_date > local_today():
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
        # Same staleness issue time.py's reminder-time entity had (v0.9.21) -
        # this writes entry.options directly, same as that entity, so it
        # needs the same nudge.
        data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
        if data is not None and data.async_request_reschedule is not None:
            await data.async_request_reschedule()

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
                vol.Optional(CONF_PERIOD_HEADS_UP_DAYS): vol.All(vol.Coerce(int), vol.Range(min=0, max=14)),
                vol.Optional(CONF_SHARED_CALENDAR_CATEGORIES): [vol.In(SHARED_CALENDAR_CATEGORIES)],
                vol.Optional(CONF_LOW_STOCK_THRESHOLD): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
                vol.Optional(CONF_NOTIFICATION_INTENSITY): vol.In(NOTIFICATION_INTENSITIES),
                vol.Optional(CONF_DEBUG_NOTIFICATIONS): cv.boolean,
            }
        ),
    )

    async def handle_pause_notifications(call: ServiceCall) -> None:
        data = _get_entry_data(hass, call.data["config_entry_id"])
        await data.async_set_notifications_paused(call.data["paused"])
        # Unpausing while the previous schedule was computed under "paused"
        # (which skips every contraception-specific candidate in
        # _compute_next_check_at()) would otherwise sit until the next plain
        # heartbeat/midnight wake - nudge it immediately instead (v0.9.21).
        if data.async_request_reschedule is not None:
            await data.async_request_reschedule()

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
        # v0.9.34: re-check/reschedule immediately - same reasoning as
        # number.py's PillsInStockNumber and button.py's
        # ConfirmPillTakenButton, see _HEARTBEAT's docstring above.
        if data.async_request_reschedule is not None:
            await data.async_request_reschedule()

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_PILLS_IN_STOCK,
        handle_set_pills_in_stock,
        schema=vol.Schema(
            {**_ENTRY_TARGET_SCHEMA, vol.Required("value"): vol.All(vol.Coerce(int), vol.Range(min=0, max=500))}
        ),
    )
