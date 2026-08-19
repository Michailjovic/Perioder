# ADR-1: Custom Lovelace Calendar Card for Perioder

**Status:** Accepted, implemented in 0.9.30 (2026-08-13) - see Action Items below
**Date:** 2026-08-12
**Decided by:** Michael (sole project maintainer)
**Follows up on:** ANALYZA-A-ROADMAP.md section 5 ("A custom JS Lovelace card...
is deferred to v2.0.0 - either bundled into the same repository..., or as a
standalone HACS 'Plugin'... The decision on which variant to go with will be
made only during v2.0.0 planning.") and section 8 (versioning table, v2.0.0 row).

## Context

Perioder currently builds its calendar dashboard on the built-in HA card
`type: calendar` (see `calendar.py`, six/seven entities split by
category - `period_calendar`/`fertile_calendar`/`pms_calendar`/
`pause_calendar`/`pill_calendar`/`cycle_calendar`/`shared_calendar`). This
card has two real, long-term unfixable pain points:

1. **Colors cannot be pinned** - HA assigns them automatically based on
   the order of entities in the card, not on what the entity actually is.
   Confirmed as an open, long-standing unresolved request on the Home
   Assistant side itself (`color` is still not a property of
   `CalendarEntity` - see
   [home-assistant/architecture#883](https://github.com/home-assistant/architecture/discussions/883),
   [home-assistant/frontend#11262](https://github.com/home-assistant/frontend/discussions/11262)),
   not a gap in Perioder.
2. **A crowded day hides an event behind "+n more"** - FullCalendar (what
   the card uses under the hood) sorts longer (multi-day) events ahead of
   shorter ones within a single day, so a one-day pill event loses out even
   when it's the one we most want visible. Today's workaround (splitting
   `calendar_calendar` into `pill_calendar`, see v0.9.28 in the CHANGELOG)
   only partially solves this - it only works if the user manually turns
   off the block calendars via a checkbox.

We tried two third-party HACS cards as a replacement:

- **`calendar-card-pro`** ([alexpfau/calendar-card-pro](https://github.com/alexpfau/calendar-card-pro))
  - there's no month grid at all - it's an agenda/list of upcoming days
    ("displaying upcoming events" - the author's own description). Poor
    fit, a different visual paradigm than what we want.
- **`atomic-calendar-revive`** ([totaldebug/atomic-calendar-revive](https://github.com/totaldebug/atomic-calendar-revive))
  - has a month grid and per-entity fixed colors, but **tested live
    (2026-08-12) and it does not merge multi-day events into a single
    bar** - exactly what we need for period/fertile window/pause. Unusable.

Both also carry a risk inherent to the project - Perioder is a health tool
used at home by a non-technical person too (Alina); depending on whether a
third-party HACS card happens to be installed/up to date, and whether its
author breaks it in some future version, is an unnecessary extra risk
compared to what Perioder can guarantee on its own.

## Decision

Build a custom Lovelace card `custom:perioder-calendar-card`, **bundled
directly into the Perioder integration repository** (not a standalone HACS
"Plugin" - decided in the 2026-08-12 conversation, see "Considered Options"
below), versioned together with `manifest.json`, and **automatically
registered as a Lovelace resource** at HA startup - no manual "add resource"
step on top of today's setup (`dashboard_alina.yaml` etc. simply get
rewritten to use the new card).

## Considered Options

### A. Hand-rolled month grid (recommended)

A custom CSS grid (7 columns × N rows depending on the month), custom data
logic in JS (analogous to what `calendar.py`/`cycle_math.py` already does
in Python - no new backend logic, the card only reads the already-computed
`calendar.*` entities). Multi-day blocks rendered as absolutely positioned
bars spanning a range of columns, split into weekly segments where they
cross a row boundary (the same technique FullCalendar uses internally). The
pill icon is never counted toward "how many events fit in the cell" - it's
rendered as a small fixed badge in the corner of the day, outside the
normal event stack.

| Criterion | Assessment |
|---|---|
| Code scope | Small - no dependencies, no build step (see below) |
| Risk | We own edge-case coverage (month/year transitions, today's date, mobile) - no library covers this for us |
| Control over behavior | Full - fixed colors and "the pill never disappears" can be enforced directly |
| Maintenance | One new area (JS) alongside Python, but small |

**Pros:** exactly what we need, nothing more; no external dependency; small
file.
**Cons:** we write the date/grid logic that FullCalendar otherwise handles
ourselves.

### B. Vendor/trim down FullCalendar

Use the same library the built-in card uses under the hood, but wrapped in
our own layer with fixed colors.

**Pros:** multi-day spanning "for free", battle-tested.
**Cons:** ~100-300 kB even trimmed; we'd still have to hack fixed colors
and pill priority through its API/CSS - solving exactly the problem we're
leaving the built-in card for, just in different packaging. **Rejected.**

### C. Generic, Perioder-independent calendar card (standalone HACS "Plugin")

Publish the card as a separately installable, generally usable product (not
tied to Perioder entities).

**Pros:** potentially useful to others too, could have value beyond this
project.
**Cons:** considerably more work (generic API, documentation, support
surface, two release cycles to keep in sync) - and above all: `Michael`'s
own reasoning for why we're doing this in the first place ("people would
install various calendars and that would generate various bugs") applies
equally to *this* card if it were standalone. This builds exactly what we
want to avoid. **Rejected, decided in the 2026-08-12 conversation.**

## Configuration and Behavior Proposal (v1 scope - minimal)

```yaml
type: custom:perioder-calendar-card
title: Kalendář cyklu
entities:
  - entity: calendar.alina_period_calendar
    color: "#e05c5c"
  - entity: calendar.alina_fertile_calendar
    color: "#4a90d9"
  - entity: calendar.alina_pause_calendar
    color: "#9b59b6"
  - entity: calendar.alina_pms_calendar
    color: "#f5a623"
pill_entity: calendar.alina_pill_calendar
```

- `color` is an optional override - without it, the card uses its own
  default palette based on the `translation_key` of the given Perioder
  calendar entity (period = red, fertile = blue, pause = purple, pms =
  orange), so it looks reasonable and meaningfully color-differentiated
  even without a single line of configuration.
- `pill_entity`: an optional special slot. Its events are **never** counted
  toward the "how many fit in the day cell" limit - it's always shown as a
  small 💊 icon, regardless of how many other blocks that day has. This
  directly fixes today's "+n more" problem at the root, instead of a
  workaround via a separate entity plus a manual checkbox (as today).
- Clicking a day expands the detail (a list of that day's events) - the
  same interaction the current built-in card has.
- Read-only, no writing/moving events - Perioder events can't be manually
  edited anyway, only logged through the existing services/entities.
- **V1 has only a month view** (`dayGridMonth` equivalent) - no week/day
  view. Extending this is possible later, but it's not part of v1.
- **Multi-day bars carry their own label** (e.g. "Perioda", "Plodné dny")
  directly on the bar, not just conveyed via color through a legend -
  as text, truncated with an ellipsis if the span doesn't fit (decided in
  the 2026-08-13 conversation). The bar's color comes from the given
  category, the text uses a darker shade of the same color family
  (contrast, same convention as the rest of the Perioder UI).

### Card configuration editor - two-tier visibility control (decided 2026-08-13)

Contrary to the original plan ("no GUI card editor, just YAML"), the card
**must have a visual editor** (`getConfigElement()`, the standard HA
custom-card pattern) - not because it's prettier, but to separate two
distinct permissions that are already clearly distinguished in the project
today (see section 2.5 - the admin decides who sees what, not the card's
end user):

1. **Card editor (admin, configuration time)** - checkboxes for "which
   categories this particular card on this particular dashboard is even
   allowed to offer" (`period`/`fertile`/`pms`/`pause`, plus **the pill as
   an equal fifth option** - not always hardcoded on, decided in the
   2026-08-13 conversation: not every dashboard viewer wants to see whether
   the pill was taken). The same thing the admin handles manually today via
   the `entities:` list in YAML (and what distinguishes
   `dashboard_alina.yaml` without PMS from `dashboard_alina_admin.yaml`
   with PMS) - the editor just does it as checkboxes instead of manually
   typing entity IDs.
2. **Card legend (anyone with dashboard access, runtime)** - checkboxes
   for temporary show/hide while viewing, but **only among the categories
   the admin enabled in step 1**. A category the admin didn't enable
   doesn't appear in the legend at all - it's not merely unchecked by
   default, it's genuinely unavailable, the same principle as
   `binary_sensor.pms_active` and `pms_calendar` today (see section 2.2).

In practice: `getConfigElement()` saves the admin's selection into the
card's `entities:` field (exactly what the card already reads today) - no
new data model is needed, just a GUI on top of the existing one.

**Colors are a suggestion, not fixed (decided 2026-08-13):** for each
enabled category, the editor offers a color picker pre-filled with our
default palette (`period`=red, `fertile`=blue, `pms`=orange,
`pause`=purple) plus a "restore suggested color" button. The admin can
override any of them; `entities:` then carries `color:` only where the
admin deviated from the suggestion (the default palette remains the
fallback, the same principle as the earlier `translation_key`-based default
from the earlier proposal). The pill retains no color of its own (it's an
icon, not a bar) - just on/off in the editor.

### Visual inspiration from other HACS calendar cards

Verified 2026-08-13 against `calendar-card-pro` (the most widespread
alternative, see README) and general trends in "nice-looking" HA
dashboards (the mushroom/bubble card style Michael also uses elsewhere).
Specific elements worth adopting into our own card:

- **Weekend distinction** (`weekend_day_color` in calendar-card-pro) - a
  lighter shade for Saturday/Sunday in both the header and the day number,
  not necessarily functionally important, but helps quick orientation in
  the grid.
- **Circular "today" badge** around the day number (not a large
  rectangular highlight across the whole cell) - cleaner, less
  distracting.
- **Pastel-toned bars** (a tint of the color as background + the full
  color as a left accent border + icon) instead of solid saturated bars -
  softer, closer to the style Michael uses elsewhere (bubble card), and at
  the same time solves text contrast for any admin-chosen color without
  having to compute luminance/contrast manually.
- **Legend as rounded "chips"** with a tinted background instead of plain
  text + checkbox - consistent with the bars, a more readable group of
  quickly toggleable filters.
- **Week number as a "pill" badge** (`week_number_*` in
  calendar-card-pro) - considered, but left out of v1 (doesn't add value
  for this particular purpose, just extra visual noise).

Source: [alexpfau/calendar-card-pro README](https://github.com/alexpfau/calendar-card-pro/blob/main/README.md)
(Visual Styling & Colors, Weekend Day Styling, Today's Date Styling sections).

## Technical Implementation - Registering as a Frontend Resource

Verified (2026-08-12) against the current (post-2024.7) HA API, not against
the deprecated `hass.http.register_static_path`:

1. `manifest.json` must declare `"dependencies": ["frontend", "http"]`
   (Perioder currently has neither - without them, registration fails
   silently).
2. The static path is registered via
   `await hass.http.async_register_static_paths([StaticPathConfig(url_base, path, False)])`
   (the async variant - the synchronous `register_static_path` is
   deprecated).
3. The actual Lovelace resource entry (`lovelace.resources.async_create_item(...)`)
   can only be registered **in storage-mode Lovelace** (the default mode,
   the one Michael uses - "Add Dashboard > New dashboard from scratch" is
   storage mode even if one particular view is then edited via "Edit in
   YAML"). In pure YAML-mode Lovelace, the user would have to add the
   resource manually once to `ui-lovelace.yaml` - doesn't affect today's
   Perioder setup though.
4. **Registration must happen in `async_setup()`, not `async_setup_entry()`**
   - Perioder currently doesn't have `async_setup()` at all (only
   `async_setup_entry` per config entry) - it needs to be added, so the JS
   gets registered once per integration, not again for every cycle owner.
5. The resource URL version (`?v={manifest_version}`) is bumped together
   with the `manifest.json` version (the same release process as today -
   section 8) - this handles the usual browser/companion-app caching of an
   old version of the JS file after an update.
6. **File structure:**
   ```
   custom_components/perioder/
     frontend/
       __init__.py          # JSModuleRegistration (see steps 1-5)
       perioder-calendar-card.js
   ```
7. **No build step** - no webpack/Node/TypeScript, a plain JS module
   (LitElement via CDN import or a vanilla Web Component - to be settled
   during implementation). Consistent with the rest of the repository
   being just Python + YAML, no JS toolchain to maintain.

Verification sources: [KipK - Developer guide: Lovelace custom card embedded in
integration](https://gist.github.com/KipK/3cf706ac89573432803aaa2f5ca40492/)
(updated 2026-02-10, describes exactly this pattern including
`StaticPathConfig`/`async_register_static_paths`).

## Data Flow

The card reads data through the same WebSocket API the built-in HA card
uses - `hass.callWS({type: "calendar/event/list", entity_id, start, end})` -
against the regular `calendar.*` entities. **No new backend logic in
`calendar.py` is needed for v1** - it's purely a frontend card layered on
top of what the integration already provides today.

## Consequences

- **Simplified:** no dependency on a third-party HACS card and its
  upkeep; a single card version, versioned and released together with the
  integration; colors and pill visibility can be enforced firmly, not
  worked around.
- **Added work:** JS/frontend is a new maintenance area alongside Python -
  the repo currently has no JS test tooling (`tests/` is pure pytest, see
  `tests/conftest.py`), so changes to the card will have to be verified
  manually on a live instance, the same limitation the notification engine
  has today.
- **To revisit during implementation:** `hacs.json`/`hassfest` validation
  with the new `frontend`/`http` dependency and a static JS file in the
  repository - confirm that the HACS category remains "Integration" and
  doesn't require special handling just because of the bundled JS.

## Action Items

1. [x] Approve/adjust the proposal above (colors, `pill_entity` behavior,
   v1 scope) - approved 2026-08-13 after several rounds of adjustments
   (editor with admin-controlled availability, optional colors, labels on
   the bars).
2. [x] `manifest.json`: `dependencies: ["frontend", "http"]`
3. [x] `custom_components/perioder/frontend/__init__.py` -
   `JSModuleRegistration` (static path + Lovelace resource, see above)
4. [x] `custom_components/perioder/frontend/perioder-calendar-card.js` -
   the card itself (month grid with navigation, labeled color bars,
   pill badge, click-to-detail) + `PerioderCalendarCardEditor`
   (`getConfigElement()`) - the editor is generic over any `calendar.*`
   entity (not hardcoded to Perioder), so it also works if the admin wants
   to mix in a different calendar.
5. [x] `async_setup()` in `__init__.py` - registers the frontend once per
   HA instance, on `EVENT_HOMEASSISTANT_STARTED` (or immediately, if HA is
   already running)
6. [ ] `hassfest`/HACS validation via GitHub Actions - **cannot be
   verified in this environment** (no running HA instance nor `hassfest`
   tool available here) - will be verified only in CI after pushing/on a
   live instance.
7. [x] Rewrote `dashboard_alina.yaml`/`dashboard_alina_admin.yaml` +
   `dashboard_test.yaml`/`dashboard_test_admin.yaml` to use the new card -
   `cycle_calendar`/`shared_calendar` remained on the built-in card (see
   "Consequences" - these are individual entities, the new card adds
   nothing for them).
8. [x] `CHANGELOG.md` (v0.9.30), `manifest.json` version, this document
   (Status -> Accepted) checked off.

**Not verified live (manual check on a real HA instance required, see
"Consequences" above):** the card's appearance in the browser/Companion
app, actual Lovelace resource registration after a restart, editor
behavior in the Lovelace UI. The JS only passed `node --check` (syntax)
and standalone assertions on the date math (weeks/month grid,
exclusive-end conversion) - no real DOM/HA environment available here.
