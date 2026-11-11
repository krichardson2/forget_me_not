#!/bin/bash
cd /home/pi/rfid-item-check
sudo systemctl stop rfid-checker      # frees the RFID reader; the LCD and LEDs go dark
/home/pi/venv/bin/python configuration/configure.py
sudo systemctl start rfid-checker     # reloads items.json and alarms.json
read -rp "Done. Press Enter to close this window."
