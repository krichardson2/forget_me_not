"""Validate and save the item and alarm lists to JSON files."""
import os
import sys
import tempfile

from google.protobuf import json_format

from . import config_pb2
from .config_reader import validate_alarms, validate_items


def _error(msg):
    print(f"ERROR: {msg}", file=sys.stderr)


def _to_json(message):
    # Keep zero values (e.g. hour 0) in the file so it stays readable.
    try:
        return json_format.MessageToJson(
            message, preserving_proto_field_name=True,
            always_print_fields_with_no_presence=True)
    except TypeError:  # protobuf older than 26.x uses the old argument name
        return json_format.MessageToJson(
            message, preserving_proto_field_name=True,
            including_default_value_fields=True)


def _save(message, path):
    """Write atomically: a power cut leaves either the old file or the new one."""
    directory = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(directory):
        _error(f"directory {directory} does not exist")
        return False
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(_to_json(message) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except OSError as e:
        _error(f"could not write {path}: {e}")
        if tmp and os.path.exists(tmp):
            os.remove(tmp)
        return False
    return True


def write_items(items, path="items.json"):
    """items: list of (tag, name) pairs. Returns True on success."""
    item_list = config_pb2.ItemList()
    for tag, name in items:
        item_list.items.add(tag=str(tag).strip().upper(), name=str(name).strip())
    errors = validate_items(item_list)
    if errors:
        for err in errors:
            _error(f"{path} not written: {err}")
        return False
    return _save(item_list, path)


def write_alarms(alarms, path="alarms.json"):
    """alarms: list of (hour, minute, second) tuples. Returns True on success."""
    alarm_list = config_pb2.AlarmList()
    try:
        for hour, minute, second in alarms:
            alarm_list.alarms.add(hour=hour, minute=minute, second=second)
    except (TypeError, ValueError) as e:  # e.g. negative or non-integer values
        _error(f"{path} not written: invalid alarm value ({e})")
        return False
    errors = validate_alarms(alarm_list)
    if errors:
        for err in errors:
            _error(f"{path} not written: {err}")
        return False
    return _save(alarm_list, path)


if __name__ == "__main__":
    ok_items = write_items([
        ("E28011B0A506007F786F06B1", "Manila Folder"),
        ("E28011B0A506007F786F06B2", "Laptop Charger"),
    ])
    ok_alarms = write_alarms([
        (7, 30, 0),
        (17, 0, 0),
    ])
    if ok_items and ok_alarms:
        print("Wrote items.json and alarms.json")
    sys.exit(0 if ok_items and ok_alarms else 1)
