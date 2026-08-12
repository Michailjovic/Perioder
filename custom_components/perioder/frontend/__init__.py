"""Registers the bundled `perioder-calendar-card` as a Lovelace resource.

v0.9.30 - see CALENDAR-CARD-ADR.md for the full design/rationale (why a
vendored FullCalendar-style solution, why bundled in this repo instead of a
separate HACS "Plugin", why not the built-in `type: calendar` card). This
module only handles making the JS file reachable and known to Lovelace -
the card itself lives in `perioder-calendar-card.js` right next to this
file.

Two things happen, once per Home Assistant instance (not per config entry -
see `async_setup()` in `__init__.py`, which is what calls
`JSModuleRegistration.async_register()`):

1. A static HTTP path (`/perioder-frontend/...`) is registered so the JS
   file is actually reachable by the browser - this always works,
   regardless of Lovelace mode.
2. A Lovelace resource entry is auto-created/updated pointing at that path,
   so the card is available without the admin manually adding a resource -
   but this part **only works in storage-mode Lovelace** (the default; the
   one Michael's dashboards already use - see dashboard_alina.yaml's setup
   instructions). In YAML-mode Lovelace this step is skipped and a debug
   log explains the one manual step needed instead.

The `?v={version}` suffix on the resource URL is bumped every time
`manifest.json`'s version changes (same release process as everything
else, see ANALYZA-A-ROADMAP.md section 8) - without it, browsers/companion
apps can keep serving a cached, stale copy of the card after an update.

Verified 2026-08-13 against current (post-2024.7) Home Assistant frontend
APIs - `hass.http.async_register_static_paths()` / `StaticPathConfig`, not
the older synchronous `register_static_path()`. See
https://gist.github.com/KipK/3cf706ac89573432803aaa2f5ca40492/ (accessed
2026-08-13) for the pattern this follows.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_call_later

_LOGGER = logging.getLogger(__name__)

_FRONTEND_DIR = Path(__file__).parent
_COMPONENT_DIR = _FRONTEND_DIR.parent

with open(_COMPONENT_DIR / "manifest.json", encoding="utf-8") as _manifest_file:
    _INTEGRATION_VERSION: str = json.load(_manifest_file).get("version", "0.0.0")

# Base path the JS file is served under - deliberately not just "/perioder"
# to avoid any chance of colliding with a future non-frontend static path
# this integration might want under that name.
URL_BASE = "/perioder-frontend"

JS_MODULES: list[dict[str, str]] = [
    {
        "name": "Perioder – kalendář cyklu",
        "filename": "perioder-calendar-card.js",
        "version": _INTEGRATION_VERSION,
    },
]


class JSModuleRegistration:
    """Registers the static path and (storage-mode only) Lovelace resource."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.lovelace = hass.data.get("lovelace")

    async def async_register(self) -> None:
        await self._async_register_path()

        if self.lovelace is None:
            _LOGGER.debug(
                "Perioder: 'lovelace' not yet in hass.data - skipping automatic "
                "resource registration this run (will retry on next HA start)"
            )
            return

        mode = getattr(self.lovelace, "mode", None)
        if mode == "storage":
            await self._async_wait_for_lovelace_resources()
        else:
            filename = JS_MODULES[0]["filename"]
            _LOGGER.info(
                "Perioder: Lovelace is in YAML mode, so the calendar card resource "
                "can't be added automatically - add this once to your Lovelace "
                "'resources': {\"url\": \"%s/%s\", \"type\": \"module\"}",
                URL_BASE,
                filename,
            )

    async def _async_register_path(self) -> None:
        try:
            await self.hass.http.async_register_static_paths(
                [StaticPathConfig(URL_BASE, str(_FRONTEND_DIR), False)]
            )
            _LOGGER.debug("Perioder: registered static path %s -> %s", URL_BASE, _FRONTEND_DIR)
        except RuntimeError:
            # Already registered - happens on config entry reload (this
            # runs once per HA instance via async_setup, but a defensive
            # no-op here costs nothing and avoids a startup-order footgun).
            _LOGGER.debug("Perioder: static path %s already registered", URL_BASE)

    async def _async_wait_for_lovelace_resources(self) -> None:
        """Lovelace's own resource storage may not be loaded yet this early
        in startup - retry every 5s (matches the verified reference pattern)
        instead of assuming it's ready.
        """

        async def _check_loaded(_now: Any) -> None:
            if self.lovelace.resources.loaded:
                await self._async_register_modules()
            else:
                async_call_later(self.hass, 5, _check_loaded)

        await _check_loaded(None)

    async def _async_register_modules(self) -> None:
        existing = [r for r in self.lovelace.resources.async_items() if r["url"].startswith(URL_BASE)]

        for module in JS_MODULES:
            url = f"{URL_BASE}/{module['filename']}"
            match = next((r for r in existing if r["url"].split("?")[0] == url), None)

            if match is None:
                _LOGGER.info(
                    "Perioder: registering Lovelace resource '%s' (v%s)", module["name"], module["version"]
                )
                await self.lovelace.resources.async_create_item(
                    {"res_type": "module", "url": f"{url}?v={module['version']}"}
                )
                continue

            current_version = match["url"].split("?v=")[-1] if "?v=" in match["url"] else None
            if current_version != module["version"]:
                _LOGGER.info(
                    "Perioder: updating Lovelace resource '%s' to v%s (was v%s)",
                    module["name"],
                    module["version"],
                    current_version,
                )
                await self.lovelace.resources.async_update_item(
                    match["id"], {"res_type": "module", "url": f"{url}?v={module['version']}"}
                )
