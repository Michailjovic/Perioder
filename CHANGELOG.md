# Changelog

All notable changes to this project are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/); see `ANALYZA-A-ROADMAP.md`
section 8 for what the pre-1.0.0 range means for this project specifically.

## [0.1.0] - 2026-07-28

First installable, testable release. Covers the M1 foundation plus just enough
of the cycle/PMS logic (pulled forward from later milestones) to see real
numbers on a dashboard with test data - contraception, the calendar, symptoms,
and the supporter notification engine are intentionally not in yet.

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
- Persistent storage layer (Home Assistant `Store`) covering cycle, contraception,
  symptoms, and supporters data, isolated per config entry so any number of
  independent cycle owners can be tracked in one instance.
- Pure cycle/fertility/PMS math module (`cycle_math.py`), with no Home Assistant
  dependencies - verified against a 28-day reference cycle covering every day 1-28
  with no unassigned "gap" days between phases.
- Sensors: `cycle_day`, `phase`, `fertility`, `next_period` (days until).
- Binary sensors: `period_active`, `pms_active` (honors a manual per-cycle override).
- Services: `perioder.log_period_start` (with optional backdating) and
  `perioder.set_pms_override` (auto / force active / force inactive) - both target
  a specific cycle owner via a config entry selector, since one HA instance may
  track several independent people.
- `lovelace_example.yaml` - a starter dashboard card for testing.
- Entities refresh immediately on service calls and on a 15-minute tick, so the
  cycle day rolls over without waiting for another action.

### Notes

- Contraception logic, the calendar, symptom logging, and the supporter
  notification engine are not implemented yet - `active`/`pill_log`/`supporters`
  are already in storage, ready for the next 0.x release to build on.
- `manifest.json` codeowners/documentation/issue_tracker now point at
  `github.com/Michailjovic/Perioder`.
