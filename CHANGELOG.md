# Changelog

All notable changes to this project are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/); see `ANALYZA-A-ROADMAP.md`
section 8 for what the pre-1.0.0 range means for this project specifically.

## [0.1.4] - 2026-07-29

Bugfix release: v0.1.3 did not actually fix anything. Confirmed live - after
upgrading to v0.1.3, restarting HA, and deleting/recreating the integration,
Developer Tools > States still showed `binary_sensor.test_pms_window`
instead of `binary_sensor.test_pms_active` (and the date entity was still
wrong too).

### Fixed

- v0.1.3's fix (`self._attr_suggested_object_id = key`) set an attribute
  that doesn't exist on Home Assistant's `Entity` class - `suggested_object_id`
  is a **read-only property**, not a settable `_attr_*` field. HA silently
  ignored it; nothing changed. Verified directly against Home Assistant core
  source (`homeassistant/helpers/entity.py`,
  `homeassistant/helpers/entity_platform.py`, `dev` branch).
- Real mechanism, now confirmed by tracing `entity_platform.py`'s
  registration code (`_async_derive_object_ids`, lines ~1273-1306): an
  entity can pin its object ID by setting `self.entity_id` directly to a
  full `"<domain>.<object_id>"` string *before* it's added. The platform
  parses it with `split_entity_id()` into
  `internal_integration_suggested_object_id`, which takes priority over the
  (display-name-derived) `suggested_object_id` property when the entity
  registry picks the final ID. All 4 platforms now do this:
  `sensor.py`/`binary_sensor.py` set `self.entity_id = f"{domain}.{key}"` in
  the shared base class `__init__`; `date.py` and `select.py` set it
  directly (`"date.last_period_start"`, `"select.pms_override"`). The
  fabricated `_attr_suggested_object_id` lines are removed everywhere.
- `dashboard_test.yaml` version references updated to v0.1.4.

### Notes

- This is now verified against actual HA core source, not inferred from
  behavior - the fix should hold going forward without another round of
  guessing.
- Existing wrongly-named entities in a live instance (e.g.
  `binary_sensor.test_pms_window`) won't rename themselves - delete and
  recreate the integration (or manually rename the entity ID in its entity
  settings) to get the corrected IDs.

## [0.1.3] - 2026-07-29

Bugfix release: two entities got the wrong `entity_id`.

### Fixed

- `binary_sensor.<name>_pms_active` and `date.<name>_last_period_start`
  didn't exist under the IDs `dashboard_test.yaml` expected - confirmed live
  ("Entity not found") after the v0.1.2 dashboard fix started actually
  rendering. Root cause: with `has_entity_name = True` and no explicit
  object ID, Home Assistant derives `entity_id` from the entity's
  *translated display name*, not from its internal key/translation_key. Two
  entities had a display name that didn't slug-match their key (`pms_active`
  displayed as "PMS window" -> `..._pms_window`; `last_period_start`
  displayed as "Log period start" -> `..._log_period_start`); the other four
  happened to match by coincidence.
- Every entity in `sensor.py`, `binary_sensor.py`, `date.py`, and `select.py`
  now sets `_attr_suggested_object_id` explicitly to its internal key, so
  `entity_id` is pinned regardless of display name or future translation
  changes - not just a fix for these two, but a fix for this whole class of
  bug going forward.
- `dashboard_test.yaml`'s markdown card text updated to reference this
  version.

## [0.1.2] - 2026-07-29

Bugfix release for `dashboard_test.yaml` - the file didn't render.

### Fixed

- `dashboard_test.yaml` was wrapped in a top-level `title:`/`views:` structure,
  which is the format for a whole-dashboard raw editor. Home Assistant's
  per-view "Edit in YAML" editor (the one these setup instructions actually
  point to) expects a single view's own keys (`title`, `path`, `cards`) at
  the root instead - pasting the old file left `views:` unrecognized and HA
  silently defaulted the view to an empty `cards: []`, producing a blank
  page. The file now matches the per-view editor's expected structure.
- Documented a simpler zero-YAML alternative in the file's header: Settings
  > Devices & Services > Perioder > (device) > "Add to dashboard" builds an
  entities card from every entity on the device automatically. A Perioder
  entry showing up directly in the generic "Add Card" search dialog would
  need a custom Lovelace card/strategy (frontend JS) - out of scope until
  v2.0.0 (see `ANALYZA-A-ROADMAP.md`).

### Notes

- GitHub repository "description" and "topics" (HACS Action's repository
  check) are GitHub metadata, not files in this repo - set them under the
  repository's "About" section on GitHub. No code change can fix this.

## [0.1.1] - 2026-07-29

Bugfix release. v0.1.0 never actually reached a working state - installing it
and opening "Configure" would crash, and settings could silently desync - so
none of this is a behavior change from a user's point of view, just v0.1.0
becoming what it was meant to be.

### Fixed

- Options Flow ("Configure" on the integration) crashed with
  `AttributeError: property 'config_entry' of 'PerioderOptionsFlow' object has
  no setter`. Home Assistant made `self.config_entry = config_entry` in
  `OptionsFlow.__init__` a hard error as of 2025.12 (previously just a
  deprecation warning) - confirmed against a live HA 2026.7.3 instance.
  `config_flow.py` now uses `OptionsFlowWithReload` with no manual assignment;
  `async_get_options_flow` returns `PerioderOptionsFlow()` with no arguments,
  matching the current Home Assistant developer docs.
- Settings and supporters were stored in two places at once - the config
  entry's `data`/`options` *and* the runtime `Store` - with nothing keeping
  them in sync, so an edit made via Options Flow could silently diverge from
  what the sensors actually read. New `settings.py` reads settings and
  supporters straight from the config entry (the single source of truth);
  `storage.py` now only holds runtime state that changes between config
  edits: `last_period_start`, `pms_override`, `contraception`, `symptoms`.
- The HACS Action's brand check failed (repository not listed in
  home-assistant/brands, no local brand assets either). Added
  `custom_components/perioder/brand/icon.png` (and a copy at `brand/icon.png`)
  so the check passes locally.

### Added

- Date entity (`date.<name>_last_period_start`): setting it logs/backdates
  the period start directly from the dashboard - no external
  `input_datetime` helper needed. Reads and writes the same storage as
  `perioder.log_period_start`.
- Select entity (`select.<name>_pms_override`): auto / active / inactive,
  applies immediately - no external helper/script needed. Reads and writes
  the same storage as `perioder.set_pms_override`.
- `dashboard_test.yaml` now includes both entities directly, so the test
  dashboard needs nothing beyond the integration itself and this one file.

### Changed

- `lovelace_example.yaml` and `dashboard_test.yaml` entity IDs standardized
  on the "Test" naming convention used throughout the docs (previously
  inconsistently referenced "Alina" in one draft).

## [0.1.0] - 2026-07-28

First installable release. Covers the M1 foundation plus just enough of the
cycle/PMS logic (pulled forward from later milestones) to see real numbers
on a dashboard with test data - contraception, the calendar, symptoms, and
the supporter notification engine are intentionally not in yet.

### Added

- Project skeleton: `manifest.json`, `hacs.json`, GitHub Actions for `hassfest`
  and HACS validation.
- Config flow for setting up a cycle owner: cycle length, period duration, goal
  (track / avoid / plan), PMS window length, contraception regimen type
  (21/7, 24/4, continuous, custom), daily reminder time.
- Options flow: edit all settings after setup, plus supporter management - add
  or remove a supporter, choose which notification categories they receive
  (PMS window, upcoming period, contraception restock, missed dose, fertility
  window) and at what detail level (general / detailed). Reachable only by a
  Home Assistant administrator, by design.
- Storage layer (Home Assistant `Store`) covering cycle, contraception,
  symptoms, and supporters/settings, isolated per config entry so any number
  of independent cycle owners can be tracked in one instance.
- Pure cycle/fertility/PMS math module (`cycle_math.py`), with no Home
  Assistant dependencies - verified against a 28-day reference cycle covering
  every day 1-28 with no unassigned "gap" days between phases.
- Sensors: `cycle_day`, `phase`, `fertility`, `next_period` (days until).
- Binary sensors: `period_active`, `pms_active` (honors a manual per-cycle
  override).
- Services: `perioder.log_period_start` (with optional backdating) and
  `perioder.set_pms_override` (auto / force active / force inactive) - both
  target a specific cycle owner via a config entry selector, since one HA
  instance may track several independent people.
- `lovelace_example.yaml` - a single card to paste into an existing dashboard.
- Entities refresh immediately on service calls and on a 15-minute tick, so
  the cycle day rolls over without waiting for another action.

### Notes

- Contraception logic, the calendar, symptom logging, and the supporter
  notification engine are not implemented yet - the storage fields they'll
  need already exist, ready for a future release to build on.
- `manifest.json` codeowners/documentation/issue_tracker point at
  `github.com/Michailjovic/Perioder`.
