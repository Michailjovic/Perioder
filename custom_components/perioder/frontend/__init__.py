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

**v0.9.31 fix (2026-08-18) - card never actually appeared live:** two bugs
in the "storage mode" detection and resource-load wait, found while
debugging why `perioder-calendar-card` rendered as "Custom element doesn't
exist" on Michael's real instance despite a clean `node --check` and a full
HA restart:

1. `hass.data["lovelace"]` is a `LovelaceData` dataclass whose field is
   `resource_mode`, not `mode` - confirmed against
   homeassistant/components/lovelace/__init__.py on the `dev` branch. The
   old code read `getattr(self.lovelace, "mode", None)`, which is always
   `None` (the attribute doesn't exist), so it always took the "YAML mode,
   skip auto-registration" branch and only logged a debug line - even on
   an instance that's genuinely in storage mode. Fixed by reading
   `resource_mode` instead.
2. `ResourceStorageCollection.loaded` only flips `True` once *something*
   calls `resources.async_load()` - normally the frontend's own resources
   panel, the first time an admin opens Settings > Dashboards > Resources
   after a restart. The old code passively polled `.loaded` every 5s
   without ever forcing the load itself, so on an instance where nobody
   has opened that panel since the last restart, the wait never ends and
   the resource is never created. Fixed by calling
   `resources.async_get_info()`, which has HA's own lazy-load guard
   built in (`if not self.loaded: await self.async_load()`) and forces
   the load immediately instead of waiting for a coincidence.
   Unguarded direct calls to `async_items()`/`async_create_item()` on a
   not-yet-loaded `ResourceStorageCollection` were also a real HA core
   data-loss bug elsewhere (silently overwrote and wiped
   `.storage/lovelace_resources` - home-assistant/core#165767, fixed by
   home-assistant/core#165773); forcing the load via `async_get_info()`
   first means this module can't hit that even on an HA version that
   predates the core fix.
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

        # NOTE: the field is `resource_mode`, not `mode` - `LovelaceData`
        # (homeassistant/components/lovelace/__init__.py) has no `mode`
        # attribute at all. Reading the wrong name silently always
        # returned None here pre-v0.9.31, which meant automatic resource
        # registration never ran even in storage mode - see module
        # docstring "v0.9.31 fix".
        resource_mode = getattr(self.lovelace, "resource_mode", None)
        if resource_mode == "storage":
            await self._async_register_modules()
        else:
            filename = JS_MODULES[0]["filename"]
            _LOGGER.info(
                "Perioder: Lovelace resources are in YAML mode (resource_mode=%s), "
                "so the calendar card resource can't be added automatically - add "
                "this once to your Lovelace 'resources': {\"url\": \"%s/%s\", "
                "\"type\": \"module\"}",
                resource_mode,
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

    async def _async_register_modules(self) -> None:
        """Force-load the resource collection, then create/update our entry.

        `resources.async_get_info()` carries HA's own lazy-load guard
        (`if not self.loaded: await self.async_load()`) and is safe to call
        any number of times - it's what forces `.loaded` to become True
        instead of this module passively waiting for something else to do
        it (see module docstring "v0.9.31 fix" point 2). Falls back to a
        short retry loop only if a future HA version ever removes
        `async_get_info()` entirely, so this never hard-fails on a version
        mismatch.
        """
        resources = self.lovelace.resources

        if hasattr(resources, "async_get_info"):
            await resources.async_get_info()
        elif not resources.loaded:
            await self._async_retry_until_loaded(resources)
            return
        else:
            await self._async_write_modules(resources)
            return

        await self._async_write_modules(resources)

    async def _async_retry_until_loaded(self, resources: Any) -> None:
        async def _check_loaded(_now: Any) -> None:
            if resources.loaded:
                await self._async_write_modules(resources)
            else:
                async_call_later(self.hass, 5, _check_loaded)

        await _check_loaded(None)

    async def _async_write_modules(self, resources: Any) -> None:
        existing = [r for r in resources.async_items() if r["url"].startswith(URL_BASE)]

        for module in JS_MODULES:
            url = f"{URL_BASE}/{module['filename']}"
            match = next((r for r in existing if r["url"].split("?")[0] == url), None)

            if match is None:
                _LOGGER.info(
                    "Perioder: registering Lovelace resource '%s' (v%s)", module["name"], module["version"]
                )
                await resources.async_create_item(
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
                await resources.async_update_item(
                    match["id"], {"res_type": "module", "url": f"{url}?v={module['version']}"}
                )
