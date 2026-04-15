#!/usr/bin/env python3
"""
Send one UART text command and print received lines.

Examples:
  py pc_tools/uart_cmd_once.py --port COM6 --cmd GET_FLASH --expect "id=0xEF4018"
  py pc_tools/uart_cmd_once.py --port COM6 --cmd BOOT_SAVE
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Optional

import serial
import serial.tools.list_ports


def choose_port(port_arg: str) -> Optional[str]:
    if port_arg.lower() != "auto":
        return port_arg
    ports = [p.device for p in serial.tools.list_ports.comports()]
    return ports[0] if ports else None


def send_with_delay(ser: serial.Serial, text: str, char_delay_s: float) -> None:
    for ch in text:
        ser.write(ch.encode("ascii", errors="ignore"))
        ser.flush()
        if char_delay_s > 0:
            time.sleep(char_delay_s)


def run_once(
    port: str,
    baud: int,
    cmd: str,
    timeout_s: float,
    char_delay_s: float,
    preflush_newlines: int,
    expect: str,
) -> int:
    with serial.Serial(port=port, baudrate=baud, timeout=0.1) as ser:
        # Clear stale input first.
        ser.reset_input_buffer()
        ser.reset_output_buffer()

        if preflush_newlines > 0:
            send_with_delay(ser, "\n" * preflush_newlines, char_delay_s)

        send_with_delay(ser, cmd.strip() + "\n", char_delay_s)

        deadline = time.time() + timeout_s
        matched = False
        got_any = False
        while time.time() < deadline:
            raw = ser.readline()
            if not raw:
                continue
            got_any = True
            line = raw.decode("utf-8", errors="ignore").rstrip()
            if not line:
                continue
            print(line)
            if expect and expect in line:
                matched = True

        if expect:
            return 0 if matched else 2
        return 0 if got_any else 3


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Project A send one UART command")
    p.add_argument("--port", default="auto", help="COM port or auto")
    p.add_argument("--baud", type=int, default=115200, help="baud rate")
    p.add_argument("--cmd", required=True, help="command text, e.g. GET_FLASH")
    p.add_argument("--timeout-s", type=float, default=2.0, help="read window seconds")
    p.add_argument("--char-delay-ms", type=float, default=0.0, help="per-char delay ms")
    p.add_argument("--preflush-newlines", type=int, default=0, help="prepend N newlines")
    p.add_argument("--expect", default="", help="expected substring")
    return p


def main() -> int:
    args = build_parser().parse_args()
    port = choose_port(args.port)
    if not port:
        print("[ERR] no serial ports found")
        return 4

    try:
        rc = run_once(
            port=port,
            baud=args.baud,
            cmd=args.cmd,
            timeout_s=args.timeout_s,
            char_delay_s=max(args.char_delay_ms, 0.0) / 1000.0,
            preflush_newlines=max(args.preflush_newlines, 0),
            expect=args.expect,
        )
        if rc == 0:
            print(f"[OK] cmd={args.cmd} port={port}")
        elif rc == 2:
            print(f"[FAIL] expect not found: {args.expect}")
        elif rc == 3:
            print("[FAIL] no response lines")
        return rc
    except serial.SerialException as exc:
        print(f"[ERR] serial open/send failed: {exc}")
        return 5


if __name__ == "__main__":
    sys.exit(main())

