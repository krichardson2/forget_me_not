import time

try:  # a try here so we can run this locally (e.g. on a Mac without RPLCD)
    from RPLCD.i2c import CharLCD
except ImportError:
    CharLCD = None

I2C_ADDRESS = 0x27
COLS, ROWS = 20, 4
PAGE_SECONDS = 3.0  # how long each page of missing items stays up

# custom characters..
raised_eyebrow = (0b01000,0b10011,0b00000,0b01010,0b00000,0b10001,0b01110,0b00000)
regular_eyebrow = (0b00000,0b11011,0b00000,0b01010,0b00000,0b10001,0b01110,0b00000)

class LCD_screen:
    def __init__(self, address=I2C_ADDRESS, port=1):
        # Build I2C connection here:
        self.lcd = None
        self._page_start = time.monotonic()
        if CharLCD is not None:
            try:
                self.lcd = CharLCD(i2c_expander='PCF8574', address=address, port=port,
                                   cols=COLS, rows=ROWS, dotsize=8,
                                   charmap='A02',
                                   auto_linebreaks=False,
                                   backlight_enabled=True)
                self.lcd.clear()
            except OSError as e:
                print(f"LCD not found at {hex(address)} ({e}); printing to terminal")
                self.lcd = None

    def _write_row(self, row, text):
        """Write one row, cut to 20 characters and padded so old text is overwritten."""
        text = str(text)[:COLS].ljust(COLS)
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
        Every row is written, so leftovers from the previous screen are cleared."""
        rows = []
        if header is not None:
            rows.append(header)
        body_rows = ROWS - len(rows) - (1 if footer is not None else 0)
        rows += list(lines or [])[:body_rows]
        rows += [""] * (body_rows - (len(rows) - (1 if header is not None else 0)))
        if footer is not None:
            rows.append(footer)
        for row_pos, line in enumerate(rows[:ROWS]):
            self._write_row(row_pos, line)

    def show_idle(self, items_count, next_alarm=None):
        """next_alarm: an Alarm from alarms.json (has .hour, .minute, .second) or None."""
        alarm = (f"Alarm: {next_alarm.hour:02}:{next_alarm.minute:02}:{next_alarm.second:02}"
                 if next_alarm is not None else "No alarms set")
        self.show([f"{items_count} in profile.", alarm], header="IDLE", footer="Press to scan")

    def show_missing(self, names):
        """3 names per page; call every loop pass and pages flip every PAGE_SECONDS."""
        names = sorted(names)
        total = len(names)
        pages = max(1, -(-total // 3))  # ceiling division
        page = int((time.monotonic() - self._page_start) / PAGE_SECONDS) % pages
        lines = [f"{i + 1}/{total} {name}" for i, name in enumerate(names)][page * 3:page * 3 + 3]
        header = f"{total} MISSING" + (f"  pg {page + 1}/{pages}" if pages > 1 else "")
        self.show(lines, header=header)

    def start_paging(self):
        """Restart missing-item paging from page 1 (call on entering Items Missing)."""
        self._page_start = time.monotonic()

    def show_all_items_clear(self, items_count):
        self.show(["", " ALL ITEMS PRESENT", f"   {items_count} of {items_count} found"])

    def close(self):
        if self.lcd is not None:
            self.lcd.clear()
            self.lcd.backlight_enabled = False
            self.lcd.close(clear=True)


if __name__ == "__main__":
    from collections import namedtuple
    TestAlarm = namedtuple("TestAlarm", "hour minute second")  # stands in for an alarms.json entry

    lcd = LCD_screen()
    try:
        lcd.show_idle(4, TestAlarm(7, 30, 0))
        time.sleep(3)
        lcd.show_missing(["Manila Folder", "Snoopy Pencil"])
        time.sleep(3)
        lcd.show_all_items_clear(4)
        time.sleep(3)
    finally:
        lcd.close()