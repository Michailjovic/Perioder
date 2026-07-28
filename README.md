# Perioder

Home Assistant custom integration for menstrual cycle and contraception tracking, with configurable notifications for "supporters" - anyone the administrator chooses to keep informed (partner, roommate, family, in any number and any combination, no assumption of a monogamous couple).

> **Status: early alpha (v0.x).** Not feature-complete. See `CHANGELOG.md` for what's actually implemented in each release, and `ANALYZA-A-ROADMAP.md` for the full plan.

> This is a home-automation tool, not a medical device. Calendar-based fertility predictions are not a reliable contraception method on their own. Always consult a healthcare professional.

## Installation (HACS)

1. HACS > Integrations > the three-dot menu > Custom repositories.
2. Add `https://github.com/Michailjovic/Perioder`, category **Integration**.
3. Install **Perioder** and restart Home Assistant.
4. Settings > Devices & Services > Add Integration > **Perioder**.

## First use / testing (v0.1.0)

1. During setup, name it exactly **Test** (this becomes the device name and
   determines entity IDs - the ready-made dashboard below assumes this name).
2. Call `perioder.log_period_start` (Developer Tools > Actions, pick the cycle
   owner from the dropdown), optionally with a backdated `date:`. Without this,
   all sensors stay "unknown".
3. Add a full test dashboard in one go: Settings > Dashboards > Add Dashboard >
   "New dashboard from scratch" > open it > pencil icon (Edit Dashboard) >
   three-dot menu > "Edit in YAML" > paste the contents of `dashboard_test.yaml`
   > Save. (`lovelace_example.yaml` is the same cards as a single card, for
   dropping into a dashboard you already have.)
4. Try `perioder.set_pms_override` (`active` / `inactive` / `auto`) to see the
   PMS window sensor react without waiting for the real date.
5. Settings > Devices & Services > Perioder > Configure lets you edit settings
   and add supporters (notification target, categories, detail level) - only
   reachable by an HA administrator, by design.

## Current scope (v0.1.0)

- Config + options flow (settings, supporter management).
- Settings/supporters live in the config entry; runtime state (cycle,
  contraception, symptoms) lives in a separate per-entry Store.
- Sensors: cycle day, phase, fertility, next period.
- Binary sensors: period active, PMS window (with manual override).
- Services: `log_period_start`, `set_pms_override`.

Not yet implemented: contraception reminders/logic, the prediction calendar, symptom logging, and the supporter notification engine. See `CHANGELOG.md` and `ANALYZA-A-ROADMAP.md`.

## Project docs

Full analysis, control model, and roadmap: `ANALYZA-A-ROADMAP.md`.
