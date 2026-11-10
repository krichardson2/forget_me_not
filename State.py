# RFID State manager

import time
import signal

from enum           import Enum
from collections    import deque
from pathlib        import Path


from peripherals            import *
from config_reader          import read_items, read_alarms
from config_writer          import write_items, write_alarms
from peripherals.uhf_reader import UHFReader
from peripherals.LED        import LED_strip, RED, GREEN, BLUE, WHITE, OFF
from peripherals.TIMER      import Timer
from peripherals.PRESENCE   import PresenceTracker
from peripherals.BUTTON     import Push_Button
from peripherals.LCD  import LCD_screen
# from peripherals.clock       import Clock

class State(Enum):
    CONFIGURATION       = 1
    IDLE                = 2
    TRIGGERED           = 3
    ITEMS_MISSING       = 4
    ITEMS_ACCOUNTED_FOR = 5

class Trigger(Enum):
    ALARM  = 1
    BUTTON = 2


def _seconds(alarm):
    """Seconds since midnight for an alarm (has .hour, .minute, .second)."""
    return alarm.hour * 3600 + alarm.minute * 60 + alarm.second

def _now_seconds():
    """Seconds since midnight right now, local time (set from the RTC at boot)."""
    t = time.localtime()
    return t.tm_hour * 3600 + t.tm_min * 60 + t.tm_sec


class StateManager():
    def __init__(self):
        #initial state
        self._state = State.IDLE
        self._tags_seen = None
        self._freshScan = True
        self._triggers = (False, False) # Alarm, Button
        self._trigger_deadline = None

        #define manager's peripherals
        self.reader = UHFReader('/dev/RFID_scanner')
        self.reader.set_region(0x02) # US region
        self.reader.set_tx_power(20)
        self.reader.set_session(0, q=4)
        self.led = LED_strip()
        self.led.off()
        self.timer = Timer()
        self.lcd = LCD_screen()
        #self.clock = Clock()
        self.button = Push_Button()

        # Read in items list
        self.items_list = read_items(path="items.json")
        self.profile = {}
        if self.items_list is None:
            print("Items list could not be loaded.")
        else:
            print("Items List: ")
            self.profile = {item.tag: item.name for item in self.items_list.items}
            # pretty print
            for ind,item in enumerate(self.items_list.items):
                print(f"\t{ind} : {item.name}\t|\t{item.tag}")

        self._presence = PresenceTracker(self.profile, window=3.0)

        # Read in alarms
        alarms = read_alarms(path="alarms.json")
        if alarms is None:
            print("Alarms list could not be loaded.")
            self.alarms_list = deque()
        else:
            self.alarms_list = deque(sorted(alarms.alarms,
                                        key=lambda a: (a.hour, a.minute, a.second)))

        # Rotate so the front of the deque is the next alarm still to come today
        # (if they've all passed, the earliest one, which is tomorrow's first)
        self._last_alarm_check = _now_seconds()
        for _ in range(len(self.alarms_list)):
            if _seconds(self.alarms_list[0]) > self._last_alarm_check:
                break
            self.alarms_list.rotate(-1)
        if self.alarms_list:
            a = self.alarms_list[0]
            print(f"Next alarm: {a.hour:02}:{a.minute:02}:{a.second:02}")

    @property
    def state(self):
        return self._state

    def transition(self, state):
        # if state valid, set it
        if state in State:
            self._state = state
        else:
            print(f"Invalid state transition attempted: {state}")


    def scan(self):
        """
        Scan for items and check against expected list.
        """
        self._presence.update(self.reader.inventory(rounds=50, duration=1.0))
        return self._presence.missing()

    def check_alarm(self):
        """
        True if the next alarm's time was crossed since the last check.
        Fired alarms rotate to the back, so alarms_list[0] is always the next one.
        Checks for crossing (not an exact second match), so a slow loop pass
        can't skip over an alarm.
        """
        if not self.alarms_list:
            return False
        now = _now_seconds()
        last, self._last_alarm_check = self._last_alarm_check, now

        def crossed(alarm):
            t = _seconds(alarm)
            if last <= now:
                return last < t <= now
            return t > last or t <= now        # midnight passed between checks

        fired = False
        for _ in range(len(self.alarms_list)):
            if not crossed(self.alarms_list[0]):
                break
            self.alarms_list.rotate(-1)
            fired = True
        return fired

    def check_triggers(self, alarm_fired):
        # alarm -> 20 minute session, pushbutton -> 5 minute session
        if alarm_fired:
            return True, False
        if self.button.get_event() == "SHORT":
            return False, True
        return False, False

    def close(self):
        # Close each device even if another one fails to close
        for name, closer in (("LED", self.led.close), ("reader", self.reader.close),
                             ("LCD", self.lcd.close), ("timer", self.timer.cancel)):
            try:
                closer()
            except Exception as e:
                print(f"Error closing {name}: {e}")

    def run(self):
        """
        Super loop of the application
        """
        while True:
            time.sleep(0.2)

            # Check every pass so the deque keeps rotating and an alarm that passes
            # outside Idle doesn't fire late when the device returns to Idle.
            alarm_fired = self.check_alarm()
            if alarm_fired and self.state != State.IDLE:
                print("Alarm time reached outside Idle; skipped.")

            if (self.state == State.IDLE):
                """
                check for triggers
                """
                self.led.off()
                self._triggers = self.check_triggers(alarm_fired)
                next_alarm = self.alarms_list[0] if self.alarms_list else None
                self.lcd.show_idle(len(self.profile), next_alarm)

                if any(self._triggers):
                    self.transition(State.TRIGGERED)
                continue
            elif (self.state == State.TRIGGERED):
                """
                Start timer for 20 minutes (Alarm) / 5 Minutes (Button)
                """
                # First pass of a new check: set it up once
                if self._trigger_deadline is None:
                    self._presence.reset()
                    # if triggered by alarm, start 20 minute timer
                    if self._triggers[0]:
                        self._triggers = (False, False)
                        print("Triggered by Alarm, starting 20 minute timer.")
                        self.timer.start(20*60)
                    # else if triggered by button, start 5 minute timer
                    elif self._triggers[1]:
                        self._triggers = (False, False)
                        print("Triggered by Button, starting 5 minute timer.")
                        self.timer.start(5*60)
                    self._trigger_deadline = time.monotonic() + 3.0

                self.missing_items = self.scan()
                if self.missing_items:
                    print(f"Missing: {self.missing_items}")

                if len(self.missing_items) == 0:
                    self._trigger_deadline = None
                    self.transition(State.ITEMS_ACCOUNTED_FOR)
                elif time.monotonic() >= self._trigger_deadline:
                    self._trigger_deadline = None
                    self.transition(State.ITEMS_MISSING)
                continue
            elif (self.state == State.ITEMS_MISSING):
                """
                New Loop
                1. continue Scanning for items,
                2. Print missing items with ID# to display
                    2/ items missing:
                        1/2: Notebook
                        2/2: Pencil Case
                3. Flash RED LED Strip
                4. If all items found, move back to IDLE
                5. If button pressed, move back to IDLE
                """
                self.led.breathe_fast(RED)
                self.missing_items = self.scan()

                missing_names = sorted(self.profile[tag] for tag in self.missing_items)
                self.lcd.show_missing(missing_names)

                if (len(self.missing_items) == 0):
                    self.transition(State.ITEMS_ACCOUNTED_FOR)
                    print("No items missing, moving to ITEMS_ACCOUNTED_FOR state.")
                # exit this state if time's up or button pressed
                if self.timer.expired:
                    print("Timer expired, moving to IDLE state.")
                    self.transition(State.IDLE)
                if self.button.get_event() == "SHORT":
                    print("Button Long pressed, moving to IDLE state.")
                    self.transition(State.IDLE)
                continue
            elif (self.state == State.ITEMS_ACCOUNTED_FOR):
                """
                1. Start 5 minute timer
                2. Glow GREEN
                3. Display: "All Items Accounted for"
                4. After timer/button press, move back to IDLE
                """
                self.led.breathe_slow(GREEN)
                self.missing_items = self.scan()
                if (len(self.missing_items) == 0):
                    self.lcd.show_all_items_clear(len(self.profile))
                    self.transition(State.ITEMS_ACCOUNTED_FOR)
                else:
                    self.transition(State.ITEMS_MISSING)
                # exit this state if time's up or button pressed
                if self.timer.expired:
                    print("Timer expired, moving to IDLE state.")
                    self.transition(State.IDLE)
                if self.button.get_event() == "SHORT":
                    print("Button Long pressed, moving to IDLE state.")
                    self.transition(State.IDLE)
                continue

            elif (self.state == State.CONFIGURATION):
                """
                This is lower priority, so it will be implemented later.
                """
                continue

def _stop(signum, frame):
    raise KeyboardInterrupt

def main():
    # systemd stop/shutdown (SIGTERM) and a closed SSH session (SIGHUP) clean up like Ctrl+C
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGHUP, _stop)
    manager = StateManager()
    try:
        manager.run()
    except KeyboardInterrupt:
        print("\nClosing manager.\n")
    finally:
        signal.signal(signal.SIGINT, signal.SIG_IGN)   # a second Ctrl+C can't interrupt cleanup
        manager.close()

if __name__ == "__main__":
    main()