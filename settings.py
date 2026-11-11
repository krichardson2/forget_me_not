"""Settings for the Forget Me Not Pack you may want to tune.

Edit a value, then restart the app so it takes effect:
    sudo systemctl restart rfid-checker
"""

# ---- RFID reader power ---------------------------------------------------------
# Transmit power in dBm. Higher reads tags farther away (and through more of the
# bag), but also picks up tags that aren't in it. The reader accepts up to 26;
# anything higher is capped at 26.
READER_TX_POWER_DBM = 20

# Power used by configuration/configure.py when naming tags. Keep it low so only
# the tag held next to the reader is seen, not others nearby.
CONFIGURE_TX_POWER_DBM = 18

# ---- Presence --------------------------------------------------------------------
# An item counts as present if its tag was read within this many seconds.
# Longer rides out tags that only read now and then; shorter notices a removed
# item sooner.
PRESENCE_WINDOW_SECONDS = 3.0

# ---- LCD icons -------------------------------------------------------------------
# Icon shown in front of "ALL ITEMS PRESENT". Use a name from ICONS in
# peripherals/LCD.py: "check", "smiley", "raised_eyebrow" or "regular_eyebrow",
# or add your own there.
ALL_CLEAR_ICON = "check"
