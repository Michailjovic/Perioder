# Perioder

Home Assistant custom integration for menstrual cycle and contraception tracking, with configurable notifications for "supporters" - anyone the administrator chooses to keep informed (partner, roommate, family, in any number and any combination, no assumption of a monogamous couple).

> **Status: early alpha (v0.x).** Not feature-complete. See `CHANGELOG.md` for what's actually implemented in each release, and `ANALYZA-A-ROADMAP.md` for the full plan.

> This is a home-automation tool, not a medical device. Calendar-based fertility predictions are not a reliable contraception method on their own. Always consult a healthcare professional.

## The model: cycle owner, supporter, administrator

Three roles, deliberately not tied to any particular relationship shape:

- **Cycle owner**: the person whose cycle/contraception is being tracked. One config entry ("integration instance") per cycle owner - track as many people in one Home Assistant as you want, each fully independent. The cycle owner always sees everything about themselves on their own dashboard.
- **Supporter**: anyone the administrator wants kept informed about a cycle owner - partner, roommate, family, whoever. A supporter only sees the notification categories (PMS window, upcoming period, contraception restock, missed dose, fertility window) and detail level (general vs. detailed) they've been subscribed to, and only for the cycle owner(s) they're subscribed under. The same person can be a supporter for several different cycle owners at once (e.g. polyamory), and each of those subscriptions is configured independently - there's no assumption of a single monogamous pair.
- **Administrator**: whoever has admin rights on the Home Assistant instance - which is also whoever can reach Settings > Devices & Services in the first place, so this isn't an extra restriction, just how the platform already works. The administrator decides which supporters exist and what they're subscribed to, via Options Flow ("Configure" on the integration) or `perioder.update_settings`. There's no separate cycle-owner-side consent step in this project's model - see `ANALYZA-A-ROADMAP.md` section 2.5 for the reasoning.

One practical consequence: the PMS-window binary sensor always exists (so an admin can verify it in Developer Tools, or wire it into an automation), but it's deliberately left off the example owner-facing dashboard card - PMS visibility is a supporter-notification thing, not something the cycle owner needs surfaced about themselves.

## Installation (HACS)

1. HACS > Integrations > the three-dot menu > Custom repositories.
2. Add `https://github.com/Michailjovic/Perioder`, category **Integration**.
3. Install **Perioder** and restart Home Assistant.
4. Settings > Devices & Services > Add Integration > **Perioder**.

## First use / testing (v0.9.14)

1. During setup, name it exactly **Test** (this becomes the device name and
   determines entity IDs - the ready-made dashboard below assumes this name).
   If you want to test the daily reminder, pick a **Your own notify device**
   too (any `mobile_app` device) - without one, the reminder/escalation has
   nowhere to send to and silently does nothing (a debug log line only).
2. Install the **card-mod** frontend module first (HACS > Frontend > search
   "card-mod" > Install > reload the browser, Ctrl+Shift+R) -
   `dashboard_test.yaml`'s calendar cards are the built-in `type: calendar`
   card with `initial_view: dayGridMonth` plus a `card_mod` style setting
   `min-height` on `ha-card`, which fixes the month-grid row height clipping
   a plain built-in card has (found live, v0.9.1/v0.9.2 - a third-party
   `atomic-calendar-revive` card was tried as a workaround in v0.9.3, but
   this `card_mod` + `initial_view` combination turned out to work fine,
   confirmed live 2026-08-07). It's the one non-native piece of this
   dashboard; every control/sensor card is still a plain entity the
   integration provides itself, no helpers or scripts.
3. Two separate single-view dashboards (v0.9.12) instead of one dashboard
   with tabs: `dashboard_test.yaml` (day-to-day: confirm pill, log period,
   cycle day/next period, symptoms, a colored period/fertile/pause calendar
   - no PMS) and `dashboard_test_admin.yaml` (everything else: PMS window,
   supporters, pack start date correction, test notification, pause switch,
   the same calendar plus PMS, the detailed pill-log calendar, and the
   shared calendar). Each file's card list is one `vertical-stack`, so it
   renders as a single predictable column regardless of screen width - a
   plain flat card list would otherwise get auto-split into multiple
   columns by Lovelace's masonry view on wide screens. Add each the same way:
   Settings > Dashboards > Add Dashboard > "New dashboard from scratch" >
   open it > pencil icon (Edit Dashboard) > three-dot menu > "Edit in YAML"
   > delete what's there > paste the file's contents > Save. Do this twice,
   once per file. (`lovelace_example.yaml` is a single small entities card,
   for dropping into a dashboard you already have - no calendar, no
   card-mod needed.)
4. From the dashboard: click the date entity and pick a date (today, or
   earlier if you're only entering it the next day) - that logs the period
   start immediately, no separate confirm step. The PMS dropdown forces the
   PMS window on/off/auto for testing without waiting for the real date.
   Once the period is over, optionally set `date.*_last_period_end` (the
   real last day of bleeding, inclusive) - the calendar's period block for
   that cycle then shows the real span instead of the `period_duration`
   estimate. It resets itself the next time you log a new period start.
5. To test contraception: just press `button.*_confirm_pill_taken` - the
   first confirmation auto-activates tracking with that day as the pack
   start date (v0.9.7). After that, `sensor.*_contraception_status` shows
   `pending`/`taken`/`missed`/`paused`/`inactive` for today. If the real
   first day was earlier than today, set `date.*_pack_start_date` instead
   (v0.9.9) - same idea as `date.*_last_period_start`: pick a date, that
   *is* the action, backdating included. Either way it's a one-time thing -
   `day_in_pack()` wraps to the next pack automatically from then on, pause
   days/reminders/restock timing all compute themselves, nothing needs
   pressing again each cycle. `perioder.start_new_pack` (Developer Tools >
   Actions) does the same as the date entity, for automations/voice/NFC.
6. The day-to-day calendar shows predicted periods (red), fertile windows
   (green) and pack-pauses (grey) - PMS is deliberately left off it (that's
   admin-only, see below). The admin dashboard's detailed calendar adds
   PMS (purple) plus every logged pill confirmation as its own event - open
   one to see how many minutes early/late it was confirmed vs. the daily
   reminder time.
7. To test the reminder/escalation: use `perioder.update_settings` to set
   `reminder_time` a couple of minutes from now (and optionally lower
   `escalation_grace_minutes`) - a check runs every 15 minutes, so give it
   at least one tick past your chosen time. Leave the dose unconfirmed to
   see the missed-dose notification and escalation; press the button to see
   it stop. `switch.*_pause_notifications` mutes all of this without losing
   any data.
8. Settings > Devices & Services > Perioder > Configure lets you edit settings
   and add supporters (notification target, categories, detail level) - only
   reachable by an HA administrator, by design. `perioder.update_settings`
   does the same thing for settings from an automation/voice/NFC.
9. The symptom buttons log a timestamped entry each press;
   `sensor.*_last_symptom` shows the most recent one. `perioder.export_symptom_log`
   writes the full history to a CSV under Home Assistant's `www/` folder.
10. The shared calendar shows only generic "Citlivé období" blocks - which
    block types it reflects at all is the `shared_calendar_categories`
    setting (defaults to just periods).
11. `number.*_pills_in_stock` is a real, settable count of tablets at home -
    set it after buying more (or via `perioder.set_pills_in_stock`); each
    confirmed dose decrements it by one. Once it drops to or below
    `low_stock_threshold` (default 5), you and subscribed supporters get
    warned once - separate from the pack-days-remaining warning above.
12. On a phone with the Home Assistant Companion app, the reminder and
    escalation notifications now carry two buttons: "Vzal(a) jsem" confirms
    today's dose without opening the app; "Odložit" postpones the nag by
    `escalation_repeat_minutes` without marking anything taken or missed.

Prefer Developer Tools > Actions, or calling this from an automation/voice
command/NFC tag? `perioder.log_period_start`, `perioder.log_period_end`,
`perioder.set_pms_override`, `perioder.log_pill_taken`, `perioder.start_new_pack`,
`perioder.set_contraception_active`, `perioder.update_settings`,
`perioder.pause_notifications`, `perioder.log_symptom`,
`perioder.export_symptom_log`, and `perioder.set_pills_in_stock` all exist
and do exactly the same thing as the matching entities/Options Flow.

## Current scope (v0.9.3)

- Config + options flow (settings, supporter management), plus
  `perioder.update_settings` for changing settings outside the flow -
  covers every setting Options Flow does.
- Settings/supporters live in the config entry; runtime state (cycle,
  contraception, symptoms, notification bookkeeping) lives in a separate
  per-entry Store.
- Sensors: cycle day, phase, fertility, next period, contraception status
  (`inactive`/`paused`/`pending`/`taken`/`missed`), pack days remaining,
  last symptom logged, supporters overview (count + per-supporter
  attributes, for a dashboard markdown card).
- Binary sensors: period active, PMS window (with manual override),
  contraception tracking active, pill taken today.
- Date entities: log/backdate the period start directly from the UI, plus an
  optional real period end (used to show the actual span in the calendar
  instead of the `period_duration` estimate for that cycle).
- Select entity: PMS override (auto / active / inactive).
- Button entities: confirm today's pill taken, log each of the 4 built-in
  symptoms (cramps, headache, low energy, mood change).
- Switch entity: pause all notifications for this cycle owner.
- Number entity: `pills_in_stock` - settable physical tablet count, auto-decremented per confirmed dose.
- Calendar entities: `cycle_calendar` (detailed - predicted period/fertile/
  pms/pack-pause blocks plus every logged pill confirmation, with the delay
  vs. the reminder time), `period_calendar`/`fertile_calendar`/
  `pms_calendar`/`pause_calendar` (the same predicted blocks split one kind
  per entity, so a Lovelace calendar card can color each one differently -
  `pms_calendar` is meant for the admin dashboard only), and
  `shared_calendar` (generic "sensitive period" blocks with no detail, for
  exporting to a shared family calendar - which block types show up at all
  is configurable).
- Notifications: daily contraception reminder + escalation to your own
  device (with actionable "Vzal(a) jsem"/"Odložit" buttons, v0.8.0), a
  missed-dose alert to subscribed supporters (with a fertile-window
  heads-up folded in), a one-shot "pack running low" notice (current pack's
  active days ending soon) and a separate one-shot "low stock" notice
  (real `pills_in_stock` count dropping to/below `low_stock_threshold`) to
  supporters subscribed to restock alerts.
- Services: `log_period_start`, `log_period_end`, `set_pms_override`,
  `log_pill_taken`, `start_new_pack`, `set_contraception_active`,
  `update_settings`, `pause_notifications`, `log_symptom`,
  `export_symptom_log`, `set_pills_in_stock` (same effect as the
  entities/Options Flow above, for automations/voice/NFC).

Not yet implemented: `pms`/`period`/`fertility` as their own
transition-triggered supporter notifications (e.g. "PMS window just
started"), and history/trend graph cards (the sensors have the needed
data, no graph card is wired into `dashboard_test.yaml` yet). The
notification dispatch code (including the v0.8.0 actionable buttons)
also hasn't been exercised against a live Home Assistant instance yet -
only its decision logic has been verified standalone; please report if a
notification doesn't arrive, or if the "Vzal(a) jsem"/"Odložit" buttons
don't show up on your phone. See `CHANGELOG.md` and `ANALYZA-A-ROADMAP.md`.

## Optional automation blueprints

Lighting scene during period/PMS, adding to a shopping list when the
contraception pack runs low or a period is coming up, and a heating pad
reminder - none of these are part of the integration itself, so nothing
installs automatically. See `BLUEPRINTS.md` for import links and details.

## Running the tests

`cycle_math.py` and `pill_math.py` are plain Python with no Home Assistant
dependency by design, specifically so they can be unit tested without
installing Home Assistant itself:

```bash
pip install pytest
pytest tests/ -v
```

`tests/conftest.py` loads just those two modules (plus `const.py`) directly
by file path instead of importing the integration package normally, since
the normal import path runs `custom_components/perioder/__init__.py`, which
*does* need Home Assistant. Everything else (config flow, entities,
services, the notification engine) isn't covered by this test suite yet -
it's been checked via standalone logic simulations during development (see
`CHANGELOG.md`) and manual testing against a real Home Assistant instance,
not automated tests.

## Known gaps

- No dashboard screenshots in this README yet - the author hasn't captured
  any from a running instance.
- The v0.8.0 actionable notification buttons ("Vzal(a) jsem"/"Odložit")
  depend on the Home Assistant Companion app version on the phone - not yet
  confirmed to actually render as tappable buttons on a real device.
- **Name your cycle owner something that won't collide with another
  integration's entities** (found live 2026-08-08). If you also run the
  [cyclist](https://github.com/ringleader/cyclist) integration (the project
  this one's fertility/phase math was originally adapted from, see
  `cycle_math.py`) for the *same person*, both integrations end up wanting
  entity IDs like `sensor.<name>_cycle_day` - whichever loads second gets
  silently suffixed `_2` by Home Assistant's entity registry, and it's very
  easy to end up with a dashboard pointed at the *other* integration's
  entity instead of Perioder's (same-shaped state, completely different -
  and in this case wildly wrong-looking - numbers, no error anywhere to
  flag it). If you hit numbers that don't match the logged dates, check
  Developer Tools > States for a same-named `_2` entity before assuming a
  math bug. Cleanest fix: don't run both integrations under the same
  name for the same person, or rename one so their entity ID prefixes
  never overlap.
- See "Not yet implemented" above and `ANALYZA-A-ROADMAP.md` for the rest.

## Project docs

Full analysis, control model, and roadmap: `ANALYZA-A-ROADMAP.md`.
Optional automation blueprints: `BLUEPRINTS.md`.
