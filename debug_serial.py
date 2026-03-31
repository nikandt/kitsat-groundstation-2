#!/usr/bin/env python
"""
Standalone serial diagnostic — bypasses kitsat multiprocessing entirely.

Usage:
    python debug_serial.py COM1
    python debug_serial.py COM1 ping
    python debug_serial.py COM1 beep 1

What it does:
  1. Opens the COM port directly in this process (no subprocess)
  2. Sends the specified command (or 'ping' by default)
  3. Waits up to 3 seconds for any response, printing raw bytes and in_waiting
  4. Also checks in_waiting BEFORE the >10 threshold to show whether that gate
     would block reception

This definitively shows whether:
  (a) The satellite sends anything at all
  (b) The in_waiting >10 threshold in the kitsat subprocess is the problem
  (c) The packet format / checksum is correct
"""

import sys
import time
import serial
from kitsat.lib import cmd_parser, packet_parser, math_utils


PORT    = sys.argv[1] if len(sys.argv) > 1 else "COM1"
CMD     = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "ping"
BAUD    = 115200
TIMEOUT = 3.0  # seconds to wait for a response


def main():
    print(f"[diag] Opening {PORT} @ {BAUD} baud ...")
    try:
        ser = serial.Serial(PORT, BAUD, timeout=TIMEOUT)
    except serial.SerialException as e:
        print(f"[ERROR] Could not open port: {e}")
        sys.exit(1)

    print(f"[diag] Port open. Sending command: '{CMD}'")

    pkt = cmd_parser.parse(CMD)
    if not pkt:
        print(f"[ERROR] cmd_parser returned empty packet for '{CMD}'. "
              "Command not found in sat_commands.csv?")
        ser.close()
        sys.exit(1)

    print(f"[diag] Packet bytes ({len(pkt)} bytes): {pkt.hex(' ')}")
    ser.write(pkt)
    print(f"[diag] Written. Waiting up to {TIMEOUT}s for response ...")

    deadline = time.monotonic() + TIMEOUT
    max_waiting_seen = 0
    raw_buf = bytearray()

    while time.monotonic() < deadline:
        waiting = ser.in_waiting
        if waiting > max_waiting_seen:
            max_waiting_seen = waiting
            print(f"[diag] in_waiting = {waiting}  (threshold in kitsat: >10)")
        if waiting > 0:
            chunk = ser.read(waiting)
            raw_buf.extend(chunk)
            print(f"[diag] Read {len(chunk)} byte(s): {chunk.hex(' ')}")
        time.sleep(0.001)

    ser.close()

    print()
    print(f"[diag] ── Summary ──────────────────────────────────────")
    print(f"[diag] Max in_waiting seen      : {max_waiting_seen}")
    print(f"[diag] Total raw bytes received : {len(raw_buf)}")

    if not raw_buf:
        print("[diag] RESULT: No bytes received from satellite.")
        print("       → Satellite not responding, or wrong port/baud rate.")
        return

    print(f"[diag] Raw buffer (hex)         : {raw_buf.hex(' ')}")
    print(f"[diag] Raw buffer (ASCII/repr)  : {repr(bytes(raw_buf))}")

    # Try to locate 'packet:' syncword and parse
    SYNC = b'packet:'
    idx = raw_buf.find(SYNC)
    if idx == -1:
        print(f"\n[diag] RESULT: Bytes received but 'packet:' syncword NOT found.")
        print("       → Protocol mismatch or satellite firmware sending different format.")
        if max_waiting_seen <= 10:
            print(f"       → Also: in_waiting never exceeded 10 ({max_waiting_seen}), so the kitsat")
            print("         subprocess would have ignored these bytes entirely.")
        return

    print(f"\n[diag] 'packet:' syncword found at offset {idx}")
    payload_start = idx + len(SYNC)
    payload = raw_buf[payload_start:]

    if len(payload) < 3:
        print(f"[diag] RESULT: Too few bytes after syncword ({len(payload)}). Incomplete packet.")
        return

    orig      = payload[0]
    cmd_id    = payload[1]
    data_len  = payload[2]
    expected_total = 3 + data_len + 8  # orig+cmd_id+data_len + data + timestamp(4)+fnv(4)

    print(f"[diag] Parsed header: orig={orig} cmd_id={cmd_id} data_len={data_len}")
    print(f"[diag] Expected total payload bytes after syncword: {expected_total}")
    print(f"[diag] Actual payload bytes available             : {len(payload)}")

    if len(payload) < expected_total:
        print("[diag] RESULT: Incomplete packet (truncated). "
              "Might need longer timeout or satellite sends in bursts.")
    else:
        pkg = bytearray(payload[:expected_total])
        fnv_ok = math_utils.check_fnv(pkg)
        print(f"[diag] FNV checksum OK: {fnv_ok}")
        parsed = packet_parser.parse(pkg)
        print(f"[diag] Parsed packet  : {parsed}")
        print()
        if max_waiting_seen <= 10:
            print(f"[ISSUE FOUND] Max in_waiting was {max_waiting_seen} ≤ 10.")
            print("  The kitsat subprocess uses `if ser.in_waiting > 10:` as a gate.")
            print("  Since in_waiting never exceeded 10, the subprocess skipped ALL reads.")
            print("  FIX: The in_waiting threshold in the kitsat library is too high.")
            print("  Workaround: use modem.writeraw() or patch the threshold.")
        else:
            print(f"[diag] RESULT: Packet received and parsed successfully!")
            print("  The in_waiting threshold was NOT the problem.")
            print("  The issue is upstream of in_waiting (subprocess comms).")


if __name__ == "__main__":
    main()
