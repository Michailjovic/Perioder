"""Notification dispatch for Perioder (M4).

Two audiences, both resolved from a Home Assistant `device_id` (picked via
`DeviceSelector(integration="mobile_app")` in Config/Options Flow) to that
device's `notify` domain entity, then sent via the generic `notify.send_message`
action - the modern (HA 2024.10+) notify-entity-platform call, which is what
a real mobile_app device on a current Home Assistant exposes. If no matching
notify entity is found (e.g. mobile_app device removed, or a very old HA
without the notify-entity rewrite), the call is skipped with a warning
instead of raising - a bad/stale notify target for one supporter shouldn't
block anything else in the integration.

- `async_notify_owner()`: the cycle owner's own device (`owner_notify_device`
  setting) - used for the daily contraception reminder/escalation.
- `async_notify_supporters()`: every supporter subscribed to the given
  category (see const.SUPPORTER_CATEGORIES), respecting each supporter's own
  `detail_level` (general vs. detailed message).

v0.8.0 adds `pill_actions()`: the two mobile_app notification actions
("Vzal(a) jsem" / "Odložit") attached to the owner's reminder/escalation
notifications, via `notify.send_message`'s `data.actions` passthrough - the
same `data` field the legacy `notify.mobile_app_*` services accepted. Tapping
one fires the `mobile_app_notification_action` event, handled in __init__.py.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import (
    ACTION_CONFIRM_PILL_PREFIX,
    ACTION_POSTPONE_PILL_PREFIX,
    CONF_OWNER_NOTIFY_DEVICE,
    DETAIL_DETAILED,
    INTENSITY_CRITICAL,
    INTENSITY_NORMAL,
    INTENSITY_QUIET,
    INTENSITY_URGENT,
)
from .settings import get_settings, get_supporters

_LOGGER = logging.getLogger(__name__)

# v0.9.20 - how pushy the daily reminder/escalation should be, see
# const.py's NOTIFICATION_INTENSITIES. Field names/values are the mobile_app
# notify platform's own `data` payload, documented at
# https://companion.home-assistant.io/docs/notifications/notifications-basic
# (channel/importance/priority/ttl - Android) and
# https://companion.home-assistant.io/docs/notifications/critical-notifications
# (push.interruption-level/push.sound - iOS). Android channels are
# per-*name* - the first notification sent to a given channel name creates
# it with that importance and that sticks even if a later notification asks
# for a different importance on the same name (Android's own rule, not
# something this integration controls) - that's why each intensity gets its
# own distinct channel name rather than trying to vary importance within one
# shared "Perioder" channel. "critical" deliberately reuses Android's
# reserved `alarm_stream` channel name (see the Companion docs' "Android
# Alarm Stream" section) instead of a custom name - that's the one that
# actually bypasses silent/vibrate mode, which is the whole point of the
# "kritická" tier; a custom channel at "high" importance (what "urgent"
# uses) still respects the phone's ringer mode.
INTENSITY_DATA: dict[str, dict[str, Any]] = {
    INTENSITY_QUIET: {
        "channel": "Perioder – tichá",
        "importance": "low",
        "push": {"interruption-level": "passive"},
    },
    INTENSITY_NORMAL: {
        "channel": "Perioder",
        "importance": "default",
        "push": {"interruption-level": "active"},
    },
    INTENSITY_URGENT: {
        "channel": "Perioder – naléhavá",
        "importance": "high",
        "priority": "high",
        "ttl": 0,
        "push": {"interruption-level": "time-sensitive"},
    },
    INTENSITY_CRITICAL: {
        "channel": "alarm_stream",
        "importance": "high",
        "priority": "high",
        "ttl": 0,
        "push": {
            "interruption-level": "critical",
            "sound": {"name": "default", "critical": 1, "volume": 1.0},
        },
    },
}


def intensity_data(level: str) -> dict[str, Any]:
    """The `data` payload fragment for one notification intensity level.

    Falls back to `INTENSITY_NORMAL`'s payload for an unrecognized level
    (e.g. a config entry from before this setting existed) rather than
    raising - a bad/missing intensity should never be the reason a
    reminder fails to send.
    """
    return dict(INTENSITY_DATA.get(level, INTENSITY_DATA[INTENSITY_NORMAL]))


def pill_actions(entry_id: str) -> list[dict[str, str]]:
    """Notification actions for the owner's daily reminder/escalation.

    The action identifiers are suffixed with `entry_id` so the shared event
    listener in __init__.py can tell which cycle owner a tap belongs to, and
    so two different Perioder entries never collide in the mobile app.
    """
    return [
        {"action": f"{ACTION_CONFIRM_PILL_PREFIX}{entry_id}", "title": "Vzal(a) jsem"},
        {"action": f"{ACTION_POSTPONE_PILL_PREFIX}{entry_id}", "title": "Odložit"},
    ]


def _notify_entity_id(hass: HomeAssistant, device_id: str) -> str | None:
    """Find the `notify.*` entity belonging to a device, if any."""
    registry = er.async_get(hass)
    for entry in er.async_entries_for_device(registry, device_id):
        if entry.entity_id.startswith("notify."):
            return entry.entity_id
    return None


async def async_send_to_device(
    hass: HomeAssistant, device_id: str, title: str, message: str, *, data: dict[str, Any] | None = None
) -> None:
    """Send a notification to a device_id, or log a warning if it can't be resolved.

    `data` is passed straight through as `notify.send_message`'s own `data`
    field - e.g. `{"actions": pill_actions(entry_id)}` for actionable buttons.
    """
    entity_id = _notify_entity_id(hass, device_id)
    if entity_id is None:
        _LOGGER.warning(
            "Perioder: no notify entity found for device %s - notification not sent (%s)",
            device_id,
            title,
        )
        return

    payload: dict[str, Any] = {"entity_id": entity_id, "title": title, "message": message}
    if data:
        payload["data"] = data
    await hass.services.async_call("notify", "send_message", payload, blocking=False)


async def async_notify_owner(
    hass: HomeAssistant, entry, title: str, message: str, *, data: dict[str, Any] | None = None
) -> None:
    """Notify the cycle owner's own device, if one is configured."""
    device_id = get_settings(entry).get(CONF_OWNER_NOTIFY_DEVICE)
    if not device_id:
        _LOGGER.debug(
            "Perioder: no owner_notify_device configured for '%s' - skipping owner notification (%s)",
            entry.title,
            title,
        )
        return
    await async_send_to_device(hass, device_id, title, message, data=data)


async def async_notify_supporters(
    hass: HomeAssistant,
    entry,
    category: str,
    *,
    title: str,
    general_message: str,
    detailed_message: str,
) -> None:
    """Notify every supporter subscribed to `category`, at their own detail level."""
    for supporter in get_supporters(entry):
        if category not in supporter.get("categories", []):
            continue
        message = detailed_message if supporter.get("detail_level") == DETAIL_DETAILED else general_message
        await async_send_to_device(hass, supporter["device_id"], title, message)
