import argparse
import csv
import json
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
PERIOD_RE = re.compile(r"^PERIOD:(\d+)$")
THR_RE = re.compile(r"^THR:T=([-+]?\d+(?:\.\d+)?),H=([-+]?\d+(?:\.\d+)?)$")
THR2_RE = re.compile(r"^THR2:D=(\d+),I=(\d+)$")
SET_OK_PERIOD_RE = re.compile(r"^SET_PERIOD_OK:(\d+)$")
SET_OK_T_RE = re.compile(r"^SET_THR_T_OK:([-+]?\d+(?:\.\d+)?)$")
SET_OK_H_RE = re.compile(r"^SET_THR_H_OK:([-+]?\d+(?:\.\d+)?)$")
SET_OK_D_RE = re.compile(r"^SET_THR_D_OK:(\d+)$")
SET_OK_I_RE = re.compile(r"^SET_THR_I_OK:(\d+)$")

DEFAULT_CFG = {
    "period_ms": 500,
    "thr_t": 26.5,
    "thr_h": 60.0,
    "thr_d": 900,
    "thr_i": 800,
}

RANGES = {
    "period_ms": (100, 5000),
    "thr_t": (0.0, 80.0),
    "thr_h": (0.0, 100.0),
    "thr_d": (50, 4000),
    "thr_i": (100, 5000),
}


def _clip_value(name: str, val):
    lo, hi = RANGES[name]
    if val < lo:
        return lo
    if val > hi:
        return hi
    return val


def normalize_cfg(raw: dict):
    cfg = dict(DEFAULT_CFG)
    if not isinstance(raw, dict):
        return cfg

    for k in cfg.keys():
        if k not in raw:
            continue
        try:
            if k in ("period_ms", "thr_d", "thr_i"):
                cfg[k] = int(raw[k])
            else:
                cfg[k] = float(raw[k])
        except (ValueError, TypeError):
            pass

    for k in cfg.keys():
        cfg[k] = _clip_value(k, cfg[k])
    return cfg


def load_cfg(path: str):
    if not os.path.exists(path):
        return dict(DEFAULT_CFG)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return normalize_cfg(data)
    except Exception as e:
        print(f"[WARN] Config load failed: {e}. Use defaults.")
        return dict(DEFAULT_CFG)


def save_cfg(path: str, cfg: dict):
    safe_cfg = normalize_cfg(cfg)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(safe_cfg, f, ensure_ascii=False, indent=2)
    return safe_cfg


def update_cfg_from_mcu_line(cfg: dict, line: str):
    m = PERIOD_RE.match(line) or SET_OK_PERIOD_RE.match(line)
    if m:
        cfg["period_ms"] = _clip_value("period_ms", int(m.group(1)))
        return

    m = THR_RE.match(line)
    if m:
        cfg["thr_t"] = _clip_value("thr_t", float(m.group(1)))
        cfg["thr_h"] = _clip_value("thr_h", float(m.group(2)))
        return

    m = THR2_RE.match(line)
    if m:
        cfg["thr_d"] = _clip_value("thr_d", int(m.group(1)))
        cfg["thr_i"] = _clip_value("thr_i", int(m.group(2)))
        return

    m = SET_OK_T_RE.match(line)
    if m:
        cfg["thr_t"] = _clip_value("thr_t", float(m.group(1)))
        return

    m = SET_OK_H_RE.match(line)
    if m:
        cfg["thr_h"] = _clip_value("thr_h", float(m.group(1)))
        return

    m = SET_OK_D_RE.match(line)
    if m:
        cfg["thr_d"] = _clip_value("thr_d", int(m.group(1)))
        return

    m = SET_OK_I_RE.match(line)
    if m:
        cfg["thr_i"] = _clip_value("thr_i", int(m.group(1)))


def update_cfg_from_tx_cmd(cfg: dict, cmd: str):
    s = cmd.strip().upper()
    try:
        if s.startswith("SET_PERIOD"):
            cfg["period_ms"] = _clip_value("period_ms", int(cmd.split()[-1]))
        elif s.startswith("SET_THR_T"):
            cfg["thr_t"] = _clip_value("thr_t", float(cmd.split()[-1]))
        elif s.startswith("SET_THR_H"):
            cfg["thr_h"] = _clip_value("thr_h", float(cmd.split()[-1]))
        elif s.startswith("SET_THR_D"):
            cfg["thr_d"] = _clip_value("thr_d", int(cmd.split()[-1]))
        elif s.startswith("SET_THR_I"):
            cfg["thr_i"] = _clip_value("thr_i", int(cmd.split()[-1]))
    except Exception:
        # Ignore parse failures; MCU reply parser is authoritative.
        pass


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

    # Prefer common CJK fonts on Windows so Chinese labels render correctly.
    plt.rcParams["font.sans-serif"] = [
        "Microsoft YaHei",
        "SimHei",
        "Noto Sans CJK SC",
        "Arial Unicode MS",
        "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False

    cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "viewer_config.json")
    current_cfg = load_cfg(cfg_path)
    if args.set_period is not None:
        current_cfg["period_ms"] = args.set_period
    print(f"[INFO] Config loaded: {current_cfg}")
    print(f"[INFO] Config path: {cfg_path}")

    tsq = deque(maxlen=args.points)
    tq = deque(maxlen=args.points)
    hq = deque(maxlen=args.points)

    plt.ion()
    fig, ax = plt.subplots()
    fig.subplots_adjust(bottom=0.32)
    line_t, = ax.plot([], [], label="温度(°C)")
    line_h, = ax.plot([], [], label="湿度(%)")
    ax.set_title("项目A 串口波形")
    ax.set_xlabel("时间(s)")
    ax.set_ylabel("数值")
    ax.grid(True)
    ax.legend()
    status_text = fig.text(0.02, 0.97, "", fontsize=10, va="top", fontweight="bold")
    status_msg = None
    status_connected = None

    def set_status(msg: str, connected: bool):
        nonlocal status_msg, status_connected
        if msg == status_msg and connected == status_connected:
            return
        status_msg = msg
        status_connected = connected
        color = "#0A7D33" if connected else "#B00020"
        dot = "●"
        status_text.set_text(f"{dot} 串口状态: {msg}")
        status_text.set_color(color)

    set_status("未连接（等待串口）", False)

    start = time.time()
    last_rx = 0.0
    last_warn = 0.0
    current_port = None
    ser = None
    csv_fp = None
    csv_writer = None
    auto_apply_on_open = True

    def save_cfg_now():
        nonlocal current_cfg
        try:
            current_cfg = save_cfg(cfg_path, current_cfg)
            print(f"[INFO] Config saved: {current_cfg}")
        except Exception as e:
            print(f"[WARN] Config save failed: {e}")

    def send_cmd(cmd: str):
        nonlocal ser, current_port, current_cfg
        cmd = cmd.strip()
        if not cmd:
            return
        if ser is None:
            print(f"[WARN] Serial not connected, command dropped: {cmd}")
            set_status("未连接，命令未发送", False)
            return
        try:
            ser.write((cmd + "\n").encode("ascii"))
            ser.flush()
            print(f"[TX] {cmd} ({current_port})")
            update_cfg_from_tx_cmd(current_cfg, cmd)
        except serial.SerialException as e:
            print(f"[WARN] TX failed on {current_port}: {e}")
            set_status(f"发送失败（{current_port}）", False)

    def apply_cfg_to_mcu():
        send_cmd(f"SET_PERIOD {int(current_cfg['period_ms'])}")
        send_cmd(f"SET_THR_T {float(current_cfg['thr_t']):.2f}")
        send_cmd(f"SET_THR_H {float(current_cfg['thr_h']):.2f}")
        send_cmd(f"SET_THR_D {int(current_cfg['thr_d'])}")
        send_cmd(f"SET_THR_I {int(current_cfg['thr_i'])}")
        send_cmd("GET_PERIOD")
        send_cmd("GET_THR")
        send_cmd("GET_THR2")

    # UI controls: click-to-send commands (no manual typing needed)
    ax_b1 = fig.add_axes([0.04, 0.20, 0.12, 0.055])
    ax_b2 = fig.add_axes([0.17, 0.20, 0.12, 0.055])
    ax_b3 = fig.add_axes([0.30, 0.20, 0.12, 0.055])
    ax_b4 = fig.add_axes([0.43, 0.20, 0.12, 0.055])
    ax_b5 = fig.add_axes([0.56, 0.20, 0.12, 0.055])
    ax_b6 = fig.add_axes([0.69, 0.20, 0.12, 0.055])
    ax_b7 = fig.add_axes([0.82, 0.20, 0.14, 0.055])
    ax_tb = fig.add_axes([0.06, 0.11, 0.70, 0.055])
    ax_bs = fig.add_axes([0.78, 0.11, 0.16, 0.055])

    btn_get_period = Button(ax_b1, "读周期")
    btn_set_500 = Button(ax_b2, "周期500ms")
    btn_get_thr = Button(ax_b3, "读阈值A1")
    btn_get_thr2 = Button(ax_b4, "读阈值A2")
    btn_preset_a1 = Button(ax_b5, "A1预设")
    btn_preset_a2 = Button(ax_b6, "A2预设")
    btn_save_cfg = Button(ax_b7, "保存配置")
    tb_cmd = TextBox(ax_tb, "命令", initial="GET_PERIOD")
    btn_send = Button(ax_bs, "发送")

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

    def on_save_cfg(_):
        save_cfg_now()

    def on_send(_):
        send_cmd(tb_cmd.text)

    btn_get_period.on_clicked(on_get_period)
    btn_set_500.on_clicked(on_set_500)
    btn_get_thr.on_clicked(on_get_thr)
    btn_get_thr2.on_clicked(on_get_thr2)
    btn_preset_a1.on_clicked(on_preset_a1)
    btn_preset_a2.on_clicked(on_preset_a2)
    btn_save_cfg.on_clicked(on_save_cfg)
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
                        set_status("未检测到串口", False)
                        last_warn = time.time()
                    time.sleep(0.2)
                    continue

                for p in candidates:
                    ser = try_open(p, args.baud)
                    if ser is not None:
                        current_port = p
                        print(f"[INFO] Serial opened: {p} @ {args.baud}")
                        set_status(f"已连接 {p} @ {args.baud}", True)
                        if auto_apply_on_open:
                            print("[INFO] Auto applying saved config to MCU...")
                            apply_cfg_to_mcu()
                        break

                if ser is None:
                    if time.time() - last_warn > 3:
                        print("[WARN] COM open failed, retrying...")
                        set_status("串口打开失败，重试中", False)
                        last_warn = time.time()
                    time.sleep(0.2)
                    continue

            line = ""
            try:
                line = ser.readline().decode("utf-8", errors="replace").strip()
            except serial.SerialException as e:
                print(f"[WARN] Serial error on {current_port}: {e}")
                set_status("连接断开，重连中", False)
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
                        update_cfg_from_mcu_line(current_cfg, line)
                        print(f"[MCU] {line}")
                    elif args.raw:
                        print(f"RAW: {line}")
            else:
                if now - last_rx > 3 and now - last_warn > 3:
                    print(
                        f"[WARN] No data on {current_port} for 3s. "
                        "Press RST once. If still no data, auto-switch port."
                    )
                    set_status(f"{current_port} 3秒无数据，尝试切换", False)
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
                                set_status(f"已切换并连接 {current_port}", True)

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
        save_cfg_now()
        if ser is not None:
            ser.close()
        if csv_fp is not None:
            csv_fp.close()


if __name__ == "__main__":
    main()
