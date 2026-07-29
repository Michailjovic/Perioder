"""Constants for the Perioder integration."""
from __future__ import annotations

DOMAIN = "perioder"

STORAGE_VERSION = 1
STORAGE_KEY_PREFIX = "perioder"

# Config / options keys - core settings
CONF_NAME = "name"
CONF_CYCLE_LENGTH = "cycle_length"
CONF_PERIOD_DURATION = "period_duration"
CONF_GOAL = "goal"
CONF_PMS_WINDOW_DAYS = "pms_window_days"
CONF_REGIMEN_TYPE = "regimen_type"
CONF_PACK_SIZE = "pack_size"
CONF_PAUSE_DAYS = "pause_days"
CONF_REMINDER_TIME = "reminder_time"

# Config / options keys - notifications (M4)
CONF_OWNER_NOTIFY_DEVICE = "owner_notify_device"
CONF_ESCALATION_GRACE_MINUTES = "escalation_grace_minutes"
CONF_ESCALATION_REPEAT_MINUTES = "escalation_repeat_minutes"
CONF_ESCALATION_MAX_COUNT = "escalation_max_count"
CONF_RESTOCK_DAYS_BEFORE = "restock_days_before"

# Config / options keys - shared calendar (M5)
CONF_SHARED_CALENDAR_CATEGORIES = "shared_calendar_categories"

# Config / options keys - pill stock (v0.8.0)
CONF_LOW_STOCK_THRESHOLD = "low_stock_threshold"

DEFAULT_CYCLE_LENGTH = 28
DEFAULT_PERIOD_DURATION = 5
DEFAULT_GOAL = "track"
DEFAULT_PMS_WINDOW_DAYS = 4
DEFAULT_REGIMEN_TYPE = "21_7"
DEFAULT_REMINDER_TIME = "21:00:00"

# Grace period before "pending" becomes "missed" (also used by pill_status()
# for the sensor, so the displayed status and the notification engine always
# agree on what "missed" means). Repeat/max count control the escalation
# nag to the owner after that point; none of this affects supporters, who
# only ever get one missed_dose notification per day (see notifications.py).
DEFAULT_ESCALATION_GRACE_MINUTES = 60
DEFAULT_ESCALATION_REPEAT_MINUTES = 30
DEFAULT_ESCALATION_MAX_COUNT = 3
DEFAULT_RESTOCK_DAYS_BEFORE = 3

# Below this many physical pills left at home, warn once (until restocked).
# Separate from restock_days_before: that one is about the *current pack*
# (its active days are running out - time to open a new one); this one is
# about the *physical supply at home* (number.*_pills_in_stock) - do you
# actually have a next pack, or do you need to go buy more. See v0.8.0.
DEFAULT_LOW_STOCK_THRESHOLD = 5

# Which block types show up (generically, no detail) on calendar.*_shared_calendar.
# The cycle owner picks these (see ANALYZA-A-ROADMAP.md section 2.7); in this
# project's admin-controlled model (section 2.5) that choice is still made
# via Options Flow/update_settings like every other setting.
SHARED_CALENDAR_PERIOD = "period"
SHARED_CALENDAR_FERTILE = "fertile"
SHARED_CALENDAR_PAUSE = "pause"
SHARED_CALENDAR_CATEGORIES = [SHARED_CALENDAR_PERIOD, SHARED_CALENDAR_FERTILE, SHARED_CALENDAR_PAUSE]
DEFAULT_SHARED_CALENDAR_CATEGORIES = [SHARED_CALENDAR_PERIOD]

# Goals - what the cycle owner is currently using the tracking for.
GOAL_TRACK = "track"
GOAL_AVOID = "avoid"
GOAL_PLAN = "plan"
GOALS = [GOAL_TRACK, GOAL_AVOID, GOAL_PLAN]

# Contraception regimen types.
REGIMEN_21_7 = "21_7"
REGIMEN_24_4 = "24_4"
REGIMEN_CONTINUOUS = "continuous"
REGIMEN_CUSTOM = "custom"
REGIMEN_TYPES = [REGIMEN_21_7, REGIMEN_24_4, REGIMEN_CONTINUOUS, REGIMEN_CUSTOM]

# (pack_size, pause_days) for the built-in regimen types.
# REGIMEN_CUSTOM has no fixed pair - pack_size/pause_days come from config instead.
REGIMEN_PACK_DEFAULTS: dict[str, tuple[int, int]] = {
    REGIMEN_21_7: (21, 7),
    REGIMEN_24_4: (24, 4),
    REGIMEN_CONTINUOUS: (28, 0),
}

# Cycle phases.
PHASE_MENSTRUATION = "menstruation"
PHASE_FOLLICULAR = "follicular"
PHASE_OVULATION = "ovulation"
PHASE_LUTEAL = "luteal"

# Fertility levels.
FERTILITY_FERTILE = "fertile"
FERTILITY_LOW = "low"
FERTILITY_SAFER = "safer"

# Contraception day status.
CONTRACEPTION_TAKEN = "taken"
CONTRACEPTION_PENDING = "pending"
CONTRACEPTION_PAUSED = "paused"
CONTRACEPTION_INACTIVE = "inactive"
CONTRACEPTION_MISSED = "missed"

# Supporter notification categories.
CATEGORY_PMS = "pms"
CATEGORY_PERIOD = "period"
CATEGORY_CONTRACEPTION_RESTOCK = "contraception_restock"
CATEGORY_MISSED_DOSE = "missed_dose"
CATEGORY_FERTILITY = "fertility"
SUPPORTER_CATEGORIES = [
    CATEGORY_PMS,
    CATEGORY_PERIOD,
    CATEGORY_CONTRACEPTION_RESTOCK,
    CATEGORY_MISSED_DOSE,
    CATEGORY_FERTILITY,
]

# Supporter notification detail level.
DETAIL_GENERAL = "general"
DETAIL_DETAILED = "detailed"
DETAIL_LEVELS = [DETAIL_GENERAL, DETAIL_DETAILED]

# Mobile app push-notification action identifiers (v0.8.0) - suffixed with a
# config entry_id at send time so multiple cycle owners in one Home Assistant
# don't collide, and so the shared event listener in __init__.py knows which
# entry's storage/settings to act on. See notifications.py / __init__.py.
ACTION_CONFIRM_PILL_PREFIX = "PERIODER_CONFIRM_PILL_"
ACTION_POSTPONE_PILL_PREFIX = "PERIODER_POSTPONE_PILL_"
EVENT_MOBILE_APP_NOTIFICATION_ACTION = "mobile_app_notification_action"

# Common symptoms for perioder.log_symptom (M2+).
SYMPTOM_CRAMPS = "cramps"
SYMPTOM_HEADACHE = "headache"
SYMPTOM_LOW_ENERGY = "low_energy"
SYMPTOM_MOOD_CHANGE = "mood_change"
SYMPTOMS = [SYMPTOM_CRAMPS, SYMPTOM_HEADACHE, SYMPTOM_LOW_ENERGY, SYMPTOM_MOOD_CHANGE]
