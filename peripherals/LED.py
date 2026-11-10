

"""
LED strip driver: WS2812B, 40 LEDs, Raspberry Pi 3B+.

Development wiring (strip powered from the Pi):
    strip red   -> Pi 5V   (physical pin 2)
    strip white -> Pi GND  (physical pin 6)
    strip green -> 330 ohm resistor -> GPIO18 (physical pin 12)

Setup:
    pip install adafruit-circuitpython-neopixel
    Add 'dtparam=audio=off' to /boot/firmware/config.txt (audio shares GPIO18's PWM)
    Run as root:  sudo ./venv/bin/python LED.py
"""

import math
import threading
import time

import board
import neopixel

NUM_LEDS = 40

# Hard cap so full white stays around 0.4 A, which the Pi's 5V rail can supply.
# Raise this only once the strip has its own power supply.
MAX_BRIGHTNESS = 0.15

FAST_PERIOD = 0.8   # seconds per full breath, dim -> bright -> dim (Items Missing)
SLOW_PERIOD = 3.0   # seconds per full breath (Items Accounted For)
FADE_TIME = 0.5     # seconds to fade out (and to fade in for solid colors)
FRAME_TIME = 0.02   # 50 updates per second keeps fades smooth
GAMMA = 2.2         # eyes see brightness non-linearly; this makes fades look even

# Colors are (red, green, blue), each 0-255.
WHITE = (255, 255, 255)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
OFF = (0, 0, 0)


def _scale(color, level):
    return tuple(round(c * level) for c in color)


class LED_strip():

    def __init__(self, pin=board.D18, num_leds=NUM_LEDS, brightness=MAX_BRIGHTNESS):
        self._pixels = neopixel.NeoPixel(
            pin, num_leds,
            brightness=min(brightness, MAX_BRIGHTNESS),
            auto_write=False,
            pixel_order=neopixel.GRB,  # WS2812B; if red shows as green, try RGB
        )
        self._stop = threading.Event()
        self._thread = None
        self._current = OFF       # what the strip is showing right now
        self._show(OFF)           # start dark immediately, no fade
        self._mode = ("off",)
        
    # ---- public API (all calls return immediately; effects run in the background)

    def solid(self, color=WHITE):
        """Fade out whatever is showing, then fade in to a steady color."""
        self._start(("solid", color), self._solid_loop, color)

    def breathe_fast(self, color=WHITE):
        """Fade out whatever is showing, then breathe quickly (Items Missing)."""
        self._start(("fast", color), self._breathe_loop, FAST_PERIOD, color)

    def breathe_slow(self, color=WHITE):
        """Fade out whatever is showing, then breathe slowly (Items Accounted For)."""
        self._start(("slow", color), self._breathe_loop, SLOW_PERIOD, color)

    def off(self):
        """Fade from whatever is showing to off."""
        self._start(("off",), self._fade_out)

    def close(self):
        """Fade to off (waits for the fade to finish), then release the pin."""
        self._stop_thread()
        self._fade_out()
        self._pixels.deinit()

    # ---- internals --------------------------------------------------------

    def _show(self, color):
        self._pixels.fill(color)
        self._pixels.show()
        self._current = color

    def _start(self, mode, target, *args):
        if self._mode == mode:
            return  # already running this effect; don't restart it
        self._stop_thread()
        self._mode = mode
        self._thread = threading.Thread(target=target, args=args, daemon=True)
        self._thread.start()

    def _stop_thread(self):
        """Interrupt the running effect, leaving its last frame on the strip."""
        if self._thread is not None and self._thread.is_alive():
            self._stop.set()
            self._thread.join()
        self._thread = None
        self._stop.clear()

    def _fade_out(self):
        """Fade from the current output to off. Returns False if interrupted."""
        start_color = self._current
        if start_color == OFF:
            return True
        t0 = time.monotonic()
        while not self._stop.is_set():
            t = (time.monotonic() - t0) / FADE_TIME
            if t >= 1:
                self._show(OFF)
                return True
            self._show(_scale(start_color, (1 - t) ** GAMMA))
            self._stop.wait(FRAME_TIME)
        return False  # a new effect took over mid-fade; it fades from here

    def _solid_loop(self, color):
        if not self._fade_out():
            return
        t0 = time.monotonic()
        while not self._stop.is_set():
            t = (time.monotonic() - t0) / FADE_TIME
            if t >= 1:
                self._show(color)
                return
            self._show(_scale(color, t ** GAMMA))
            self._stop.wait(FRAME_TIME)

    def _breathe_loop(self, period, color):
        if not self._fade_out():
            return
        start = time.monotonic()
        while not self._stop.is_set():
            phase = ((time.monotonic() - start) % period) / period  # 0.0 -> 1.0
            level = (1 - math.cos(2 * math.pi * phase)) / 2          # 0 -> 1 -> 0
            self._show(_scale(color, level ** GAMMA))
            self._stop.wait(FRAME_TIME)
        # No final "off" here: the next effect fades out from the last frame.


if __name__ == "__main__":
    strip = LED_Strip()
    try:
        print("Fast breathing, red, for 4 s")
        strip.breathe_fast(RED)
        time.sleep(4)
        print("Fade to slow breathing, green, for 6 s")
        strip.breathe_slow(GREEN)
        time.sleep(6)
        print("Fade to solid blue for 3 s")
        strip.solid(BLUE)
        time.sleep(3)
        print("Fade to off")
        strip.off()
        time.sleep(1)
    finally:
        strip.close()