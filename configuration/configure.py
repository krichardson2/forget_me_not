"""Build alarms.json and items.json from the terminal.

On the Pi, run configuration/configure.sh (or the desktop icon). It stops the app
so the reader is free, runs this script, then starts the app again. To run it by hand:
    sudo systemctl stop rfid-checker
    /home/pi/venv/bin/python configuration/configure.py
    sudo systemctl start rfid-checker
"""
import os
import select
import subprocess
import sys
import termios
import time
import tty
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR))      # so the configuration and peripherals packages import

from configuration.config_reader import MAX_ALARMS, MAX_ITEMS, TAG_PATTERN
from configuration.config_writer import write_alarms, write_items
from settings import CONFIGURE_TX_POWER_DBM as TX_POWER_DBM   # edit in settings.py

CONFIG_DIR = REPO_DIR                  # items.json and alarms.json live next to State.py
READER_DEV = "/dev/RFID_scanner"
SERVICE = "rfid-checker"

DIM, RESET, CLEAR_LINE = "\033[2m", "\033[0m", "\r\033[K"


def ask_yes(question):
    return input(f"{question} [y/N] ").strip().lower() in ("y", "yes")


def fmt_time(t):
    return f"{t[0]:02}:{t[1]:02}:{t[2]:02}"


# ---- alarms -------------------------------------------------------------------

def _digit_allowed(digits, ch):
    """Only accept digits that can still make a valid 24-hour time."""
    pos, d = len(digits), int(ch)
    if pos == 0:
        return d <= 2                          # hour tens: 0-2
    if pos == 1:
        return digits[0] != "2" or d <= 3      # 20-23
    if pos in (2, 4):
        return d <= 5                          # minute / second tens: 0-5
    return pos < 6


def _render_time(prompt, digits):
    """Typed digits replace the HH:MM:SS placeholder from left to right."""
    out, i = [], 0
    for ch in "HH:MM:SS":
        if ch == ":":
            out.append(":")
        elif i < len(digits):
            out.append(digits[i])
            i += 1
        else:
            out.append(f"{DIM}{ch}{RESET}")
            i += 1
    sys.stdout.write(CLEAR_LINE + prompt + "".join(out))
    sys.stdout.flush()


def read_time(prompt):
    """Read HH:MM:SS one key at a time. Returns (h, m, s), or None on an empty Enter."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    digits = []
    try:
        tty.setcbreak(fd)          # keys arrive one at a time; Ctrl+C still works
        _render_time(prompt, digits)
        while True:
            ch = sys.stdin.read(1)
            if ch in ("\r", "\n"):
                if not digits:
                    return None
                if len(digits) == 6:
                    return int("".join(digits[0:2])), int("".join(digits[2:4])), int("".join(digits[4:6]))
                sys.stdout.write("\a")             # incomplete time
            elif ch in ("\x7f", "\b"):
                if digits:
                    digits.pop()
            elif ch.isdigit() and len(digits) < 6 and _digit_allowed(digits, ch):
                digits.append(ch)
            else:
                sys.stdout.write("\a")
            _render_time(prompt, digits)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        print()


def configure_alarms():
    print(f"\nAlarms: up to {MAX_ALARMS}. Type the digits; press Enter on an empty time to finish.\n")
    alarms = []
    while len(alarms) < MAX_ALARMS:
        t = read_time(f"Enter Alarm #{len(alarms) + 1} in 24Hr time: ")
        if t is None:
            break
        if t in alarms:
            print(f"  {fmt_time(t)} is already set.")
            continue
        alarms.append(t)
    else:
        print(f"Maximum of {MAX_ALARMS} alarms reached.")

    if not alarms:
        print("No alarms entered; nothing saved.")
        return
    print(f"\nYou configured {len(alarms)} alarm(s):")
    for i, t in enumerate(sorted(alarms), start=1):
        print(f"  {i:2}. {fmt_time(t)}")
    path = CONFIG_DIR / "alarms.json"
    if ask_yes(f"\nSave these to {path.name}? This replaces the current file."):
        if write_alarms(alarms, path=str(path)):
            print(f"Saved {path}")
    else:
        print("Not saved.")


# ---- items --------------------------------------------------------------------

def _service_running():
    try:
        return subprocess.run(["systemctl", "is-active", "--quiet", SERVICE]).returncode == 0
    except FileNotFoundError:          # no systemd (e.g. testing on a laptop)
        return False


def _enter_pressed():
    """True if the user pressed Enter (consumes the line). Doesn't block."""
    if select.select([sys.stdin], [], [], 0)[0]:
        sys.stdin.readline()
        return True
    return False


def setup_reader(reader):
    """Send the same reader settings State.py uses. Returns (hardware version or None, warnings)."""
    from peripherals.uhf_reader import REGION_US
    version = reader.hardware_version()
    if version is None:
        return None, []
    checks = ((reader.set_region(REGION_US), "US region"),
              (reader.set_tx_power(TX_POWER_DBM), f"power {TX_POWER_DBM} dBm"),
              (reader.set_session(0, q=4), "session 0, Q=4"))
    return version, [f"the reader didn't confirm {label}" for ok, label in checks if not ok]


RECHECK_EVERY = 20     # empty scans in a row before checking the reader is still answering


def wait_for_single_tag(reader, named, setup=None):
    """Scan until exactly one new tag is in range. Returns its EPC, or None if Enter is pressed.

    `named` maps tags already named this session to their names. A tag is accepted only
    after two scans in a row see it and nothing else, so a second tag that reads only
    now and then isn't missed. After RECHECK_EVERY empty scans in a row, `setup(reader)`
    runs again, in case the reader reset or stopped answering.
    """
    history, status, scans, empty = [], None, 0, 0
    while True:
        if _enter_pressed():
            if status:
                print()
            return None
        history = (history + [reader.inventory(rounds=50, duration=0.25)])[-3:]   # same as State.py
        time.sleep(0.05)       # same gap as State.py's loop, so the reader finishes stopping
        scans += 1
        seen = set().union(*history)
        empty = 0 if history[-1] else empty + 1

        if not seen:
            msg = f"Waiting for a tag... (scan {scans})"   # the count shows it's still scanning
            if setup and empty >= RECHECK_EVERY:
                empty = 0
                version, warnings = setup(reader)
                if version is None:
                    msg = f"The reader isn't answering - unplug it and plug it back in (scan {scans})"
                elif warnings:
                    msg = f"Reader warning: {warnings[0]} (scan {scans})"
        elif len(seen) > 1:
            msg = f"{len(seen)} tags in range - move all but one away"
        else:
            tag = next(iter(seen))
            if tag in named:
                msg = f"That tag is already named \"{named[tag]}\" - bring a new tag"
            elif not TAG_PATTERN.match(tag):
                msg = f"Tag {tag} isn't a 96-bit (24-character) EPC and can't be used"
            elif len(history) >= 2 and all(h == {tag} for h in history[-2:]):
                if status:
                    print()
                return tag
            else:
                msg = "Tag found, checking it's the only one..."
        if msg != status:
            sys.stdout.write(CLEAR_LINE + "  " + msg)
            sys.stdout.flush()
            status = msg


def ask_name():
    """Ask for an item name in plain printable ASCII. Returns None if left blank (skip)."""
    while True:
        name = input("  Item name (blank to skip this tag): ").strip()
        if not name:
            return None
        if all(32 <= ord(c) < 127 for c in name):
            return name
        print("  Use regular characters only: letters, numbers, spaces and punctuation.")


def configure_items():
    if not os.path.exists(READER_DEV):
        print(f"\nRFID reader not found at {READER_DEV}.")
        print("Check that it's plugged in and that rules/99-rfid-scanner.rules is installed.")
        return
    if _service_running():
        print(f"\nThe {SERVICE} app is using the reader. Stop it first:")
        print(f"  sudo systemctl stop {SERVICE}")
        return

    from peripherals.uhf_reader import UHFReader   # needs pyserial; only for items
    reader = UHFReader(READER_DEV)
    items = []
    try:
        version, warnings = setup_reader(reader)
        if version is None:
            print(f"\nThe reader at {READER_DEV} isn't answering. Unplug it, plug it back in and try again.")
            return
        print(f"\nReader on {READER_DEV}: {version.strip() or 'connected'}")
        for w in warnings:
            print(f"  Warning: {w}.")

        print(f"\nItems: up to {MAX_ITEMS}. Press Enter at any time while scanning to finish.")
        while len(items) < MAX_ITEMS:
            print(f"\nItem #{len(items) + 1}: bring a single tag near the reader.")
            # The reader sat idle while the name was typed; send its settings again first
            for w in setup_reader(reader)[1]:
                print(f"  Warning: {w}.")
            tag = wait_for_single_tag(reader, dict(items), setup=setup_reader)
            if tag is None:
                break
            print(f"  Tag: {tag}")
            name = ask_name()
            if name is None:
                print("  Skipped.")
                continue
            items.append((tag, name))
            print(f"  Added \"{name}\". Move that tag away from the reader.")
        else:
            print(f"\nMaximum of {MAX_ITEMS} items reached.")
    finally:
        reader.close()

    if not items:
        print("No items entered; nothing saved.")
        return
    print(f"\nYou configured {len(items)} item(s):")
    for i, (tag, name) in enumerate(items, start=1):
        print(f"  {i:2}. {name:<24} {tag}")
    path = CONFIG_DIR / "items.json"
    if ask_yes(f"\nSave these to {path.name}? This replaces the current file."):
        if write_items(items, path=str(path)):
            print(f"Saved {path}")
    else:
        print("Not saved.")


def main():
    if not sys.stdin.isatty():
        sys.exit("Run this in a terminal.")
    try:
        while True:
            print("\nForget Me Not Pack - configuration")
            print("  1. Alarms")
            print("  2. Items")
            print("  q. Quit")
            choice = input("Choose: ").strip().lower()
            if choice == "1":
                configure_alarms()
            elif choice == "2":
                configure_items()
            elif choice in ("q", "quit", ""):
                break
        print(f"\nRestart the app to load your changes:  sudo systemctl start {SERVICE}")
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled. Nothing more was saved.")


if __name__ == "__main__":
    main()
