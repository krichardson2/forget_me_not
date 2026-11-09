# RFID State manager

import time

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
# from peripherals.lcd_screen  import LCD_screen
# from peripherals.clock       import Clock
# from peripherals.push_button import PushButton

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
        self._state = State.TRIGGERED 
        self._tags_seen = None
        self._freshScan = True
        self._triggers = (False, False) # Alarm, Button

        #define manager's peripherals
        self.reader = UHFReader('/dev/RFID_scanner')
        self.led = LED_strip()
        self.led.off()
        self.timer = Timer()
        #self.screen = LCD_screen()
        #self.clock = Clock()
        #self.button = PushButton()

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
        
        self._presence = PresenceTracker(self.profile, window=5.0)

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
        self._presence.update(self.reader.inventory(rounds=50, duration=0.5))
        return self._presence.missing()

        """
        # at the start of a new scan, start with a fresh set of tags seen
        if self._freshScan:
            self._tags_seen = set()
            self._freshScan = False
        tags_expected = set(self.profile)
        tags_current_read = self.reader.inventory(rounds=50, duration=0.5)

        print(f"Expected:\t{tags_expected}")
        print(f"Seen:\t{tags_current_read}")

        self._tags_seen |= tags_current_read

        tags_missing = tags_expected - self._tags_seen

        # Let's do some better logic here. Should not just be binary each scan,
        # but rather, keep track of last seen time.


        if len(tags_missing) > 0:
            print(f"Items Missing: {tags_missing}")
            missing_names = sorted(self.profile[tag] for tag in tags_missing)
            print(f"Missing Names: {missing_names}")
            self.transition(State.ITEMS_MISSING)
        elif len(tags_missing) == 0:
            print("All items accounted for.\n")
            # Reload state variable for new check
            self._freshScan = True
            self.transition(State.ITEMS_ACCOUNTED_FOR)
        return
        """

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
        if self.button.short_pressed:
            return False, True
        return False, False

    def check_peripherals(self):
        self.reader.check()
        self.screen.check()
        self.clock.check()

    def close(self):
        self.reader.close() # close serial connection to 
        self.timer.cancel() # cancel any running timers
        self.led.off()      # turn off LED strip

        # self.LCD_screen.close() # Close I2C bus 

    def run(self):
        while True:
            time.sleep(1)

            if (self.state == State.IDLE):
                """
                check for triggers
                """

                self._triggers = self.check_triggers()


                continue
            elif (self.state == State.TRIGGERED):
                """
                Start timer for 20 minutes (Alarm) / 5 Minutes (Button)
                """
                self._presence.reset()
                # if triggered by alarm, start 20 minute timer
                if self._triggers[0]:
                    self.timer.start(20*60)
                # else if triggered by button, start 5 minute timer
                elif self._triggers[1]:
                    self.timer.start(5*60)
                

                self.missing_items = self.scan()
                print(f"Missing: {self.missing_items}")
                
                if len(self.missing_items) > 0:
                    self.transition(State.ITEMS_MISSING)
                else:
                    self.transition(State.ITEMS_ACCOUNTED_FOR)
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

                if (len(self.missing_items) == 0):
                    self.transition(State.ITEMS_ACCOUNTED_FOR)

                # exit this state if time's up or button pressed
                if self.timer.expired: # or self.button.pressed:
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
                    self.transition(State.ITEMS_ACCOUNTED_FOR)
                else:
                    self.transition(State.ITEMS_MISSING)
                # exit this state if time's up or button pressed
                if self.timer.expired: # or self.button.pressed:
                    self.transition(State.IDLE)
                continue
            elif (self.state == State.CONFIGURATION):
                """
                This is lower priority, so it will be implemented later.
                """
                continue

def main():
    manager = StateManager()
    try:
        manager.run()
    except KeyboardInterrupt:
        manager.close()

if __name__ == "__main__":
    main()