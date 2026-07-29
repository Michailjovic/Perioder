# Perioder

Home Assistant custom integration for menstrual cycle and contraception tracking, with configurable notifications for "supporters" - anyone the administrator chooses to keep informed (partner, roommate, family, in any number and any combination, no assumption of a monogamous couple).

> **Status: early alpha (v0.x).** Not feature-complete. See `CHANGELOG.md` for what's actually implemented in each release, and `ANALYZA-A-ROADMAP.md` for the full plan.

> This is a home-automation tool, not a medical device. Calendar-based fertility predictions are not a reliable contraception method on their own. Always consult a healthcare professional.

## Installation (HACS)

1. HACS > Integrations > the three-dot menu > Custom repositories.
2. Add `https://github.com/Michailjovic/Perioder`, category **Integration**.
3. Install **Perioder** and restart Home Assistant.
4. Settings > Devices & Services > Add Integration > **Perioder**.

## First use / testing (v0.4.0)

1. During setup, name it exactly **Test** (this becomes the device name and
   determines entity IDs - the ready-made dashboard below assumes this name).
   If you want to test the daily reminder, pick a **Your own notify device**
   too (any `mobile_app` device) - without one, the reminder/escalation has
   nowhere to send to and silently does nothing (a debug log line only).
2. Add a full test dashboard in one go: Settings > Dashboards > Add Dashboard >
   "New dashboard from scratch" > open it > pencil icon (Edit Dashboard) >
   three-dot menu > "Edit in YAML" > paste the contents of `dashboard_test.yaml`
   > Save. No helpers or scripts needed - every control is a native entity
   the integration provides itself. (`lovelace_example.yaml` is the same
   sensor cards as a single card, for dropping into a dashboard you already have.)
3. From the dashboard: click the date entity and pick a date (today, or
   earlier if you're only entering it the next day) - that logs the period
   start immediately, no separate confirm step. The PMS dropdown forces the
   PMS window on/off/auto for testing without waiting for the real date.
4. To test contraception: call `perioder.start_new_pack` once (Developer
   Tools > Actions) to set a pack start date - after that, `sensor.*_contraception_status`
   shows `pending`/`taken`/`missed`/`paused`/`inactive` for today, and pressing
   `button.*_confirm_pill_taken` logs today's dose (same as `perioder.log_pill_taken`).
5. The calendar card shows predicted periods/fertile windows/pack-pauses,
   plus every logged pill confirmation as its own event - open one to see
   how many minutes early/late it was confirmed vs. the daily reminder time.
6. To test the reminder/escalation: use `perioder.update_settings` to set
   `reminder_time` a couple of minutes from now (and optionally lower
   `escalation_grace_minutes`) - a check runs every 15 minutes, so give it
   at least one tick past your chosen time. Leave the dose unconfirmed to
   see the missed-dose notification and escalation; press the button to see
   it stop. `switch.*_pause_notifications` mutes all of this without losing
   any data.
7. Settings > Devices & Services > Perioder > Configure lets you edit settings
   and add supporters (notification target, categories, detail level) - only
   reachable by an HA administrator, by design. `perioder.update_settings`
   does the same thing for settings from an automation/voice/NFC.

Prefer Developer Tools > Actions, or calling this from an automation/voice
command/NFC tag? `perioder.log_period_start`, `perioder.set_pms_override`,
`perioder.log_pill_taken`, `perioder.start_new_pack`,
`perioder.set_contraception_active`, `perioder.update_settings`, and
`perioder.pause_notifications` all exist and do exactly the same thing as
the matching entities/Options Flow.

## Current scope (v0.4.0)

- Config + options flow (settings, supporter management), plus
  `perioder.update_settings` for changing settings outside the flow.
- Settings/supporters live in the config entry; runtime state (cycle,
  contraception, symptoms, notification bookkeeping) lives in a separate
  per-entry Store.
- Sensors: cycle day, phase, fertility, next period, contraception status
  (`inactive`/`paused`/`pending`/`taken`/`missed`), pack days remaining.
- Binary sensors: period active, PMS window (with manual override),
  contraception tracking active, pill taken today.
- Date entity: log/backdate the period start directly from the UI.
- Select entity: PMS override (auto / active / inactive).
- Button entity: confirm today's pill taken.
- Switch entity: pause all notifications for this cycle owner.
- Calendar entity: predicted period/fertile/pack-pause blocks (forward and
  backward), plus every logged pill confirmation as an event, with the
  delay vs. the reminder time in its description.
- Notifications: daily contraception reminder + escalation to your own
  device, a missed-dose alert to subscribed supporters (with a
  fertile-window heads-up folded in), and a one-shot "pack running low"
  notice to supporters subscribed to restock alerts.
- Services: `log_period_start`, `set_pms_override`, `log_pill_taken`,
  `start_new_pack`, `set_contraception_active`, `update_settings`,
  `pause_notifications` (same effect as the entities/Options Flow above,
  for automations/voice/NFC).

Not yet implemented: `pms`/`period`/`fertility` as their own
transition-triggered supporter notifications (e.g. "PMS window just
started"), actionable notification buttons (confirming from the push
notification itself, not just the dashboard), and symptom logging. The
notification dispatch code in this release also hasn't been exercised
against a live Home Assistant instance yet - only its decision logic has
been verified standalone; please report if a notification doesn't actually
arrive. See `CHANGELOG.md` and `ANALYZA-A-ROADMAP.md`.

## Project docs

Full analysis, control model, and roadmap: `ANALYZA-A-ROADMAP.md`.
