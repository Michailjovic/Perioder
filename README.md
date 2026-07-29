# Perioder

Home Assistant custom integration for menstrual cycle and contraception tracking, with configurable notifications for "supporters" - anyone the administrator chooses to keep informed (partner, roommate, family, in any number and any combination, no assumption of a monogamous couple).

> **Status: early alpha (v0.x).** Not feature-complete. See `CHANGELOG.md` for what's actually implemented in each release, and `ANALYZA-A-ROADMAP.md` for the full plan.

> This is a home-automation tool, not a medical device. Calendar-based fertility predictions are not a reliable contraception method on their own. Always consult a healthcare professional.

## Installation (HACS)

1. HACS > Integrations > the three-dot menu > Custom repositories.
2. Add `https://github.com/Michailjovic/Perioder`, category **Integration**.
3. Install **Perioder** and restart Home Assistant.
4. Settings > Devices & Services > Add Integration > **Perioder**.

## First use / testing (v0.2.0)

1. During setup, name it exactly **Test** (this becomes the device name and
   determines entity IDs - the ready-made dashboard below assumes this name).
2. Add a full test dashboard in one go: Settings > Dashboards > Add Dashboard >
   "New dashboard from scratch" > open it > pencil icon (Edit Dashboard) >
   three-dot menu > "Edit in YAML" > paste the contents of `dashboard_test.yaml`
   > Save. No helpers or scripts needed - the date input, PMS override, and
   pill-confirmation button are native entities the integration provides
   itself. (`lovelace_example.yaml` is the same sensor cards as a single
   card, for dropping into a dashboard you already have.)
3. From the dashboard: click the date entity and pick a date (today, or
   earlier if you're only entering it the next day) - that logs the period
   start immediately, no separate confirm step. The PMS dropdown forces the
   PMS window on/off/auto for testing without waiting for the real date.
4. To test contraception: call `perioder.start_new_pack` once (Developer
   Tools > Actions) to set a pack start date - after that, `sensor.*_contraception_status`
   shows `pending`/`taken`/`missed`/`paused`/`inactive` for today, and pressing
   `button.*_confirm_pill_taken` logs today's dose (same as `perioder.log_pill_taken`).
5. Settings > Devices & Services > Perioder > Configure lets you edit settings
   and add supporters (notification target, categories, detail level) - only
   reachable by an HA administrator, by design.

Prefer Developer Tools > Actions, or calling this from an automation/voice
command/NFC tag? `perioder.log_period_start`, `perioder.set_pms_override`,
`perioder.log_pill_taken`, `perioder.start_new_pack`, and
`perioder.set_contraception_active` all exist and do exactly the same thing
as the matching entities.

## Current scope (v0.2.0)

- Config + options flow (settings, supporter management).
- Settings/supporters live in the config entry; runtime state (cycle,
  contraception, symptoms) lives in a separate per-entry Store.
- Sensors: cycle day, phase, fertility, next period, contraception status
  (`inactive`/`paused`/`pending`/`taken`/`missed`), pack days remaining.
- Binary sensors: period active, PMS window (with manual override),
  contraception tracking active, pill taken today.
- Date entity: log/backdate the period start directly from the UI.
- Select entity: PMS override (auto / active / inactive).
- Button entity: confirm today's pill taken.
- Services: `log_period_start`, `set_pms_override`, `log_pill_taken`,
  `start_new_pack`, `set_contraception_active` (same effect as the entities
  above, for automations/voice/NFC).

Not yet implemented: the daily contraception reminder + escalation
notification, the prediction calendar, symptom logging, and the supporter
notification engine. The reminder/escalation piece was deliberately deferred
alongside the supporter notification engine (M4) - both need the same
underlying actionable-notification plumbing. See `CHANGELOG.md` and
`ANALYZA-A-ROADMAP.md`.

## Project docs

Full analysis, control model, and roadmap: `ANALYZA-A-ROADMAP.md`.
