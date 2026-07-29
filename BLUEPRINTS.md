# Perioder blueprints

Optional automation blueprints built on top of the Perioder integration -
not part of the core integration itself, so you turn on only what you want
(see `ANALYZA-A-ROADMAP.md` section 2.6). They're plain automation
blueprints (same mechanism as `BLUEPRINTS.md` in
[cyclist](https://github.com/ringleader/cyclist)), not something HACS
installs automatically alongside the integration - import each one
separately, once, the first time you want it.

## Import

For each blueprint below:

1. Settings > Automations & Scenes > Blueprints tab > **Import Blueprint**.
2. Paste the blueprint's URL from the table below and confirm.
3. Settings > Automations & Scenes > **+ Add Automation** > pick the
   imported blueprint from the list, fill in the inputs, save.

| Blueprint | Import URL |
|---|---|
| Lighting scene during period/PMS | `https://github.com/Michailjovic/Perioder/blob/main/blueprints/automation/perioder/period_pms_lighting_scene.yaml` |
| Add to shopping list when running low | `https://github.com/Michailjovic/Perioder/blob/main/blueprints/automation/perioder/contraception_period_shopping_list.yaml` |
| Heating pad reminder | `https://github.com/Michailjovic/Perioder/blob/main/blueprints/automation/perioder/heating_pad_reminder.yaml` |

## What each one does

### Lighting scene during period/PMS

Activates a scene you choose as soon as either the period or the PMS
window starts, and restores a normal scene once both have ended. Point
the two inputs at Perioder's own `binary_sensor.*_period_active` and
`binary_sensor.*_pms_active` for one cycle owner - both always exist on
the device, no extra helpers needed.

The PMS sensor is meant for supporters rather than the cycle owner's own
dashboard (see section 2.2 of `ANALYZA-A-ROADMAP.md`) - that's a
dashboard/notification convention, not an entity restriction, so wiring
an automation to it here is fine.

### Add to shopping list when running low

Adds an item to a to-do/shopping list of your choice when the
contraception pack has a configurable number of days left, and/or when
the next predicted period is a configurable number of days away. Each
half fires once per crossing (a numeric_state trigger only fires the
moment the value drops below the threshold), so it won't spam the list
with duplicates while the value stays low.

### Heating pad reminder

Sends a notification suggesting the heating pad the moment a period
starts, and can optionally also turn on a heating pad switch/smart plug
directly if you leave that input filled in.

## Notes

- All three reference entities Perioder already creates for a cycle
  owner (`binary_sensor.*_period_active`/`*_pms_active`,
  `sensor.*_pack_days_remaining`, `sensor.*_next_period`) - no
  `input_datetime`/`input_boolean` helpers, scripts, or extra
  configuration needed beyond picking your own scenes/lists/notify
  targets/switches when setting up the automation.
- These are independent automations per cycle owner - if you track more
  than one person in the same Home Assistant instance, import the
  blueprint once and create one automation instance per cycle owner,
  pointing each at that owner's entities.
