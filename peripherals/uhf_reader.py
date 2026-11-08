"""
Minimal driver for MagicRF M100-based UHF RFID readers (YRM100 series).

Frame format:  BB | Type | Cmd | Len(2, big-endian) | Payload | Checksum | 7E
Checksum = low byte of the sum of Type..end of Payload.

Verify command codes and the region code against your module's protocol
document before relying on this.

Requires: pyserial  (apt: python3-serial)
"""
import time

import serial

HEADER = 0xBB
END = 0x7E

CMD_HW_VERSION = 0x03
CMD_SET_REGION = 0x07
CMD_SINGLE_POLL = 0x22
CMD_MULTI_POLL = 0x27
CMD_STOP_POLL = 0x28

TYPE_RESPONSE = 0x01
TYPE_NOTICE = 0x02  # tag data arrives in notice frames

REGION_US = 0x02  # 902-928 MHz (confirm in your protocol doc)


def build_frame(cmd, payload=b""):
    body = bytes([0x00, cmd]) + len(payload).to_bytes(2, "big") + payload
    return bytes([HEADER]) + body + bytes([sum(body) & 0xFF, END])


class UHFReader:
    def __init__(self, port="/dev/ttyUSB0", baud=115200, timeout=0.05):
        self.ser = serial.Serial(port, baud, timeout=timeout)

    def close(self):
        self.ser.close()

    # ---- low-level framing ------------------------------------------------

    def _read_frames(self, duration):
        """Yield valid frames received within `duration` seconds."""
        buf = bytearray()
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            buf += self.ser.read(self.ser.in_waiting or 1)
            while True:
                start = buf.find(HEADER)
                if start < 0:
                    buf.clear()
                    break
                if len(buf) < start + 5:  # need header through length bytes
                    del buf[:start]
                    break
                length = int.from_bytes(buf[start + 3:start + 5], "big")
                end = start + 5 + length + 2
                if len(buf) < end:  # frame not complete yet
                    del buf[:start]
                    break
                frame = bytes(buf[start:end])
                if frame[-1] == END and (sum(frame[1:-2]) & 0xFF) == frame[-2]:
                    del buf[:end]
                    yield frame
                else:
                    del buf[:start + 1]  # bad frame; resync on next 0xBB

    def _command(self, cmd, payload=b"", wait=0.3):
        """Send a command and return the payload of its response frame."""
        self.ser.reset_input_buffer()
        self.ser.write(build_frame(cmd, payload))
        for frame in self._read_frames(wait):
            if frame[1] == TYPE_RESPONSE and frame[2] == cmd:
                return frame[5:-2]
        return None

    # ---- commands ---------------------------------------------------------

    def hardware_version(self):
        payload = self._command(CMD_HW_VERSION, b"\x00")
        return payload[1:].decode(errors="ignore") if payload else None

    def set_region(self, region=REGION_US):
        return self._command(CMD_SET_REGION, bytes([region])) is not None

    def inventory(self, rounds=10, duration=0.5):
        """
        Run `rounds` inventory rounds and return the set of EPCs seen,
        as uppercase hex strings. One call = one 'read cycle'.
        """
        self.ser.reset_input_buffer()
        payload = bytes([0x22]) + rounds.to_bytes(2, "big")
        self.ser.write(build_frame(CMD_MULTI_POLL, payload))

        tags = set()
        for frame in self._read_frames(duration):
            if frame[1] == TYPE_NOTICE and frame[2] == CMD_SINGLE_POLL:
                data = frame[5:-2]  # RSSI(1) PC(2) EPC(n) CRC(2)
                epc = data[3:-2]
                if epc:
                    tags.add(epc.hex().upper())

        self.ser.write(build_frame(CMD_STOP_POLL))
        return tags


if __name__ == "__main__":
    # Bench test: confirm the module answers, set US region, then poll.
    reader = UHFReader("/dev/cu.usbserial-21110")
    print("Hardware version:", reader.hardware_version())
    print("Region set to US:", reader.set_region(REGION_US))
    try:
        while True:
            seen = reader.inventory()
            print(f"{len(seen)} tag(s):", ", ".join(sorted(seen)) or "-")
            time.sleep(0.5)
    except KeyboardInterrupt:
        reader.close()