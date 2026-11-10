import time

try:  # a try here so we can run this locally (e.g. on a Mac without RPLCD)
    from RPLCD.i2c import CharLCD
except ImportError:
    CharLCD = None

I2C_ADDRESS = 0x27
COLS, ROWS = 20, 4
PAGE_SECONDS = 3.0   # minimum time each page of missing items stays up
SCROLL_STEP = 0.4    # seconds per one-character scroll (below ~0.3 s gets hard to read)
SCROLL_PAUSE = 4     # steps to hold the start of a long name before it scrolls
SCROLL_GAP = "   "   # spacing between the end of a name and its start coming around


# custom characters..
SMILEY = (0b00000, 0b01010, 0b01010, 0b00000, 0b10001, 0b01110, 0b00000, 0b00000)
CHECK  = (0b00000, 0b00001, 0b00011, 0b10110, 0b11100, 0b01000, 0b00000, 0b00000)
raised_eyebrow = (0b01000,0b10011,0b00000,0b01010,0b00000,0b10001,0b01110,0b00000)
regular_eyebrow = (0b00000,0b11011,0b00000,0b01010,0b00000,0b10001,0b01110,0b00000)



ICON_SMILEY, ICON_CHECK = "\x00", "\x01"     # characters that display slots 0 and 1
ICON_RAISED, ICON_REGULAR = "\x02", "\x03"
TERMINAL_ICONS = str.maketrans({ICON_SMILEY: "☺", ICON_CHECK: "✓"})


def center(text):
    return str(text)[:COLS].center(COLS)


def marquee(text, width, elapsed):
    """Return `width` characters of text. Text that fits is returned as-is;
    longer text scrolls left, pausing at the start of each pass.
    `elapsed` is seconds since the scroll started, so every page starts at the beginning."""
    if len(text) <= width:
        return text
    padded = text + SCROLL_GAP
    step = int(elapsed / SCROLL_STEP) % (len(padded) + SCROLL_PAUSE)
    offset = max(0, step - SCROLL_PAUSE)
    return (padded + padded)[offset:offset + width]


def scroll_seconds(text, width):
    """How long one full scroll pass of `text` takes (0 if it fits)."""
    if len(text) <= width:
        return 0.0
    return (len(text) + len(SCROLL_GAP) + SCROLL_PAUSE) * SCROLL_STEP


class LCD_screen:
    def __init__(self, address=I2C_ADDRESS, port=1):
        # Build I2C connection here:
        self.lcd = None
        self._shown = [None] * ROWS  # what's on each row now, so unchanged rows aren't rewritten
        self._page = 0
        self._page_start = time.monotonic()
        if CharLCD is not None:
            try:
                self.lcd = CharLCD(i2c_expander='PCF8574', address=address, port=port,
                                   cols=COLS, rows=ROWS, dotsize=8,
                                   charmap='A02',
                                   auto_linebreaks=False,
                                   backlight_enabled=True)
                self.lcd.clear()
                self.lcd.create_char(0, SMILEY)
                self.lcd.create_char(1, CHECK)
                self.lcd.create_char(2, raised_eyebrow)
                self.lcd.create_char(3, regular_eyebrow)
            except OSError as e:
                print(f"LCD not found at {hex(address)} ({e}); printing to terminal")
                self.lcd = None

    def _write_row(self, row, text):
        """Write one row, cut to 20 characters and padded so old text is overwritten.
        Skips the write if the row already shows this text, which keeps scrolling
        and frequent updates from flickering."""
        text = str(text)[:COLS].ljust(COLS)
        if text == self._shown[row]:
            return
        self._shown[row] = text
        if self.lcd is None:
            print(f"[LCD row {row}] |{text}|")
            return
        self.lcd.cursor_pos = (row, 0)
        self.lcd.write_string(text)

    def print_header(self, header=""):
        self._write_row(0, header)

    def print_footer(self, footer=""):
        self._write_row(ROWS - 1, footer)

    def backlight(self, enable=False):
        if self.lcd is not None:
            self.lcd.backlight_enabled = enable

    def show(self, lines=None, header=None, footer=None):
        """Header on row 0 and footer on row 3 (if given); lines fill the rows between.
        Every row is set, so leftovers from the previous screen are cleared."""
        rows = []
        if header is not None:
            rows.append(header)
        body_rows = ROWS - len(rows) - (1 if footer is not None else 0)
        body = list(lines or [])[:body_rows]
        rows += body + [""] * (body_rows - len(body))
        if footer is not None:
            rows.append(footer)
        for row_pos, line in enumerate(rows[:ROWS]):
            self._write_row(row_pos, line)

    def show_idle(self, items_count, next_alarm=None):
        """next_alarm: an Alarm from alarms.json (has .hour, .minute, .second) or None."""
        alarm = (f"Alarm: {next_alarm.hour:02}:{next_alarm.minute:02}:{next_alarm.second:02}"
                 if next_alarm is not None else "No alarms set")
        self.show([center(f"{items_count} in profile."), center(alarm)],
                  header=center("IDLE"), footer=center("Press to scan"))

    def show_missing(self, names):
        """3 names per page, under a centered header. Names too long for their row
        scroll horizontally. A page stays up for PAGE_SECONDS, or longer if a name
        on it needs more time to scroll all the way through once.
        Call every loop pass; paging and scrolling happen on their own."""
        names = sorted(names)
        total = len(names)
        pages = max(1, -(-total // 3))  # ceiling division
        self._page %= pages

        def page_items(page):
            return [(f"{i}/{total} ", name)
                    for i, name in enumerate(names[page * 3:page * 3 + 3], start=page * 3 + 1)]

        # Move to the next page once this one has been up long enough
        elapsed = time.monotonic() - self._page_start
        needed = max([PAGE_SECONDS] + [scroll_seconds(n, COLS - len(p))
                                       for p, n in page_items(self._page)])
        if pages > 1 and elapsed >= needed:
            self._page = (self._page + 1) % pages
            self._page_start = time.monotonic()
            elapsed = 0.0

        lines = [prefix + marquee(name, COLS - len(prefix), elapsed)
                 for prefix, name in page_items(self._page)]
        header = f"{total} MISSING" + (f"  pg {self._page + 1}/{pages}" if pages > 1 else "")
        self.show(lines, header=center(header))

    def start_paging(self):
        """Restart missing-item paging from page 1 (call on entering Items Missing)."""
        self._page = 0
        self._page_start = time.monotonic()

    def show_all_items_clear(self, items_count, icon=ICON_CHECK):
        self.show(["", center(f"{icon} ALL ITEMS PRESENT"),
                   center(f"{items_count} of {items_count} found")])

    def close(self):
        if self.lcd is not None:
            self.lcd.clear()
            self.lcd.backlight_enabled = False
            self.lcd.close(clear=True)
        self._shown = [None] * ROWS


if __name__ == "__main__":
    from collections import namedtuple
    TestAlarm = namedtuple("TestAlarm", "hour minute second")  # stands in for an alarms.json entry

    lcd = LCD_screen()
    try:
        lcd.show_idle(4, TestAlarm(7, 30, 0))
        time.sleep(3)
        lcd.start_paging()
        names = ["Manila Folder", "Laptop Charger and Cable", "Snoopy Pencil", "iPad"]
        end = time.monotonic() + 20
        while time.monotonic() < end:
            lcd.show_missing(names)
            time.sleep(0.1)
        lcd.show_all_items_clear(4)
        time.sleep(3)
    finally:
        lcd.close()