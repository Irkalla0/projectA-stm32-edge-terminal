import argparse
import time
from typing import Dict, List, Optional, Tuple

import serial
import serial.tools.list_ports


TELEMETRY_KEYWORDS = (
    "SIM ",
    "SIM2 ",
    "FRAME_HEX",
    "ALARM",
    "TEMP=",
    "RH=",
)

CMD_EXPECT = {
    "GET_VER": ("VER:",),
    "GET_CAP": ("CAP:",),
    "GET_BOOTSTATE": ("BOOT:",),
    "UPG_STATUS": ("UPG_STATUS:",),
    "GET_PERIOD": ("PERIOD:",),
    "GET_THR": ("THR:",),
    "GET_THR2": ("THR2:",),
}


def list_ch340_ports() -> List[str]:
    ports = []
    for p in serial.tools.list_ports.comports():
        desc = (p.description or "").upper()
        hwid = (p.hwid or "").upper()
        if "CH340" in desc or "1A86:7523" in hwid:
            ports.append(p.device)
    return sorted(set(ports))


def open_serial(port: str, baud: int) -> Optional[serial.Serial]:
    try:
        return serial.Serial(port, baudrate=baud, timeout=0.12)
    except Exception:
        return None


def read_lines(ser: serial.Serial, seconds: float) -> List[str]:
    out = []
    end = time.time() + seconds
    while time.time() < end:
        try:
            line = ser.readline().decode("utf-8", errors="replace").strip()
        except Exception:
            line = ""
        if line:
            out.append(line)
    return out


def telemetry_score(lines: List[str]) -> int:
    score = 0
    for line in lines:
        if any(k in line for k in TELEMETRY_KEYWORDS):
            score += 1
    return score


def send_cmd_slow(ser: serial.Serial, cmd: str, char_delay: float) -> None:
    # Clear stale partial command bytes in firmware parser.
    ser.write(b"\n\n")
    ser.flush()
    time.sleep(0.02)
    for ch in cmd:
        ser.write(ch.encode("ascii"))
        ser.flush()
        time.sleep(char_delay)
    ser.write(b"\n")
    ser.flush()


def probe_command(
    ser: serial.Serial,
    cmd: str,
    expect_prefixes: Tuple[str, ...],
    retries: int,
    char_delay: float,
    wait_s: float,
) -> Optional[str]:
    for _ in range(retries):
        send_cmd_slow(ser, cmd, char_delay)
        lines = read_lines(ser, wait_s)
        for line in lines:
            if line.startswith(expect_prefixes):
                return line
    return None


def pick_port(ports: List[str], baud: int, scan_s: float) -> Tuple[Optional[str], Dict[str, int]]:
    scores: Dict[str, int] = {}
    best_port = None
    best_score = -1

    for p in ports:
        ser = open_serial(p, baud)
        if ser is None:
            scores[p] = -1
            continue
        try:
            lines = read_lines(ser, scan_s)
            score = telemetry_score(lines)
            scores[p] = score
            if score > best_score:
                best_score = score
                best_port = p
        finally:
            ser.close()

    return best_port, scores


def main() -> None:
    parser = argparse.ArgumentParser(description="Project A UART link diagnostics")
    parser.add_argument("--port", default="auto", help="Target COM port or 'auto'")
    parser.add_argument("--baud", type=int, default=115200, help="Baudrate")
    parser.add_argument("--scan-seconds", type=float, default=2.0, help="Per-port telemetry scan time")
    parser.add_argument("--cmd-wait-seconds", type=float, default=1.6, help="Wait time after one command send")
    parser.add_argument("--char-delay", type=float, default=0.025, help="Slow-send per-char delay in seconds")
    parser.add_argument("--retries", type=int, default=3, help="Retry count per command")
    args = parser.parse_args()

    if args.port.lower() == "auto":
        ports = list_ch340_ports()
    else:
        ports = [args.port]

    if not ports:
        print("[ERR] No CH340 serial ports found.")
        return

    print(f"[INFO] Candidate ports: {', '.join(ports)}")

    if args.port.lower() == "auto":
        selected, scores = pick_port(ports, args.baud, args.scan_seconds)
        for p in ports:
            print(f"[SCAN] {p}: telemetry_score={scores.get(p, -1)}")
        if selected is None or scores.get(selected, 0) <= 0:
            print("[FAIL] No active telemetry detected.")
            print("[TIP] Check board power, GND common, and MCU TX -> CH340 RX wiring.")
            return
        port = selected
        print(f"[OK] Selected active port: {port}")
    else:
        port = args.port

    ser = open_serial(port, args.baud)
    if ser is None:
        print(f"[ERR] Failed to open {port} @ {args.baud}")
        return

    try:
        _ = read_lines(ser, 0.6)
        print(f"[INFO] Probing commands on {port} ...")

        ok = 0
        total = len(CMD_EXPECT)
        for cmd, prefixes in CMD_EXPECT.items():
            resp = probe_command(
                ser=ser,
                cmd=cmd,
                expect_prefixes=prefixes,
                retries=max(1, args.retries),
                char_delay=max(0.0, args.char_delay),
                wait_s=max(0.3, args.cmd_wait_seconds),
            )
            if resp is None:
                print(f"[FAIL] {cmd} -> no expected response")
            else:
                ok += 1
                print(f"[OK] {cmd} -> {resp}")

        print("\n=== SUMMARY ===")
        print(f"port={port}, baud={args.baud}")
        print(f"command_success={ok}/{total}")
        if ok == total:
            print("[PASS] UART command channel is healthy.")
        elif ok >= 3:
            print("[WARN] UART is partially healthy. Likely timing/noise/wiring issue remains.")
            print("[TIP] Keep one CH340 only, ensure GND common, and keep short jumper wires.")
        else:
            print("[FAIL] UART command channel is not usable.")
            print("[TIP] Re-check TX/RX cross wiring and try a manual reset.")
    finally:
        ser.close()


if __name__ == "__main__":
    main()
