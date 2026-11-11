# Forget Me Not Pack – User Guide

Draft 1 · 2026-11-10 · Three Labs, LLC

## 1. About this guide

The Forget Me Not Pack checks that every tagged item in a profile is nearby, and names any missing item on its screen. This guide covers assembling the prototype, powering it on, configuring items and alarms, and running a demonstration.

A check starts at a scheduled alarm time or when someone presses the button. The device scans for RFID tags. A slow green glow means every item was found. A fast red pulse means something is missing, and the LCD lists what.

### What's in the kit

| Part | Notes |
| --- | --- |
| Raspberry Pi 3 Model B+ | Runs the application from microSD |
| microSD card (2) | One in the Pi, one flashed as a backup |
| UHF RFID reader (YRM100, M100 chip) | Connects by USB |
| 20x4 character LCD with I2C backpack | I2C address 0x27 |
| WS2812B LED strip, 40 LEDs | Powered from the Pi's 5 V pin |
| DS3231 real-time clock module | Coin cell backup, I2C address 0x68 |
| Momentary pushbutton | Starts or cancels a check |
| UHF RFID tags (10) | Assigned to the preset item profile |
| 330 Ω resistor | In series with the LED strip's data line |

### Safety and handling

- Use a 5 V, 2.5 A (or larger) Raspberry Pi power supply. The reader, LED strip and LCD all draw from it.
- LED brightness is capped in software at 15% so the strip stays within what the Pi's 5 V pin can supply. Don't raise it without giving the strip its own power supply.
- Shut down before unplugging (section 7). Pulling power while the system is writing can damage the microSD card.
- If the DS3231 module has a charging circuit (common on ZS-042 boards), use a rechargeable LIR2032 cell, or remove the charging diode before fitting a CR2032.

## 2. Assembly

The unit ships assembled. Use these steps to rebuild it or to prepare a replacement microSD card.

### 2.1 Wiring

Disconnect power before wiring. Pin numbers are physical header pins; pin 1 has the square pad. The RFID reader plugs into any USB port and doesn't use the header.

| Device | Device pin | Pi pin | Pi function |
| --- | --- | --- | --- |
| LED strip | 5V (red wire) | 2 | 5 V power |
| LED strip | DIN (green wire), through the 330 Ω resistor | 12 | GPIO18 (PWM) |
| LED strip | GND (white wire) | 6 | Ground |
| LCD 20x4 | VCC | 1 | 3.3 V power |
| LCD 20x4 | GND | 9 | Ground |
| LCD 20x4 | SDA | 3 | GPIO2 (I2C SDA) |
| LCD 20x4 | SCL | 5 | GPIO3 (I2C SCL) |
| DS3231 RTC | VCC | 17 | 3.3 V power |
| DS3231 RTC | GND | 39 | Ground |
| DS3231 RTC | SDA | 3 | Shared with the LCD |
| DS3231 RTC | SCL | 5 | Shared with the LCD |
| Pushbutton | One leg | 16 | GPIO23 (internal pull-up) |
| Pushbutton | Other leg | 14 | Ground |
| RFID reader | USB | Any USB port | Appears as /dev/RFID_scanner |

The LCD and RTC share the I2C bus: both SDA wires go to pin 3 and both SCL wires to pin 5. A wiring diagram is in `docs/wiring.svg`.

### 2.2 Preparing the microSD card

1. Flash Raspberry Pi OS (64-bit, with desktop) with Raspberry Pi Imager. The desktop is needed for configuration. Create the user `pi`.
2. Boot the Pi with a keyboard, mouse and monitor attached.
3. Add these lines to `/boot/firmware/config.txt`, then reboot:
   ```
   dtparam=i2c_arm=on
   dtoverlay=i2c-rtc,ds3231
   dtparam=audio=off
   ```
   They enable I2C, load the RTC driver, and free GPIO18's PWM for the LED strip.
4. Remove the fake clock so the system takes its time from the RTC:
   ```
   sudo apt purge fake-hwclock
   ```
5. Copy the application folder to `/home/pi/rfid-item-check`.
6. Create the Python environment and install the libraries:
   ```
   python3 -m venv /home/pi/venv
   /home/pi/venv/bin/pip install pyserial protobuf gpiozero lgpio RPLCD smbus2 adafruit-blinka adafruit-circuitpython-neopixel rpi_ws281x
   ```
7. Install the reader's device rule so it always appears as `/dev/RFID_scanner`:
   ```
   sudo cp rules/99-rfid-scanner.rules /etc/udev/rules.d/
   sudo udevadm control --reload && sudo udevadm trigger
   ```
8. Install and start the service so the application runs at every boot:
   ```
   sudo cp service/rfid-checker.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now rfid-checker
   ```

### 2.3 Setting the clock

The RTC is set once during assembly and keeps time on its coin cell. It can't be changed through the device's configuration. To set it, set the system time and copy it to the RTC:

```
sudo date -s "2026-11-10 14:30:00"
sudo hwclock -w
```

### 2.4 Checking the hardware

| Check | Command | Expected result |
| --- | --- | --- |
| I2C devices | `sudo i2cdetect -y 1` | `27` (LCD) and `UU` at 68 (RTC, claimed by its driver) |
| RTC time | `sudo hwclock -r` | Current local date and time |
| RFID reader | `ls -l /dev/RFID_scanner` | A link to `/dev/ttyUSB0` or similar |
| Application | `systemctl status rfid-checker` | `active (running)` |

## 3. Power on

Plug in the power supply. After about 30–60 seconds the application starts on its own in Idle. The LED strip stays off, and the LCD shows:

```
        IDLE
   10 in profile.
   Alarm: 17:00:00
    Press to scan
```

The second line is the number of items in the profile. The third line is the next scheduled alarm, or "No alarms set". If the application stops for any reason, it restarts itself within a few seconds.

## 4. Configuration

Configuration uses a keyboard, mouse and monitor connected directly to the Pi. Items and alarms are stored in two files in `/home/pi/rfid-item-check`:

- `items.json`: the item profile (tag and name for each item)
- `alarms.json`: the scheduled check times

### 4.1 Editing the files

1. Stop the application: `sudo systemctl stop rfid-checker`
2. Open the file in the desktop's Text Editor.
3. Make the changes and save.
4. Start the application: `sudo systemctl start rfid-checker`

The application reads both files only when it starts, so changes take effect at the restart. If a file has a mistake, the application ignores the whole file and logs the reason (section 7). An invalid `items.json` shows as "0 in profile." on the Idle screen.

### 4.2 Item profile (items.json)

```json
{
  "items": [
    { "tag": "E28011B0A506007F786F06B1", "name": "Pencil case" },
    { "tag": "E28011B0A506007F786F06B2", "name": "Laptop charger" }
  ]
}
```

| Field | Rule |
| --- | --- |
| `tag` | The tag's EPC: exactly 24 characters, 0–9 and A–F, uppercase. Each tag only once. |
| `name` | At least 1 character of plain ASCII (no accents or emoji). Names longer than the screen scroll. |
| Count | Up to 50 items. |

To add an item, add a `{ "tag": ..., "name": ... }` entry. To delete an item, remove its entry. Entries are separated by commas, with no comma after the last one.

### 4.3 Finding a tag's EPC by scanning

1. Stop the application: `sudo systemctl stop rfid-checker`
2. Place only the new tag near the reader.
3. Run the reader test: `cd /home/pi/rfid-item-check && sudo /home/pi/venv/bin/python peripherals/uhf_reader.py`
4. Copy the 24-character code it prints into `items.json`, then start the application again.

### 4.4 Scheduled alarms (alarms.json)

```json
{
  "alarms": [
    { "hour": 7, "minute": 30, "second": 0 },
    { "hour": 17, "minute": 0, "second": 0 }
  ]
}
```

| Field | Rule |
| --- | --- |
| `hour` | 0–23 (24-hour clock) |
| `minute` | 0–59 |
| `second` | 0–59 |
| Count | Up to 10 alarms, no two at the same time. |

Each alarm starts a 20-minute check at that time of day, every day.

## 5. Operation

The device moves between five states:

```
                 alarm time or button press
   +--------+  ----------------------------->  +-----------+
   |  IDLE  |                                  | TRIGGERED |  "Scanning..." (up to 3 s)
   +--------+  <---+                           +-----------+
       ^           |                  all found /     \ still missing after 3 s
       |           |                           v       v
       |           |       +----------------------+   +---------------+
       |           +-------| ITEMS ACCOUNTED FOR  |<->| ITEMS MISSING |
       |  timer ends or    +----------------------+   +---------------+
       |  button press          (an item leaves or returns)      |
       +---------------------------------------------------------+
                         timer ends or button press
```

| State | LED strip | LCD | Ends when |
| --- | --- | --- | --- |
| Idle | Off | Item count, next alarm, "Press to scan" | An alarm time arrives, or the button is pressed |
| Triggered | Unchanged | "Scanning..." | All items found, or 3 seconds pass |
| Items missing | Fast red pulse | "N MISSING" and up to 3 items per page, e.g. "1/3 Pencil case" | All items found, the timer ends, or the button is pressed |
| Items accounted for | Slow green glow | Check-mark icon, "ALL ITEMS PRESENT", "10 of 10 found" | An item goes missing, the timer ends, or the button is pressed |
| Configuration | — | — | Not used in this prototype; see section 4 |

**Check length.** A check started by an alarm lasts 20 minutes. A check started by the button lasts 5 minutes. At the end the device returns to Idle.

**Missing list.** Missing items appear in alphabetical order, three per page. With more than three, the pages change every 3 seconds or longer, giving long names time to scroll. The header shows the page, e.g. "5 MISSING  pg 1/2".

**Button.** A press of up to 2 seconds starts a check from Idle, or ends the current check. Presses longer than 2 seconds are ignored.

**Detection.** An item counts as present if its tag was read in the last 2 seconds. During a check the device keeps scanning, so the screen updates as items are packed or taken out.

**Alarms during a check.** If an alarm time arrives while a check is already running, that alarm is skipped.

## 6. Demonstration

This script shows each state with the preset 10-item profile. It takes about 5 minutes.

1. Power on and wait for the Idle screen. Point out the item count and the next alarm.
2. Put all 10 tagged items within range of the reader.
3. Press the button. The LCD shows "Scanning...", then the strip glows green and the LCD shows the check mark with "ALL ITEMS PRESENT" and "10 of 10 found".
4. Remove two items and move them out of range. Within a few seconds the strip pulses red and the LCD lists both, e.g. "1/2 Laptop charger" and "2/2 Pencil case".
5. Remove three more items. The list now has five items over two pages; point out the page changes and a long name scrolling.
6. Put all five items back. The strip returns to green.
7. Press the button to end the check. The device returns to Idle.
8. Optional: show a scheduled check by stopping the application, adding an alarm two minutes ahead to `alarms.json` (section 4.4) and starting it again. At that time the check starts on its own.

## 7. Troubleshooting and maintenance

### Common problems

| Symptom | Likely cause | What to do |
| --- | --- | --- |
| LCD blank, LED off after 2 minutes | Application not running | `systemctl status rfid-checker`; check the logs |
| LCD lit but no text | Contrast too low | Turn the contrast screw on the LCD backpack |
| "0 in profile." | `items.json` missing or has a mistake | Check the logs for the reason; fix the file (section 4.2) |
| "No alarms set" | `alarms.json` missing or has a mistake | Check the logs; fix the file (section 4.4) |
| Every item always missing | Reader unplugged or not answering | Check the USB cable and `ls -l /dev/RFID_scanner` |
| One item comes and goes | Tag at the edge of range or blocked by metal or water | Move it closer; turn the tag so it faces the reader |
| Alarm at the wrong time | RTC time wrong or coin cell flat | `sudo hwclock -r`; replace the cell and set the clock (section 2.3) |
| Strip shows wrong colors | Strip uses a different color order | Change `pixel_order` in `peripherals/LED.py` |

### Logs

Show the application's messages live:

```
journalctl -u rfid-checker -f
```

### Shutting down

Shut down before unplugging, either from the desktop menu or with:

```
sudo shutdown -h now
```

Unplug when the Pi's green light stops flashing.

### Backup microSD card

The kit includes a second card with the same software. If the unit won't boot, power off, swap cards, and power on. Copy your current `items.json` and `alarms.json` onto the backup card if they've changed since delivery. To make a new backup, use the desktop's SD Card Copier with a USB card reader.

### Limitations

The prototype does not include, and won't do:

- Detect every tag every time. RFID reads depend on distance, tag direction, and nearby metal or water.
- Tell whether a tagged item is inside a bag or just near it.
- Name tags through any interface other than a directly connected keyboard.
- Connect to Wi-Fi, Bluetooth or any network, or offer a web interface.
- Set the time from any source other than the RTC, or change RTC settings through configuration.
- Sleep or low-power modes, geolocation or geofencing.
- A custom enclosure.

---

## Open items before delivery (internal – remove from the customer copy)

These are gaps between the statement of work and the current code.

1. **Preset profile has 4 items.** The SOW requires 10 tags configured; `items.json` has 4.
2. **Missing-item wording.** The SOW example is "Missing item 1 of 3: Pencil case"; the LCD shows "1/3 Pencil case" under a "3 MISSING" header. "Missing item 1 of 3:" fills a whole 20-character row, so the SOW wording would allow one item per page. Confirm with HATS that the short form is acceptable.
3. **No scan-to-name tool.** The SOW says items are assigned by scanning tags. Section 4.3 uses the reader bench test, which also changes the reader's power settings and prints test counts. A small `enroll.py` that prints one tag's EPC (or adds it to `items.json`) would match the SOW better.
4. **Configuration state isn't implemented.** The SOW says lists can't be modified in Idle. Today the files are read only at start-up, and the guide tells the user to stop the service first. Confirm that's acceptable or implement the state.
5. **Install steps are untested.** The pip list in section 2.2 is from the imports, not a clean install. Add a `requirements.txt` and test on a fresh card. `config_pb2.py` needs protobuf 7.35 or newer.
6. **RTC at boot.** The service starts after `local-fs.target` and doesn't wait for the RTC to set the system time. Add `After=time-sync.target` or a wait (from the code review).
7. **Alarm edge cases.** A daylight-saving change in the fall triggers a false check, and alarms can be skipped if the clock jumps (from the code review).
8. **Session lengths** (20 minutes after an alarm, 5 after a button press) aren't in the SOW. Confirm them with HATS.
9. **Backup card** still needs flashing and testing.
10. **Log messages** say "Button Long pressed" for what is now a short press (cosmetic, `State.py`).
