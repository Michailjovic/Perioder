"""Notification dispatch for Perioder (M4).

Two audiences, both resolved from a Home Assistant `device_id` (picked via
`DeviceSelector(integration="mobile_app")` in Config/Options Flow) to that
device's legacy per-device `notify.mobile_app_<slug>` service - deliberately
NOT the newer (HA 2024.10+) `notify.send_message` entity action, even though
that looks like the "modern"/correct choice.

Confirmed live 2026-08-09: `notify.send_message` rejects any extra `data`
payload at all - `voluptuous.Invalid: extra keys not allowed @ data['data']`
- for a mobile_app notify entity. It only supports a plain `title`/`message`,
not actionable buttons, Android channel/importance, iOS interruption-level/
critical sound, or any other companion-app-specific field this integration
needs (`pill_actions()`, `INTENSITY_DATA`, below). This is a confirmed,
still-open Home Assistant limitation as of 2026.8 - see
https://github.com/orgs/home-assistant/discussions/3684 ("Support advanced
companion app notification options for notify entities and groups", opened
2026-05-07, unresolved) - not a bug in this integration. The legacy
per-device service is still the only way to send anything beyond a bare
title/message; this is why v0.9.20's actionable buttons only ever "worked"
for the plain-message test-notification button (no `data=` argument, so it
never hit this) and never for the actual daily reminder until now. If HA
ever adds real support for this to `notify.send_message`, this module is
the only place that would need to change.

If no matching legacy service is found (e.g. mobile_app device removed, its
name changed since `owner_notify_device`/a supporter's `device_id` was
picked, or a future HA version finally drops the legacy service), the call
is skipped with a warning instead of raising - a bad/stale notify target for
one supporter shouldn't block anything else in the integration.

- `async_notify_owner()`: the cycle owner's own device (`owner_notify_device`
  setting) - used for the daily contraception reminder/escalation.
- `async_notify_supporters()`: every supporter subscribed to the given
  category (see const.SUPPORTER_CATEGORIES), respecting each supporter's own
  `detail_level` (general vs. detailed message).

v0.8.0 adds `pill_actions()`: the two mobile_app notification actions
("Vzal(a) jsem" / "Odložit") attached to the owner's reminder/escalation
notifications, via the legacy service's `data.actions` field. Tapping one
fires the `mobile_app_notification_action` event, handled in __init__.py.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.util import slugify

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


def _legacy_notify_service(hass: HomeAssistant, device_id: str) -> str | None:
    """The legacy per-device `notify.mobile_app_<slug>` service name for a
    mobile_app device, if one is currently registered - see module
    docstring for why this (not `notify.send_message`) is what actually
    gets called.

    v0.9.24 slugified `device.name` (the device registry's own name field)
    - wrong, confirmed live 2026-08-09: a device the user later renamed via
    Settings > Devices ("1plus") still failed with "no legacy
    notify.mobile_app_* service found", even though it was correctly
    selected as `owner_notify_device`. The legacy service's slug is fixed
    at mobile_app registration time from the *push-registration* device
    name (`config_entry.data["device_name"]`, the `mobile_app` integration's
    own `ATTR_DEVICE_NAME`) - it does NOT get renamed when the user renames
    the device afterwards in the UI. `device.name`/`device.name_by_user`
    can legitimately differ from that original registration name, so
    slugifying either of them can point at a service that was never
    created.

    Fixed by trying, in order of decreasing authority: every mobile_app
    config entry's own stored `device_name` (the actual source the legacy
    service slug was built from), then `device.name_by_user`, then
    `device.name` - first one that resolves to a service that actually
    exists wins. A device normally only has one mobile_app config entry, so
    in practice this is "try the real registration name, then fall back to
    whatever's shown in the UI".
    """
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        return None

    candidates: list[str] = []
    for entry_id in device.config_entries:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is not None and entry.domain == "mobile_app":
            registered_name = entry.data.get("device_name")
            if registered_name:
                candidates.append(registered_name)
    if device.name_by_user:
        candidates.append(device.name_by_user)
    if device.name:
        candidates.append(device.name)

    tried: list[str] = []
    for name in candidates:
        service = f"mobile_app_{slugify(name)}"
        if service in tried:
            continue
        tried.append(service)
        if hass.services.has_service("notify", service):
            return service

    _LOGGER.debug(
        "Perioder: no legacy notify.mobile_app_* service matched device %s - tried %s",
        device_id,
        tried,
    )
    return None


async def async_send_to_device(
    hass: HomeAssistant, device_id: str, title: str, message: str, *, data: dict[str, Any] | None = None
) -> None:
    """Send a notification to a device_id, or log a warning if it can't be resolved.

    `data` is passed straight through as the legacy service's own `data`
    field - e.g. `{"actions": pill_actions(entry_id)}` for actionable
    buttons, or an `INTENSITY_DATA` entry for channel/importance/push.
    """
    service = _legacy_notify_service(hass, device_id)
    if service is None:
        _LOGGER.warning(
            "Perioder: no legacy notify.mobile_app_* service found for device %s - notification not sent (%s)",
            device_id,
            title,
        )
        return

    payload: dict[str, Any] = {"title": title, "message": message}
    if data:
        payload["data"] = data
    await hass.services.async_call("notify", service, payload, blocking=False)


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
