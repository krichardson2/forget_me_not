# RFID State manager

import time

from enum           import Enum
from collections    import deque
from pathlib        import Path


from peripherals    import *
from config_reader import read_items, read_alarms
from config_writer import write_items, write_alarms
from peripherals.uhf_reader import UHFReader

class State(Enum):
    CONFIGURATION       = 1
    IDLE                = 2
    TRIGGERED           = 3
    ITEMS_MISSING       = 4
    ITEMS_ACCOUNTED_FOR = 5

class StateManager():
    def __init__(self):
        #initial state for testing
        self._state = State.TRIGGERED 
        self._tags_seen = None
        self._freshScan = True

        #define manager's peripherals
        self.reader = UHFReader('/dev/cu.usbserial-21110')

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
        # self._state = state
        pass

    def scan(self):
        
        if self._freshScan:
            self._tags_seen = set()
            self._freshScan = False
        print(f"Seen: {self._tags_seen}")
        print(f"Expected: {tags_expected}")

        tags_current_read = self.reader.inventory()
        tags_expected = set(self.profile)

        self._tags_seen |= tags_current_read

        tags_missing = tags_expected - self._tags_seen

        if len(tags_missing) > 0:
            print(f"Items Missing: {tags_missing}")
            missing_names = sorted(profile[tag] for tag in missing)

            self.transition(State.ITEMS_MISSING)
        elif len(tags_missing) == 0:
            print("All items accounted for.\n")
            # Reload state variable for new check
            self._freshScan = True

            self.transition(State.ITEMS_ACCOUNTED_FOR)



    def check_triggers(self):
        # from trigger, start 20 minute timer for mode
        # from pushbutton, start 5 minute timer for trigger
        return [false, false]

    def check_peripherals(self):
        self.reader.check()
        self.screen.check()
        self.clock.check()

    def close(self):
        self.reader.close() # close serial conneciton to 
        # self.LCD_screen.close() # Close I2C bus 

def main():
    manager = StateManager()
    # manager.initalize_lists(items="/opt/item_list.json", alarms="/opt/alarm_list.json"

    try:
        while True:
            time.sleep(1)

            print(f"State: {manager.state}")
            if (manager.state == State.IDLE):
                """
                check for triggers
                """


                continue
            elif (manager.state == State.TRIGGERED):
                """
                Start timer for 20 minutes (Alarm) / 5 Minutes (Button)
                """
                manager.scan()
                
                continue
            elif (manager.state == State.ITEMS_MISSING):
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
                
                continue
            elif (manager.state == State.ITEMS_ACCOUNTED_FOR):
                """
                1. Start 5 minute timer
                2. Glow GREEN
                3. Display: "All Items Accounted for"
                4. After timer/button press, move back to IDLE
                """

                continue
            elif (manager.state == State.CONFIGURATION):
                
                continue



    
    except KeyboardInterrupt:
        manager.close()



if __name__ == "__main__":
    main()