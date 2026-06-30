"""Constants for the Infinitude integration."""

DOMAIN = "infinitude_beyond"

# Preset modes are slugs so hassfest accepts the icons.json/translation keys.
# Display names live in translations (see strings.json / translations/en.json).
PRESET_SCHEDULE = "schedule"
PRESET_WAKE = "wake"
PRESET_HOLD = "hold"
PRESET_HOLD_UNTIL = "hold_until"

# Map the old human-readable preset values to the new slugs so automations
# calling climate.set_preset_mode with the previous names keep working.
LEGACY_PRESET_ALIASES = {
    "Scheduled activity": PRESET_SCHEDULE,
    "Wake": PRESET_WAKE,
    "Hold indefinitely": PRESET_HOLD,
    "Hold until next activity": PRESET_HOLD_UNTIL,
}
