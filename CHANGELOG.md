# Changelog

All notable changes to this project are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/); see `ANALYZA-A-ROADMAP.md`
section 8 for what the pre-1.0.0 range means for this project specifically.

## [0.4.0] - 2026-07-29

M4 - notification engine. This is the original motivating problem for the
whole project: a real daily contraception reminder with escalation,
replacing a dumb daily alarm, plus the supporter side of the notification
model designed all the way back in section 2.5 of `ANALYZA-A-ROADMAP.md`.

### Added

- `notifications.py`: dispatch helpers that resolve a `device_id` (picked
  via `DeviceSelector(integration="mobile_app")`, same as supporters
  already used) to that device's `notify` entity and call the generic
  `notify.send_message` action - the modern (2024.10+) notify-entity
  pattern. `async_notify_owner()` targets the new `owner_notify_device`
  setting; `async_notify_supporters()` targets every supporter subscribed
  to a given category, at their own `detail_level`. A device that can't be
  resolved to a notify entity logs a warning instead of failing anything
  else.
- New settings: `owner_notify_device` (optional - the cycle owner's own
  device for the daily reminder), `escalation_grace_minutes` (default 60,
  replaces the value that was hardcoded in v0.2.0/v0.3.0),
  `escalation_repeat_minutes` (default 30), `escalation_max_count` (default
  3), `restock_days_before` (default 3). All editable via Options Flow or
  `perioder.update_settings`.
- The 15-minute tick (already used for `request_refresh()`) now also runs
  `_async_check_contraception_notifications()`:
  - Sends the daily reminder to `owner_notify_device` once `reminder_time`
    has passed for a still-unconfirmed pill day.
  - After `escalation_grace_minutes` with no confirmation, calls
    `perioder.log_pill_missed` for real (this existed in storage.py since
    v0.2.0 but nothing ever called it), notifies the owner, and notifies
    every supporter subscribed to the `missed_dose` category - with a note
    appended if today is also in the fertile window (the "vynechaná dávka
    → propojení s fertilním oknem" item from the roadmap's M2/M3 section
    2.3).
  - Keeps re-notifying the owner only (not supporters again) every
    `escalation_repeat_minutes`, up to `escalation_max_count` times.
  - Confirming the dose (taken) at any point stops all of the above for
    that day - only an actual "taken" status ends it, not just any pill_log
    entry (see Fixed below).
  - Separately, once the pack has `restock_days_before` or fewer active
    pill days left, notifies supporters subscribed to
    `contraception_restock` once per pack.
  - Tick granularity is 15 minutes, so this isn't exact-time - fine for a
    daily reminder, but `escalation_repeat_minutes` shorter than ~15 has no
    extra effect.
- `switch.pause_notifications` + `perioder.pause_notifications` service:
  mute everything above (owner reminder/escalation and all supporter
  categories) without losing any cycle/contraception data.

### Fixed

- Caught during testing of the tick logic (standalone simulation, not live
  HA - see Notes): the first draft stopped the reminder/escalation flow
  entirely as soon as *any* `pill_log` entry existed for today, including
  one just created by the "missed" branch itself - so escalation fired
  once and then silently never repeated, no matter how long it went
  unconfirmed. Fixed to only stop on a `"taken"` status; a `"missed"` entry
  now correctly keeps escalating up to `escalation_max_count`.

### Changed

- `sensor.contraception_status` now uses the configurable
  `escalation_grace_minutes` setting instead of a hardcoded 60-minute grace
  period, so the sensor and the notification engine always agree on what
  "missed" means.
- `hacs.json`'s minimum Home Assistant version raised from `2024.6.0` to
  `2024.10.0` - the notify-entity platform (`notify.send_message`) this
  release's dispatch relies on landed around then. This is a reasonable
  estimate, not something verified against Home Assistant's own release
  notes for the exact version.

### Notes

- **Scope, deliberately**: only `missed_dose` and `contraception_restock`
  fire as supporter notifications in this release. `pms`, `period`, and
  `fertility` as their own *transition-triggered* supporter notifications
  (e.g. "PMS window just started", "period starting in 2 days") are not
  wired up yet - the category subscriptions have existed since v0.1.1 and
  the dispatch engine now exists to support them, but building all five at
  once risked doing each one less carefully. Left as an explicit follow-up
  on the roadmap.
- **Not independently verified against a live Home Assistant instance or a
  real mobile_app device** - only the pure decision logic (when to remind,
  when to escalate, when to stop, restock timing) was verified via a
  standalone simulation outside Home Assistant (same approach used for
  `cycle_math.py`/`pill_math.py`/`calendar.py`'s date arithmetic). The
  device_id → notify entity resolution and the actual `notify.send_message`
  call are new, HA-coupled code paths that haven't been exercised against
  a running instance - please report if a configured `owner_notify_device`
  or supporter doesn't actually receive anything.

## [0.3.0] - 2026-07-29

M3 completed (except the notification-facing pieces, deferred to M4) -
`calendar.py` and `perioder.update_settings`.

### Added

- `calendar.cycle_calendar` (one per cycle owner): predicted period blocks
  and fertile-window blocks projected both forward and backward from
  `last_period_start` to cover whatever range Home Assistant queries, plus
  predicted pack-pause blocks when the regimen has pause days. On top of the
  predictions, every *logged* `pill_log` entry (taken/missed) shows up as
  its own single-day event, with the confirmation delay vs. `reminder_time`
  in the description - directly the "see which dates the pill was actually
  taken, and how delayed" idea noted in `ANALYZA-A-ROADMAP.md` section 2.1
  on 2026-07-29. Deliberately does not invent an event for every
  future/unlogged pill day, to avoid a wall of one-event-per-day noise.
- `perioder.update_settings` service: change one or more settings
  (cycle_length, period_duration, goal, pms_window_days, regimen_type,
  pack_size, pause_days, reminder_time) for a cycle owner without going
  through Options Flow - only the fields provided are changed. Applies
  immediately without a reload: sensors already read settings straight from
  the config entry on every access (see settings.py), and
  `async_update_entry` mutates that same entry object in place.
- `dashboard_test.yaml` now includes a calendar card.

### Changed

- **Storage schema**: `pill_log` entries changed from a plain
  `"taken"`/`"missed"` string to `{"status": ..., "logged_at": <isoformat
  datetime or None>}`, so the actual confirmation time is available (needed
  for the calendar's delay display). Existing v0.2.0 data is normalized to
  the new shape automatically on load - no manual migration needed, no data
  lost (old entries just get `logged_at: None`, so they won't show a delay
  figure, only the taken/missed marker).
- `pill_math.pill_status()` updated for the new `pill_log` shape; added
  `pill_math.delay_minutes()`.
- `sensor.contraception_status` now exposes `logged_at`/`delay_minutes` as
  extra state attributes when today's dose has been confirmed.

## [0.2.0] - 2026-07-29

M2 - contraception core. First release that does something with contraception
data beyond storing it: pack-day status, a one-tap "confirm taken" button,
and the matching services. This was the original motivating problem for the
whole project (replacing a dumb daily alarm) - see `ANALYZA-A-ROADMAP.md`.

### Added

- `pill_math.py` - pure pack-day math, no Home Assistant dependencies (same
  pattern as `cycle_math.py`): `day_in_pack`, `is_pill_day`,
  `days_until_pack_ends`, and `pill_status` (today's status: `inactive` /
  `paused` / `pending` / `taken` / `missed`, the last one based on
  `reminder_time` + a grace period, default 60 minutes). Verified standalone
  against a 21/7 regimen: pill days, pause days, cycle wraparound, and all
  five statuses.
- `sensor.contraception_status` and `sensor.pack_days_remaining`.
- `binary_sensor.contraception_active` and `binary_sensor.pill_taken_today`.
- `button.confirm_pill_taken` - one tap logs today's dose as taken; calls
  the same storage method as the new service below.
- Services: `perioder.log_pill_taken` (optional date, for backdating),
  `perioder.start_new_pack` (optional date), `perioder.set_contraception_active`.
- `dashboard_test.yaml` and `lovelace_example.yaml`/README updated with the
  new entities and a one-time `start_new_pack` call to begin testing.

### Notes

- The daily reminder + escalation notification (also listed under M2 on the
  roadmap) is deferred to M4, where it's built together with the supporter
  notification engine - both need the same "send + track an actionable
  notification" plumbing, and there's no owner-facing notify target
  configured yet to build it against. Today's status is fully computable
  and visible on the dashboard/Developer Tools without it; only the *push
  notification* is still manual for now.
- `pack_size`/`pause_days` are the actual source of truth for the math
  regardless of which `regimen_type` label is picked in Config/Options Flow
  - all three built-in regimens just pre-fill those two numbers in the form.
  Not a new issue introduced here, just documented while implementing
  `pill_math.py` against the existing `settings.py`.

## [0.1.5] - 2026-07-29

Bugfix release: v0.1.4 fixed the *object ID* part but dropped the device
name prefix - entities came back as `binary_sensor.pms_active` instead of
`binary_sensor.test_pms_active` (confirmed live).

### Fixed

- v0.1.4 pinned `self.entity_id` to a fixed string like
  `"binary_sensor.pms_active"`, with no reference to the device/entry name.
  That value becomes `internal_integration_suggested_object_id` and is used
  *as-is* by the entity registry - unlike the normal `has_entity_name`
  auto-naming path, it does **not** get the device name prepended. Since
  every cycle owner is a separate config entry/device, this would also have
  caused an ID collision the moment a second owner was added (both wanting
  plain `pms_active`).
- All 4 platforms now build the entity_id from the device name themselves:
  `self.entity_id = f"{domain}.{slugify(entry.title)}_{key}"` (e.g. entry
  titled "Test" -> `binary_sensor.test_pms_active`,
  `date.test_last_period_start`). This restores the per-owner prefix
  `dashboard_test.yaml` already expects, and keeps IDs distinct when
  multiple cycle owners exist.
- `dashboard_test.yaml` version references updated to v0.1.5.

### Notes

- As with v0.1.4, existing wrongly-named entities from a live instance
  won't rename themselves - delete and recreate the integration to pick up
  the corrected IDs.

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
