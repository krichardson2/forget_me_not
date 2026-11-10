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

class StateManager():
    def __init__(self):
        #initial state for testing
        self._state = State.IDLE 
        self._tags_seen = None
        self._freshScan = True
        self._triggers = (False, True) # Alarm, Button
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
        if self.items_list is None:
            print("Items List Empty.")
        else:
            print("Items List: ")
            self.profile = {item.tag: item.name for item in self.items_list.items} 
            # pretty print
            for ind,item in enumerate(self.items_list.items):
                print(f"\t{ind} : {item.name}\t|\t{item.tag}")
        
        self._presence = PresenceTracker(self.profile, window=2.0)

        # Read in alarms
        alarms = read_alarms(path="alarms.json")
        if alarms is None:
            print("Alarms list could not be loaded.")
            self.alarms_list = deque()
        else:
            self.alarms_list = deque(sorted(alarms.alarms,
                                        key=lambda a: (a.hour, a.minute, a.second)))

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

    def check_triggers(self):
        # from trigger, start 20 minute timer for mode
        # from pushbutton, start 5 minute timer for trigger
        if len(self.alarms_list) > 0:
            now = time.localtime()
            for alarm in self.alarms_list:
                if (alarm.hour == now.tm_hour and
                    alarm.minute == now.tm_min and
                    alarm.second == now.tm_sec):
                    return True, False
        if self.button.get_event() == "SHORT":
            return False, True
        return False, False

    def check_peripherals(self):
        self.reader.check()
        self.screen.check()
        self.clock.check()

    def close(self):
        self.reader.close() # close serial connection to 
        self.timer.cancel() # cancel any running timers
        self.lcd.close()
        self.led.close()      # turn off LED strip

        # self.LCD_screen.close() # Close I2C bus 

    def run(self):
        """
        Super loop of the application
        """
        while True:
            time.sleep(0.2)

            if (self.state == State.IDLE):
                """
                check for triggers
                """
                self.led.off()
                self._triggers = self.check_triggers()
                self.lcd.show_idle(len(self.profile))
        
                ## TODO: Still need to rotate after alarms fire
                
                if any(self._triggers):
                    self.transition(State.TRIGGERED)
                continue
            elif (self.state == State.TRIGGERED):
                """
                Start timer for 20 minutes (Alarm) / 5 Minutes (Button)
                """
                self._presence.reset()
                # if triggered by alarm, start 20 minute timer
                if self._trigger_deadline is None:
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
                if not self.missing_items:
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

                missing_names = (self.profile[tag] for tag in self.missing_items)
                self.lcd.show_missing(missing_names)

                if (len(self.missing_items) == 0):
                    self.transition(State.ITEMS_ACCOUNTED_FOR)
                    print("No items missing, moving to ITEMS_ACCOUNTED_FOR state.")
                # exit this state if time's up or button pressed
                if self.timer.expired: 
                    print("Timer expired, moving to IDLE state.")
                    self.transition(State.IDLE)
                if self.button.get_event() == "LONG":
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
                if self.button.get_event() == "LONG":
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