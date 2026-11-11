"""Generate the wiring diagram for the RFID item checker (Raspberry Pi 3B+).

Run:  python docs/wiring_diagram.py   ->  writes docs/wiring.svg

The Pi 3B+ has the same 40-pin header as the Pi 4, so the Pi 4 board layout is used.
"""
from pathlib import Path

from pinviz import (boards, devices, Component, ComponentType, Connection,
                    Device, DevicePin, Diagram, PinRole, Point, SVGRenderer)

registry = devices.get_registry()

# WS2812B strip (40 LEDs), see peripherals/LED.py
led_strip = Device(
    name="WS2812B Strip",
    pins=[
        DevicePin("5V", PinRole.POWER_5V, Point(5, 10)),
        DevicePin("DIN", PinRole.PWM, Point(5, 20)),
        DevicePin("GND", PinRole.GROUND, Point(5, 30)),
    ],
    height=40,
    color="#2E7D32",
    description="40x WS2812B NeoPixel strip",
)

# 20x4 character LCD with PCF8574 I2C backpack at 0x27, see peripherals/LCD.py
lcd = registry.create("lcd1602")
lcd.name = "LCD 20x4"
for pin in lcd.pins:          # this LCD runs from 3.3V, not the template's 5V
    if pin.name == "VCC":
        pin.role = PinRole.POWER_3V3

# DS3231 RTC at 0x68 on the same I2C bus
rtc = registry.create("ds3231")

# Push button on GPIO23 with the internal pull-up, see peripherals/BUTTON.py
button = registry.create("button")
button.name = "Push Button"

# UHF RFID reader: plugged into a USB port (CH340, /dev/RFID_scanner), not the header
rfid = Device(
    name="UHF RFID Reader",
    pins=[DevicePin("USB", PinRole.GPIO, Point(5, 10))],
    height=20,
    color="#757575",
    description="YRM100 (M100) over USB, not on the GPIO header",
)

connections = [
    # LED strip
    Connection(2, "WS2812B Strip", "5V"),
    Connection(12, "WS2812B Strip", "DIN",
               components=[Component(ComponentType.RESISTOR, "330Ω")]),   # GPIO18
    Connection(6, "WS2812B Strip", "GND"),

    # LCD (I2C)
    Connection(1, "LCD 20x4", "VCC"),     # 3.3V
    Connection(9, "LCD 20x4", "GND"),
    Connection(3, "LCD 20x4", "SDA"),     # GPIO2
    Connection(5, "LCD 20x4", "SCL"),     # GPIO3

    # RTC (I2C, shares SDA/SCL with the LCD)
    Connection(17, "DS3231 RTC", "VCC"),  # 3.3V
    Connection(39, "DS3231 RTC", "GND"),
    Connection(3, "DS3231 RTC", "SDA"),
    Connection(5, "DS3231 RTC", "SCL"),

    # Push button
    Connection(16, "Push Button", "SIG"),  # GPIO23
    Connection(14, "Push Button", "GND"),
]

board = boards.raspberry_pi_4()
board.name = "Raspberry Pi 3 Model B+"   # same 40-pin header as the Pi 4

diagram = Diagram(
    title="RFID Item Checker - Raspberry Pi 3B+",
    board=board,
    devices=[led_strip, lcd, rtc, button, rfid],
    connections=connections,
)

out = Path(__file__).with_name("wiring.svg")
SVGRenderer().render(diagram, str(out))
print(f"Wrote {out}")
