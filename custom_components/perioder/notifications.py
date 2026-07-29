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
"""
from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import CONF_OWNER_NOTIFY_DEVICE, DETAIL_DETAILED
from .settings import get_settings, get_supporters

_LOGGER = logging.getLogger(__name__)


def _notify_entity_id(hass: HomeAssistant, device_id: str) -> str | None:
    """Find the `notify.*` entity belonging to a device, if any."""
    registry = er.async_get(hass)
    for entry in er.async_entries_for_device(registry, device_id):
        if entry.entity_id.startswith("notify."):
            return entry.entity_id
    return None


async def async_send_to_device(hass: HomeAssistant, device_id: str, title: str, message: str) -> None:
    """Send a notification to a device_id, or log a warning if it can't be resolved."""
    entity_id = _notify_entity_id(hass, device_id)
    if entity_id is None:
        _LOGGER.warning(
            "Perioder: no notify entity found for device %s - notification not sent (%s)",
            device_id,
            title,
        )
        return

    await hass.services.async_call(
        "notify",
        "send_message",
        {"entity_id": entity_id, "title": title, "message": message},
        blocking=False,
    )


async def async_notify_owner(hass: HomeAssistant, entry, title: str, message: str) -> None:
    """Notify the cycle owner's own device, if one is configured."""
    device_id = get_settings(entry).get(CONF_OWNER_NOTIFY_DEVICE)
    if not device_id:
        _LOGGER.debug(
            "Perioder: no owner_notify_device configured for '%s' - skipping owner notification (%s)",
            entry.title,
            title,
        )
        return
    await async_send_to_device(hass, device_id, title, message)


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
