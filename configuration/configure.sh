#!/bin/bash
cd /home/pi/rfid-item-check
sudo systemctl stop rfid-checker      # frees the RFID reader; the LCD and LEDs go dark
# Start the app again however this script ends, including Ctrl+C or closing the window
trap 'sudo systemctl start rfid-checker' EXIT
/home/pi/venv/bin/python configuration/configure.py
read -rp "Done. Press Enter to close this window."
