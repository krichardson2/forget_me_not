"""Debounces RFID reads: an item counts as present if seen within the last `window` seconds."""
import time


class PresenceTracker:
    def __init__(self, tags, window=3.0):
        """tags: any iterable of expected tags (a list, set, or the {tag: name} profile dict)."""
        self.window = window
        self.last_seen = {tag: None for tag in tags}

    def update(self, seen):
        """Record a read cycle's results. Tags not in the profile are ignored."""
        now = time.monotonic()
        for tag in seen & self.last_seen.keys():
            self.last_seen[tag] = now

    def missing(self):
        """Return the set of expected tags not seen within the window."""
        now = time.monotonic()
        return {tag for tag, t in self.last_seen.items()
                if t is None or now - t > self.window}

    def reset(self):
        """Forget all sightings (call at the start of each new check)."""
        self.last_seen = dict.fromkeys(self.last_seen)