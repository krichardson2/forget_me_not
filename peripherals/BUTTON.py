import signal
import time
import queue

from gpiozero import Button

SHORT_MAX = 2.0
SHORT_MIN = 0.15

class Push_Button:
    def __init__(self, pin=23, bounce_time=0.05):
        self._button = Button(pin, pull_up=True, bounce_time=bounce_time, hold_time=5.0)
        self._pressed_at    = None
        self._held          = False
        self._button.when_pressed   = self._on_press
        self._button.when_released  = self._on_release
        self._button.when_held      = self._on_hold
        self._events = queue.Queue()

    def _on_press(self):
        self._pressed_at = time.monotonic()
        self._held = False

    # Hold for longer than HOLD_TIME seconds
    def _on_hold(self):
        self._held = True
        self._events.put("HOLD")

    # determine if button press is short or long
    def _on_release(self):
        if self._pressed_at is None or self._held:
            return
        duration = time.monotonic() - self._pressed_at
        self._pressed_at = None
        if duration >= SHORT_MIN:
            self._events.put("SHORT" if duration <= SHORT_MAX else "LONG")

    def get_event(self):
        try:
            return self._events.get_nowait()
        except queue.Empty:
            return None

    def clear(self):
        while self.get_event() is not None:
            pass
    @property
    def is_pressed(self):
        return self._button.is_pressed

    def close(self):
        self._button.close()


if __name__ == "__main__":
    button = Push_Button()

    try:
        while True:
            event = button.get_event()
            if event:
                print(f"Event: {event}")
                time.sleep(0.05)
    except KeyboardInterrupt:
        button.close()