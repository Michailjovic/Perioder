# Perioder — Project Analysis and Roadmap

A custom Home Assistant component for managing the menstrual cycle and contraception. Inspired by the [cyclist](https://github.com/ringleader/cyclist) integration, but we're writing our own component from scratch. The goal is a **general-purpose integration** — not a solution tailored to one household, but a tool that anyone with a similar need can set up and use (an individual, a couple, a broader support network).

> This is a home automation tool, not a medical device. Calendar-based fertility predictions have low accuracy without physiological data. It does not replace a consultation with a gynecologist.

---

## 1. Goal and Philosophy

- **Local and private** — everything lives in the HA instance's `.storage/`, no cloud, no external app.
- **Generally usable, without assuming a monogamous couple** — one config entry = one "cycle owner" (the person whose cycle is tracked). Any number of "supporters" (partner, roommate, parent, anyone) can be linked to them — what and how each person receives is decided by the HA instance administrator (see 2.5), not by the cycle owner themselves. The cycle owner ↔ supporter relationship is **N:M and unlimited in both directions**: one supporter can subscribe to any number of cycle owners (polyamorous relationships, multiple partners at once), and one cycle owner can have any number of supporters. Nothing in the data model or UI assumes a couple, marriage, or a specific gender/role — just "cycle owner" and "supporter", and one person can be both at once in different config entries. No name or relationship role is hardcoded.
- **The number of tracked people is unlimited** — HA integrations naturally support multiple config entries of the same domain, so a single instance can have any number of independent "cycle owners" at once, each with their own settings and circle of supporters.
- **The tracking goal is configurable** — `track` / `avoid` / `plan`, switchable at any time, with notifications adapting accordingly.
- **One source of truth** — logging the first day of menstruation (dashboard, button, voice, NFC) is the only thing the cycle owner actively enters on a regular basis. Everything else is derived from this date: cycle day, phase, fertility, PMS window, predictions.
- **Contraception as a separate but connected module** — it doesn't depend 1:1 on the cycle (a pack has its own rhythm), but it intersects with it where it makes sense (a missed dose during the fertile window = an extra warning).

---

## 2. Functional Areas

### 2.1 Cycle and Fertility (foundation from cyclist)

- Date of the last period start → derived cycle day, phase (menstruation/follicular/ovulation/luteal), fertility (`fertile`/`low`/`safer`).
- Configurable `cycle_length` and `period_duration`, no back-calculation from history by default — the configured setting takes precedence.
- Optionally, additional BBT/CM/LH for symptothermal refinement (a later phase, not required for MVP).
- Calendar (`calendar.perioder`) with a 3-month look-ahead — period + fertile window.
- ✅ **(idea from 2026-07-29, implemented in v0.3.0)** The calendar displays contraception history day by day — when a pill was confirmed taken/missed (`pill_log`), and the event description also shows the delay relative to `reminder_time` (in minutes). Estimates are not shown for future/unlogged days, only actually logged entries.
- ✅ **(requested live on 2026-07-29, implemented in v0.9.0)** Optional `date.*_last_period_end` — the real, confirmed last day of menstruation (inclusive). If logged, the "Period" block in the calendar for the current cycle shows the actual range instead of an estimate derived from `period_duration`; it resets automatically on the next period-start entry (a per-cycle fact, just like `pms_override`).
- The goal (`goal`) affects the tone and type of notifications.

### 2.2 PMS / Emotional Window

- A derived window at the end of the luteal phase — the last `pms_window_days` days before the predicted period (configurable, default e.g. 4).
- **Manual override per cycle** — the cycle owner can explicitly turn the window on or off for the current cycle (`perioder.set_pms_override` with a value of `true`/`false`/`null` = back to automatic), because it may not hold true the same way every month.
- `binary_sensor.perioder_pms_aktivni` — `on` during this window (after accounting for any override).
- Notification to supporters is always optional and **configurable per recipient** (see 2.5) — general ("more difficult days are approaching, be considerate") or more detailed, if both the recipient and the cycle owner request it.
- **Exclusively for supporters** — the PMS window card/notification is not shown on the cycle owner's dashboard (they don't need it themselves, they know their own state without being alerted); it's information intended solely for the people around them who have opted in. Visibility is controlled purely by that particular supporter's subscription to the category (see 2.5) — never by gender or role, the system doesn't deal with those attributes at all.

### 2.3 Contraception — Management and Reminders

- `active` (on/off without deleting history), `regimen_type` (`21_7`, `24_4`, `continuous`, `custom`), `pack_start_date`, `reminder_time`, `pill_log`.
- `is_pill_day = active AND day_in_pack < pack_size` — a pure function, no HA dependencies.
- A daily reminder only when today is actually a pill day and it hasn't been confirmed yet; an actionable notification with a "Taken" button; escalation on non-confirmation (configurable interval and number of repeats); silence during the weekend... er, during the pack pause and when `active = false`.
- A missed dose → a `missed` record, a morning summary to the cycle owner and to subscribed supporters.
- Link to fertility: if a missed dose falls within the fertile window, the notification explicitly warns about the need for backup protection.
- A pack running low → a restock notification (configurable number of days in advance).
- **Actual physical pill supply at home** (`pills_in_stock`, v0.8.0) — a configurable number, not derived from the pack schedule, with its own threshold for a "running low" alert; independent of the "pack running low" notification above, since the latter is about the current pack, while this one is about whether there's another pack at home at all.
- Services: `start_new_pack`, `set_contraception_active`.

### 2.4 Symptoms and History/Trends

- An extended symptom log (mood, cramps, headache, energy, ...) with a timestamp — `perioder.log_symptom`.
- History enables: retrospectively seeing the pattern within a specific cycle, a dashboard graph (history/statistics graph card), and in the future, refining the PMS window based on real data instead of a fixed number of days.
- Exportable log (e.g. to CSV) for gynecologist consultations.

### 2.5 Notifications and "Supporters"

- **Permissions are set by the HA instance administrator, not by the cycle owner.** The Config Flow and Options Flow in Home Assistant are only accessible to users with administrator rights anyway (a regular user can't even reach Settings > Devices & Services), so this just matches the reality of the platform — and at the same time it's a deliberate decision: the administrator is the one who knows the whole household/group and is best positioned to judge who should receive what, without requiring an approval step from the cycle owner.
- In the Options Flow, the administrator adds any number of supporters to any cycle owner they manage within the instance. The same person (the same `mobile_app_*` target) can appear as a supporter for several different cycle owners at once — the subscription settings are always tied to a specific **pair** (cycle owner, supporter), never globally to a person. For each such pair, the following is configured:
  - the notification target (`mobile_app_*` device),
  - the categories that supporter subscribes to (PMS window, upcoming period, pack running low, missed dose, fertility),
  - the level of detail (general vs. with symptom detail).
- The cycle owner always sees everything about themselves on their dashboard; supporters only see what the administrator has configured for them, and only for the cycle owner they're subscribed to.
- A pattern using `tag` (to prevent buildup) and grouping by type (`contraception`, `cycle`, `pms`), further distinguished by cycle owner so that notifications about multiple tracked people don't get mixed up together.

### 2.6 Convenience Automations (blueprints on top of the integration)

- Lighting scene / "do not disturb" suggestion during the period or the PMS window.
- Heating pad reminder.
- Automatically adding items to the HA shopping list (`todo.add_item`) when contraception is running low or a period is approaching.
- These are separate blueprints (like `BLUEPRINTS.md` in cyclist), not the core of the integration — the user enables them voluntarily.

### 2.7 Shared Calendar with a Privacy Level

- `calendar.perioder` — detailed, for the cycle owner only.
- `calendar.perioder_shared` — generic blocks ("sensitive period") without detail, visible/exportable to a shared family calendar. The cycle owner chooses which categories are even reflected in the shared calendar.

### 2.8 Vacation / Pause Mode

- A single button/service `perioder.pause_notifications` (optionally with a resume date) — temporarily silences absolutely all notifications to all supporters, without needing to change the settings of individual modules. The underlying data (cycle, contraception) continues to be computed and logged, only nobody is bothered with notifications about it.

### 2.9 Dashboard

- Cycle status card (day, phase, gauge), contraception status (today's status, days until the pack ends), PMS window.
- Quick actions: "Period started", "Pill taken", symptom logging.
- Calendar card (detailed and shared versions).
- Overview of supporters and their subscription settings.
- The PMS window card is shown only in the supporter's view (dashboard/notification), not in the cycle owner's view (see 2.2).
- **Aggregated view for supporters** — if one person supports several cycle owners at once (e.g. in a polyamorous relationship), a dedicated card/dashboard showing the status of all tracked people side by side, not just one.

---

## 3. Entities (proposed)

| Entity | Description |
|---|---|
| `sensor.perioder_cyklus_den` | Current cycle day |
| `sensor.perioder_faze` | `menstruace`/`folikularni`/`ovulace`/`luteal` |
| `sensor.perioder_plodnost` | `fertile`/`low`/`safer` |
| `sensor.perioder_dalsi_perioda` | Days until the predicted period |
| `binary_sensor.perioder_perioda_aktivni` | `on` during the period |
| `binary_sensor.perioder_pms_aktivni` | `on` during the PMS window (after accounting for a manual override) |
| `sensor.perioder_antikoncepce_stav` | `vzato`/`ceka_se`/`pauza`/`neaktivni`/`vynechano` |
| `binary_sensor.perioder_pilulka_dnes_potreba` | `on` when today is a pill day and it hasn't been confirmed yet |
| `sensor.perioder_antikoncepce_zbyva_dni` | Days until the pack ends |
| `calendar.perioder` | Detailed cycle prediction + pack schedule |
| `calendar.perioder_shared` | Generic blocks for the shared calendar |

## 4. Services (proposed)

| Service | Description |
|---|---|
| `perioder.log_period_start` | Period start, optional `date:` |
| `perioder.log_pill_taken` | Confirmation of pill intake, optional `date:` |
| `perioder.start_new_pack` | Start a new pack, optional `regimen_type:` |
| `perioder.set_contraception_active` | Enable/disable use (without deleting history) |
| `perioder.set_pms_override` | Manual override of the PMS window for the current cycle (`true`/`false`/`null`) |
| `perioder.log_symptom` | Log a symptom with a timestamp |
| `perioder.pause_notifications` | Temporarily silence all notifications, optional resume date |
| `perioder.update_settings` | `cycle_length`, `period_duration`, `goal`, `reminder_time`, `pms_window_days` |

---

## 5. Technical Architecture

- `custom_components/perioder/` — a custom HA integration, `DOMAIN = "perioder"`. One config entry = one cycle owner; an HA instance can have any number of them without an artificial limit.
- Config Flow (cycle owner + basic settings) + Options Flow (editing settings + managing supporters and their subscriptions, N:M relative to other entries).
- **Settings and supporters live in the config entry** (`data`/`options`), not in the Store — they're managed by the Config/Options Flow and read by `settings.py`. The runtime `Store` (`hass.helpers.storage.Store`, JSON) holds only what changes via services between settings edits: `last_period_start`, `pms_override`, `contraception` (active pack, pill log), `symptoms`/`symptom_log` — always under a specific config entry, i.e. under a specific cycle owner. The split prevents two copies of the same thing from diverging (in v0.1.0 this originally also existed duplicated in the Store, fixed before the first push).
- Pure computational logic separated from HA (`cycle_math.py`, `pill_math.py`) — testable without the HA runtime.
- Distribution via HACS (custom repository).
- Reminder escalation via `timer.*` helpers + reacting to `mobile_app_notification_action`, rather than via repeated automations tied to a fixed time.
- **Backend vs. frontend, versioning:** the Python code in `custom_components/perioder/` is the backend, it only runs inside the Home Assistant process (no separate server). For **v1.x**, a single HACS repository (Integration category) is sufficient — the dashboard is composed of standard built-in Lovelace cards, no custom frontend card is written.
- **Custom JS Lovelace calendar card — implemented in v0.9.30 (2026-08-13), see `CALENDAR-CARD-ADR.md`:** the built-in HA calendar card cannot be forced to use fixed colors per entity (a confirmed, long-standing open limitation of HA itself) and, on a crowded day, hides a single-day pill event behind "+n more" (FullCalendar sorts multi-day blocks first). Two third-party HACS cards that were tried (`calendar-card-pro` and `atomic-calendar-revive`) both fall short (agenda-only, and not merging multi-day events, respectively) — and relying on a third-party card is also an unnecessary risk for a health tool used by even a non-technical member of the household. Solved with a custom `custom:perioder-calendar-card` (`custom_components/perioder/frontend/`), **bundled directly into this repository**, automatically registered as a Lovelace resource on HA startup (`async_setup()`), with a visual card editor (the admin controls which categories/entities the card even offers, and their colors — recommended, not enforced). The full design history and technical validation is in `CALENDAR-CARD-ADR.md`. **The first live deployment (2026-08-18) revealed two bugs** in the automatic Lovelace resource registration — `hass.data["lovelace"]` was read as `.mode` instead of the correct `.resource_mode` (so automatic registration was always silently skipped), and passive waiting on `resources.loaded`, which without a forced load (`resources.async_get_info()`) never completed unless the admin had opened Settings > Dashboards > Resources since the restart. Fixed in v0.9.31. **After the fix, the card registered and loaded, but showed no events at all** (just a grid with today's date) — `_fetchEvents()` was calling the non-existent WS command `calendar/event/list`, the error was silently swallowed in a `try/catch`, and an empty list was substituted for each entity; the card editor also crashed with "Cannot read properties of undefined (reading 'entities')", because `this._config` could still be `undefined` at the moment of the first render. Both fixed in v0.9.31 → v0.9.32 by switching to the REST endpoint `GET /api/calendars/{entity_id}` (the same one the built-in HA calendar card uses) and guarding `this._config` in every editor method, see CHANGELOG. **After v0.9.32, colored event bars finally appeared too, but user feedback (2026-08-19, with screenshots) pointed out two shortcomings:** a visually "disjointed" impression (day numbers and bars felt like two unrelated pieces, no visible cell borders) and missing interactivity (the legend at the top wasn't clickable, and it wasn't clear you could click on a day). V0.9.33 addresses both — one continuous CSS grid per week with visible cell borders, per-week bar "packing" (greedy interval scheduling, no empty reserved rows for categories that don't overlap that week), a clickable legend (runtime toggling of category visibility), and a day-detail panel rendered directly below the week of the clicked day, with a highlighted border. This time it was also verified visually (headless Chromium/Playwright with fixture data), not just `node --check` — see CHANGELOG v0.9.33. Live confirmation on Michael's instance is still pending.

## 6. Security and Privacy

- No data leaves the HA instance.
- Supporters see only what they've been granted permission to see (per-category, per-detail level) — never more, until the administrator allows it (see 2.5).
- A clear disclaimer in the README that this is home automation, not a medical device.

---

## 7. Roadmap

### M0 — Decisions and Specification (this document)
- [x] Analysis of functionality and controls
- [x] Chose a custom component built from scratch, generally usable (not tailored to one household)
- [x] Extension with the PMS window, symptoms/trends, convenience automations, shared calendar, pause mode

### M1 — Project Foundation ✅ (v0.1.0)
- [x] `manifest.json`, `const.py`, `hacs.json`
- [x] Config Flow: cycle_length, period_duration, goal, regimen_type, reminder_time, pms_window_days
- [x] Options Flow: editing settings + managing supporters (add/remove, category, detail level)
- [x] Storage layer (`cycle`, `contraception`, `symptoms`, `supporters`)
- [x] `cycle_math.py`

**Note:** v0.1.0 also pulled forward part of M3 (see below), so that something could actually be seen on the dashboard right away with test data — M1 alone (with no entities) wouldn't have been testable on its own.

### M2 — Contraception Core ✅ partially (v0.2.0)
- [x] `pill_math.py`: is_pill_day, remaining pack days, day status (`pill_status`)
- [x] `sensor.py` + `binary_sensor.py` for contraception, `button.py` (one-click confirmation)
- [x] Services: `log_pill_taken`, `start_new_pack`, `set_contraception_active`
- [ ] Daily reminder + escalation (timer helper + actionable notification) — moved to M4, shares infrastructure with the supporter notification engine (see CHANGELOG v0.2.0)
- [ ] Morning "missed" summary + link to the fertile window — to be handled together with M4

### M3 — Cycle, Fertility, and PMS Window ✅ (v0.3.0)
- [x] `sensor.py`: cycle_day, phase, fertility, next_period
- [x] `binary_sensor.py`: period_active, pms_active (with manual override)
- [x] Services: `log_period_start`, `set_pms_override`
- [x] `calendar.py` — prediction of periods/fertile days/pack pauses (both forward and backward), plus display of logged `pill_log` entries (taken/missed) with computed delay relative to `reminder_time` (idea from 2026-07-29, see 2.1 and CHANGELOG v0.3.0)
- [x] Service: `update_settings`

### M4 — Supporters and Notifications ✅ (v0.4.0, completed in v0.9.29)
- [x] Supporter data model (target, category, detail level) — already done in Options Flow (v0.1.1)
- [x] Notification engine respecting subscriptions and detail level per recipient (`notifications.py`)
- [x] Daily contraception reminder + escalation (moved from M2 — see CHANGELOG v0.2.0/v0.4.0), including a "missed" notification and linking to the fertile window
- [x] `perioder.pause_notifications` + `switch.pause_notifications`
- [x] **Completed in v0.9.29:** `pms`/`period`/`fertility` as dedicated *transition-triggered* notifications to supporters — "period approaching" (`period_heads_up_days` days in advance, a new setting), start of the PMS window, start of the fertile window. Independent of `contraception.active`, respects `pause_notifications`, deduplicated per cycle using the same pattern as `restock_notified_for`. See `_async_check_cycle_notifications()` in `__init__.py`.
- [x] Actionable notifications ("Taken"/"Snooze" buttons directly in the push notification) — completed in M8/v0.8.0, see below
- [ ] Verification against a real running Home Assistant instance and a real mobile_app device — so far verified only by logic (a standalone simulation of the decision tree), not by a live notification delivery

### M5 — Symptoms, Shared Calendar, Dashboard ✅ (v0.5.0)
- [x] `log_symptom` (service + per-symptom buttons) + `sensor.last_symptom`; export via `perioder.export_symptom_log` (CSV into `www/`)
- [x] `calendar.*_shared_calendar` with generic blocks, categories chosen via `shared_calendar_categories`
- [x] Dashboard cards (cycle, contraception, PMS, supporters via `sensor.supporters`, quick actions including symptoms)
- [ ] History/trend graphs (history/statistics graph card) — `sensor.last_symptom` and `sensor.contraception_status` already have the necessary data, but no concrete graph card is part of `dashboard_test.yaml` yet
- [ ] Learning the PMS window from symptom history (mentioned as a future possibility in 2.4, not part of M5)

### M6 — Blueprints and Convenience Automations ✅ (v0.6.0)
- [x] Blueprint: lighting/scene during the period/PMS window (`period_pms_lighting_scene.yaml`)
- [x] Blueprint: shopping list when contraception/period is approaching (`contraception_period_shopping_list.yaml`)
- [x] Blueprint: heating pad reminder (`heating_pad_reminder.yaml`)
- See `BLUEPRINTS.md` for import instructions and description; verified only statically (consistency of `!input` vs. declared inputs), not by a live import into a running instance

### M7 — Polish, Tests, and GitHub Documentation (closes out v1.0.0) — partially done (v0.7.0)
- [x] `tests/test_pill_math.py`, `tests/test_cycle_math.py` (26 tests) + `.github/workflows/test.yaml`
- [x] Edge cases covered: changing regimen_type mid-pack, pausing and re-enabling, backdated logging — tested; a future date (rejected) — verified by code inspection (3 services + the date entity), not by a new test; PMS override across cycles — **this was a real bug, fixed** (see CHANGELOG v0.7.0)
- [x] `README.md`: installation, first use, the cycle owner/supporter/administrator model, blueprints, disclaimer, "Running the tests" and "Known gaps" sections
- [x] `hacs.json`, GitHub Actions (`hassfest`, `hacs` validation) — done since M1
- [x] `CHANGELOG.md` with semver
- [ ] **Not done:** dashboard screenshots for the README — nothing to capture without a running HA instance, this needs live testing

### M8 — Pill Stock and Actionable Notifications ✅ (v0.8.0)

Requested live after the first real testing in HA (2026-07-29) — not in the original M1–M7 scope, extends section 2.3.

- [x] `number.*_pills_in_stock` — a real, configurable count of tablets at home (not derived from the pack schedule), auto-decremented on each first confirmation of a dose for a given day (a second confirmation for the same day doesn't decrement again), `perioder.set_pills_in_stock` service
- [x] A separate "running low" notification based on `low_stock_threshold` (default 5 tablets) — independent of the existing "pack ending" notification from M4 (that one is about the pack schedule, this one is about the actual physical supply); notifies once, and re-arms only after the stock is manually reset
- [x] Actionable buttons "Taken" (confirms the dose) and "Snooze" (delays the nag by `escalation_repeat_minutes`, doesn't confirm or mark anything as missed) on both the daily reminder and the escalation — `notify.send_message` `data.actions` + a shared listener on `mobile_app_notification_action`
- [ ] **Not done:** live verification on a real phone with the Home Assistant Companion app — so far only a standalone simulation of the logic (decrement guard, notify-once/re-arm, snooze window), the same as with M4

### M9 — Real Period End in the Calendar ✅ (v0.9.0)

Requested live, right after M8 — extends section 2.1.

- [x] `date.*_last_period_end` + `perioder.log_period_end` — an optional real period end (last day of menstruation, inclusive), validated against a future date and against a date before the start
- [x] The "Period" calendar block for the current cycle uses the real range (and a different label, "Period (confirmed end)") instead of an estimate from `period_duration`, as soon as the end is logged; other (past/future, still only predicted) blocks are unaffected
- [x] Reset of `last_period_end` on the next `log_period_start` (a per-cycle fact, same logic as `pms_override` from M7)
- [ ] **Not done:** live verification in a real HA calendar view — so far only a standalone simulation of the date arithmetic (`_period_and_fertile_blocks`)

### v2.0.0 — Future Extensions (outside the current scope)
- [ ] Custom Lovelace card (JS) — a purpose-built gauge/visualization instead of standard cards
- [ ] Decision: bundle it into the integration's repository, or release it as a separate HACS frontend "plugin"
- [ ] Optional: learning the PMS window from symptom history instead of a fixed setting (see open questions)

---

## 8. Versioning and Release Process

- **Semver since v0.1.0**: `MAJOR.MINOR.PATCH`. MAJOR = a major/incompatible change, MINOR = new functionality within the given major (typically = completion of one milestone), PATCH = a bug fix with no new functionality.
- **Three phases by version range:**

  | Range | Phase | Character |
  |---|---|---|
  | v0.1.0 – v0.x.x | Alpha development | Progressive minor versions roughly following milestones M1–M7, but the scope and order may change — features are still being tuned, nothing is final. |
  | v1.0.0 | Agreed-upon product | The point where we jointly confirm that the functional scope (M1–M7: cycle, contraception, PMS, supporters, symptoms, blueprints, tests, documentation) is complete and usable — not necessarily identical to "M7 done" on the exact day, but the moment of agreement. |
  | v1.x.x – v2.0.0 | Stable use + refinement | The product is fully usable and deployed, further minor/patch versions address things found in operation as well as small extensions, heading toward a custom frontend card. |
  | v2.0.0 | Frontend and further development | A custom Lovelace card (see section 5) and continuation based on whatever proves necessary by then. |

  Within both the alpha (0.x) and later phases, the same rule applies for PATCH: a fix with no functional change bumps only the last number (v0.1.1, v1.2.1...).

- **Release process for each version** — goal: from pushing to GitHub, it should be installable directly via HACS with no further intervention:
  1. `version` in `manifest.json` set exactly to the version going into the tag/release.
  2. `hacs.json` and GitHub Actions (`hassfest`, HACS validation — same as cyclist) must pass without errors before the release.
  3. For the given version, a `CHANGELOG.md` entry is prepared in English, in Keep a Changelog format (`Added` / `Changed` / `Fixed` / `Removed`).
  4. You commit, create a git tag and a GitHub Release with the same number, and paste the prepared changelog into the release notes.
  5. In HA: add/update via HACS, restart — no manual intervention in the code after installation.

---

## 9. Open Questions

- Which `regimen_type` is the default/most common (21/7, 24/4, other)?
- How many minutes/repeats of contraception reminder escalation before it stops nagging?
- A physical button/NFC tag in the bathroom for logging — from M2, or later?
- Should the PMS window in the future (M6+) learn from symptom history instead of a fixed number of days, or stay purely configurable + manual override?
- Resolved: the number of cycle owners and supporters is unlimited and the relationship between them is N:M — no assumption of a monogamous couple (see sections 1, 2.5, 2.9).
