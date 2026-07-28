# Perioder

Home Assistant custom integration for menstrual cycle and contraception tracking, with configurable notifications for "supporters" - anyone the administrator chooses to keep informed (partner, roommate, family, in any number and any combination, no assumption of a monogamous couple).

> **Status: early alpha (v0.x).** Not feature-complete. See `CHANGELOG.md` for what's actually implemented in each release, and `ANALYZA-A-ROADMAP.md` for the full plan.

> This is a home-automation tool, not a medical device. Calendar-based fertility predictions are not a reliable contraception method on their own. Always consult a healthcare professional.

## Installation (HACS)

1. HACS > Integrations > the three-dot menu > Custom repositories.
2. Add `https://github.com/Michailjovic/Perioder`, category **Integration**.
3. Install **Perioder** and restart Home Assistant.
4. Settings > Devices & Services > Add Integration > **Perioder**.

## First use (v0.1.0)

1. During setup, give it a name (e.g. "Alina") - this becomes the device name and shows up in entity IDs.
2. Call the `perioder.log_period_start` action (Developer Tools > Actions) for that cycle owner, optionally with a backdated `date:`. Without this, all sensors stay "no data".
3. Check Settings > Devices & Services > Perioder > (your device) for the created entities, or Developer Tools > States.
4. Add `lovelace_example.yaml` to a dashboard (adjust entity IDs to match your device's slug) to see cycle day, phase, fertility, and days until the next period update live.
5. Try `perioder.set_pms_override` (`active` / `inactive` / `auto`) to see the PMS window sensor react without waiting for the real date.
6. Settings > Devices & Services > Perioder > Configure lets you edit settings and add supporters (notification target, categories, detail level) - only reachable by an HA administrator, by design.

## Current scope (v0.1.0)

- Config + options flow (settings, supporter management).
- Storage for cycle, contraception, symptoms, and supporters.
- Sensors: cycle day, phase, fertility, next period.
- Binary sensors: period active, PMS window (with manual override).
- Services: `log_period_start`, `set_pms_override`.

Not yet implemented: contraception reminders/logic, the prediction calendar, symptom logging, and the supporter notification engine. See `CHANGELOG.md` and `ANALYZA-A-ROADMAP.md`.

## Project docs

Full analysis, control model, and roadmap: `ANALYZA-A-ROADMAP.md`.
