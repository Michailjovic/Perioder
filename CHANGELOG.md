# Changelog

All notable changes to this project are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/); see `ANALYZA-A-ROADMAP.md`
section 8 for what the pre-1.0.0 range means for this project specifically.

## [0.9.22] - 2026-08-09

### Added

- Full debug trace for the notification engine, so "why didn't it fire" is
  answerable from inside Home Assistant instead of by pasting logs into a
  chat: `_async_check_contraception_notifications()` and
  `_compute_next_check_at()` now both return a short Czech explanation of
  what they did/decided (which branch, which value tipped it) instead of
  silently returning `None`. Surfaced two ways after every single run,
  successful or not:
  - `sensor.*_notification_debug` (new, diagnostic category): state = last
    outcome, attributes = `checked_at`, `next_check_at`, `next_check_reason`.
  - A `persistent_notification` with a fixed `notification_id` per entry
    (updates in place, doesn't spam the bell icon) showing the same thing.
  Both added to `dashboard_alina_admin.yaml` / `dashboard_test_admin.yaml`
  (a markdown card unpacks the attributes into readable text). The daily
  reminder/notification-intensity entities were also added to the admin
  dashboard's "Ovládání" section - they'd only been on the day-to-day one
  so far.

## [0.9.21] - 2026-08-09

### Fixed

- Root cause of "I set a new reminder time / notification intensity and
  nothing happened" persisting even after 0.9.19's point-in-time scheduler:
  `time.py`'s reminder-time entity and `select.py`'s notification-intensity
  entity (both new in 0.9.19/0.9.20) write straight to `entry.options`,
  deliberately *without* triggering Options Flow's usual full entry reload
  (see their docstrings) - but nothing told the already-running scheduler
  to recompute. It kept sleeping until whatever instant it had *previously*
  computed, which could be long after (or entirely unrelated to) the value
  someone had just changed - silently dropping the change. The existing
  `perioder.update_settings` service (writes `entry.options` the same way,
  pre-dates this notification engine) and the pause-notifications
  switch/service (unpausing skips straight back to whatever stale schedule
  was computed while paused) had the identical gap.
  - New `PerioderData.async_request_reschedule` hook (set by
    `__init__.py`'s `async_setup_entry`): a zero-arg async callable that
    forces an immediate re-check + reschedule. Wired into `time.py`,
    `select.py`, `switch.py`'s pause toggle, and the `update_settings` /
    `pause_notifications` services.
- Defensive hardening: `_async_run_and_reschedule()` now wraps both the
  check itself and computing the next wake in their own try/except. Before
  this, *any* unhandled exception on any single run (a bug, a partially
  deployed version with mismatched files across settings.py/__init__.py,
  ...) would have silently killed the entire reschedule chain forever -
  nothing would fire again until the next full HA restart, with no
  indication why. Now it logs the traceback and falls back to a plain
  `_HEARTBEAT` retry instead, so a bug in one check costs at most one
  missed check, never every future one.

## [0.9.20] - 2026-08-09

### Added

- `select.*_notification_intensity` (four levels: quiet / normal / urgent /
  critical) - how pushy the daily reminder + its escalation should be on
  the owner's phone. Only those two notifications; not supporters, not the
  one-shot restock/low-stock notices. Settable both from admin Configure
  (`notification_intensity` in the settings form) and from the cycle
  owner's own dashboard (same `entry.options`-direct-write pattern as
  `time.py`'s reminder-time entity, added to `dashboard_alina.yaml` /
  `dashboard_test.yaml`). Levels map to real mobile_app `data` payloads in
  `notifications.INTENSITY_DATA` - Android notification channel + importance
  (`quiet`→low, `normal`→default, `urgent`→high with `priority: high`/
  `ttl: 0`), iOS `push.interruption-level` (passive/active/time-sensitive),
  and for `critical` specifically: iOS `push.sound.critical: 1` (true
  critical alert, bypasses silent/Do Not Disturb) and Android's reserved
  `alarm_stream` channel (bypasses silent/vibrate mode) - see the Home
  Assistant Companion docs linked in `notifications.py`.

## [0.9.19] - 2026-08-09

### Fixed

- 0.9.18's 1-minute polling interval was a stopgap, not the real fix - still
  not "exactly at the configured time" as expected, just close to it. The
  notification engine no longer polls on any fixed interval: `__init__.py`
  now schedules exactly one `async_track_point_in_time` call for the next
  instant that actually matters (`reminder_time`, the grace deadline, the
  next escalation, a live snooze, or local midnight for the plain cycle
  sensors), and reschedules itself from scratch every time it runs, from
  the fresh state that run just produced. See `_compute_next_check_at()`
  and `_async_run_and_reschedule()`. A settings change (which reloads the
  entry) now also takes effect on its very next wake instead of up to a
  polling-interval's worth of delay later.
- Options Flow navigation was backwards: the base menu (Edit settings /
  Manage supporters) had no "Done" of its own - the only step that actually
  saved (`async_create_entry`) lived inside "Manage supporters", so editing
  just the settings meant detouring through an unrelated submenu to find
  the save button. "Done" now lives directly in the base menu; "Manage
  supporters" instead gets a "Back to menu" option, matching how "Edit
  settings" already returned to the base menu after its own submit.

### Added

- `time.*_reminder_time` (`time.py`): the daily contraception reminder time
  is now also settable as a plain entity, not just via the admin-only
  Options Flow - so the cycle owner can pick her own reminder time from her
  own dashboard. Writes straight to `entry.options` (the same place Options
  Flow writes to, so whichever UI was used last simply wins - no separate
  "two sources of truth"), without triggering Options Flow's usual full
  entry reload, since the notification scheduler already reads settings
  fresh on every run. Added to `dashboard_alina.yaml` / `dashboard_test.yaml`
  next to the pills-in-stock tile.

## [0.9.18] - 2026-08-09

### Fixed

- Even after 0.9.17's deadlock fix, a freshly-set `reminder_time` (e.g.
  21:25, tested live 2026-08-09) still didn't arrive by a minute past -
  because `async_track_time_interval(REFRESH_INTERVAL)` fires relative to
  whenever the config entry last (re)loaded (HA restart, or any Options Flow
  save via `OptionsFlowWithReload` - including the very save that changed
  `reminder_time`), not aligned to wall-clock boundaries. With
  `REFRESH_INTERVAL` at 15 minutes, the next check after a given
  `reminder_time` could legitimately land anywhere up to ~15 minutes later
  depending on that reload phase - not a bug in the notification logic
  itself, just very poor perceived timing precision for something users set
  to an exact minute.
  - `REFRESH_INTERVAL`: 15 minutes -> 1 minute. Caps the worst case at under
    a minute, cheap enough to run every minute (in-memory checks + at most
    one notify call).

## [0.9.17] - 2026-08-09

### Fixed

- The daily contraception reminder could get permanently stuck and stop
  firing entirely - confirmed live 2026-08-09, still happening even with
  0.9.16 (the clock fix) deployed and the notify pipeline itself verified
  working ("Test notification" button). Root cause: in
  `_async_check_contraception_notifications()`, the `snoozed_until` check
  (from tapping "Odložit" on a reminder/escalation push) ran *before* the
  check that sends today's initial reminder and clears `snoozed_until`
  (`async_mark_reminder_sent()`). If `snoozed_until` was ever left sitting
  in the future for any reason (a value computed before the 0.9.16 clock
  fix, an unusually long `escalation_repeat_minutes`, ...), every future
  reminder was blocked forever - the only code path that clears
  `snoozed_until` was itself unreachable while snoozed, a deadlock.
  - Reordered the checks: today's initial reminder now always sends once
    `last_reminder_date != today`, regardless of any leftover snooze -
    "Odložit" is only meant to postpone the *escalation* nag after a
    reminder already went out, not block the next day's fresh one. This
    also self-heals any snooze stuck in the future, since sending today's
    reminder always clears it.

## [0.9.16] - 2026-08-08

### Fixed

- The daily contraception reminder (and every other time-of-day-sensitive
  check: escalation, grace period, snooze, restock/low-stock dedup, the
  09:00-style `reminder_time` comparison itself) used Python's bare
  `datetime.now()` / `date.today()` throughout the integration. Those read
  the underlying OS/container clock, not Home Assistant's own configured
  time zone (Settings > General > Time zone) - a very common mismatch when
  HA runs in a Docker container whose OS clock is UTC regardless of what
  time zone HA is actually set to. Confirmed live 2026-08-08: the 09:00
  reminder never fired because the code's "now" didn't match the intended
  wall-clock 09:00.
  - New `time_util.py`: `local_now()`/`local_today()`, both backed by
    `homeassistant.util.dt.now()` (HA's own timezone-correct "now"), with
    the tzinfo stripped back off so they stay drop-in compatible with
    every existing naive-datetime call site (`datetime.combine(...)`,
    stored `.isoformat()` timestamps, etc.) - no aware/naive comparison
    changes needed anywhere else.
  - Every `datetime.now()`/`date.today()` call across `__init__.py`,
    `sensor.py`, `binary_sensor.py`, `button.py`, `calendar.py`, `date.py`,
    and `storage.py` now goes through `time_util` instead.

## [0.9.15] - 2026-08-08

### Fixed

- The four dashboard files' calendar cards used `entities: [{entity: ...,
  color: '#...'}]` to force a custom color per category calendar. That
  object form isn't part of the built-in `type: calendar` card's schema
  (confirmed against the official docs - `entities` is a plain list of
  entity ID strings, nothing more; per-entity custom colors are a
  long-standing open feature request, not implemented). The invalid
  config made the card hang in a permanent loading spinner client-side -
  no error shown, and a hard refresh didn't help because the config
  itself, not cached state, was the problem. Reverted `entities:` back to
  plain entity ID lists on all four dashboards. The four category
  calendars from 0.9.14 (`period_calendar`/`fertile_calendar`/
  `pms_calendar`/`pause_calendar`) are still split out and each still
  gets *a* distinct color from the built-in card's own auto-assignment
  (by entity list order) - just not the specific red/green/purple/grey
  chosen in 0.9.14, since the built-in card has no way to pin that down.
  A third-party card (e.g. `calendar-card-pro` via HACS) would be needed
  for exact, chosen-by-us colors; not added here - ask if that's wanted.

## [0.9.14] - 2026-08-08

### Added

- `calendar.py`: four new lightweight per-category calendar entities -
  `period_calendar`, `fertile_calendar`, `pms_calendar`, `pause_calendar` -
  each showing only its own block kind. The built-in Lovelace `calendar`
  card can only color events per-*entity*, not per-event-type within one
  entity, so this is what makes real color-coding possible (period/fertile
  window/PMS/pack pause each in their own color) without pulling in a
  third-party calendar card again.

### Changed

- `dashboard_test.yaml` / `dashboard_alina.yaml` (the day-to-day view):
  - The whole card list is now wrapped in one `vertical-stack`. Lovelace's
    default masonry view auto-distributes top-level cards into multiple
    columns based on screen width, which on a wide screen was splitting
    the symptom tiles and calendar into a seemingly random second/third
    column instead of following reading order. A `vertical-stack` counts
    as a single card for masonry's purposes, so the layout is now always
    one predictable top-to-bottom column regardless of screen width.
  - The bottom calendar no longer points at `cycle_calendar` (which always
    includes PMS) - it now lists `period_calendar` (red), `fertile_calendar`
    (green) and `pause_calendar` (grey) with per-entity colors. PMS is
    admin-only info about the cycle owner, not something to surface to her
    about herself on her own dashboard - same convention already
    documented on `binary_sensor.pms_active`, just not actually followed
    on the calendar card until now.
- `dashboard_test_admin.yaml` / `dashboard_alina_admin.yaml`: same
  vertical-stack wrap, plus a new "Kalendář cyklu (barevně)" card listing
  all four category calendars including `pms_calendar` (purple), colored
  the same way as the owner dashboard. The existing detailed single-color
  `cycle_calendar` card (pill-log confirmation history) is kept alongside
  it, retitled to make clear it's specifically for that.
- Colors used: period `#e5484d` (red), fertile window `#30a46c` (green),
  PMS `#8e4ec6` (purple), pack pause `#8b8d98` (grey) - a fairly standard
  palette in period-tracking apps (red/coral for bleeding, green for the
  fertile window, purple for PMS/mood-related symptoms, neutral grey for
  "nothing to track" days).

## [0.9.13] - 2026-08-08

### Changed

- `dashboard_test.yaml` / `dashboard_alina.yaml` (the day-to-day view)
  redesigned per feedback that the previous version, while less cluttered
  than the original single flat list, still wasn't comfortable to use:
  - Every button (confirm pill, log symptom) now requires a **hold**
    instead of a tap (`tap_action: none` + `hold_action` calling
    `button.press`) - a plain tap or a scroll gesture over the tile no
    longer does anything, which was the actual bug: scrolling past
    "Potvrdit prášek" or a symptom tile could register as a press.
  - Warmer, less clinical look: pink/purple/amber/red tile colors instead
    of blue, warmer icons (`mdi:water-outline`, `mdi:moon-waning-crescent`,
    `mdi:heart-pulse`-style symptom icons), a friendly Czech greeting.
  - Contraception status and last symptom are now full Czech sentences via
    a templated markdown card (`{{ map.get(state, state) }}`) instead of
    the entity's raw translated state - which was leaking English
    ("Pending", "Mood change") whenever the viewing profile's HA frontend
    language wasn't Czech; the template sidesteps frontend locale
    entirely.

## [0.9.12] - 2026-08-08

### Diagnosed (no code change - environment issue)

- Root cause of the "cycle day: 98 / next period: -69 days" reports finally
  found: the user also runs the `cyclist` integration for the same person,
  named "Alina" in both. Home Assistant's entity registry gave the
  second-loaded integration's `sensor.alina_cycle_day` a silent `_2` suffix
  to avoid the collision - the dashboard's unsuffixed `sensor.alina_cycle_day`
  was actually `cyclist`'s entity (unrelated data, coincidentally
  same-shaped state), not Perioder's. Every live check via the Home
  Assistant MCP connector had actually been reading the *correct* (`_2`)
  Perioder entity the whole time, which is why the numbers always looked
  right from that angle - the disconnect was entirely about which entity
  the dashboard YAML pointed at. Resolved by uninstalling `cyclist` and
  recreating the affected entity IDs; no Perioder code was at fault. See
  the new README "Known gaps" entry for how to avoid this with any other
  same-purpose integration.

### Changed

- Reverted the v0.9.11 two-tab single-dashboard (`views:` + "Raw
  configuration editor") back to **two separate single-view dashboards**
  per the user's explicit preference: `dashboard_test.yaml` (day-to-day)
  and `dashboard_test_admin.yaml` (everything else), each pasted the
  original, simpler way (per-view "Edit in YAML"). Same split for the
  personal `dashboard_alina*.yaml` copies.

### Investigating

- "Cycle day"/"next period" still shown wrong on the dashboard (98 /
  -69 days) after a hard refresh, despite `sensor.*_cycle_day` /
  `sensor.*_next_period` reading correctly (12 / 17, matching the logged
  dates) via three separate live queries through the Home Assistant MCP
  connector across ~40 minutes. Since that path reads Home Assistant's
  in-memory state directly (not the browser), the backend computation
  itself is very likely fine; a plain browser hard-refresh not fixing it
  points at something below the browser cache layer for however the
  dashboard is actually being viewed (frontend service worker/PWA cache,
  a Companion App WebView on a tablet - "Ctrl+Shift+R" doesn't apply
  there at all, or a caching reverse proxy) - unresolved, needs to know
  which device/app is showing the stale value to pin down further.

## [0.9.11] - 2026-08-08

### Changed

- `dashboard_test.yaml` / `dashboard_alina.yaml` restructured into a whole
  dashboard with **two views/tabs** instead of one flat card list: a simple
  day-to-day tab (confirm pill, log period, cycle day/next period,
  symptoms, calendar) and an "Admin" tab with everything else (PMS window,
  supporters, pack start date correction, test notification, pause switch,
  both calendars) - the single flat list had grown to ~20 cards/rows and
  was reported as genuinely hard for a non-technical cycle owner to use.
  PMS stays off the simple tab on purpose (see binary_sensor.py - it's a
  supporter-facing signal, not something to surface to the cycle owner
  about themselves). Setup changed accordingly: this now needs the
  dashboard-level **"Raw configuration editor"** (handles multiple
  `views:`), not the single-view YAML editor used by older versions of
  this file.

### Fixed nothing, but investigated

- Reported "cycle day shows 98 / next period shows -69" while phase/
  fertility looked correct: live-queried the actual entity states via the
  Home Assistant MCP connector (bypasses any dashboard/frontend caching)
  and got `cycle_day: 12`, `next_period: 17` - matching what the code
  computes from the logged dates. `next_period` in particular can
  structurally never be negative (`days_until_next_period()`'s loop only
  ever advances `candidate` until it's `>= today`), which rules out a
  current backend bug outright - the dashboard was showing a stale
  browser-cached value, not a live one. No code change needed; a hard
  refresh (Ctrl+Shift+R) should clear it.

## [0.9.10] - 2026-08-08

### Added

- `button.*_test_notification` - fires `notifications.async_notify_owner()`
  directly, bypassing every bit of the reminder/escalation timing logic
  (reminder_time, grace period, pause state, the 15-minute tick). Isolates
  "the notify pipeline itself is broken" from "it's just not the right
  moment yet" - both look identical from "nothing arrived on my phone",
  which is exactly the report that prompted this (owner confirmed
  `owner_notify_device` is set, no notification the previous evening).
  Also drops a `persistent_notification` reporting whether
  `owner_notify_device` was even configured, since a bad/missing notify
  target otherwise fails silently on the push side by design (one
  supporter's bad target shouldn't block anything else - see
  notifications.py).

## [0.9.9] - 2026-08-07

### Changed

- Replaced `button.*_start_new_pack` (v0.9.5, today-only) with
  `date.*_pack_start_date` (date.py) - a settable date entity, same pattern
  as `date.*_last_period_start`: picking a date *is* the action (activates
  tracking + sets `pack_start_date`, via the same `async_start_new_pack()`),
  backdating included, no separate button needed for "today" vs. a service
  call for "any other day". This is meant to make the one-time setup step
  clearer: set this once (or press `button.*_confirm_pill_taken`, which
  auto-activates with today, v0.9.7) and the rest - pill day vs. pause day,
  restock timing, calendar pause blocks, daily reminders - already computes
  itself every cycle from that single date, nothing here needs repeating.
  `perioder.start_new_pack` (the service) is unchanged.

## [0.9.8] - 2026-08-07

### Fixed

- **Critical**: every service/button that relied on `date.today()` as a
  default (`log_period_start`, `log_pill_taken`, `start_new_pack`, and the
  `>` future-date guards in `log_period_end`) failed with
  `AttributeError: module 'custom_components.perioder.date' has no
  attribute 'today'` as soon as the integration's own `date` platform
  (`date.py`) got loaded. Root cause: `__init__.py` IS the package's own
  module namespace, and Python's import machinery binds any submodule it
  imports (`custom_components.perioder.date`, the Platform.DATE entity
  file) as an attribute of that same name on the parent package - silently
  overwriting the `date` name `__init__.py` had bound to `datetime.date` at
  import time via `from datetime import date`. Fixed by aliasing the import
  (`from datetime import date as dt_date, ...`) and updating every call
  site - `__init__.py` no longer keeps a `date` name around for the
  platform import to clobber. Only `__init__.py` was affected; every other
  module (`calendar.py`, `sensor.py`, `storage.py`, etc.) has its own
  separate namespace and was never at risk.

### Changed

- Dashboards (`dashboard_test.yaml`, and the personal, gitignored
  `dashboard_*.yaml` copies) swap the third-party `atomic-calendar-revive`
  card (v0.9.3) for the built-in `type: calendar` card with
  `initial_view: dayGridMonth` plus a `card_mod` style setting `min-height`
  on `ha-card` - confirmed live 2026-08-07 that this combination (unlike
  the plain `card_mod` attempt in v0.9.2) actually fixes the month-grid
  clipping, so the integration needs only the common `card-mod` HACS
  frontend module instead of a whole extra calendar card.

## [0.9.7] - 2026-08-07

### Fixed

- `button.*_confirm_pill_taken` (and `perioder.log_pill_taken`) only ever
  wrote to `pill_log` and never touched `active`/`pack_start_date` - so
  confirming doses while contraception tracking had never been started left
  `binary_sensor.*_contraception_active` stuck `off` next to real, logged
  pill confirmations, with no obvious reason why. `storage.py`'s
  `async_log_pill_taken()` now auto-activates on first confirmation
  (`pack_start_date` = that day, if none was ever set), or just resumes in
  place if a pack already existed but tracking was paused.
  `button.*_start_new_pack` (v0.9.5) stays around for explicitly
  (re)setting/backdating the pack start date.

### Changed

- `dashboard_test.yaml` / `lovelace_example.yaml`: entity IDs switched from
  the `test_*` slug to `alina_*` (cycle owner named "Alina"), and
  `dashboard_test.yaml` now includes `button.alina_start_new_pack` (added in
  v0.9.5, wasn't on the dashboard until now) plus a PMS shared-calendar
  category mention.

## [0.9.6] - 2026-08-07

### Fixed

- The "pack running low" restock notification's once-per-pack dedup key was
  the stored `contraception.pack_start_date`, which never changes once set -
  `day_in_pack()` wraps to the next pack automatically via modulo, on
  purpose, precisely so nobody has to press anything each cycle. That meant
  the restock notice only ever fired once, ever, for the very first pack,
  and silently never again for any later automatic cycle. Added
  `pill_math.current_pack_start()` - the start date of the cycle `today`
  actually falls in - and switched the dedup key to that instead, so the
  notification now re-arms every cycle exactly like the pill day/pause day
  math already does. `button.*_start_new_pack` (v0.9.5) remains a one-time
  activation / manual-correction action, not something meant to be pressed
  every cycle.

## [0.9.5] - 2026-08-07

### Added

- `button.*_start_new_pack` - one tap activates contraception tracking with
  today as `pack_start_date` (`storage.py`'s `async_start_new_pack()`, same
  as `perioder.start_new_pack` with no `date`). Root cause for
  `binary_sensor.*_contraception_active` sitting "off with no obvious
  reason": tracking is `inactive` by default and, before this button,
  turning it on required calling `perioder.start_new_pack` via Developer
  Tools > Actions - `dashboard_test.yaml` even calls this out in its own
  instructions, but there was no button for it, only the service.

## [0.9.4] - 2026-08-07

### Fixed

- `mobile_app_notification_action` listener in `__init__.py` is now decorated
  with `@callback` instead of being a bare lambda. An undecorated listener is
  dispatched by the event bus via a worker thread, and calling
  `hass.async_create_task()` from there triggered HA's
  "calls hass.async_create_task from a thread other than the event loop"
  frame-helper warning every time a reminder/escalation notification action
  button ("Vzal(a) jsem" / "Odložit") was tapped.
- Both calendar entities (`cycle_calendar` and `shared_calendar`) never
  generated a PMS block - `_period_and_fertile_blocks()` only ever emitted
  "period"/"fertile", even though `pms_window_days` and
  `binary_sensor.*_pms_active` already existed. In the shared calendar this
  meant the generic "Citlivé období" block was always exactly the period
  dates (the "PMS window" category in `shared_calendar_categories` had no
  block type behind it at all). Added a `pms` block - `cm.pms_window()`
  applied per-cycle, same window the binary sensor uses - to both calendar
  entities. **Existing entries keep their current `shared_calendar_categories`
  selection - add "PMS okno" via Options Flow > Upravit nastavení if you want
  it to actually show up.**

## [0.9.3] - 2026-07-29

Second attempt at the calendar-card fix - `card-mod` (v0.9.2) didn't work
for the user, so this replaces the built-in calendar card with a
third-party one instead of fighting the built-in one's CSS.

### Changed

- `dashboard_test.yaml`'s two calendar cards are now
  `custom:atomic-calendar-revive` (HACS, actively maintained -
  [totaldebug/atomic-calendar-revive](https://github.com/totaldebug/atomic-calendar-revive),
  654 stars, latest release v10.3.1) instead of the built-in `type:
  calendar`. It takes any `calendar.*` entity the same way the built-in
  card does (`entities: [{entity: calendar.test_cycle_calendar}]`) - it's
  documented around Google Calendar/CalDav but the config just points at a
  standard HA calendar-domain entity, same API either way. Configured with
  `defaultMode: Calendar` (month grid, not the event-list mode) and an
  explicit `cardHeight` (700px / 500px) - this card has a real height
  option, unlike the built-in one, which was the actual missing piece.
  Requires installing it via HACS > Frontend first (documented in the new
  setup step 2). This is the one non-native-HA piece of the whole test
  dashboard; everything else stays plain HA cards/entities.

### Notes

- Not yet verified live - confirmed via the project's GitHub page and docs
  that it's maintained and takes a plain entity_id, but the actual
  clipping fix (`cardHeight`) hasn't been checked against a running
  instance.

## [0.9.2] - 2026-07-29

Reverts the v0.9.1 fix - user rejected `listWeek` as unusable, wants the
month grid kept.

### Changed

- `dashboard_test.yaml` calendar cards back to the default month grid
  (removed `initial_view: listWeek`), now paired with a `card_mod` block
  (`ha-full-calendar { min-height: ...px; }`) to force taller rows instead
  of switching views. Requires the **card-mod** HACS frontend resource to
  have any effect - if it's not installed, the `card_mod` key is just
  silently ignored (no error, but no fix either). Not verified live - the
  exact internal element/class HA's calendar card exposes can differ by
  frontend version; if `min-height` has no visible effect, inspect the
  card in the browser's DevTools to find the right selector for that HA
  version.

## [0.9.1] - 2026-07-29

Dashboard-only fix, found live: no integration code changed.

### Fixed

- **`dashboard_test.yaml` calendar cards clipped multi-day event bars.**
  HA's built-in calendar card's default month grid (`dayGridMonth`) has a
  fixed row height with no config option to make it taller; in a narrower
  dashboard column, a multi-day block's label/bar can render below the
  visible area of its cell - so a real, correctly-computed period could be
  sitting right there in the data and still be invisible on screen. Not a
  data/logic bug (verified: `_period_and_fertile_blocks()` generates the
  right dates) - a Lovelace layout limitation. Both `cycle_calendar` and
  `shared_calendar` cards now set `initial_view: listWeek` (events as a
  list, no grid cells to clip). A commented-out `card-mod` snippet is left
  in the file for anyone who'd rather keep the month grid and just force it
  taller instead (requires the card-mod HACS frontend addon).

## [0.9.0] - 2026-07-29

Second user-requested feature after live testing: the calendar's period
block can now reflect the real, confirmed span of a period instead of only
the `period_duration` estimate.

### Added

- **`date.*_last_period_end`** - optional, settable date entity: the real
  last day of bleeding for the current period, inclusive. `perioder.log_period_end`
  is the matching service. Validated the same way as `last_period_start`
  (can't be in the future) plus one more rule: can't be before the logged
  start. Automatically reset back to unset every time a new
  `log_period_start` happens - it's a per-cycle fact, same reasoning as the
  M7 `pms_override` reset.
- **`cycle_calendar` / `shared_calendar`**: the period block for the
  *current* cycle now uses the real start-to-end span (labeled "Perioda
  (potvrzený konec)" on the detailed calendar) once `last_period_end` is
  logged, instead of always assuming exactly `period_duration` days. Every
  other period block - past or future, still only predicted - is
  unaffected; only the one cycle matching `last_period_start` exactly can
  be overridden, and only if the confirmed end date isn't before its start
  (a stale/bad value is silently ignored rather than corrupting the block).

### Notes

- Verified via a standalone re-implementation of `_period_and_fertile_blocks()`'s
  date arithmetic (same method used for the M3 calendar logic and the M4
  notification engine) - covers: no real end (unchanged predicted
  behavior), real end shorter than `period_duration`, real end longer,
  other cycles staying untouched, and a bad (pre-start) real end being
  ignored. Not yet checked against a real Home Assistant calendar view.

## [0.8.0] - 2026-07-29

First user-requested feature batch after live testing began: a real pill
stock count, and actionable buttons on the contraception notifications.

### Added

- **`number.*_pills_in_stock`** - a settable count of how many tablets are
  physically at home. `perioder.log_pill_taken` (and the "Confirm pill
  taken" button) now decrements it by one automatically the first time a
  given date is confirmed - re-confirming the same date again (e.g. a
  double tap), or confirming a date already logged as "taken", does not
  decrement a second time; a date previously logged "missed" and then
  confirmed late still decrements once, since that tablet genuinely came out
  of stock. `perioder.set_pills_in_stock` sets it directly (after a
  purchase, or to correct drift) and re-arms the low-stock warning below.
  Never goes negative - clamped at 0.
- **Low-stock warning**, driven by the real count above: once
  `pills_in_stock` drops to or below `low_stock_threshold` (new setting,
  default 5), the owner and supporters subscribed to
  `contraception_restock` are notified once, and not again until the count
  is set back above the threshold via `perioder.set_pills_in_stock` /
  the number entity. This is a deliberately separate signal from the
  existing "pack running low" notification (M4): that one is about the
  *current pack*'s active days running out (time to open the next one);
  this one is about the *physical supply at home* (is there actually a next
  pack, or is it time to go buy more) - the two can and do fire
  independently.
- **Actionable push notification buttons**: the owner's daily reminder and
  every escalation nag now carry two buttons - "Vzal(a) jsem" (confirms
  today's dose, same as the button/service) and "Odložit" (postpones the
  nag by `escalation_repeat_minutes`, without marking anything taken or
  missed). Implemented via `notify.send_message`'s `data.actions` field and
  a single shared `mobile_app_notification_action` event listener
  (registered once per Home Assistant instance, not per cycle owner - the
  event itself carries no config_entry_id, so the action identifiers are
  suffixed with it instead, see `notifications.pill_actions()`). Supporter
  notifications are unchanged - a supporter still can't confirm someone
  else's dose, only the cycle owner's own reminder gets action buttons.
- `perioder.set_pills_in_stock` service, and `low_stock_threshold` added to
  `perioder.update_settings` / Config+Options Flow.

### Notes

- Verification for this release is standalone logic simulation only (see
  `/tmp/sim_stock.py` during development, not committed) - the stock
  decrement guard, the notify-once/re-arm low-stock logic, and the snooze
  window were all checked against a plain-Python re-implementation of the
  real logic, the same way the M4 escalation engine was. None of this has
  been exercised against a real Home Assistant instance or an actual mobile
  app push notification yet - please report back once you've tried the
  "Vzal(a) jsem"/"Odložit" buttons live, especially whether the actions show
  up at all (this depends on your Home Assistant Companion app version).
- `storage.py`/`__init__.py` import Home Assistant, so (like the rest of the
  notification engine) none of this new logic is covered by the automated
  `pytest` suite - only `cycle_math.py`/`pill_math.py` are.

## [0.7.0] - 2026-07-29

M7 (partial) - tests, a real bug found while reviewing edge cases, and
documentation. Screenshots and a couple of other M7 items are still open -
see Notes.

### Fixed

- **PMS override didn't reset between cycles.** `perioder.set_pms_override`
  (and the matching `select` entity) is documented as a *per-cycle* manual
  override (ANALYZA-A-ROADMAP.md section 2.2 - "protože to nemusí platit
  každý měsíc stejně"), but `storage.async_set_last_period_start()` never
  actually cleared it: forcing the PMS window on/off for one cycle would
  silently carry over into every future cycle until someone remembered to
  set it back to "auto" by hand. Logging a new period start now resets
  `pms_override` to `None` (automatic) - found while writing the "PMS
  override across cycles" edge case from the M7 checklist, not reported by
  a user.

### Added

- `tests/test_cycle_math.py`, `tests/test_pill_math.py` - 26 unit tests
  covering both pure math modules: every cycle day maps to exactly one
  phase (no gaps), fertility/PMS window boundaries, the manual PMS
  override, and the M7 edge cases specifically - changing regimen_type
  (pack_size/pause_days) mid-pack, deactivating and reactivating
  contraception tracking, and backdating a confirmation.
  `tests/conftest.py` loads `cycle_math.py`/`pill_math.py`/`const.py`
  directly by file path rather than importing the integration package
  normally, since the normal path runs `__init__.py`, which needs Home
  Assistant - these two modules are pure Python by design specifically so
  they don't need it for testing.
- `.github/workflows/test.yaml`: runs `pytest tests/` on every push/PR.
- README: a "The model: cycle owner, supporter, administrator" section
  explaining the three roles and how they relate (was previously only in
  `ANALYZA-A-ROADMAP.md`), a "Running the tests" section, and a "Known
  gaps" section consolidating what's honestly still missing.

### Notes

- **Not done in this release, from the M7 checklist**: dashboard
  screenshots in the README (nothing to capture from - no running Home
  Assistant instance available while developing this), and the "reject a
  future date" edge case is enforced at the entity/service layer
  (`date.py`, `__init__.py`'s three date-accepting services all raise
  `ValueError`) rather than in `pill_math.py` itself, so it's verified by
  code inspection here, not a new automated test.
- Given the PMS-override bug above, this is a good moment to say plainly:
  this project's tests cover the pure math modules only. Config flow,
  entities, services, and the notification engine are still verified by
  standalone logic simulations and manual testing, not automated tests -
  if you find something else that doesn't match its documentation, that's
  exactly the kind of gap this release's process was meant to start
  closing.

## [0.6.0] - 2026-07-29

M6 - blueprints. These are optional automation blueprints on top of the
integration, not code inside `custom_components/perioder/` - nothing in the
integration itself changed in this release.

### Added

- `blueprints/automation/perioder/period_pms_lighting_scene.yaml`:
  activates a chosen scene while a period or PMS window is active, restores
  a normal scene once both end.
- `blueprints/automation/perioder/contraception_period_shopping_list.yaml`:
  adds an item to a to-do list when the contraception pack is running low
  and/or the next period is coming up soon.
- `blueprints/automation/perioder/heating_pad_reminder.yaml`: notifies (and
  optionally switches on a heating pad) when a period starts.
- `BLUEPRINTS.md`: import instructions (Settings > Automations & Scenes >
  Blueprints > Import Blueprint with each file's GitHub URL) and what each
  one does - same mechanism as `BLUEPRINTS.md` in the
  [cyclist](https://github.com/ringleader/cyclist) integration this
  project took inspiration from.

### Notes

- All three blueprints were checked for internal consistency (every
  `!input` reference in the automation body matches a declared blueprint
  input, and vice versa) via a small script parsing the YAML with a stub
  `!input` tag handler - not by importing them into a running Home
  Assistant instance. Please report back after testing tonight if an
  import or an automation built from one doesn't behave as described.

## [0.5.0] - 2026-07-29

M5 - symptoms, shared calendar, dashboard. Closes out every M1-M5 milestone
on the roadmap; M6 (blueprints) and M7 (tests/docs/polish) remain before v1.0.0.

### Added

- `perioder.log_symptom` service (finally registered - `storage.py` has had
  `async_log_symptom`/`symptoms`/`symptom_log` since v0.1.0, but nothing
  ever called the service in `__init__.py` until now) and one
  `button.log_symptom_<symptom>` per entry in `const.SYMPTOMS` (cramps,
  headache, low_energy, mood_change) for one-tap logging from the dashboard
  - the "rychlé akce ... log symptomu" item from
  ANALYZA-A-ROADMAP.md section 2.9.
- `sensor.last_symptom`: which symptom was logged most recently and when
  (`logged_at`, `log_entry_count` attributes) - enough for a history graph
  card or just a glance at the dashboard.
- `perioder.export_symptom_log` service: writes the full symptom history to
  a CSV file under Home Assistant's `www/` folder (downloadable at
  `/local/<filename>`) and creates a persistent notification with the
  resulting path - for a gynecologist consultation, per section 2.4.
- `calendar.shared_calendar`: a second calendar entity per cycle owner with
  generic "Citlivé období" blocks and no detail (no period/fertile/pause
  distinction, no pill data at all) - for exporting into a shared family
  calendar (ANALYZA-A-ROADMAP.md section 2.7). New `shared_calendar_categories`
  setting controls which block *types* (period/fertile/pause) show up at
  all; defaults to just `period`. `calendar.py`'s block-generation functions
  were refactored to module-level pure functions so both calendars (and the
  detailed one from v0.3.0) share the exact same date math.
- `sensor.supporters`: supporter count, with each supporter's device/categories/
  detail_level as an attribute - since supporters are config entry options,
  not entities themselves, this is what lets a dashboard markdown card show
  a "supporters overview" (section 2.9) via `state_attr(...)`.
- `dashboard_test.yaml`: symptom quick-action buttons, a supporters overview
  markdown card, and the shared calendar card.

### Fixed

- `perioder.update_settings` (added in v0.3.0) and its Options Flow
  equivalent (extended in v0.4.0) had drifted apart: the four M4 notification
  settings (`owner_notify_device`, `escalation_grace_minutes`,
  `escalation_repeat_minutes`, `escalation_max_count`, `restock_days_before`)
  were only ever addable via Options Flow, not via the service - an oversight
  from v0.4.0, caught while adding `shared_calendar_categories` to both
  places for this release. `update_settings` now covers every setting
  Options Flow does.

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
