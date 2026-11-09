import time

class Timer:
    def __init__(self):
        self._end = None

    def start(self, seconds):
        self._end = time.monotonic() + seconds

    def cancel(self):
        self._end = None

    @property
    def running(self):
        return self._end is not None and time.monotonic() < self._end

    @property
    def expired(self):
        return self._end is not None and time.monotonic() >= self._end

    @property
    def remaining(self):
        return max(0.0, self._end - time.monotonic()) if self._end else 0.0