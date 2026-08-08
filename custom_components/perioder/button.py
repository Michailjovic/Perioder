"""Button platform for Perioder.

- "Confirm pill taken": one tap logs today's dose, so the dashboard doesn't
  need `perioder.log_pill_taken` for the common case (today, right now). If
  tracking wasn't active yet, this also auto-activates it (v0.9.7, see
  storage.py's `async_log_pill_taken()`) - today becomes `pack_start_date`.
  `date.*_pack_start_date` (date.py, v0.9.9) is there for picking a
  *different* day than today (the actual first day, backdated) - there used
  to be a `button.*_start_new_pack` here too, but a today-only button next
  to a full date picker doing the same underlying call
  (`async_start_new_pack()`) was one redundant control too many; removed in
  v0.9.9. `perioder.start_new_pack` (the service) is unaffected, still
  there for automations/voice/NFC.
- "Test notification" (v0.9.10): fires `notifications.async_notify_owner()`
  directly, bypassing every bit of `__init__.py`'s reminder/escalation
  timing logic (reminder_time, grace period, pause/missed state, the
  15-minute tick). Exists to isolate "the notify pipeline itself is broken
  (bad/missing `owner_notify_device`, no `notify.*` entity for it, HA can't
  reach the phone)" from "the pipeline is fine, it's just not the right
  moment yet" - the two look identical from "nothing arrived on my phone".
  Also drops a `persistent_notification` (Settings bell icon) reporting
  whether `owner_notify_device` was even configured, since a misconfigured
  device fails *silently* on the push side (see notifications.py's
  `async_notify_owner()`/`async_send_to_device()` - by design, one
  supporter's bad notify target shouldn't raise and block anything else).
- One "Log symptom: <x>" button per entry in `const.SYMPTOMS` (M5) - the
  "rychlé akce ... log symptomu" quick action from
  ANALYZA-A-ROADMAP.md section 2.9, logging via the same storage method as
  `perioder.log_symptom`.

The matching services still exist for backdating or automation/voice/NFC
use cases.
"""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from . import notifications
from .const import CONF_OWNER_NOTIFY_DEVICE, DOMAIN, SYMPTOMS
from .settings import get_settings
from .storage import PerioderData
from .time_util import local_now, local_today


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Perioder buttons for one cycle owner."""
    data: PerioderData = hass.data[DOMAIN][entry.entry_id]
    entities: list[ButtonEntity] = [
        ConfirmPillTakenButton(entry, data),
        TestNotificationButton(entry),
    ]
    entities.extend(LogSymptomButton(entry, data, symptom) for symptom in SYMPTOMS)
    async_add_entities(entities)


class TestNotificationButton(ButtonEntity):
    """Pressing this sends a one-off test push straight to `owner_notify_device`,
    with no reminder-time/grace-period/pause checks in the way - see the
    module docstring above for why this exists.
    """

    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_translation_key = "test_notification"
        self.entity_id = f"button.{slugify(entry.title)}_test_notification"
        self._attr_unique_id = f"{entry.entry_id}_test_notification"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Perioder",
        )

    async def async_press(self) -> None:
        settings = get_settings(self._entry)
        device_id = settings.get(CONF_OWNER_NOTIFY_DEVICE)

        await notifications.async_notify_owner(
            self.hass,
            self._entry,
            "🔔 Perioder - testovací notifikace",
            "Pokud tohle vidíš na telefonu, notifikační kanál (owner_notify_device -> notify.* entita) funguje.",
        )

        if device_id:
            outcome = (
                f"owner_notify_device je nastavené ({device_id}) - notifikace byla odeslána. "
                "Pokud na telefonu nic nepřišlo, zkontroluj v logu (Nastavení > Systém > Logy) "
                "hlášku 'Perioder: no notify entity found for device' - znamená to, že to "
                "zařízení nemá odpovídající notify.* entitu (stará/odpojená Companion app)."
            )
        else:
            outcome = (
                "owner_notify_device NENÍ v Configure nastavené - notifikace se neměla kam "
                "poslat (viz DEBUG log). Nastav ho v Nastavení > Zařízení a služby > Perioder > "
                "Configure > 'Tvoje vlastní notifikační zařízení'."
            )

        await self.hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "title": "Perioder - test notifikace",
                "message": f"Tlačítko zmáčknuto {local_now().strftime('%H:%M:%S')}. {outcome}",
                "notification_id": f"perioder_test_notification_{self._entry.entry_id}",
            },
        )


class ConfirmPillTakenButton(ButtonEntity):
    """Pressing this logs today's dose as taken.

    v0.9.7: if contraception tracking wasn't active yet, this also
    auto-activates it (see storage.py's `async_log_pill_taken()`) - so this
    button alone is enough for the common "just start taking it" case, and
    `date.*_pack_start_date` is only needed to explicitly (re)set/backdate
    the pack start date to something other than today.
    """

    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry, data: PerioderData) -> None:
        self._data = data
        self._attr_translation_key = "confirm_pill_taken"
        self.entity_id = f"button.{slugify(entry.title)}_confirm_pill_taken"
        self._attr_unique_id = f"{entry.entry_id}_confirm_pill_taken"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Perioder",
        )

    async def async_press(self) -> None:
        await self._data.async_log_pill_taken(local_today())


class LogSymptomButton(ButtonEntity):
    """Pressing this logs one symptom (see const.SYMPTOMS) with a timestamp."""

    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry, data: PerioderData, symptom: str) -> None:
        self._data = data
        self._symptom = symptom
        self._attr_translation_key = f"log_symptom_{symptom}"
        self.entity_id = f"button.{slugify(entry.title)}_log_symptom_{symptom}"
        self._attr_unique_id = f"{entry.entry_id}_log_symptom_{symptom}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Perioder",
        )

    async def async_press(self) -> None:
        await self._data.async_log_symptom(self._symptom)
