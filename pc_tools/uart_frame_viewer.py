import argparse
import csv
import os
import re
import struct
import time
from collections import deque

import matplotlib.pyplot as plt
from matplotlib.widgets import Button, TextBox
import serial
import serial.tools.list_ports


FRAME_HEX_RE = re.compile(r"FRAME_HEX:\s*([0-9A-Fa-f ]+)")
SIM_LINE_RE = re.compile(r"(?:SIM\s+)?TEMP=([-+]?\d+(?:\.\d+)?)C\s+RH=([-+]?\d+(?:\.\d+)?)%")
HEX_BYTE_RE = re.compile(r"\b[0-9A-Fa-f]{2}\b")


def crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def parse_frame(line: str):
    m = FRAME_HEX_RE.search(line)
    raw = None
    if m:
        try:
            raw = bytes(int(x, 16) for x in m.group(1).split())
        except ValueError:
            raw = None
    else:
        toks = HEX_BYTE_RE.findall(line)
        if len(toks) >= 17:
            vals = [int(t, 16) for t in toks]
            for i in range(0, len(vals) - 16):
                if vals[i] == 0xAA and vals[i + 1] == 0x55:
                    raw = bytes(vals[i : i + 17])
                    break

    if raw is None or len(raw) < 17 or raw[0] != 0xAA or raw[1] != 0x55:
        return None

    cmd = raw[2]
    payload_len = raw[3] | (raw[4] << 8)
    seq = raw[5] | (raw[6] << 8)
    ts_ms = raw[7] | (raw[8] << 8) | (raw[9] << 16) | (raw[10] << 24)
    v1_raw = struct.unpack("<h", raw[11:13])[0]
    v2_raw = raw[13] | (raw[14] << 8)
    recv_crc = raw[15] | (raw[16] << 8)
    calc_crc = crc16_modbus(raw[:15])

    temp_c = None
    hum_rh = None
    dist_mm = None
    curr_ma = None
    if cmd in (0x01, 0xA1):
        temp_c = v1_raw / 100.0
        hum_rh = v2_raw / 100.0
    elif cmd in (0x02, 0xA2):
        dist_mm = v1_raw
        curr_ma = v2_raw

    return {
        "seq": seq,
        "cmd": cmd,
        "len": payload_len,
        "ts_ms": ts_ms,
        "temp_c": temp_c,
        "hum_rh": hum_rh,
        "dist_mm": dist_mm,
        "curr_ma": curr_ma,
        "crc_ok": recv_crc == calc_crc,
    }


def parse_sim_line(line: str):
    m = SIM_LINE_RE.search(line)
    if not m:
        return None
    return {"temp_c": float(m.group(1)), "hum_rh": float(m.group(2))}


def list_candidate_ports(preferred: str):
    if preferred.lower() != "auto":
        return [preferred]

    ports = list(serial.tools.list_ports.comports())
    ch340 = sorted([p.device for p in ports if "CH340" in (p.description or "").upper()])
    others = sorted(
        [p.device for p in ports if p.device not in ch340 and p.device.upper().startswith("COM")]
    )
    return ch340 + others


def try_open(port: str, baud: int):
    try:
        ser = serial.Serial(port, baudrate=baud, timeout=0.2)
        return ser
    except serial.SerialException:
        return None


def probe_other_port_with_data(current_port: str, baud: int):
    for p in list_candidate_ports("auto"):
        if p == current_port:
            continue
        ser = try_open(p, baud)
        if ser is None:
            continue
        try:
            t0 = time.time()
            while time.time() - t0 < 0.8:
                line = ser.readline().decode("utf-8", errors="replace").strip()
                if line:
                    return p
        finally:
            ser.close()
    return None


def main():
    parser = argparse.ArgumentParser(description="Project A UART waveform viewer")
    parser.add_argument("--port", default="auto", help="COM port, default auto")
    parser.add_argument("--baud", type=int, default=115200, help="baudrate, default 115200")
    parser.add_argument("--points", type=int, default=180, help="plot points, default 180")
    parser.add_argument("--csv", default="", help="optional csv output path")
    parser.add_argument(
        "--set-period",
        type=int,
        default=None,
        help="optional sample period command in ms (100~5000), e.g. --set-period 500",
    )
    parser.add_argument("--raw", action="store_true", help="print non-frame raw lines")
    args = parser.parse_args()
    if args.set_period is not None and not (100 <= args.set_period <= 5000):
        parser.error("--set-period must be in range 100~5000")

    tsq = deque(maxlen=args.points)
    tq = deque(maxlen=args.points)
    hq = deque(maxlen=args.points)

    plt.ion()
    fig, ax = plt.subplots()
    fig.subplots_adjust(bottom=0.30)
    line_t, = ax.plot([], [], label="Temp(C)")
    line_h, = ax.plot([], [], label="RH(%)")
    ax.set_title("Project A UART Waveform")
    ax.set_xlabel("Time(s)")
    ax.set_ylabel("Value")
    ax.grid(True)
    ax.legend()

    start = time.time()
    last_rx = 0.0
    last_warn = 0.0
    current_port = None
    ser = None
    csv_fp = None
    csv_writer = None

    def send_cmd(cmd: str):
        nonlocal ser, current_port
        cmd = cmd.strip()
        if not cmd:
            return
        if ser is None:
            print(f"[WARN] Serial not connected, command dropped: {cmd}")
            return
        try:
            ser.write((cmd + "\n").encode("ascii"))
            ser.flush()
            print(f"[TX] {cmd} ({current_port})")
        except serial.SerialException as e:
            print(f"[WARN] TX failed on {current_port}: {e}")

    # UI controls: click-to-send commands (no manual typing needed)
    ax_b1 = fig.add_axes([0.06, 0.20, 0.12, 0.055])
    ax_b2 = fig.add_axes([0.20, 0.20, 0.12, 0.055])
    ax_b3 = fig.add_axes([0.34, 0.20, 0.12, 0.055])
    ax_b4 = fig.add_axes([0.48, 0.20, 0.12, 0.055])
    ax_b5 = fig.add_axes([0.62, 0.20, 0.14, 0.055])
    ax_b6 = fig.add_axes([0.78, 0.20, 0.16, 0.055])
    ax_tb = fig.add_axes([0.06, 0.11, 0.70, 0.055])
    ax_bs = fig.add_axes([0.78, 0.11, 0.16, 0.055])

    btn_get_period = Button(ax_b1, "GET_PERIOD")
    btn_set_500 = Button(ax_b2, "SET_500")
    btn_get_thr = Button(ax_b3, "GET_THR")
    btn_get_thr2 = Button(ax_b4, "GET_THR2")
    btn_preset_a1 = Button(ax_b5, "A1_PRESET")
    btn_preset_a2 = Button(ax_b6, "A2_PRESET")
    tb_cmd = TextBox(ax_tb, "CMD", initial="GET_PERIOD")
    btn_send = Button(ax_bs, "SEND")

    def on_get_period(_):
        send_cmd("GET_PERIOD")

    def on_set_500(_):
        send_cmd("SET_PERIOD 500")

    def on_get_thr(_):
        send_cmd("GET_THR")

    def on_get_thr2(_):
        send_cmd("GET_THR2")

    def on_preset_a1(_):
        send_cmd("SET_THR_T 26.5")
        send_cmd("SET_THR_H 60")
        send_cmd("GET_THR")

    def on_preset_a2(_):
        send_cmd("SET_THR_D 900")
        send_cmd("SET_THR_I 800")
        send_cmd("GET_THR2")

    def on_send(_):
        send_cmd(tb_cmd.text)

    btn_get_period.on_clicked(on_get_period)
    btn_set_500.on_clicked(on_set_500)
    btn_get_thr.on_clicked(on_get_thr)
    btn_get_thr2.on_clicked(on_get_thr2)
    btn_preset_a1.on_clicked(on_preset_a1)
    btn_preset_a2.on_clicked(on_preset_a2)
    btn_send.on_clicked(on_send)
    tb_cmd.on_submit(lambda text: send_cmd(text))

    if args.csv:
        csv_path = os.path.abspath(args.csv)
        os.makedirs(os.path.dirname(csv_path), exist_ok=True)
        csv_fp = open(csv_path, "a", newline="", encoding="utf-8")
        csv_writer = csv.writer(csv_fp)
        if csv_fp.tell() == 0:
            csv_writer.writerow(
                [
                    "host_ts",
                    "source",
                    "temp_c",
                    "hum_rh",
                    "dist_mm",
                    "curr_ma",
                    "seq",
                    "cmd",
                    "crc_ok",
                    "port",
                ]
            )
            csv_fp.flush()
        print(f"[INFO] CSV logging: {csv_path}")

    print("[INFO] Starting UART viewer. If no data, press RST once.")

    try:
        while True:
            if ser is None:
                candidates = list_candidate_ports(args.port)
                if not candidates:
                    if time.time() - last_warn > 3:
                        print("[WARN] No COM ports found.")
                        last_warn = time.time()
                    time.sleep(0.2)
                    continue

                for p in candidates:
                    ser = try_open(p, args.baud)
                    if ser is not None:
                        current_port = p
                        print(f"[INFO] Serial opened: {p} @ {args.baud}")
                        if args.set_period is not None:
                            tx_cmd = f"SET_PERIOD {args.set_period}\n"
                            ser.write(tx_cmd.encode("ascii"))
                            ser.flush()
                            print(f"[TX] {tx_cmd.strip()}")
                        break

                if ser is None:
                    if time.time() - last_warn > 3:
                        print("[WARN] COM open failed, retrying...")
                        last_warn = time.time()
                    time.sleep(0.2)
                    continue

            line = ""
            try:
                line = ser.readline().decode("utf-8", errors="replace").strip()
            except serial.SerialException as e:
                print(f"[WARN] Serial error on {current_port}: {e}")
                try:
                    ser.close()
                except Exception:
                    pass
                ser = None
                current_port = None
                time.sleep(0.2)
                continue

            now = time.time()
            if line:
                last_rx = now
                frame = parse_frame(line)
                if frame is not None:
                    is_temp_hum = frame["cmd"] in (0x01, 0xA1) and frame["temp_c"] is not None
                    is_dist_curr = frame["cmd"] in (0x02, 0xA2) and frame["dist_mm"] is not None

                    if is_temp_hum:
                        tsq.append(now - start)
                        tq.append(frame["temp_c"])
                        hq.append(frame["hum_rh"])
                    if csv_writer is not None:
                        csv_writer.writerow(
                            [
                                f"{now:.3f}",
                                "frame",
                                f"{frame['temp_c']:.2f}" if frame["temp_c"] is not None else "",
                                f"{frame['hum_rh']:.2f}" if frame["hum_rh"] is not None else "",
                                frame["dist_mm"] if frame["dist_mm"] is not None else "",
                                frame["curr_ma"] if frame["curr_ma"] is not None else "",
                                frame["seq"],
                                frame["cmd"],
                                int(frame["crc_ok"]),
                                current_port,
                            ]
                        )
                        csv_fp.flush()
                    if is_temp_hum:
                        print(
                            f"SEQ={frame['seq']:04d} CMD=0x{frame['cmd']:02X} "
                            f"T={frame['temp_c']:.2f}C RH={frame['hum_rh']:.2f}% "
                            f"CRC={'OK' if frame['crc_ok'] else 'BAD'}"
                        )
                        if frame["cmd"] == 0xA1:
                            print(
                                f"[ALARM_FRAME] seq={frame['seq']:04d} "
                                f"T={frame['temp_c']:.2f}C RH={frame['hum_rh']:.2f}%"
                            )
                    elif is_dist_curr:
                        print(
                            f"SEQ={frame['seq']:04d} CMD=0x{frame['cmd']:02X} "
                            f"DIST={frame['dist_mm']}mm CUR={frame['curr_ma']}mA "
                            f"CRC={'OK' if frame['crc_ok'] else 'BAD'}"
                        )
                        if frame["cmd"] == 0xA2:
                            print(
                                f"[ALARM2_FRAME] seq={frame['seq']:04d} "
                                f"DIST={frame['dist_mm']}mm CUR={frame['curr_ma']}mA"
                            )
                else:
                    sim = parse_sim_line(line)
                    if sim is not None:
                        tsq.append(now - start)
                        tq.append(sim["temp_c"])
                        hq.append(sim["hum_rh"])
                        if csv_writer is not None:
                            csv_writer.writerow(
                                [
                                    f"{now:.3f}",
                                    "sim",
                                    f"{sim['temp_c']:.2f}",
                                    f"{sim['hum_rh']:.2f}",
                                    "",
                                    "",
                                    "",
                                    "",
                                    "",
                                    current_port,
                                ]
                            )
                            csv_fp.flush()
                        print(f"SIM T={sim['temp_c']:.2f}C RH={sim['hum_rh']:.2f}%")
                    elif (
                        line.startswith("SET_PERIOD_OK")
                        or line.startswith("SET_PERIOD_ERR")
                        or line.startswith("PERIOD:")
                        or line.startswith("SET_THR_")
                        or line.startswith("THR:")
                        or line.startswith("THR2:")
                        or line.startswith("CMD_ERR:")
                    ):
                        print(f"[MCU] {line}")
                    elif args.raw:
                        print(f"RAW: {line}")
            else:
                if now - last_rx > 3 and now - last_warn > 3:
                    print(
                        f"[WARN] No data on {current_port} for 3s. "
                        "Press RST once. If still no data, auto-switch port."
                    )
                    last_warn = now
                    if args.port.lower() == "auto":
                        other = probe_other_port_with_data(current_port, args.baud)
                        if other and other != current_port:
                            try:
                                ser.close()
                            except Exception:
                                pass
                            ser = try_open(other, args.baud)
                            if ser is not None:
                                current_port = other
                                print(f"[INFO] Switched to active port: {current_port}")

            if tsq:
                line_t.set_data(list(tsq), list(tq))
                line_h.set_data(list(tsq), list(hq))
                ax.relim()
                ax.autoscale_view()
            fig.canvas.draw_idle()
            fig.canvas.flush_events()
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\n[INFO] Exit")
    finally:
        if ser is not None:
            ser.close()
        if csv_fp is not None:
            csv_fp.close()


if __name__ == "__main__":
    main()
