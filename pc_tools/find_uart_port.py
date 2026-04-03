import argparse
import time
from dataclasses import dataclass, field

import serial
import serial.tools.list_ports


KEYWORDS = ("SIM ", "FRAME_HEX", "BOOT_", "TEMP=", "PERIOD:", "THR:", "THR2:")
PING_CMD = b"GET_PERIOD\n"


@dataclass
class PortStat:
    lines: int = 0
    hit_keywords: int = 0
    noise_like: int = 0
    sample_lines: list = field(default_factory=list)


def looks_like_noise(raw: bytes) -> bool:
    if not raw:
        return False
    high = sum(1 for b in raw if b >= 0x80)
    ff_like = sum(1 for b in raw if b in (0xFF, 0xBF, 0x7F))
    return high >= max(4, len(raw) // 2) or ff_like >= max(4, len(raw) // 2)


def list_ch340_ports():
    ports = []
    for p in serial.tools.list_ports.comports():
        desc = (p.description or "").upper()
        hwid = (p.hwid or "").upper()
        if "CH340" in desc or "1A86:7523" in hwid:
            ports.append(p.device)
    return sorted(set(ports))


def main():
    parser = argparse.ArgumentParser(description="Find active CH340 port with useful UART data")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--duration", type=float, default=25.0, help="scan seconds")
    parser.add_argument("--send-ping", action="store_true", default=True, help="periodically send GET_PERIOD")
    args = parser.parse_args()

    ports = list_ch340_ports()
    if not ports:
        print("[ERR] 没找到 CH340 串口")
        return

    print("[INFO] 检测到串口:", ", ".join(ports))
    print("[INFO] 可短按一次 RST，脚本会自动识别哪个口有有效日志...")

    opened = {}
    stats = {p: PortStat() for p in ports}

    for p in ports:
        try:
            opened[p] = serial.Serial(p, args.baud, timeout=0.15)
        except Exception as e:
            print(f"[WARN] {p} 打开失败: {e}")

    if not opened:
        print("[ERR] 所有候选串口都无法打开。")
        return

    end_time = time.time() + args.duration
    last_ping = 0.0

    try:
        while time.time() < end_time:
            now = time.time()
            if args.send_ping and (now - last_ping) > 1.0:
                for p, s in opened.items():
                    try:
                        s.write(PING_CMD)
                        s.flush()
                    except Exception:
                        pass
                last_ping = now

            for p, s in opened.items():
                try:
                    raw = s.readline()
                except Exception:
                    raw = b""

                if not raw:
                    continue

                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                st = stats[p]
                st.lines += 1
                if looks_like_noise(raw):
                    st.noise_like += 1
                if any(k in line for k in KEYWORDS):
                    st.hit_keywords += 1
                if len(st.sample_lines) < 5:
                    st.sample_lines.append(line)

                print(f"[{p}] {line}")

                if st.hit_keywords >= 2:
                    print(f"\n[OK] 找到有效串口: {p}")
                    print(f"[OK] 建议命令: py -m serial.tools.miniterm {p} {args.baud}")
                    return
    finally:
        for s in opened.values():
            try:
                s.close()
            except Exception:
                pass

    print("\n[FAIL] 扫描结束，未发现稳定有效日志。")
    for p in ports:
        st = stats[p]
        print(f"- {p}: lines={st.lines}, keyword_hits={st.hit_keywords}, noise_like={st.noise_like}")
        for idx, sample in enumerate(st.sample_lines, 1):
            print(f"  sample{idx}: {sample}")

    print("[TIP] 高 noise_like 通常表示 RX 悬空/共地缺失/线序错误。")
    print("[TIP] 先保证 GND 共地，再试：PA2->CH340 RXD（只接单向先看日志）。")
    print("[TIP] 若仍无日志，再试 PA9->CH340 RXD（双串口固件已支持 USART1/USART2）。")


if __name__ == "__main__":
    main()
