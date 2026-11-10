"""Load and validate the item and alarm lists from JSON files."""
import os
import re
import sys

from google.protobuf import json_format

import config_pb2

MAX_ITEMS = 50
MAX_ALARMS = 10
TAG_PATTERN = re.compile(r"^[0-9A-F]{24}$")  # 96-bit EPC, uppercase hex


def _error(msg):
    print(f"ERROR: {msg}", file=sys.stderr)


def validate_items(item_list):
    """Return a list of problems with an ItemList (empty list = valid)."""
    errors = []
    if len(item_list.items) > MAX_ITEMS:
        errors.append(f"{len(item_list.items)} items exceeds the limit of {MAX_ITEMS}")
    seen = set()
    for i, item in enumerate(item_list.items, start=1):
        if not TAG_PATTERN.match(item.tag):
            errors.append(f"item {i}: tag '{item.tag}' must be 24 hex characters (0-9, A-F)")
        elif item.tag in seen:
            errors.append(f"item {i}: duplicate tag {item.tag}")
        seen.add(item.tag)
        if not item.name:
            errors.append(f"item {i}: name must not be empty")
        elif not all(32 <= ord(c) < 127 for c in item.name):
            errors.append(f"item {i}: name '{item.name}' must use plain ASCII characters")
    return errors


def validate_alarms(alarm_list):
    """Return a list of problems with an AlarmList (empty list = valid)."""
    errors = []
    if len(alarm_list.alarms) > MAX_ALARMS:
        errors.append(f"{len(alarm_list.alarms)} alarms exceeds the limit of {MAX_ALARMS}")
    seen = set()
    for i, a in enumerate(alarm_list.alarms, start=1):
        if a.hour > 23 or a.minute > 59 or a.second > 59:
            errors.append(f"alarm {i}: {a.hour}:{a.minute}:{a.second} is not a valid 24-hour time")
        elif (a.hour, a.minute, a.second) in seen:
            errors.append(f"alarm {i}: duplicate time {a.hour:02}:{a.minute:02}:{a.second:02}")
        seen.add((a.hour, a.minute, a.second))
    return errors


def _load(path, message, validator):
    if not os.path.isfile(path):
        _error(f"{path} not found")
        return None
    try:
        with open(path, encoding="utf-8") as f:
            json_format.Parse(f.read(), message)
    except (OSError, UnicodeDecodeError) as e:
        _error(f"could not read {path}: {e}")
        return None
    except json_format.ParseError as e:
        _error(f"{path} is not valid: {e}")
        return None
    errors = validator(message)
    if errors:
        for err in errors:
            _error(f"{path}: {err}")
        return None
    return message


def read_items(path="items.json"):
    """Return an ItemList, or None if the file is missing or invalid."""
    return _load(path, config_pb2.ItemList(), validate_items)


def read_alarms(path="alarms.json"):
    """Return an AlarmList, or None if the file is missing or invalid."""
    return _load(path, config_pb2.AlarmList(), validate_alarms)


if __name__ == "__main__":
    items = read_items()
    alarms = read_alarms()

    if items is not None:
        print(f"{len(items.items)} item(s):")
        for item in items.items:
            print(f"  {item.tag}  {item.name}")
    if alarms is not None:
        print(f"{len(alarms.alarms)} alarm(s):")
        for a in alarms.alarms:
            print(f"  {a.hour:02}:{a.minute:02}:{a.second:02}")

    sys.exit(0 if items is not None and alarms is not None else 1)
