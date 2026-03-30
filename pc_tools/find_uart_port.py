import time
import serial
import serial.tools.list_ports


KEYWORDS = ("SIM ", "FRAME_HEX", "BOOT_", "TEMP=")


def main():
    ports = [p.device for p in serial.tools.list_ports.comports() if "CH340" in p.description.upper()]
    if not ports:
        print("[ERR] 没找到 CH340 串口")
        return

    print("[INFO] 检测到串口:", ", ".join(ports))
    print("[INFO] 现在请短按一次 RST，脚本会自动识别哪个口有数据...")

    end_time = time.time() + 25
    opened = {}
    for p in ports:
        try:
            opened[p] = serial.Serial(p, 115200, timeout=0.2)
        except Exception as e:
            print(f"[WARN] {p} 打开失败: {e}")

    try:
        while time.time() < end_time:
            for p, s in list(opened.items()):
                try:
                    line = s.readline().decode("utf-8", errors="replace").strip()
                except Exception:
                    line = ""
                if not line:
                    continue
                print(f"[{p}] {line}")
                if any(k in line for k in KEYWORDS):
                    print(f"\n[OK] 找到有效串口: {p}")
                    print(f"[OK] 后续请用: py -m serial.tools.miniterm {p} 115200")
                    return
    finally:
        for s in opened.values():
            try:
                s.close()
            except Exception:
                pass

    print("[FAIL] 25秒内没抓到有效数据。")
    print("[TIP] 检查: MCU供电(USB_OTG/5V)、TX/RX交叉、GND共地、程序已烧录。")


if __name__ == "__main__":
    main()
